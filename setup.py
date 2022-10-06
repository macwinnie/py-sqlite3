#!/usr/bin/env python3

from setuptools import find_packages, setup
import os, pipfile
import json

pf = pipfile.load("Pipfile").data

f = open("buildconfig.json")
j = json.load(f)
build_version = j["version"]
f.close()

setup(
    name="macwinnie_sqlite3",
    version=build_version,
    author="macwinnie",
    author_email="dev@macwinnie.me",
    license="AGPL-3.0-or-later",
    description="Pushover client for Python projects.",
    long_description="## SQLite Interface\n\nInterface for basic interactions with SQLite databases in Python projects.\n\nThe detailled documentation can be found at [GitHub](https://macwinnie.github.io/py-sqlite3).",
    long_description_content_type="text/markdown",
    url="https://github.com/macwinnie/python-pushover",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Operating System :: OS Independent",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">={pyVersion}".format(pyVersion=pf["_meta"]["requires"]["python_version"]),
    install_requires=[
        "{package}{version}".format(package=p, version=v) if v != "*" else p
        for p, v in pf["default"].items()
    ],
    extras_requires={
        "develop": [
            "{package}{version}".format(package=p, version=v) if v != "*" else p
            for p, v in pf["develop"].items()
        ],
    },
)
