# -*- coding: utf-8 -*-
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from ortools.sat.python import cp_model

from .span import Span
from .tag import Tag


class Schedule:
    """Class that is used to build (via subclassing) 'schedules'.

    Schedules here are 'blueprints' that can be given a Span, and will generate
    tags representing events such that certain constraints (defined by the
    subclasser) are met. These tags may then be used to populate a timespan -
    the caller does this.

    Most constraints should be built in the subclassing Schedule's __init__
    method.

    Remember to call super().__init__() !
    """

    def __init__(self):
        self.tasks: Dict[str, "Task"] = {}
        self.model = cp_model.CpModel()

    def task(
        self,
        task: "Task",
        between: Optional[Tuple[time, time]] = None,
        after: Optional["Task"] = None,
        by: Optional[time] = None,
    ):
        if task.name in self.tasks:
            raise ValueError("Task names must be unique")
        self.tasks[task.name] = task

        if between is not None:
            task.between = between

        if by is not None:
            if between is not None:
                raise ValueError("Cannot specify both `by` and `between`")
            task.by = by

        if after is not None:
            task.after.append(after)

    def not_within(self, task_a: "Task", task_b: "Task", bound: timedelta) -> None:
        """task_a and task_b must both not start or stop within `bound` of eachother."""
        task_a.not_within.append((task_b, bound))

    def populate(self, span: Span) -> List[Tag]:
        if span.begins_at is None or span.finish_at is None:
            raise ValueError("Schedules must have concrete, finite spans.")

        start_times = [
            self.model.NewIntVar(
                int(span.begins_at.timestamp()),  # upper_bound
                int((span.finish_at - task.duration).timestamp()),  # lower_bound
                task.name,
            )
            for task in self.tasks.values()
        ]

        stop_times = [
            self.model.NewIntVar(
                int((span.begins_at + task.duration).timestamp()),  # upper_bound
                int(span.finish_at.timestamp()),  # lower_bound
                task.name,
            )
            for task in self.tasks.values()
        ]

        intervals = [
            self.model.NewIntervalVar(
                start_time, int(task.duration.total_seconds()), stop_time, task.name
            )
            for task, start_time, stop_time in zip(
                self.tasks.values(), start_times, stop_times
            )
        ]

        # Helper data structure for the above
        tasks_to_times = {
            otask.name: (start_time, stop_time)
            for otask, start_time, stop_time in zip(
                self.tasks.values(), start_times, stop_times
            )
        }

        # No time overlapping
        self.model.AddNoOverlap(intervals)

        # Additional constraints
        for task, start_time, stop_time in zip(
            self.tasks.values(), start_times, stop_times
        ):
            # between intervals
            if task.between is not None:
                days = []
                daily_start = task.between[0]
                daily_stop = task.between[1]
                for i, day in enumerate(days_between(span)):
                    start = int(datetime.combine(day, daily_start).timestamp())
                    stop = int(datetime.combine(day, daily_stop).timestamp())
                    start_cons = start_time > start
                    stop_cons = stop_time < stop
                    this_day = self.model.NewBoolVar(f"day_{i}_between_{task.name}")
                    self.model.Add(start_cons).OnlyEnforceIf(this_day)
                    self.model.Add(stop_cons).OnlyEnforceIf(this_day)
                    days.append(this_day)
                self.model.AddBoolXOr(days)

            # by constraint
            if task.by:
                days = []
                for i, day in enumerate(days_between(span)):
                    by_time = int(datetime.combine(day, task.by).timestamp())
                    this_day = self.model.NewBoolVar(f"day_{i}_by_{task.name}")
                    self.model.Add(stop_time < by_time).OnlyEnforceIf(this_day)
                    days.append(this_day)
                self.model.AddBoolXOr(days)

            # after constraint
            if task.after:
                for other_task in task.after:
                    other_start, other_stop = tasks_to_times[other_task.name]
                    self.model.Add(start_time > other_stop)

            # not-within bounds
            if task.not_within:
                for other_task, bound in task.not_within:
                    other_start, other_stop = tasks_to_times[other_task.name]
                    gap = int(bound.total_seconds())
                    smallest_stop = self.model.NewIntVar(
                        int(span.begins_at.timestamp()),
                        int(span.finish_at.timestamp()),
                        f"smallest_stop_{task.name}_{other_task.name}",
                    )
                    largest_start = self.model.NewIntVar(
                        int(span.begins_at.timestamp()),
                        int(span.finish_at.timestamp()),
                        f"largest_start_{task.name}_{other_task.name}",
                    )
                    self.model.AddMinEquality(smallest_stop, [stop_time, other_stop])
                    self.model.AddMaxEquality(largest_start, [start_time, other_start])

                    self.model.Add(largest_start - smallest_stop > gap)

        # And, now for the magic!
        solver = cp_model.CpSolver()
        status = solver.Solve(self.model)

        if status != cp_model.FEASIBLE:
            # TODO - much better error handling. Also, optional events!
            raise ValueError("Non-feasible scheduling problem, uhoh!")

        return [
            Tag(
                name=task.name,
                # TODO - category,
                valid_from=datetime.fromtimestamp(
                    solver.Value(start_time), timezone.utc
                ),
                valid_to=datetime.fromtimestamp(solver.Value(stop_time), timezone.utc),
            )
            for task, start_time, stop_time in zip(
                self.tasks.values(), start_times, stop_times
            )
        ]


class Task:
    def __init__(self, name: str, duration: timedelta = timedelta(minutes=30)):
        self.name = name
        self.duration = duration
        self.between: Optional[Tuple[time, time]] = None
        self.by: Optional[time] = None
        self.not_within: List[Tuple["Task", timedelta]] = []
        self.after: List["Task"] = []


def days_between(span: Span) -> Iterable[date]:
    if span.begins_at is None or span.finish_at is None:
        raise ValueError("Span must be concrete and finite")
    begins_at: datetime = span.begins_at
    finish_at: datetime = span.finish_at

    if begins_at.tzinfo != finish_at.tzinfo:
        finish_at = finish_at.astimezone(tz=begins_at.tzinfo)

    day: date = begins_at.date()
    while (
        datetime.combine(
            day,
            time(hour=0, minute=0, second=0, microsecond=0),
            tzinfo=begins_at.tzinfo,
        )
        < finish_at
    ):
        yield day
        day += timedelta(days=1)
