# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from hermes.clients.gcal import GoogleCalendarTimeSpan
from hermes.schedule import Schedule, Task
from hermes.span import Span


class DailySchedule(Schedule):
    def __init__(self):
        super().__init__()

        # Take medicine
        medicine = Task("Take my medicine", duration=timedelta(minutes=5))
        self.task(medicine)

        # Drink metamucil but not within 1 hour of taking medicine
        metamucil = Task("Drink metamucil", duration=timedelta(minutes=10))
        self.task(metamucil)
        # self.not_within(medicine, metamucil, timedelta(minutes=60))

        # Take out trash after 8pm
        trash = Task("Take out the trash", duration=timedelta(minutes=30))
        self.task(trash)

        # Eat Breakfast
        breakfast = Task("Eat breakfast", duration=timedelta(minutes=45))
        self.task(breakfast, between=(time(hour=8), time(hour=10)))

        # Eat Lunch
        lunch = Task("Eat lunch", duration=timedelta(minutes=45))
        self.task(lunch, between=(time(hour=12), time(hour=14)))

        # Eat Dinner
        dinner = Task("Eat dinner", duration=timedelta(minutes=60))
        self.task(dinner, between=(time(hour=19), time(hour=21)))

        # Do dishes after 8pm and after dinner
        dishes = Task("Do the dishes", duration=timedelta(minutes=15))
        self.task(dishes)

        # Set out clothes for tomorrow by 9pm and after dinner
        clothes = Task("Set out clothes", duration=timedelta(minutes=15))
        self.task(clothes)


start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
stop = start + timedelta(hours=16)

today = Span(begins_at=start, finish_at=stop)
daily_schedule = DailySchedule()
tasks = daily_schedule.populate(today)
calendar = GoogleCalendarTimeSpan.calendar_by_name("Hermes Test")

for task in tasks:
    calendar.insert_tag(task)

calendar.flush()
