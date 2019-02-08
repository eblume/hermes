from datetime import datetime, timedelta, date, time
from operator import attrgetter
from typing import Dict, List, Optional, Iterator

from .tag import Tag
from .timespan import SqliteTimeSpan

import constraint as solver

# Notes:
# a) The python-constraint solver should eventually be removed to use something
#    that is aware of `datetime` objects natively.


class Schedule:

    def __init__(self) -> None:
        self.tasks: List[Task] = []
        self.constraints: List["Constraint"] = []
        self.today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def task(self, task: "Task") -> None:
        self.tasks.append(task)

    def solve(self) -> "PlannedSchedule":
        tags = []
        slots = list(slice_day(self.today, timedelta(minutes=15)))
        vars_to_tasks = dict(enumerate(self.tasks))

        problem = solver.Problem(solver.MinConflictsSolver())

        problem.addVariables(vars_to_tasks.keys(), slots)

        problem.addConstraint(solver.AllDifferentConstraint()) # Don't multi-assign slots

        for constraint in self.constraints:
            problem.addConstraint(constraint.constrain())

        solution = problem.getSolution()

        for variable, slot in solution.items():
            task = vars_to_tasks[variable]
            start = datetime.fromtimestamp(slot)
            stop = start + task.duration
            tags.append(task.tag(start, stop))

        return PlannedSchedule(*tags)

    def start_time(self, time: time) -> None:
        self.constraints.append(StartTimeConstraint(time, self.today))

    def stop_time(self, time: time) -> None:
        self.constraints.append(StopTimeConstraint(time, self.today))


class PlannedSchedule:

    def __init__(self, *tags: "Tag") -> None:
        self.plan = SqliteTimeSpan()
        for tag in tags:
            self.plan.insert_tag(tag)

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


class Constraint:
    def constrain(self, vars_to_tasks: Dict[int, "Task"]) -> solver.Constraint:
        raise NotImplementedError("ABC Must be implemented")


class StartTimeConstraint(Constraint):
    def __init__(self, time: time, today: datetime) -> None:
        self.time = time
        self.today = today

    def constrain(self) -> solver.Constraint:
        start_time = self.today.replace(
            hour=self.time.hour,
            minute=self.time.minute,
            second=self.time.second,
            microsecond=self.time.microsecond,
        ).timestamp()
        return solver.FunctionConstraint(lambda *xs: all(x > start_time for x in xs))


class StopTimeConstraint(Constraint):
    def __init__(self, time: time, today: datetime) -> None:
        self.time = time
        self.today = today

    def constrain(self) -> solver.Constraint:
        stop_time = self.today.replace(
            hour=self.time.hour,
            minute=self.time.minute,
            second=self.time.second,
            microsecond=self.time.microsecond,
        ).timestamp()
        return solver.FunctionConstraint(lambda *xs: all(x < stop_time for x in xs))


def slice_day(day: datetime, interval: timedelta) -> Iterator[float]:
    cursor = day
    while cursor - day < timedelta(hours=24):
        yield cursor.timestamp()
        cursor += interval
