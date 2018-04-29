import pytest

from tests.factories import make_timeaccount


@pytest.fixture
def complex_account():
    return make_timeaccount(num_tags=10)


@pytest.fixture(autouse=True)
def add_doctest_fixtures(doctest_namespace, complex_account):
    doctest_namespace["account"] = complex_account
