from datetime import time, timedelta

from hermes.schedule import Schedule, Task

schedule = Schedule()

# Take medicine
medicine = Task("Take my medicine", duration=timedelta(minutes=5))
schedule.task(medicine)

# Drink metamucil but not within 1 hour of taking medicine
metamucil = Task("Drink metamucil", duration=timedelta(minutes=10))
schedule.task(metamucil)
# schedule.not_within(medicine, metamucil, timedelta(minutes=60))

# Take out trash after 8pm
trash = Task("Take out the trash", duration=timedelta(minutes=30))
schedule.task(trash)

# Eat Breakfast
breakfast = Task("Eat breakfast", duration=timedelta(minutes=45))
schedule.task(breakfast, between=(time(hour=8), time(hour=10)))

# Eat Lunch
lunch = Task("Eat lunch", duration=timedelta(minutes=45))
schedule.task(lunch, between=(time(hour=12), time(hour=14)))

# Eat Dinner
dinner = Task("Eat dinner", duration=timedelta(minutes=60))
schedule.task(dinner, between=(time(hour=19), time(hour=21)))

# Do dishes after 8pm and after dinner
dishes = Task("Do the dishes", duration=timedelta(minutes=15))
schedule.task(dishes)

# Set out clothes for tomorrow by 9pm and after dinner
clothes = Task("Set out clothes", duration=timedelta(minutes=15))
schedule.task(clothes)

schedule.start_time(time(hour=8))  # NB: means 7 o'clock... unsure if I like that
schedule.stop_time(time(hour=23))

plan = schedule.solve()

plan.print()
