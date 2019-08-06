Hermes
======

by Erich Blume (blume.erich@gmail.com) 2019

This project contains the code for Hermes, which is a Time Accountant. That is
to say, Hermes is a set of tools for managing time. The scope of Hermes is
quite large, but right now this project primarily provides `hermes`, which is a
python package for manipulating, building, querying, filtering, and tabulating
timespans.

[![Build Status](https://travis-ci.com/eblume/hermes.svg?branch=master)](https://travis-ci.com/eblume/hermes)

How to use Hermes
-----------------

TODO - expand this documentation! Please seen CONTRIBUTING.rst.

For now, please check out the `tests` directory for usage examples.


Installation
===========

This project uses [`poetry`](https://github.com/sdispater/poetry) to manage
installation and dependencies. Once you've installed poetry, run

    poetry install

Then, you can run the hermes cli via

    poetry run hermes-exec

An example wrapper executable is provided in `/bin` called simply `hermes`, this
allows you to install the hermes command wherever in your '$PATH' you'd like, and
invoke hermes with

    hermes list

Finally, if you would like to run hermes unit tests, you can run

    poetry run tox

Which will also generate a coverage report. More complete testing can be performed
with the optional (off-by-default) integration tests, these can be run ( **WITH CAUTION** )
via

    poetry run hermes_integration_tests.sh

To test hermes against public APIs, you will need to first create an API access
token for those services. The easiest way to do this is probably to just run
`hermes_integration_tests.sh` and see what the failures are - any failures
about missing files will be your clue. Please file a bug for me to make this
experience less painful and let me know what you think.

NOTE that integration tests **modify your public API data**. I've tried to
design them in such a way that they shouldn't be 'destructive'... but that
relies on working code, which is the point of the test.

Modifying / Licensing
=====================

Please see LICENSE and CONTRIBUTING.rst
