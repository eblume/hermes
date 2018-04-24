#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages
from pipenv.project import Project
from pipenv.utils import convert_deps_to_pip


with open("README.md") as readme_file:
    readme = readme_file.read()

with open("HISTORY.rst") as history_file:
    history = history_file.read()


pfile = Project(chdir=False).parsed_pipfile
setup_requirements = convert_deps_to_pip(pfile["packages"], r=False)
test_requirements = convert_deps_to_pip(pfile["dev-packages"], r=False)


setup(
    name="hermes",
    version="0.0.1",
    description="Personal Automaton",
    long_description=readme + "\n\n" + history,
    author="Erich Blume",
    author_email="erich@patreon.com",
    url="https://github.com/patreon/devxpr",
    project_urls={
        # TODO: trick my coworkers in to paying me
        # 'Funding': 'https://patreon.com/erich',
        "Source": "https://github.com/eblume/hermes",
        "Tracker": "https://github.com/eblume/hermes/issues",
    },
    packages=find_packages(include=["devxpr"]),
    entry_points={"console_scripts": ["hermes=hermes.cli:main"]},
    # include_package_data=True,  # not currently needed
    # install_requires=setup_requirements,  # not currently needed
    # license="Apache Software License 2.0",  # TODO: Opensource this!
    # zip_safe=False,  # not currently needed
    keywords="schedule assistant planning",
    # TODO: spruce up these classifiers before any pypi publishing
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        # 'License :: OSI Approved :: Apache Software License',
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6",
    ],
    test_suite="tests",
    tests_require=test_requirements,
    setup_requires=setup_requirements,
)
