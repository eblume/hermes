from datetime import datetime, time, timedelta
from itertools import combinations
from operator import attrgetter
from typing import Iterator, List, Optional, Tuple, Type

import constraint as solver

from .tag import Tag
from .timespan import SqliteTimeSpan

# Notes:
# a) The python-constraint solver should eventually be removed to use something
#    that is aware of `datetime` objects natively.


class Schedule:
    def __init__(self) -> None:
        self.tasks: List[Task] = []
        self.constraints: List["Constraint"] = []
        self.today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.interval = timedelta(minutes=5)

    def task(self, task: "Task", between: Optional[Tuple[time, time]] = None) -> None:
        self.tasks.append(task)
        task.solver_variable = len(self.tasks) - 1

        if between is not None:
            # Map from times to datetimes
            dt_between = tuple(
                map(
                    lambda x: self.today.replace(
                        hour=x.hour,
                        minute=x.minute,
                        second=x.second,
                        microsecond=x.microsecond,
                    ),
                    between,
                )
            )
            task.constrain(BetweenConstraint, *dt_between)

    def solve(self) -> "PlannedSchedule":
        tags = []
        slots = list(slice_day(self.today, self.interval))
        # We use the index of the tasks array as variables - dumb, but it works
        variables = list(range(len(self.tasks)))

        problem = solver.Problem(solver.MinConflictsSolver())

        problem.addVariables(variables, slots)

        problem.addConstraint(
            solver.AllDifferentConstraint()
        )  # Don't multi-assign slots

        # Add schedule-general constraints
        for constraint in self.constraints:
            problem.addConstraint(constraint.constraint, constraint.variables)

        # Add task-specific constraints
        for task in self.tasks:
            for constraint in task.constraints:
                # Maybe this should use the tasks's variable rather than the constraints?
                # Hard to say
                problem.addConstraint(constraint.constraint, constraint.variables)

        # Also, don't overlap time assignments
        # This will eventually need to be redone to handle cases of sub-tasks
        for var_a, var_b in combinations(variables, 2):
            task_a = self.tasks[var_a]
            task_b = self.tasks[var_b]

            def _dont_overlap(timestamp_a: int, timestamp_b: int) -> bool:
                time_a = datetime.fromtimestamp(timestamp_a)
                time_b = datetime.fromtimestamp(timestamp_b)
                b_overlaps = time_a < time_b < time_a + task_a.duration + task_a.gap
                a_overlaps = time_b < time_a < time_b + task_b.duration + task_b.gap
                return not b_overlaps and not a_overlaps

            problem.addConstraint(_dont_overlap, (var_a, var_b))

        # Do the math stuff please (wish it was always this easy)
        solution = problem.getSolution()

        # map solutions to tasks to make tags
        for variable, slot in solution.items():
            task = self.tasks[variable]
            start = datetime.fromtimestamp(slot)
            stop = start + task.duration
            tags.append(task.tag(start, stop))

        return PlannedSchedule(*tags)

    def start_time(self, time: time) -> None:
        when = self.today.replace(
            hour=time.hour,
            minute=time.minute,
            second=time.second,
            microsecond=time.microsecond,
        )
        self.constraints.append(StartTimeConstraint(when))

    def stop_time(self, time: time) -> None:
        when = self.today.replace(
            hour=time.hour,
            minute=time.minute,
            second=time.second,
            microsecond=time.microsecond,
        )
        self.constraints.append(StopTimeConstraint(when))


class PlannedSchedule:
    def __init__(self, *tags: "Tag") -> None:
        self.plan = SqliteTimeSpan()
        for tag in tags:
            self.plan.insert_tag(tag)

    def print(self) -> None:
        for i, task in enumerate(
            sorted(self.plan.iter_tags(), key=attrgetter("valid_from"))
        ):
            print(
                f"[{i+1}] {task.name}: {task.valid_from.time().isoformat()} to {task.valid_to.time().isoformat()}"
            )


class Task:

    task_name: str = "Untitled Task"
    duration: timedelta = timedelta(hours=1)
    gap: timedelta = timedelta(minutes=5)
    constraints: List["Constraint"] = None
    solver_variable: Optional[int] = None

    def __init__(
        self, name: Optional[str] = None, duration: Optional[timedelta] = None
    ) -> None:
        self.constraints = []
        if name is not None:
            self.task_name = name

        if duration is not None:
            self.duration = duration

    def __str__(self) -> str:
        return self.task_name

    def tag(self, start: datetime, stop: datetime) -> Tag:
        return Tag(name=self.task_name, valid_from=start, valid_to=stop)

    def constrain(self, constraint_type: Type["Constraint"], *args) -> None:
        if self.solver_variable is None:
            raise ValueError(
                "You must assign this task a variable before you may constrain it."
            )
        self.constraints.append(constraint_type(self.solver_variable, *args))


class Constraint:
    # TODO - implement the ABC interface
    @property
    def variables(self) -> Optional[List[int]]:
        return None  # means 'all variables'


class StartTimeConstraint(Constraint):
    def __init__(self, when: datetime) -> None:
        self.when = when.timestamp()

    @property
    def constraint(self) -> solver.Constraint:
        return solver.FunctionConstraint(lambda *xs: all(x > self.when for x in xs))


class StopTimeConstraint(Constraint):
    def __init__(self, when: datetime) -> None:
        self.when = when.timestamp()

    @property
    def constraint(self) -> solver.Constraint:
        return solver.FunctionConstraint(lambda *xs: all(x < self.when for x in xs))


class BetweenConstraint(Constraint):
    def __init__(self, variable: int, begin: datetime, end: datetime) -> None:
        self.variable = variable
        self.begin = begin.timestamp()
        self.end = end.timestamp()

    @property
    def constraint(self) -> solver.Constraint:
        return solver.FunctionConstraint(
            lambda x: self.begin < x < self.end, [self.variable]
        )

    @property
    def variables(self) -> Optional[List[int]]:
        return [self.variable]


def slice_day(day: datetime, interval: timedelta) -> Iterator[float]:
    cursor = day
    while cursor - day < timedelta(hours=24):
        yield cursor.timestamp()
        cursor += interval
