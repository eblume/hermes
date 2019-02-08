from hermes.schedule import Schedule, Task

schedule = Schedule()

# Take medicine
medicine = Task("Take my medicine")
schedule.task(medicine)

# Drink metamucil but not within 1 hour of taking medicine
metamucil = Task("Drink metamucil")
schedule.task(metamucil)

# Take out trash after 8pm
trash = Task("Take out the trash")
schedule.task(trash)

# Eat Breakfast
breakfast = Task("Eat breakfast")
schedule.task(breakfast)

# Eat Lunch
lunch = Task("Eat lunch")
schedule.task(lunch)

# Eat Dinner
dinner = Task("Eat dinner")
schedule.task(dinner)

# Do dishes after 8pm and after dinner
dishes = Task("Do the dishes")
schedule.task(dishes)

# Set out clothes for tomorrow by 9pm and after dinner
clothes = Task("Set out clothes")
schedule.task(clothes)

plan = schedule.solve()

plan.print()
