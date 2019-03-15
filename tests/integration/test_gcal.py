# -*- coding: utf-8 -*-
from datetime import timedelta
from operator import attrgetter

from dateutil.parser import parse as date_parse

from hermes.clients.gcal import GoogleCalendarClient, GoogleCalendarTimeSpan

import pytest


@pytest.fixture(scope="module")
def gcal_march_2019():
    begin = date_parse("01 March 2019 00:00:00 PDT")
    finish = date_parse("31 March 2019 23:59:59 PDT")
    return GoogleCalendarTimeSpan.calendar_by_name(
        "Hermes Test", begins_at=begin, finish_at=finish
    )


@pytest.fixture(scope="module")
def gcal_feb_02_2019():
    begin = date_parse("02 February 2019 00:00:00 PDT")
    finish = date_parse("02 February 2019 23:59:59 PDT")
    return GoogleCalendarTimeSpan.calendar_by_name(
        "Hermes Test", begins_at=begin, finish_at=finish
    )


@pytest.fixture(scope="module")
def gcal_hermes_test_id():
    client = GoogleCalendarClient()
    for calendar in client.calendars():
        if calendar.get("summary") == "Hermes Test":
            return calendar.get("id")
    raise ValueError("Test Calendar not found!")


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


def test_alternate_creation_args(gcal_hermes_test_id):
    begin = date_parse("01 March 2019 00:00:00 PDT")
    finish = date_parse("31 March 2019 23:59:59 PDT")
    tags_a = set(
        GoogleCalendarTimeSpan(
            GoogleCalendarClient(begins_at=begin, finish_at=finish),
            calendar_id=gcal_hermes_test_id,
        ).iter_tags()
    )
    tags_b = set(
        GoogleCalendarTimeSpan(calendar_id=gcal_hermes_test_id)[
            begin:finish
        ].iter_tags()
    )
    assert tags_a == tags_b
    assert len(tags_a) == 3


def test_category_pool(gcal_march_2019):
    assert len(gcal_march_2019.category_pool) == 2
    assert "GCal/Hermes Test" in gcal_march_2019.category_pool


def test_filter(gcal_march_2019):
    assert len(gcal_march_2019.filter("not a tag")) == 0
    assert len(gcal_march_2019.filter("GCal")) == 3


def test_calendar_by_name(gcal_march_2019, gcal_hermes_test_id):
    assert gcal_march_2019.calendar_id == gcal_hermes_test_id


def test_create_event(gcal_feb_02_2019):
    assert len(gcal_feb_02_2019) == 0

    test_event_offset = timedelta(hours=12)
    test_event_duration = timedelta(hours=1)
    gcal_feb_02_2019.add_event(
        "Test Event 1", offset=test_event_offset, duration=test_event_duration
    )

    assert len(gcal_feb_02_2019) == 1

    os = gcal_feb_02_2019.span
    new_gcal = GoogleCalendarTimeSpan.calendar_by_name(
        "Hermes Test", begins_at=os.begins_at, finish_at=os.finish_at
    )

    assert len(new_gcal) == 0  # no flush yet

    gcal_feb_02_2019.flush()

    assert len(gcal_feb_02_2019) == 1
    assert len(new_gcal) == 0  # Still no flush

    new_gcal.flish()

    assert len(new_gcal) == 1
