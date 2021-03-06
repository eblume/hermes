# -*- coding: utf-8 -*-
import datetime as dt
from operator import attrgetter
import os
from pathlib import Path
import tempfile

from hermes.span import Span
from hermes.timespan import SqliteTimeSpan, TimeSpan, WriteableTimeSpan
import pytest

from .conftest import GENERIC_RO_TIMESPANS


def test_can_make_account(simple_account):
    # Leaving this in as a legacy, it was the first test - timespans used to
    # be called 'accounts', as hermes is a 'time accountant'.
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


def test_slicing_nonsense(complex_timespan):
    with pytest.raises(TypeError) as excinfo:
        complex_timespan[1]
    assert "must be sliced with datetime" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        complex_timespan[1:3]
    assert "must be sliced with datetime" in str(excinfo.value)


def test_query_by_category_filter(complex_timespan):
    assert len(complex_timespan.filter("A/B")) == 2
    assert len(complex_timespan.filter(None)) == 4
    assert len(complex_timespan.filter("A/B").filter(None)) == 2
    assert len(complex_timespan.filter("Not A Tag")) == 0


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


def test_sqlite_reslice(sqlite_timespan):
    span = sqlite_timespan.span
    newsqlite = sqlite_timespan[span.begins_at : span.finish_at]
    assert len(newsqlite) == len(sqlite_timespan)


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


def test_sqlitemeta_data(sqlite_metatimespan):
    assert isinstance(sqlite_metatimespan, WriteableTimeSpan)
    data = {
        key: value
        for mt in sqlite_metatimespan.iter_metatags()
        for key, value in mt.data.items()
    }
    assert "☃" in data
    assert data["☃"][3] == "snowman"
    assert data["foo"] == 10
    assert data["null"] is None
