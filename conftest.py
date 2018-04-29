import pytest

from tests.test_timeaccount import complex_account, complex_account_tags


@pytest.fixture(autouse=True)
def add_doctest_fixtures(doctest_namespace):
    doctest_namespace["timeline"] = complex_account(complex_account_tags())
