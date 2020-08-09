# -*- coding: utf-8 -*-
import datetime as dt

from hermes.categorypool import MutableCategoryPool
from hermes.span import Span
from hermes.tag import Category, MetaTag, Tag
from hermes.utils import get_now
import pytest

from .conftest import GENERIC_RO_TIMESPANS


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


def test_mutable_category_pool():
    pool = MutableCategoryPool()
    with pytest.raises(ValueError):
        pool.get_category("", True)
    b_cat = pool.get_category("alfalfa/banana")
    a_cat = pool.get_category("alfalfa")
    assert b_cat.parent == a_cat


def test_categorypool_contains_string(complex_timespan):
    assert "not a tag" not in complex_timespan.category_pool
    assert "A/B" in complex_timespan.category_pool
    assert "B" in complex_timespan.category_pool
    assert "A/A" not in complex_timespan.category_pool


def test_categorypool_length(complex_timespan):
    assert len(complex_timespan.category_pool) == 3


def test_category_contains_with_none():
    tag = Tag(
        name="Foo",
        category=None,
        valid_from=get_now(),
        valid_to=get_now(),
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


@pytest.mark.parametrize(
    "path", ["☃", "/", " /foo", "/bar", "  ", "  //  / /", "\\ ", "\\"]
)
def test_category_badpath(path, complex_timespan):
    with pytest.raises(ValueError):
        complex_timespan.category_pool.get_category(path)


def test_span_ordering():
    now = get_now()
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


def test_meta_tags(generic_span):
    tag = Tag.from_span(generic_span, name="example tag")
    mtag = MetaTag.from_tag(tag, {"foo": "bar"})
    assert mtag.data["foo"] == "bar"


def test_meta_tag_equality(generic_span):
    time1 = generic_span.begins_at
    time2 = generic_span.finish_at
    t1 = MetaTag(
        name="Foo", category=None, valid_from=time1, valid_to=time2, data={"foo": "bar"}
    )
    t2 = MetaTag.from_tag(t1, data={"biff": "boff"}, merge_data=False)
    assert t1 != t2
    assert "biff" not in t1.data
    assert "foo" not in t2.data
