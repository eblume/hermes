# -*- coding: utf-8 -*-
from datetime import time, timedelta as td

from hermes.schedule import DailySchedule


class MyDailySchedule(DailySchedule):
    def schedule(self):
        # There are defaults, but I'm including them for documentation
        self.day_start = time(hour=8)
        self.day_end = time(hour=23)

        # Take medicine
        medicine = self.add_event(
            "Take my medicine", duration=td(minutes=10), by=time(hour=9)
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
            between=(time(hour=8), time(hour=10)),
        )

        # Eat Lunch
        lunch = self.add_event(
            "Eat lunch", duration=td(minutes=45), between=(time(hour=12), time(hour=14))
        )

        # Eat Dinner
        dinner = self.add_event(
            "Eat dinner",
            duration=td(minutes=60),
            between=(time(hour=18), time(hour=20)),
        )

        # Do dishes after 8pm and after dinner
        self.add_event(
            "Do the dishes",
            duration=td(minutes=15),
            between=(time(hour=20), time(hour=23)),
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
