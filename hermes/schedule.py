# -*- coding: utf-8 -*-
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

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
        self.tasks: List["Task"] = []
        self.model = cp_model.CpModel()

    def task(self, task: "Task", between: Optional[Tuple[time, time]] = None):
        self.tasks.append(task)

        if between is not None:
            task.between = between

    def populate(self, span: Span) -> List[Tag]:
        if span.begins_at is None or span.finish_at is None:
            raise ValueError("Schedules must have concrete, finite spans.")

        start_times = [
            self.model.NewIntVar(
                int(span.begins_at.timestamp()),  # upper_bound
                int((span.finish_at - task.duration).timestamp()),  # lower_bound
                task.name,
            )
            for task in self.tasks
        ]

        stop_times = [
            self.model.NewIntVar(
                int((span.begins_at + task.duration).timestamp()),  # upper_bound
                int(span.finish_at.timestamp()),  # lower_bound
                task.name,
            )
            for task in self.tasks
        ]

        intervals = [
            self.model.NewIntervalVar(
                start_time, int(task.duration.total_seconds()), stop_time, task.name
            )
            for task, start_time, stop_time in zip(self.tasks, start_times, stop_times)
        ]

        # No time overlapping
        self.model.AddNoOverlap(intervals)

        # Additional constraints
        for task, start_time, stop_time in zip(self.tasks, start_times, stop_times):
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

                if not days:
                    # Should never happen. If it does... debug. TODO: unit test?
                    raise ValueError(f"Somehow there are no days in {span}... wut?")

                self.model.AddBoolXOr(days)

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
            for task, start_time, stop_time in zip(self.tasks, start_times, stop_times)
        ]


class Task:
    def __init__(self, name: str, duration: timedelta = timedelta(minutes=30)):
        self.name = name
        self.duration = duration
        self.between: Optional[Tuple[time, time]] = None


def days_between(span: Span) -> Iterable[date]:
    if span.begins_at is None or span.finish_at is None:
        raise ValueError("Span must be concrete and finite")
    begins_at: datetime = span.begins_at
    finish_at: datetime = span.finish_at

    if begins_at.tzinfo != finish_at.tzinfo:
        finish_at = finish_at.astimezone(tz=begins_at.tzinfo)

    day: date = begins_at.date()
    while (
        datetime.combine(day, time(hour=0, minute=0, second=0, microsecond=0))
        < finish_at
    ):
        yield day
        day += timedelta(days=1)
