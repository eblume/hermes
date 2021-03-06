# -*- coding: utf-8 -*-
from datetime import timedelta, datetime
from operator import attrgetter
from pathlib import Path

from dateutil.tz import tzlocal
from hermes.clients.gcal import GoogleCalendarAPI, GoogleCalendarTimeSpan, GoogleClient
from hermes.span import Span
from hermes.timespan import date_parse
from hermes.util import get_now
import pytest


@pytest.fixture(scope="module")
def gcal_client():
    token_file = Path("calendar.token")
    if not token_file.exists():
        client = GoogleClient.from_local_web_server()
        client.write_access_token_file(token_file)
    else:
        client = GoogleClient.from_access_token_file(token_file)
    return client


@pytest.fixture(scope="module")
def gcal_api(gcal_client):
    return GoogleCalendarAPI(gcal_client)


@pytest.fixture(scope="module")
def gcal_jan_2019(gcal_api):
    begin = date_parse("01 January 2019 00:00:00 PDT")
    finish = date_parse("31 January 2019 23:59:59 PDT")
    return GoogleCalendarTimeSpan.calendar_by_name(
        "Hermes Test",
        load_span=Span(begins_at=begin, finish_at=finish),
        client=gcal_api,
    )


@pytest.fixture(scope="module")
def feb_02_2019():
    begin = date_parse("02 February 2019 00:00:00 PDT")
    finish = date_parse("02 February 2019 23:59:59 PDT")
    return Span(begins_at=begin, finish_at=finish)


@pytest.fixture(scope="module")
def gcal_feb_02_2019(gcal_api, feb_02_2019):
    return GoogleCalendarTimeSpan.calendar_by_name(
        "Hermes Test", load_span=feb_02_2019, client=gcal_api
    )


@pytest.fixture(scope="module")
def gcal_hermes_test_id(gcal_api):
    return gcal_api.calendar_info_by_name("Hermes Test")["id"]


def test_has_events(gcal_jan_2019):
    assert len(gcal_jan_2019) == 3
    tags = list(gcal_jan_2019.iter_tags())
    tags_with_concrete_time = [
        t for t in tags if t.valid_from is not None and t.valid_to is not None
    ]
    earliest_time = min(map(attrgetter("valid_from"), tags_with_concrete_time))
    last_time = max(map(attrgetter("valid_to"), tags_with_concrete_time))
    assert earliest_time >= gcal_jan_2019.span.begins_at
    assert last_time <= gcal_jan_2019.span.finish_at


def test_alternate_creation_args(gcal_hermes_test_id, gcal_api):
    begin = date_parse("01 January 2019 00:00:00 PDT")
    finish = date_parse("31 January 2019 23:59:59 PDT")
    tags_a = set(
        GoogleCalendarTimeSpan(
            calendar_id=gcal_hermes_test_id,
            load_span=Span(begins_at=begin, finish_at=finish),
            client=gcal_api,
        ).iter_tags()
    )
    tags_b = set(
        GoogleCalendarTimeSpan(calendar_id=gcal_hermes_test_id, client=gcal_api)[
            begin:finish
        ].iter_tags()
    )
    assert tags_a == tags_b
    assert len(tags_a) == 3


def test_category_pool(gcal_jan_2019):
    assert len(gcal_jan_2019.category_pool) == 2
    assert "GCal/Hermes Test" in gcal_jan_2019.category_pool


def test_filter(gcal_jan_2019):
    assert len(gcal_jan_2019.filter("not a tag")) == 0
    assert len(gcal_jan_2019.filter("GCal")) == 3


def test_calendar_by_name(gcal_jan_2019, gcal_hermes_test_id):
    assert gcal_jan_2019.calendar_id == gcal_hermes_test_id


def test_create_event(gcal_feb_02_2019, feb_02_2019, gcal_api):
    assert len(gcal_feb_02_2019) == 0

    event = gcal_feb_02_2019.add_event(
        "Test Event 1",
        when=feb_02_2019.begins_at + timedelta(hours=1),
        duration=timedelta(hours=2),
    )
    assert len(gcal_feb_02_2019) == 1

    new_gcal = GoogleCalendarTimeSpan.calendar_by_name(
        "Hermes Test", load_span=feb_02_2019, client=gcal_api
    )
    assert len(new_gcal) == 0  # no flush yet

    assert len(gcal_feb_02_2019) == 1
    gcal_feb_02_2019.flush()
    assert len(gcal_feb_02_2019) == 1
    assert len(new_gcal) == 0  # Still no flush

    new_gcal.flush()
    assert len(new_gcal) == 1

    # and then clean up
    new_gcal.remove_events("Test Event 1", during=event.span)
    assert len(new_gcal) == 0
    assert len(gcal_feb_02_2019) == 1

    new_gcal.flush()
    gcal_feb_02_2019.flush()
    assert len(gcal_feb_02_2019) == 0


def test_can_gen_next_5_events(gcal_api):
    """This test prevents a regression on some behavior I encountered when
    trying to generate the "next five events" on any calendar on my account."""

    def _gen():
        now = get_now()
        next_24_hours = Span(begins_at=now, finish_at=now + timedelta(hours=24))
        for i, event in zip(range(5), gcal_api.events(span=next_24_hours)):
            start = event.valid_from.strftime("%H:%M")
            stop = event.valid_to.strftime("%H:%M")
            yield f" {i}) [{start} - {stop}] {event.name}"

    assert 1 <= len(list(_gen())) <= 5
