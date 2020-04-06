# -*- coding: utf-8 -*-
from datetime import date

from hermes.span import Span
from hermes.scheduler import ScheduleItem, Schedule
from hermes.scheduler.constraint import IntervalOverlap
from hermes.scheduler.model import Model

import pytest


@pytest.fixture
def a_day():
    return Span.from_date(date.today())


@pytest.fixture
def basic_schedule_items():
    return [ScheduleItem("item 1"), ScheduleItem("item 2"), ScheduleItem("item 3")]


@pytest.fixture
def reasonable_schedule(basic_schedule_items):
    schedule = Schedule("A reasonable schedule")
    schedule.add_schedule_items(*basic_schedule_items)
    return schedule


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


def test_a_reasonable_schedule(basic_schedule_items, reasonable_schedule, a_day):
    events = list(reasonable_schedule.events(a_day))
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


def test_unrelated_context(basic_schedule_items, complex_timespan, a_day):
    schedule = Schedule("An empty Schedule", context=complex_timespan)
    schedule.add_schedule_items(*basic_schedule_items)
    events = list(schedule.events(a_day))
    assert len(events) == 3


def test_schedules_with_mutual_items(basic_schedule_items, a_day):
    schedule_a = Schedule("schedule a")
    schedule_b = Schedule("schedule b")
    schedule_a.add_schedule_items(*basic_schedule_items[:2])  # 0, 1
    schedule_b.add_schedule_items(*basic_schedule_items[1:])  # 1, 2

    events_a = list(schedule_a.events(a_day))
    events_b = list(schedule_b.events(a_day))

    assert len(events_a) == len(events_b) == 2

    shared_events = [
        (event_a, event_b)
        for event_a in events_a
        for event_b in events_b
        if event_a.name == event_b.name
    ]
    assert len(shared_events) == 1

    event_a, event_b = shared_events[0]
    assert event_a == event_b  # which should imply:
    assert event_a.duration == event_b.duration
    assert event_a.start_time == event_b.start_time
    assert event_a.stop_time == event_b.stop_time
    assert event_a.is_present == event_b.is_present
    assert event_a.interval == event_b.interval
    assert event_a._constraints == event_b._constraints
    assert event_a.external == event_b.external

    # Check that, for this test, all other events are in fact not equal.
    unshared_events = [
        (event_a, event_b)
        for event_a in events_a
        for event_b in events_b
        if event_a.name != event_b.name  # just an inversion of above.
    ]
    for event_a, event_b in unshared_events:
        assert event_a != event_b


def test_schedules_with_models(reasonable_schedule, a_day):
    model = Model()
    result = model.schedule(a_day, reasonable_schedule)
    assert False
    assert result
