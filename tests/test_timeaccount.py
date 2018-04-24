import datetime as dt
import pytest

from hermes import BaseTimeAccount, TimeAccount, CombinedTimeAccount


@pytest.mark.usefixtures('simple_account')
def test_can_make_account(simple_account):
    assert len(simple_account) == 0


@pytest.mark.usefixtures('simple_account')
def test_cant_slice_with_nonsense(simple_account):
    with pytest.raises(TypeError) as excinfo:
        simple_account["friday"]
    assert excinfo.value.args == ("TimeAccount objects must be sliced with `datetime.datetime`", )


def test_basetimeaccount():
    with pytest.raises(NotImplementedError):
        BaseTimeAccount()

    class DummyClass(BaseTimeAccount):
        def __init__(self):
            pass

    with pytest.raises(NotImplementedError):
        DummyClass().tags

    with pytest.raises(NotImplementedError):
        len(DummyClass())  # __len__ itself doesn't error, but calls .tags


@pytest.mark.usefixtures('complex_account')
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
    assert all(
        isinstance(tag.valid_from, dt.datetime)
        for tag in complex_account.tags
    )
    assert all(
        isinstance(tag.valid_to, dt.datetime)
        for tag in complex_account.tags
    )
    assert all(
        tag.valid_to >= tag.valid_from
        for tag in complex_account.tags
    )

    # divide the tags in the account in to groups of two hours length.
    # (see test/fixtures/timeaccount.py for the layout reference)

    two_hours = dt.timedelta(hours=2)
    accounts = list(complex_account[::two_hours])
    assert len(accounts[0]) == 3
    assert len(accounts[1]) == 2
    combined = CombinedTimeAccount(*accounts)
    assert len(combined) == 4
    assert set(complex_account.tags) == set(combined.tags)

    # first subspan
    assert(len(accounts[0])) == 3
    assert accounts[0].span.begins_at == complex_account.list_tags[0].valid_from
    assert accounts[0].span.finish_at == complex_account.list_tags[2].valid_to

    # second subspan
    assert(len(accounts[1])) == 2
    assert accounts[1].span.begins_at == complex_account.list_tags[2].valid_from
    assert accounts[1].span.finish_at == complex_account.list_tags[3].valid_to


@pytest.mark.usefixtures('complex_account')
def test_slice_without_step(complex_account):
    begins_at = complex_account.span.begins_at
    finish_at = complex_account.span.finish_at
    full_copy = complex_account[begins_at:finish_at]
    assert isinstance(full_copy, TimeAccount)


@pytest.mark.usefixtures('complex_account')
def test_slice_wrong_step_type(complex_account):
    with pytest.raises(TypeError):
        complex_account[::5]


@pytest.mark.usefixtures('complex_account')
def test_equality(complex_account):
    begins_at = complex_account.span.begins_at
    finish_at = complex_account.span.finish_at

    assert complex_account == complex_account[begins_at:finish_at]
    assert complex_account == complex_account[:]
    assert complex_account != TimeAccount([])
