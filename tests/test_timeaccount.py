import datetime as dt
from operator import attrgetter

from hermes import BaseTimeAccount, Category, Span, Spannable, Tag, TimeAccount

import pytest


@pytest.fixture
def simple_account():
    """Blank account, very simple"""
    return TimeAccount({})


@pytest.fixture
def complex_account_tags():
    """Four main tags with various overlaps and data for unit testing"""

    # tagname |  0 | 0.5|  1 | 1.5|  2 | 2.5|  3 | 3.5|  4 |
    #  Tag A  |####|####|####|    |    |    |    |    |    |
    #  Tag B  |    |####|####|    |    |    |    |    |    |
    #  Tag C  |    |    |####|####|####|####|    |    |    |
    #  Tag D  |    |    |    |    |    |####|####|####|####|

    t0h = dt.datetime(2018, 4, 16, 6, 43, 15, 13)  # when doesn't matter
    t05 = t0h + dt.timedelta(hours=0, minutes=30)
    t1h = t0h + dt.timedelta(hours=1)
    # t15 = t0h + dt.timedelta(hours=1, minutes=30)
    # t2h = t0h + dt.timedelta(hours=2)
    t25 = t0h + dt.timedelta(hours=2, minutes=30)
    # t3h = t0h + dt.timedelta(hours=3)
    t4h = t0h + dt.timedelta(hours=4)

    a_cat = Category("A", None)
    b_cat = Category("B", a_cat)
    c_cat = Category("C", b_cat)

    return {
        Tag("Tag A", category=a_cat, valid_from=t0h, valid_to=t1h),
        Tag("Tag B", category=b_cat, valid_from=t05, valid_to=t1h),
        Tag("Tag C", category=c_cat, valid_from=t1h, valid_to=t25),
        Tag("Tag D", category=a_cat, valid_from=t25, valid_to=t4h),
    }


@pytest.fixture
def complex_account(complex_account_tags):
    """An account with four main tags, for unit testing"""
    return TimeAccount(complex_account_tags)


def test_can_make_account(simple_account):
    assert len(simple_account) == 0


def test_describe_complex_topology(complex_account, complex_account_tags):
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

    # divide the tags in the account in to groups of two hours length.
    # (see test/fixtures/timeaccount.py for the layout reference)

    two_hours = dt.timedelta(hours=2)
    accounts = list(complex_account.subspans(two_hours))
    assert len(accounts) == 2
    assert len(accounts[0]) == 3
    assert len(accounts[1]) == 2
    combined = TimeAccount.combine(*accounts)
    assert len(combined) == 4
    assert set(complex_account.tags) == set(combined.tags)

    tags = list(sorted(complex_account.tags, key=attrgetter("valid_from")))

    # first subspan
    assert len(accounts[0]) == 3
    assert accounts[0].span.begins_at == tags[0].valid_from
    assert accounts[0].span.finish_at == tags[2].valid_to

    # second subspan
    assert len(accounts[1]) == 2
    assert accounts[1].span.begins_at == tags[2].valid_from
    assert accounts[1].span.finish_at == tags[3].valid_to


def test_subspans(complex_account):
    two_hours = dt.timedelta(hours=2)

    # Span subspanning
    spans = list(complex_account.span.subspans(two_hours))
    for span in spans:
        assert span.duration <= two_hours
    assert Span(spans[0].begins_at, spans[1].finish_at) == complex_account.span
    assert spans[0].finish_at == spans[1].begins_at
    assert spans[0].duration == spans[1].duration


def test_spans(complex_account):
    span = complex_account.span
    begins_plus5 = span.begins_at + dt.timedelta(minutes=5)
    begins_minus5 = span.begins_at - dt.timedelta(minutes=5)
    finish_plus5 = span.finish_at + dt.timedelta(minutes=5)
    finish_minus5 = span.finish_at - dt.timedelta(minutes=5)

    ## Positive cases
    # identical
    assert Span(span.begins_at, span.finish_at) in span
    # fully contained
    assert Span(begins_plus5, finish_minus5) in span
    # overlapping left
    assert Span(begins_minus5, begins_plus5) in span
    # overlapping right
    assert Span(finish_minus5, finish_plus5) in span
    # contained fully
    assert Span(begins_minus5, finish_plus5) in span
    # shares boundary left
    assert Span(span.begins_at, finish_minus5) in span
    # shares boundary right
    assert Span(begins_plus5, span.finish_at) in span

    ## Negative cases
    # fully left
    assert Span(begins_minus5, begins_plus5) not in Span(finish_minus5, finish_plus5)
    # fully right
    assert Span(finish_minus5, finish_plus5) not in Span(begins_minus5, begins_plus5)

    ## Edge Cases
    # 0-duration span in span (positive)
    assert Span(begins_plus5, begins_plus5) in span
    # span in 0-duration span (positive)
    assert span in Span(begins_minus5, begins_plus5)
    # 0-duration span in itself (positive)
    assert Span(begins_plus5, begins_plus5) in Span(begins_plus5, begins_plus5)
    # 0-duration span in a different 0-duration span (negative)
    assert Span(begins_minus5, begins_minus5) not in Span(begins_plus5, begins_plus5)
    assert Span(begins_plus5, begins_plus5) not in Span(begins_minus5, begins_minus5)


def test_equality(complex_account):
    begins_at = complex_account.span.begins_at
    finish_at = complex_account.span.finish_at

    assert complex_account == complex_account[begins_at:finish_at]
    assert complex_account == complex_account[:]
    assert complex_account != TimeAccount({})


def test_slice_syntaxes(complex_account):
    assert complex_account[:] == complex_account.reslice(None, None)
    assert len(complex_account[:]) == 4
    assert len({t for t in complex_account.tags}) == 4
    assert (
        {t for t in complex_account.tags if t in complex_account.span}
        == complex_account.tags
    )

    past_half = complex_account.span.begins_at + dt.timedelta(minutes=60 * 2 + 10)
    assert len(complex_account[past_half:]) == 2
    assert complex_account[past_half:] == complex_account.reslice(past_half, None)


def test_category():
    cat = Category("Test Category", None)
    other_cat = cat / "Child"
    assert other_cat.parent == cat
    with pytest.raises(ValueError):
        cat / "Bad Name!"


def test_category_pool(complex_account):
    pool = complex_account.category_pool
    d_cat = pool.get_category("A/B/C/D")
    assert d_cat not in pool
    assert d_cat.parent in pool
    assert d_cat.parent is pool.get_category("A/B/C")

    splat = sorted((fullpath, cat.name) for fullpath, cat in pool.categories.items())
    assert splat == [("A", "A"), ("A/B", "B"), ("A/B/C", "C")]


def test_base_spannable_iface():
    span = Spannable()
    with pytest.raises(NotImplementedError):
        span.span


def test_span_ordering():
    now = dt.datetime.now()
    span_left = Span(now, now + dt.timedelta(minutes=1))
    span_right = Span(now + dt.timedelta(minutes=2), now + dt.timedelta(minutes=3))

    assert span_left < span_right
    assert span_right > span_left
    assert span_left <= span_left
    assert span_left >= span_left

    assert not span_left > span_right
    assert not span_right < span_left

    overlap_right_of_left = Span(
        span_left.begins_at + dt.timedelta(seconds=10),
        span_left.finish_at + dt.timedelta(seconds=10),
    )
    overlap_left_of_right = Span(
        span_right.begins_at - dt.timedelta(seconds=10),
        span_right.finish_at - dt.timedelta(seconds=10),
    )

    assert span_left < overlap_right_of_left
    assert span_right > overlap_left_of_right


def test_basetimeaccount_iface():
    account = BaseTimeAccount()
    with pytest.raises(NotImplementedError):
        account.category_pool

    with pytest.raises(NotImplementedError):
        account.iter_tags()

    with pytest.raises(NotImplementedError):
        account.filter(str())

    with pytest.raises(NotImplementedError):
        account.reslice(None, None)


def test_slicing_nonsense(complex_account):
    with pytest.raises(TypeError) as excinfo:
        complex_account[1]
    assert "must be sliced with datetime" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        complex_account[1:3]
    assert "must be sliced with datetime" in str(excinfo.value)


@pytest.mark.parametrize(
    "path", ["☃", "/", " /foo", "/bar", "  ", "  //  / /", "\\ ", "\\"]
)
def test_category_badpath(path, complex_account):
    with pytest.raises(ValueError):
        complex_account.category_pool.get_category(path)


def test_query_by_category_filter(complex_account):
    assert len(complex_account.filter("A/B")) == 2
