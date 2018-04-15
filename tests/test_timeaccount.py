import pytest

from hermes import TimeAccount


@pytest.fixture
def simple_account():
    return TimeAccount()


def test_can_make_account(simple_account):
    assert len(simple_account) == 0
