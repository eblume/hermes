#!/bin/sh

exec poetry run python -m pytest --cov=hermes --cov-report term-missing --ignore tests/integration
