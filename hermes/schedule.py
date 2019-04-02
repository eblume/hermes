# -*- coding: utf-8 -*-
from datetime import date, datetime, time, timedelta, timezone
from typing import cast, Dict, Iterable, List, Optional, Tuple

from dateutil.tz import tzlocal
from ortools.sat.python import cp_model

from .span import Span
from .tag import Tag


class Schedule:
    """Class that is used to build (via subclassing) 'schedules'.

    Schedules here are 'blueprints' that can be given a Span, and will generate
    tags representing events such that certain constraints (defined by the
    subclasser) are met. These tags may then be used to populate a timespan -
    the caller does this.

    **All concrete subclasses MUST implement a `schedule` method.** This
    method is called to actually create the scheduling constraints at
    runtime. A 'concrete' schedule is a subclass of Schedule that will itself
    be instantiated, as opposed to 'virtual' schedules (of which Schedule is
    one) that are intended to be subclassed. 'Virtual' schedules MUST NOT
    implement a `schedule` method, or else Hermes will attempt to use them
    as an actual schedule!

    To put it another way: All children-classes of Schedule that implement
    a `schedule` method WILL be scheduled.

    Finally, note that you can override `NAME` as an attribute on a schedule
    in order to provide a different name to the tagger. This changes, at
    minimum, the leaf Category (which will be set to `NAME` or the schedule's
    class name, in that order).
    """

    NAME: Optional[str] = None

    def __init__(self, **kwargs):
        if kwargs:
            raise ValueError("Unrecognized kwargs", kwargs)
        self.tasks: Dict[str, "Task"] = {}
        self.model = cp_model.CpModel()

    def event_windows(self, overall: Span) -> Iterable[Span]:
        """Generate all valid scheduling windows over the given span.

        This base implementation simply yields the entire span of the schedule all at
        once, but subclasses can change this behavior.

        This is so that schedules can be configured to only schedule events
        during certain windows inside of their overall span.

        Importantly, the schedule is _stretched_ across all windows! That is to
        say, this does not _repeat_ the schedule in each window. If you would
        like to repeat the schedule, then simply apply the schedule seperately
        for each intended window. You can even use this method in a recipe to
        do that:

            foo = MySchedule()  # implements a custom `event_windows()`
            for window in foo.event_windows():
                events = foo.populate(window)  # foo now 'repeated' across all windows

        However, note that in order for this to work, `event_windows()` must
        be designed to 'terminate recursively', because `populate()` itself
        uses `event_windows()`. Most commonly, you would want each windows'
        individual `event_windows()` subdivision to just return itself. See
        `DailySchedule` for a basic, common example.
        """
        yield overall

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
            # event windows
            windows = []
            for i, window in enumerate(self.event_windows(span)):
                start_cons = start_time > int(
                    cast(datetime, window.begins_at).timestamp()
                )
                stop_cons = stop_time < int(
                    cast(datetime, window.finish_at).timestamp()
                )
                this_window = self.model.NewBoolVar(f"{task.name}_window_{i}")
                self.model.Add(start_cons).OnlyEnforceIf(this_window)
                self.model.Add(stop_cons).OnlyEnforceIf(this_window)
                windows.append(this_window)
            self.model.AddBoolXOr(windows)

            # between intervals
            # 'between' refers to hours in the day, so this is basically just
            # another scheduling window constraint, but individualized per-task
            if task.between is not None:
                days = []
                daily_start = task.between[0]
                daily_stop = task.between[1]
                for i, day in enumerate(dates_between(span)):
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
            # Same note here as for 'between'.
            if task.by:
                days = []
                for i, day in enumerate(dates_between(span)):
                    by_time = int(datetime.combine(day, task.by).timestamp())
                    this_day = self.model.NewBoolVar(f"day_{i}_by_{task.name}")
                    self.model.Add(stop_time < by_time).OnlyEnforceIf(this_day)
                    days.append(this_day)
                self.model.AddBoolXOr(days)

            # after constraint
            # Same note here as for 'between'.
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


def dates_between(span: Span) -> Iterable[date]:
    if not span.is_finite():
        raise ValueError("Span must be concrete and finite")
    begins_at: datetime = cast(datetime, span.begins_at)
    finish_at: datetime = cast(datetime, span.finish_at)

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


class DailySchedule(Schedule):
    """Helper class - this schedule type (and its descendants) only assign
    events during the day."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.day_start = time(hour=8)  # if needed, just overwrite these directly.
        self.day_end = time(hour=22)

    def event_windows(self, overall: Span) -> Iterable[Span]:
        for day in dates_between(overall):
            start = datetime.combine(
                day, self.day_start, tzinfo=self.day_start.tzinfo or tzlocal()
            )
            stop = datetime.combine(
                day, self.day_end, tzinfo=self.day_end.tzinfo or tzlocal()
            )
            yield Span(
                begins_at=max(start, overall.begins_at),
                finish_at=min(stop, overall.finish_at),
            )
