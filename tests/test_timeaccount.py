import datetime as dt
import pytest


@pytest.mark.usefixtures('simple_account')
def test_can_make_account(simple_account):
    assert len(simple_account) == 0


@pytest.mark.usefixtures('simple_account')
def test_cant_slice_with_nonsense(simple_account):
    with pytest.raises(TypeError) as excinfo:
        simple_account["friday"]
    assert excinfo.value.args == ('invalid type for key', 'friday')


@pytest.mark.usefixtures('complex_account')
def test_describe_complex_topology(complex_account):
    # The purpose of this test was to write a descriptive test for the
    # complex_account fixture. As new tests need more complexity from
    # complex_account, we will add to this test (or other tests related to it)

    # There are 4 tags active in this account
    assert len(complex_account) == 4
    # The 4 tags have 4 distinct names
    assert len(set(tag.name for tag in complex_account)) == 4
    # The 4 tags have 4 distinct start times
    assert len(set(tag.valid_from for tag in complex_account)) == 4
    # The 4 tags have 3 distinct end times
    assert len(set(tag.valid_to for tag in complex_account)) == 3

    # time
    assert all(
        isinstance(tag.valid_from, dt.datetime)
        for tag in complex_account
    )
    assert all(
        isinstance(tag.valid_to, dt.datetime)
        for tag in complex_account
    )
    assert all(
        tag.valid_to >= tag.valid_from
        for tag in complex_account
    )

    # divide the tags in the account in to groups of two hours length.
    # (see test/fixtures/timeaccount.py for the layout reference)

    two_hours = dt.timedelta(hours=2)
    accounts = list(complex_account[::two_hours])
    assert len(complex_account) == len(
        set(tag for account in accounts for tag in account)
    )
