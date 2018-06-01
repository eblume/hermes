# -*- coding: utf-8 -*-
from operator import attrgetter

from dateutil.parser import parse as date_parse

from hermes.clients import GoogleCalendarTimeSpan

import pytest


@pytest.fixture(scope="module")
def gcal_may_2018():
    begin = date_parse("01 May 2018 00:00:00 PDT")
    finish = date_parse("06 May 2018 23:59:59 PDT")
    return GoogleCalendarTimeSpan()[begin:finish]


def test_has_events(gcal_may_2018):
    assert len(gcal_may_2018) == 93
    tags = list(gcal_may_2018.iter_tags())
    tags_with_concrete_time = [
        t for t in tags if t.valid_from is not None and t.valid_to is not None
    ]
    earliest_time = min(map(attrgetter("valid_from"), tags_with_concrete_time))
    last_time = max(map(attrgetter("valid_to"), tags_with_concrete_time))
    assert earliest_time >= gcal_may_2018.span.begins_at
    assert last_time <= gcal_may_2018.span.finish_at


def test_alternate_creation_args():
    begin = date_parse("01 June 2016 00:00:00 PDT")
    finish = date_parse("01 June 2016 00:00:00 PDT")
    tags_a = set(GoogleCalendarTimeSpan(begins_at=begin, finish_at=finish).iter_tags())
    tags_b = set(GoogleCalendarTimeSpan()[begin:finish].iter_tags())
    assert tags_a == tags_b
