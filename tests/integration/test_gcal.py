# -*- coding: utf-8 -*-
from operator import attrgetter

from dateutil.parser import parse as date_parse

from hermes.clients.gcal import GoogleCalendarClient, GoogleCalendarTimeSpan

import pytest


@pytest.fixture(scope="module")
def gcal_march_2019():
    begin = date_parse("01 March 2019 00:00:00 PDT")
    finish = date_parse("31 March 2019 23:59:59 PDT")
    return GoogleCalendarTimeSpan()[begin:finish]


def test_has_events(gcal_march_2019):
    assert len(gcal_march_2019) == 3
    tags = list(gcal_march_2019.iter_tags())
    tags_with_concrete_time = [
        t for t in tags if t.valid_from is not None and t.valid_to is not None
    ]
    earliest_time = min(map(attrgetter("valid_from"), tags_with_concrete_time))
    last_time = max(map(attrgetter("valid_to"), tags_with_concrete_time))
    assert earliest_time >= gcal_march_2019.span.begins_at
    assert last_time <= gcal_march_2019.span.finish_at


def test_alternate_creation_args():
    begin = date_parse("11 March 2019 00:00:00 PDT")
    finish = date_parse("11 March 2019 23:59:59 PDT")
    tags_a = set(GoogleCalendarTimeSpan(GoogleCalendarClient(begins_at=begin, finish_at=finish)).iter_tags())
    tags_b = set(GoogleCalendarTimeSpan()[begin:finish].iter_tags())
    assert tags_a == tags_b
    assert len(tags_a) == 3


def test_category_pool(gcal_march_2019):
    assert len(gcal_march_2019.category_pool) == 2
    assert "GCal/Erich Blume Personal" in gcal_march_2019.category_pool


def test_filter(gcal_march_2019):
    assert len(gcal_march_2019.filter("not a tag")) == 0
    assert len(gcal_march_2019.filter("GCal")) == 3
