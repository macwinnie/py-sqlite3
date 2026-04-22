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
        self.dbPath = Path(dbPath).expanduser()

        log.info(f"Initializing SQLite DB at {self.dbPath}")

        self._ensure_parent_dir_exists()

        if migrationsPath is not None:
            log.info(f"Running migrations from {migrationsPath}")
            self.migrate(migrationsPath)

    def __getattr__(self, name: str):
        """
        magic method to use given methods of database response objects like `fetchall` or `fetchone`.

        name:   method or attribute to run
        args:   positional arguments
        kwargs: keyword arguments
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
            log.debug(f"Creating directory {self.dbPath.parent}")
        self.dbPath.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_db_file_exists(self) -> None:
        if not self.dbPath.exists():
            log.info(f"Creating DB file {self.dbPath}")
        self.dbPath.touch(exist_ok=True)

    def _backend_url(self) -> str:
        return f"sqlite:///{self.dbPath.resolve().as_posix()}"

    # ----------------
    # Migration
    # ----------------

    def migrate(self, migrationsPath: str | Path) -> None:
        self._ensure_db_file_exists()

        backend_url = self._backend_url()
        log.debug(f"Using backend {backend_url}")

        backend = yoyo.get_backend(backend_url)
        migrations = yoyo.read_migrations(str(Path(migrationsPath)))

        log.debug(f"Loaded {len(migrations)} migrations")

        try:
            to_apply = backend.to_apply(migrations)
            log.info(f"Migrations pending: {len(to_apply)}")

            if not to_apply:
                log.info("No migrations to apply")
                return

            log.debug("Acquiring migration lock")
            with backend.lock():
                log.debug("Applying migrations")
                backend.apply_migrations(to_apply)

            log.info("Migrations applied successfully")

        except Exception as exc:
            log.exception("Migration failed")
            raise

    # ----------------
    # Connection handling
    # ----------------

    def startAction(self) -> None:
        """Connect to database and so start an action"""
        if self.connection is not None:
            raise DatabaseError("DB already connected!")

        log.debug("Opening SQLite connection")
        self.connection = sqlite3.connect(str(self.dbPath))

    def execute(self, query: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
        """execute SQL statement on database"""
        if self.connection is None:
            raise DatabaseError("No active DB connection. Call startAction().")

        if params is None:
            params = []

        log.debug(f"Executing SQL: {query} | params={params}")

        self.result = self.connection.cursor()
        self.result.execute(query, params)

    def commitAction(self) -> None:
        """commit your actions done through the execute statements between `startAction` and `commitAction` – so finish the transaction."""
        if self.connection is None:
            raise DatabaseError("No active DB connection to commit.")

        log.debug("Committing transaction")

        try:
            self.connection.commit()
        finally:
            self.close()

    def rollbackAction(self) -> None:
        """method to roll back executed statements from `startAction` until `rollbackAction` without `commitAction` has been invoked."""
        if self.connection is None:
            raise DatabaseError("No active DB connection to rollback.")

        log.warning("Rolling back transaction")

        try:
            self.connection.rollback()
        finally:
            self.close()

    def fullExecute(self, query: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
        """combination method for a full transaction"""
        if params is None:
            params = []

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
        """clean close of the database connection"""
        if self.connection is not None:
            log.debug("Closing SQLite connection")
            self.connection.close()

        self.connection = None
        self.result = None

    # ----------------
    # Fetch helpers
    # ----------------

    def fetchallNamed(self) -> list[dict[str, Any]]:
        """regular `fetchall` for the results of `SELECT` statements executed return lists of lists of values. This method migrates those inner lists to key-value dicts."""
        if self.result is None or self.result.description is None:
            raise DatabaseError("No active SELECT result.")

        rowKeys = [col[0] for col in self.result.description]
        rows = self.result.fetchall()

        log.debug(f"Fetched {len(rows)} rows")

        return [dict(zip(rowKeys, row)) for row in rows]

    def fetchoneNamed(self) -> dict[str, Any] | None:
        """regular `fetchone` for results of `SELECT` statements executed return a list of values. This method migrates those lists to key-value dicts."""
        if self.result is None or self.result.description is None:
            raise DatabaseError("No active SELECT result.")

        rowKeys = [col[0] for col in self.result.description]
        row = self.result.fetchone()

        if row is None:
            log.debug("fetchone returned no result")
            return None

        return dict(zip(rowKeys, row))
