# -*- coding: utf-8 -*-
from datetime import date, timedelta

from hermes.span import Span
from hermes.scheduler import ScheduleItem
from hermes.scheduler.constraint import IntervalOverlap
import pytest


td = timedelta  # helper shortcut


@pytest.fixture
def a_day():
    return Span.from_date(date.today())


@pytest.fixture
def basic_schedule_items():
    return [ScheduleItem("item 1"), ScheduleItem("item 2"), ScheduleItem("item 3")]


def test_can_use_schedule_items_to_create_events(basic_schedule_items, a_day):
    events = []
    for schedule_item in basic_schedule_items:
        for event in schedule_item.events(a_day):
            events.append(event)

    assert len(events) == 3
    assert not any(map(lambda x: x.external, events))
    assert all(map(lambda x: len(x._constraints) == 2, events))

    for event in events:
        con = event._constraints[0]
        assert con._event == event
        assert type(con) == IntervalOverlap
