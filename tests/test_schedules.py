# -*- coding: utf-8 -*-
from datetime import date, time, timedelta

from hermes.schedule import DailySchedule, Schedule
from hermes.span import Span
from hermes.tag import Tag
from hermes.timespan import TimeSpan
from hermes.stochastics import Frequency
from hermes.chores import ChoreSchedule, Chore
import pytest


td = timedelta  # helper shortcut


class MyDailySchedule(DailySchedule):
    def schedule(self):
        # There are defaults, but I'm including them for documentation
        self.day_start = time(hour=7)
        self.day_end = time(hour=23)

        # Take medicine
        medicine = self.add_event(
            "Take my medicine", duration=td(minutes=10), by=time(hour=10)
        )

        # Drink metamucil but not within 1 hour of taking medicine
        metamucil = self.add_event("Drink metamucil", duration=td(minutes=10))
        self.not_within(medicine, metamucil, td(minutes=60))

        # Make bed
        self.add_event("Make my bed", duration=td(minutes=10), by=time(hour=10))

        # Cat litter
        self.add_event("Do cat litter", duration=td(minutes=20))

        # Tidy something up
        self.add_event("Tidy something up", duration=td(minutes=30))

        # Shower in the morning
        self.add_event("Take a shower", duration=td(minutes=30), by=time(hour=9))

        # Eat Breakfast
        breakfast = self.add_event(
            "Eat breakfast",
            duration=td(minutes=45),
            between=(time(hour=7), time(hour=11)),
        )

        # Eat Lunch
        lunch = self.add_event(
            "Eat lunch", duration=td(minutes=45), between=(time(hour=11), time(hour=14))
        )

        # Eat Dinner
        dinner = self.add_event(
            "Eat dinner",
            duration=td(minutes=60),
            between=(time(hour=16), time(hour=20)),
        )

        # Do dishes after 8pm and after dinner
        self.add_event(
            "Do the dishes",
            duration=td(minutes=15),
            between=(time(hour=19), time(hour=23)),
            after=dinner,
        )

        # Take out trash after 8pm and after dinner
        self.add_event(
            "Take out the trash",
            duration=td(minutes=30),
            between=(time(hour=20), time(hour=23)),
            after=dinner,
        )

        # Set out clothes for tomorrow by 10pm and after dinner
        self.add_event(
            "Set out clothes", duration=td(minutes=15), after=dinner, by=time(hour=22)
        )

        # Also, don't have metamucil within 30 minutes of any meal
        for meal in [breakfast, lunch, dinner]:
            self.not_within(metamucil, meal, td(minutes=30))


class MyDailyChoreSchedule(MyDailySchedule, ChoreSchedule):
    def schedule(self):
        super().schedule()
        self.add_chore_slots(limit=3, duration=td(minutes=15))
        self.add_chore(
            Chore(name="Example chore A", frequency=Frequency(minimum=td(days=3)))
        )
        self.add_chore(
            Chore(
                name="Example chore B",
                duration=td(minutes=5),
                frequency=Frequency(mean=td(hours=1)),
            )
        )


@pytest.fixture
def example_daily_schedule():
    return MyDailySchedule


@pytest.fixture
def daily_schedule_with_choreslots():
    return MyDailyChoreSchedule


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
    return list(built_schedule.populate(a_day).iter_tags())


def test_daily_schedule_can_schedule(scheduled_events, a_day):
    assert len(scheduled_events) == 12
    for event in scheduled_events:
        assert event.valid_from < event.valid_to
        assert event.valid_from > a_day.begins_at
        assert event.valid_to < a_day.finish_at
    assert len({event.valid_from for event in scheduled_events}) == 12
    assert len({event.valid_to for event in scheduled_events}) == 12


def test_can_schedule_and_then_add_events(example_daily_schedule, a_day):
    eight_am = a_day.begins_at.replace(hour=8)
    eight_am_hour = Span(begins_at=eight_am, finish_at=eight_am + timedelta(hours=1))
    twelve_pm_hour = Span(
        begins_at=eight_am + timedelta(hours=4), finish_at=eight_am + timedelta(hours=5)
    )

    schedule = example_daily_schedule()
    schedule.schedule()

    schedule.add_event(
        "Test event A", between=(time(hour=8), time(hour=9)), optional=False
    )
    schedule.add_event(
        "Test event B", between=(time(hour=12), time(hour=13)), optional=False
    )
    scheduled_events = list(schedule.populate(a_day).iter_tags())

    assert len(scheduled_events) == 14
    for event in scheduled_events:
        if event.name == "Test event A":
            assert event.span in eight_am_hour
        elif event.name == "Test event B":
            assert event.span in twelve_pm_hour


def test_can_schedule_with_unknown_preexisting_events(example_daily_schedule, a_day):
    eight_am = a_day.begins_at.replace(hour=8)
    eight_am_hour = Span(begins_at=eight_am, finish_at=eight_am + timedelta(hours=1))
    twelve_pm_hour = Span(
        begins_at=eight_am + timedelta(hours=4), finish_at=eight_am + timedelta(hours=5)
    )
    pre_existing_events = TimeSpan(
        {
            Tag.from_span(
                list(eight_am_hour.subspans(timedelta(minutes=10)))[0], "Test event A"
            ),
            Tag.from_span(
                list(twelve_pm_hour.subspans(timedelta(minutes=10)))[0], "Test event B"
            ),
        }
    )
    schedule = example_daily_schedule()
    schedule.schedule()
    scheduled_events = list(schedule.populate(a_day, [pre_existing_events]).iter_tags())

    assert len(scheduled_events) == 12
    for event in scheduled_events:
        if event.span in eight_am_hour:
            event.span.begins_at > eight_am_hour.begins_at + timedelta(minutes=10)
        if event.span in twelve_pm_hour:
            event.span.begins_at > twelve_pm_hour.begins_at + timedelta(minutes=10)


def test_can_schedule_with_known_preexisting_events(example_daily_schedule, a_day):
    twelve_pm_hour = Span(
        begins_at=a_day.begins_at.replace(hour=12),
        finish_at=a_day.begins_at.replace(hour=12, minute=10),
    )
    pre_existing_events = TimeSpan([Tag.from_span(twelve_pm_hour, "Eat lunch")])

    schedule = example_daily_schedule()
    schedule.schedule()
    scheduled_events = list(schedule.populate(a_day, [pre_existing_events]).iter_tags())

    assert len(scheduled_events) == 12
    for event in scheduled_events:
        if event.name == "Eat lunch":
            assert event.span in twelve_pm_hour


def test_records_subclass_schedules(example_daily_schedule, a_day):
    assert example_daily_schedule.__name__ == "MyDailySchedule"
    assert example_daily_schedule.__name__ in Schedule.DEFINED_SCHEDULES
    new_schedule = Schedule.DEFINED_SCHEDULES[example_daily_schedule.__name__]()
    new_schedule.schedule()
    assert len(list(new_schedule.populate(a_day).iter_tags())) == 12


def test_can_schedule_with_chores(daily_schedule_with_choreslots, a_day):
    schedule = daily_schedule_with_choreslots()
    schedule.schedule()
    scheduled_events = list(schedule.populate(a_day).iter_tags())
    not_chore_events = [
        event for event in scheduled_events if "chore" not in event.name
    ]
    assert len(not_chore_events) == 12

    chore_events = [event for event in scheduled_events if "chore" in event.name]
    assert len(chore_events) > 0
