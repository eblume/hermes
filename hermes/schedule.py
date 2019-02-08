from datetime import datetime, timedelta, date
from operator import attrgetter
from typing import List, Optional, Iterator

from .tag import Tag
from .timespan import SqliteTimeSpan

import constraint as solver

# Notes:
# a) The python-constraint solver should eventually be removed to use something
#    that is aware of `datetime` objects natively.


class Schedule:

    def __init__(self) -> None:
        self.tasks: List[Task] = []

    def task(self, task: "Task") -> None:
        self.tasks.append(task)

    def solve(self) -> "PlannedSchedule":
        return PlannedSchedule(*self.tasks)


class PlannedSchedule:

    def __init__(self, *tasks: "Task") -> None:
        self.plan = SqliteTimeSpan()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        slots = list(slice_day(today, timedelta(minutes=15)))
        vars_to_tasks = dict(enumerate(tasks))

        problem = solver.Problem(solver.MinConflictsSolver())

        problem.addVariables(vars_to_tasks.keys(), slots)

        problem.addConstraint(solver.AllDifferentConstraint()) # Don't multi-assign slots

        solution = problem.getSolution()

        for variable, slot in solution.items():
            task = vars_to_tasks[variable]
            start = datetime.fromtimestamp(slot)
            stop = start + task.duration
            self.plan.insert_tag(task.tag(start, stop))


    def print(self) -> None:
        for i, task in enumerate(sorted(self.plan.iter_tags(), key=attrgetter('valid_from'))):
            print(f"[{i}] {task.name}: {task.valid_from.time().isoformat()} to {task.valid_to.time().isoformat()}")


class Task:

    task_name: str = "Untitled Task"
    duration: timedelta = timedelta(hours=1)

    def __init__(self, name: Optional[str]) -> None:
        if name is not None:
            self.task_name = name

    def __str__(self) -> str:
        return self.task_name

    def tag(self, start: datetime, stop: datetime) -> Tag:
        return Tag(
            name=self.task_name,
            valid_from=start,
            valid_to=stop,
        )


def slice_day(day: datetime, interval: timedelta) -> Iterator[float]:
    cursor = day
    while cursor - day < timedelta(hours=24):
        yield cursor.timestamp()
        cursor += interval
