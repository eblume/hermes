import pytest


@pytest.fixture
def just_a_fixture():
    return 2


def test_math():
    assert 2 + 2 == 4


def test_fixture(just_a_fixture):
    assert just_a_fixture + 1 == 3


@pytest.mark.parametrize("a,b,c", [(3, 4, 5), (6, 8, 10)])
def test_parametric_test(a, b, c):
    assert a ** 2 + b ** 2 == c ** 2
