import pytest

from hermes import TimeAccount


@pytest.fixture
def simple_account():
    return TimeAccount()


def test_can_make_account(simple_account):
    assert len(simple_account) == 0


def test_cant_slice_with_nonsense(simple_account):
    with pytest.raises(TypeError) as excinfo:
        simple_account["friday"]
    assert excinfo.value.args == ('invalid type for key', 'friday')
