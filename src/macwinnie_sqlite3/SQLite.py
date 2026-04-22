#!/usr/bin/env python3

"""SQLite interface to be used with Python projects."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import yoyo


# ----------------
# Logging setup
# ----------------

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("macwinnie.sqlite")

    if not logger.handlers:
        level_name = os.getenv("SQLITE_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [sqlite] %(message)s"
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False

    return logger


log = _setup_logger()


# ----------------
# Exceptions
# ----------------

class DatabaseError(Exception):
    pass


# ----------------
# Database class
# ----------------

class database:
    def __init__(self, dbPath: str | Path, migrationsPath: str | Path | None = None):
        self.connection: sqlite3.Connection | None = None
        self.result: sqlite3.Cursor | None = None
        self.dbPath = Path(dbPath).expanduser().resolve()

        log.info("Initializing SQLite DB at %s", self.dbPath)

        self._ensure_parent_dir_exists()

        if migrationsPath is not None:
            log.info("Running migrations from %s", migrationsPath)
            self.migrate(migrationsPath)

    def __getattr__(self, name: str):
        """
        Forward missing attributes/methods to the active cursor result.

        Typical use cases are fetchall() / fetchone() after execute().
        """
        if self.result is None:
            raise AttributeError(f"No active result for '{name}'")

        attr = getattr(self.result, name)
        if callable(attr):
            def method(*args, **kwargs):
                return attr(*args, **kwargs)
            return method
        return attr

    # ----------------
    # Setup helpers
    # ----------------

    def _ensure_parent_dir_exists(self) -> None:
        if not self.dbPath.parent.exists():
            log.debug("Creating directory %s", self.dbPath.parent)
        self.dbPath.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_db_file_exists(self) -> None:
        if not self.dbPath.exists():
            log.info("Creating DB file %s", self.dbPath)
            self.dbPath.touch()
        else:
            self.dbPath.touch(exist_ok=True)

    def _backend_url(self) -> str:
        # yoyo expects an absolute sqlite URL
        return f"sqlite:///{self.dbPath.as_posix()}"

    def _ensure_no_active_connection(self) -> None:
        """
        yoyo should manage its own backend connection and transaction handling.

        If our wrapper currently has an open sqlite3 connection, close it before
        migration work starts so yoyo is not affected by any app-level state.
        """
        if self.connection is not None:
            log.warning(
                "Closing active application SQLite connection before running migrations."
            )
            self.close()

    def _close_cursor(self) -> None:
        if self.result is not None:
            try:
                self.result.close()
            except Exception:
                log.debug("Ignoring cursor close failure", exc_info=True)
            finally:
                self.result = None

    # ----------------
    # Migration
    # ----------------

    def migrate(self, migrationsPath: str | Path) -> None:
        """
        Run yoyo migrations using yoyo's own backend/transaction management.

        Important:
        - do not reuse this wrapper's sqlite3 connection
        - do not open an application transaction before calling yoyo
        """
        self._ensure_parent_dir_exists()
        self._ensure_db_file_exists()
        self._ensure_no_active_connection()

        migrations_path = Path(migrationsPath).expanduser().resolve()
        if not migrations_path.exists():
            raise DatabaseError(f"Migration path does not exist: {migrations_path}")

        backend_url = self._backend_url()
        log.debug("Using yoyo backend %s", backend_url)

        try:
            backend = yoyo.get_backend(backend_url)
            migrations = yoyo.read_migrations(str(migrations_path))
            log.debug("Loaded %d migrations", len(migrations))

            # Must happen outside any application-level sqlite transaction.
            to_apply = backend.to_apply(migrations)
            log.info("Migrations pending: %d", len(to_apply))

            if not to_apply:
                log.info("No migrations to apply")
                return

            log.debug("Acquiring yoyo migration lock")
            with backend.lock():
                log.debug("Applying migrations")
                backend.apply_migrations(to_apply)

            log.info("Migrations applied successfully")

        except Exception as exc:
            log.exception("Migration failed")
            raise DatabaseError(
                f"Migration failed for database {self.dbPath} using {migrations_path}"
            ) from exc

    # ----------------
    # Connection handling
    # ----------------

    def startAction(self) -> None:
        """Connect to database and start an action."""
        if self.connection is not None:
            raise DatabaseError("DB already connected!")

        log.debug("Opening SQLite connection")
        self.connection = sqlite3.connect(str(self.dbPath))
        self.result = None

    def execute(
        self,
        query: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> None:
        """Execute SQL statement on database."""
        if self.connection is None:
            raise DatabaseError("No active DB connection. Call startAction().")

        if params is None:
            params = ()

        self._close_cursor()

        log.debug("Executing SQL: %s | params=%s", query, params)

        self.result = self.connection.cursor()
        self.result.execute(query, params)

    def commitAction(self) -> None:
        """
        Commit actions executed between startAction() and commitAction(),
        then close the connection.
        """
        if self.connection is None:
            raise DatabaseError("No active DB connection to commit.")

        log.debug("Committing transaction")

        try:
            self.connection.commit()
        finally:
            self.close()

    def rollbackAction(self) -> None:
        """
        Roll back actions executed after startAction() and close the connection.
        """
        if self.connection is None:
            raise DatabaseError("No active DB connection to rollback.")

        log.warning("Rolling back transaction")

        try:
            self.connection.rollback()
        finally:
            self.close()

    def fullExecute(
        self,
        query: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> None:
        """Execute a full transaction lifecycle for a single statement."""
        if params is None:
            params = ()

        log.debug("Starting fullExecute transaction")

        self.startAction()
        try:
            self.execute(query, params)
            self.commitAction()
        except Exception:
            log.exception("fullExecute failed, rolling back")
            self.rollbackAction()
            raise

    def close(self) -> None:
        """Clean close of the database connection and any active cursor."""
        self._close_cursor()

        if self.connection is not None:
            log.debug("Closing SQLite connection")
            try:
                self.connection.close()
            finally:
                self.connection = None
        else:
            self.connection = None

    # ----------------
    # Fetch helpers
    # ----------------

    def fetchallNamed(self) -> list[dict[str, Any]]:
        """
        Convert fetchall() results into a list of dictionaries keyed by column name.
        """
        if self.result is None or self.result.description is None:
            raise DatabaseError("No active SELECT result.")

        rowKeys = [col[0] for col in self.result.description]
        rows = self.result.fetchall()

        log.debug("Fetched %d rows", len(rows))

        return [dict(zip(rowKeys, row)) for row in rows]

    def fetchoneNamed(self) -> dict[str, Any] | None:
        """
        Convert fetchone() result into a dictionary keyed by column name.
        """
        if self.result is None or self.result.description is None:
            raise DatabaseError("No active SELECT result.")

        rowKeys = [col[0] for col in self.result.description]
        row = self.result.fetchone()

        if row is None:
            log.debug("fetchone returned no result")
            return None

        return dict(zip(rowKeys, row))
