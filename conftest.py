import pytest

from tests.test_timeaccount import complex_account


@pytest.fixture(autouse=True)
def add_doctest_fixtures(doctest_namespace):
    doctest_namespace["account"] = complex_account
