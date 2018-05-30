# -*- coding: utf-8 -*-
import datetime as dt
import os
import tempfile
from operator import attrgetter
from pathlib import Path

from hermes.categorypool import BaseCategoryPool, MutableCategoryPool
from hermes.span import Span, Spannable
from hermes.tag import Category, Tag
from hermes.timespan import (
    BaseTimeSpan,
    InsertableTimeSpan,
    RemovableTimeSpan,
    SqliteTimeSpan,
    TimeSpan,
    WriteableTimeSpan,
)

import pytest


@pytest.fixture(scope="function")
def simple_account():
    """Blank account, very simple"""
    return TimeSpan({})


@pytest.fixture(scope="module")
def complex_timespan_tags():
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


@pytest.fixture(scope="module")
def complex_timespan(complex_timespan_tags):
    """An account with four main tags, for unit testing"""
    return TimeSpan(complex_timespan_tags)


@pytest.fixture(scope="function")
def sqlite_timespan(complex_timespan_tags):
    return SqliteTimeSpan(complex_timespan_tags)


GENERIC_RO_TIMESPANS = {
    "base": lambda tags: TimeSpan(tags),
    "sqlite": lambda tags: SqliteTimeSpan(tags),
}


@pytest.fixture
def generic_ro_timespan(request, complex_timespan_tags):
    global GENERIC_RO_TIMESPANS
    if request.param not in GENERIC_RO_TIMESPANS:
        raise ValueError("Not in GENERIC_RO_TIMESPANS:", request.param)

    return GENERIC_RO_TIMESPANS[request.param](complex_timespan_tags)


def test_can_make_account(simple_account):
    assert len(simple_account) == 0


def test_describe_complex_topology(complex_timespan, complex_timespan_tags):
    # The purpose of this test was to write a descriptive test for the
    # complex_timespan fixture. As new tests need more complexity from
    # complex_timespan, we will add to this test (or other tests related to it)

    # There are 4 tags active in this account
    assert len(complex_timespan) == 4
    # The 4 tags have 4 distinct names
    assert len(set(tag.name for tag in complex_timespan.tags)) == 4
    # The 4 tags have 4 distinct start times
    assert len(set(tag.valid_from for tag in complex_timespan.tags)) == 4
    # The 4 tags have 3 distinct end times
    assert len(set(tag.valid_to for tag in complex_timespan.tags)) == 3
    # The 4 tags are hashable and hashably unique
    assert len(set(complex_timespan.tags)) == 4

    # time
    assert all(isinstance(tag.valid_from, dt.datetime) for tag in complex_timespan.tags)
    assert all(isinstance(tag.valid_to, dt.datetime) for tag in complex_timespan.tags)
    assert all(tag.valid_to >= tag.valid_from for tag in complex_timespan.tags)

    # divide the tags in the account in to groups of two hours length.
    # (see test/fixtures/timeaccount.py for the layout reference)

    two_hours = dt.timedelta(hours=2)
    accounts = list(complex_timespan.subspans(two_hours))
    assert len(accounts) == 2
    assert len(accounts[0]) == 3
    assert len(accounts[1]) == 2
    combined = TimeSpan.combine(*accounts)
    assert len(combined) == 4
    assert set(complex_timespan.tags) == set(combined.tags)

    tags = list(sorted(complex_timespan.tags, key=attrgetter("valid_from")))

    # first subspan
    assert len(accounts[0]) == 3
    assert accounts[0].span.begins_at == tags[0].valid_from
    assert accounts[0].span.finish_at == tags[2].valid_to

    # second subspan
    assert len(accounts[1]) == 2
    assert accounts[1].span.begins_at == tags[2].valid_from
    assert accounts[1].span.finish_at == tags[3].valid_to


@pytest.mark.parametrize(
    "generic_ro_timespan", GENERIC_RO_TIMESPANS.keys(), indirect=True
)
def test_subspans(generic_ro_timespan):
    two_hours = dt.timedelta(hours=2)

    # Span subspanning
    spans = list(generic_ro_timespan.span.subspans(two_hours))
    for span in spans:
        assert span.duration <= two_hours
    assert Span(spans[0].begins_at, spans[1].finish_at) == generic_ro_timespan.span
    assert spans[0].finish_at == spans[1].begins_at
    assert spans[0].duration == spans[1].duration


@pytest.mark.parametrize(
    "generic_ro_timespan", GENERIC_RO_TIMESPANS.keys(), indirect=True
)
def test_spans(generic_ro_timespan):
    span = generic_ro_timespan.span
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


@pytest.mark.parametrize(
    "generic_ro_timespan", GENERIC_RO_TIMESPANS.keys(), indirect=True
)
def test_slice_syntaxes(generic_ro_timespan):
    assert len(generic_ro_timespan) == 4

    base_tags = list(generic_ro_timespan[:].iter_tags())
    resliced_tags = list(generic_ro_timespan.reslice(None, None).iter_tags())
    assert base_tags == resliced_tags

    assert len(generic_ro_timespan[:]) == 4
    assert len({t for t in generic_ro_timespan.iter_tags()}) == 4
    base_tags = list(generic_ro_timespan.iter_tags())
    spanned_tags = [
        t for t in generic_ro_timespan.iter_tags() if t in generic_ro_timespan.span
    ]
    assert base_tags == spanned_tags

    past_half = generic_ro_timespan.span.begins_at + dt.timedelta(minutes=60 * 2 + 10)
    assert len(generic_ro_timespan[past_half:]) == 2
    assert len(generic_ro_timespan[:past_half]) == 3
    assert len(generic_ro_timespan[past_half:past_half]) == 1

    base_tags = list(generic_ro_timespan[past_half:].iter_tags())
    resliced_tags = list(generic_ro_timespan.reslice(past_half, None).iter_tags())
    assert base_tags == resliced_tags


@pytest.mark.parametrize(
    "generic_ro_timespan", GENERIC_RO_TIMESPANS.keys(), indirect=True
)
def test_tag_having(generic_ro_timespan):
    a_tag = next(generic_ro_timespan.iter_tags())
    assert generic_ro_timespan.has_tag(a_tag)


def test_category():
    cat = Category("Test Category", None)
    other_cat = cat / "Child"
    assert other_cat.parent == cat
    with pytest.raises(ValueError):
        cat / "Bad Name!"


def test_category_pool(complex_timespan):
    pool = complex_timespan.category_pool
    d_cat = pool.get_category("A/B/C/D")
    assert d_cat not in pool
    assert d_cat.parent in pool
    assert d_cat.parent is pool.get_category("A/B/C")

    splat = sorted((fullpath, cat.name) for fullpath, cat in pool.categories.items())
    assert splat == [("A", "A"), ("A/B", "B"), ("A/B/C", "C")]


def test_base_category_pool_iface():
    pool = BaseCategoryPool()
    with pytest.raises(NotImplementedError):
        pool.categories

    with pytest.raises(TypeError):
        "foo" in pool

    with pytest.raises(ValueError):
        pool.get_category("")


def test_mutable_category_pool():
    pool = MutableCategoryPool()
    with pytest.raises(ValueError):
        pool.get_category("", True)
    b_cat = pool.get_category("alfalfa/banana")
    a_cat = pool.get_category("alfalfa")
    assert b_cat.parent == a_cat


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
    account = BaseTimeSpan()
    with pytest.raises(NotImplementedError):
        account.category_pool

    with pytest.raises(NotImplementedError):
        account.iter_tags()

    with pytest.raises(NotImplementedError):
        account.filter(str())

    with pytest.raises(NotImplementedError):
        account.reslice(None, None)


def test_slicing_nonsense(complex_timespan):
    with pytest.raises(TypeError) as excinfo:
        complex_timespan[1]
    assert "must be sliced with datetime" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        complex_timespan[1:3]
    assert "must be sliced with datetime" in str(excinfo.value)


@pytest.mark.parametrize(
    "path", ["☃", "/", " /foo", "/bar", "  ", "  //  / /", "\\ ", "\\"]
)
def test_category_badpath(path, complex_timespan):
    with pytest.raises(ValueError):
        complex_timespan.category_pool.get_category(path)


def test_query_by_category_filter(complex_timespan):
    assert len(complex_timespan.filter("A/B")) == 2
    assert len(complex_timespan.filter(None)) == 4
    assert len(complex_timespan.filter("A/B").filter(None)) == 2
    assert len(complex_timespan.filter("Not A Tag")) == 0


def test_category_contains_with_none():
    tag = Tag(
        name="Foo",
        category=None,
        valid_from=dt.datetime.now(),
        valid_to=dt.datetime.now(),
    )
    assert tag.category is None
    other_category = Category("Bar", parent=None)
    assert tag not in other_category


def test_infinite_spans(complex_timespan):
    span1 = Span(None, None)
    span2 = Span(None, complex_timespan.span.finish_at)
    assert span2 in span1
    assert span1 in span2
    assert span1.duration == span2.duration


def test_sqlite_backend(complex_timespan, sqlite_timespan):
    assert len(sqlite_timespan) == len(complex_timespan)
    assert (
        sqlite_timespan.category_pool.categories
        == complex_timespan.category_pool.categories
    )
    sqlite_tags = list(sqlite_timespan.iter_tags())
    base_tags = list(complex_timespan.iter_tags())
    assert sqlite_tags == base_tags

    sqlite_tags = sorted(sqlite_timespan.filter("A/B").iter_tags())
    base_tags = sorted(complex_timespan.filter("A/B").iter_tags())
    assert sqlite_tags == base_tags


def test_insertable_removable_interface():
    class FakeTimeSpan(InsertableTimeSpan, RemovableTimeSpan):
        pass

    ts = FakeTimeSpan()
    with pytest.raises(NotImplementedError):
        ts.insert_tag(Tag("Tag A"))
    with pytest.raises(NotImplementedError):
        ts.remove_tag(Tag("Tag A"))


def test_insertable_removable(sqlite_timespan):
    # sqlite is both insertable and removable so we'll use it
    a_tag = next(sqlite_timespan.iter_tags())
    assert sqlite_timespan.has_tag(a_tag)
    assert sqlite_timespan.remove_tag(a_tag)
    assert not sqlite_timespan.has_tag(a_tag)


def test_sqlite_writable(sqlite_timespan):
    assert isinstance(sqlite_timespan, WriteableTimeSpan)
    with tempfile.NamedTemporaryFile() as tempf:
        # TODO - hack involving suffixing a tempfile name, which loses the
        # awesome security of tempfile's context manager :(
        try:
            hack_filepath = Path(tempf.name + "-test")
            sqlite_timespan.write_to(hack_filepath)
            new_span = SqliteTimeSpan.read_from(hack_filepath)
        finally:
            if hack_filepath.exists():
                os.unlink(str(hack_filepath))
    assert sorted(sqlite_timespan.iter_tags()) == sorted(new_span.iter_tags())

    with tempfile.NamedTemporaryFile() as tempf:
        with pytest.raises(ValueError):
            sqlite_timespan.write_to(Path(tempf.name))


def test_writable_iface():
    class Foo(WriteableTimeSpan):
        pass

    with pytest.raises(NotImplementedError):
        Foo().write_to("/tmp/this_should_never_exist_hermes")
    with pytest.raises(NotImplementedError):
        Foo.read_from("/tmp/this_should_never_exist_hermes")
