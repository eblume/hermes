# -*- coding: utf-8 -*-
from datetime import time, timedelta

from hermes.schedule import DailySchedule, Task


class MyDailySchedule(DailySchedule):
    def schedule(self):
        # These are the defaults, but I'm including them for documentation
        self.day_start = time(hour=8)
        self.day_end = time(hour=22)

        # Take medicine
        medicine = Task("Take my medicine", duration=timedelta(minutes=10))
        self.task(medicine)

        # Drink metamucil but not within 1 hour of taking medicine
        metamucil = Task("Drink metamucil", duration=timedelta(minutes=10))
        self.task(metamucil)
        self.not_within(medicine, metamucil, timedelta(minutes=60))

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
