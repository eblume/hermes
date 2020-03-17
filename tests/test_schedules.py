# -*- coding: utf-8 -*-
from datetime import date, timedelta

from hermes.span import Span
from hermes.scheduler import ScheduleItem, Schedule
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


def test_a_reasonable_schedule(basic_schedule_items, a_day):
    schedule = Schedule("A reasonable schedule")
    for schedule_item in basic_schedule_items:
        schedule.add_schedule_item(schedule_item)
    events = list(schedule.events(a_day))
    assert len(events) == len(basic_schedule_items)

    # Some basic smoke tests for things:

    # Is each event constrained?
    assert all(len(event._constraints) >= 1 for event in events)

    # Is each event constrained... properly? Ish?
    for event in events:
        interval_overlaps = [
            c for c in event._constraints if type(c) == IntervalOverlap
        ]
        assert len(interval_overlaps) == 1


def test_empty_schedule(a_day):
    schedule = Schedule("An empty schedule")
    events = list(schedule.events(a_day))
    assert len(events) == 0
