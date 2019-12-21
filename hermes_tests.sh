#!/bin/sh

exec poetry run python -m pytest --ignore=tests/integration/ --cov=hermes --cov-report term-missing $@
