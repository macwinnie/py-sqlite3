#!/usr/bin/env python3

"""SQLite interface to be used with Python projects. Can be installed by `pip install macwinnie_sqlite3`"""

import sqlite3, yoyo, os


class database:

    connection = None
    result = None
    dbPath = None

    def __init__(self, dbPath, migrationsPath=None):
        self.dbPath = dbPath
        if migrationsPath != None:
            self.migrate(migrationsPath)

    def __getattr__(self, name):
        """magic method to use given methods of database response objects like `fetchall` or `fetchone`."""
        # args:   positional arguments
        # kwargs: keyword arguments
        def method(*args, **kwargs):
            cllbl = getattr(self.result, name)
            if callable(cllbl):
                return cllbl(*args, **kwargs)
            else:
                return cllbl

        return method

    def migrate(self, migrationsPath):
        """Method to apply yoyo-migrations to database"""
        backendS = "sqlite:///{}".format(self.dbPath)
        # ensure DB file exists
        if not os.path.isfile(self.dbPath):
            open(self.dbPath, "w").close()
        # ensure all DB migrations are applied
        backend = yoyo.get_backend(backendS)
        migrations = yoyo.read_migrations(migrationsPath)
        backend.apply_migrations(backend.to_apply(migrations))

    def startAction(self):
        """Connect to database and so start an action"""
        if self.connection != None:
            raise Exception("DB already connected!")
        self.connection = sqlite3.connect(self.dbPath)

    def execute(self, query, params=[]):
        """execute SQL statement on database"""
        self.result = self.connection.cursor()
        self.result.execute(query, params)

    def commitAction(self):
        """commit your actions done through the execute statements between `startAction` and `commitAction` – so finish the transaction."""
        self.connection.commit()
        self.close()

    def fullExecute(self, query, params=[]):
        """combination method for a full transaction"""
        self.startAction()
        self.execute(query, params)
        self.commitAction()

    def rollbackAction(self):
        """method to roll back executed statements from `startAction` until `rollbackAction` without `commitAction` has been invoked."""
        self.connection.rollback()
        self.close()

    def close(self):
        """clean close of the database connection"""
        self.connection.close()
        self.connection = None

    def fetchallNamed(self):
        """regular `fetchall` for the results of `SELECT` statements executed return lists of lists of values. This method migrates those inner lists to key-value dicts."""
        rowKeys = [i[0] for i in self.description()]
        allResults = self.fetchall()
        allReturn = []
        for ar in allResults:
            allReturn.append(dict(zip(rowKeys, ar)))
        return allReturn

    def fetchoneNamed(self):
        """regular `fetchone` for results of `SELECT` statements executed return a list of values. This method migrates those lists to key-value dicts."""
        rowKeys = [i[0] for i in self.description()]
        results = self.fetchone()
        toReturn = dict(zip(rowKeys, results))
        return toReturn
