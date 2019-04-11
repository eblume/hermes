# -*- coding: utf-8 -*-
from datetime import date, time, timedelta

from hermes.schedule import DailySchedule, Task
from hermes.span import Span
from hermes.tag import Tag
import pytest


@pytest.fixture
def example_daily_schedule():
    class MyDailySchedule(DailySchedule):
        def schedule(self):
            # These are the defaults, but I'm including them for documentation
            self.day_start = time(hour=8)
            self.day_end = time(hour=22)

            # Take medicine
            medicine = Task("Take my medicine", duration=timedelta(minutes=10))
            self.task(medicine)

            # Make bed
            make_bed = Task("Make my bed", duration=timedelta(minutes=10))
            self.task(make_bed, by=time(hour=10))

            # Cat litter
            cat_litter = Task("Do cat litter", duration=timedelta(minutes=20))
            self.task(cat_litter)

            # Tidy something up
            tidy_misc = Task("Tidy something up", duration=timedelta(minutes=30))
            self.task(tidy_misc)

            # Shower in the morning
            shower = Task("Take a shower", duration=timedelta(minutes=30))
            self.task(shower, by=time(hour=9))

            # Eat Breakfast
            breakfast = Task("Eat breakfast", duration=timedelta(minutes=45))
            self.task(breakfast, between=(time(hour=8), time(hour=10)))

            # Eat Lunch
            lunch = Task("Eat lunch", duration=timedelta(minutes=45))
            self.task(lunch, between=(time(hour=12), time(hour=14)))

            # Eat Dinner
            dinner = Task("Eat dinner", duration=timedelta(minutes=60))
            self.task(dinner, between=(time(hour=18), time(hour=20)))

            # Do dishes after 8pm and after dinner
            dishes = Task("Do the dishes", duration=timedelta(minutes=15))
            self.task(dishes, between=(time(hour=20), time(hour=23)), after=dinner)

            # Take out trash after 8pm and after dinner
            trash = Task("Take out the trash", duration=timedelta(minutes=30))
            self.task(trash, between=(time(hour=20), time(hour=23)), after=dinner)

            # Set out clothes for tomorrow by 10pm and after dinner
            clothes = Task("Set out clothes", duration=timedelta(minutes=15))
            self.task(clothes, after=dinner, by=time(hour=22))

            # Drink metamucil but not within 1 hour of taking medicine
            metamucil = Task("Drink metamucil", duration=timedelta(minutes=10))
            self.task(metamucil)
            self.not_within(medicine, metamucil, timedelta(minutes=60))

    return MyDailySchedule


@pytest.fixture(scope="function")
def built_schedule(example_daily_schedule):
    schedule = example_daily_schedule()
    schedule.schedule()
    return schedule


@pytest.fixture
def a_day():
    return Span.from_date(date.today())


@pytest.fixture(scope="function")
def scheduled_events(built_schedule, a_day):
    return list(built_schedule.populate(a_day))


def test_daily_schedule_can_schedule(scheduled_events, a_day):
    assert len(scheduled_events) == 12
    for event in scheduled_events:
        assert event.valid_from < event.valid_to
        assert event.valid_from > a_day.begins_at
        assert event.valid_to < a_day.finish_at
    assert len({event.valid_from for event in scheduled_events}) == 12
    assert len({event.valid_to for event in scheduled_events}) == 12


def test_can_schedule_with_unknown_preexisting_events(example_daily_schedule, a_day):
    eight_am = a_day.begins_at.replace(hour=8)
    eight_am_hour = Span(begins_at=eight_am, finish_at=eight_am + timedelta(minutes=10))
    twelve_pm_hour = Span(
        begins_at=eight_am + timedelta(hours=4),
        finish_at=eight_am + timedelta(hours=4, minutes=10),
    )
    pre_existing_events = [
        Tag.from_span(eight_am_hour, "Test event A"),
        Tag.from_span(twelve_pm_hour, "Test event B"),
    ]
    schedule = example_daily_schedule()
    schedule.pre_existing_events(pre_existing_events)
    schedule.schedule()
    scheduled_events = list(schedule.populate(a_day))

    assert len(scheduled_events) == 12
    for event in scheduled_events:
        assert event.span not in eight_am_hour
        assert event.span not in twelve_pm_hour


def test_can_schedule_with_known_preexisting_events(example_daily_schedule, a_day):
    twelve_pm_hour = Span(
        begins_at=a_day.begins_at.replace(hour=12),
        finish_at=a_day.begins_at.replace(hour=12, minute=10),
    )
    pre_existing_events = [Tag.from_span(twelve_pm_hour, "Eat lunch")]

    schedule = example_daily_schedule()
    schedule.schedule()
    schedule.pre_existing_events(pre_existing_events)
    scheduled_events = list(schedule.populate(a_day))

    assert len(scheduled_events) == 11


def test_can_schedule_with_known_preexisting_events_by_ignoring_them(
    example_daily_schedule, a_day
):
    # Note that by 'ignore' here we mean 'schedule around, and duplicate'
    twelve_pm_hour = Span(
        begins_at=a_day.begins_at.replace(hour=12),
        finish_at=a_day.begins_at.replace(hour=12, minute=10),
    )
    pre_existing_events = [Tag.from_span(twelve_pm_hour, "Eat lunch")]

    schedule = example_daily_schedule()
    schedule.schedule()
    schedule.pre_existing_events(pre_existing_events, preserve_schedule=False)
    scheduled_events = list(schedule.populate(a_day))

    assert len(scheduled_events) == 12
    for event in scheduled_events:
        assert event.span not in twelve_pm_hour
