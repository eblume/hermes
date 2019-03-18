# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional, Tuple

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

    def task(
        self,
        task: "Task",
        between: Optional[Tuple[Optional[time], Optional[time]]] = None,
    ):
        self.tasks.append(task)

        # TODO between

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
