import datetime as dt

from hermes import TimeAccount

import pytest


@pytest.mark.usefixtures("simple_account")
def test_can_make_account(simple_account):
    assert len(simple_account) == 0


@pytest.mark.usefixtures("complex_account")
def test_describe_complex_topology(complex_account):
    # The purpose of this test was to write a descriptive test for the
    # complex_account fixture. As new tests need more complexity from
    # complex_account, we will add to this test (or other tests related to it)

    # There are 4 tags active in this account
    assert len(complex_account) == 4
    # The 4 tags have 4 distinct names
    assert len(set(tag.name for tag in complex_account.tags)) == 4
    # The 4 tags have 4 distinct start times
    assert len(set(tag.valid_from for tag in complex_account.tags)) == 4
    # The 4 tags have 3 distinct end times
    assert len(set(tag.valid_to for tag in complex_account.tags)) == 3
    # The 4 tags are hashable and hashably unique
    assert len(set(complex_account.tags)) == 4

    # time
    assert all(isinstance(tag.valid_from, dt.datetime) for tag in complex_account.tags)
    assert all(isinstance(tag.valid_to, dt.datetime) for tag in complex_account.tags)
    assert all(tag.valid_to >= tag.valid_from for tag in complex_account.tags)


@pytest.mark.usefixtures("complex_account")
def test_equality(complex_account):
    begins_at = complex_account.span.begins_at
    finish_at = complex_account.span.finish_at

    assert complex_account == complex_account[begins_at:finish_at]
    assert complex_account == complex_account[:]
    assert complex_account != TimeAccount({})


@pytest.mark.usefixtures("complex_account")
def test_slice_syntaxes(complex_account):
    assert complex_account[:] == complex_account.slice(None, None)
    assert len(complex_account[:]) == 4

    past_half = complex_account.span.begins_at + dt.timedelta(minutes=60 * 2 + 10)
    assert len(complex_account[past_half:]) == 2
    assert complex_account[past_half:] == complex_account.slice(past_half, None)
