# -*- coding: utf-8 -*-
from datetime import date, datetime, time, timedelta, timezone
from typing import cast, Dict, Iterable, List, Optional, Tuple

from dateutil.tz import tzlocal
from ortools.sat.python import cp_model

from .span import FiniteSpan, Span
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
    a `schedule` method WILL be scheduled. This behavior is enforced by the
    CLI of hermes, rather than the package itself, so if you are not using
    the CLI then you don't 'need' to do this, but you'll still have
    to build an actual schedule at some point.

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
        self.model: cp_model.CpModel = cp_model.CpModel()
        self._pre_existing_events: List[Tag] = []
        self._skip_existing: bool = True

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

    def pre_existing_events(
        self, events: Iterable[Tag], preserve_schedule: bool = True
    ) -> None:
        """Tell the scheduler about these pre-existing events. It will not
        schedule any overlapping events during these events.

        If `preserve_schedule` is True (default), events that are already scheduled
        that show up in the pending schedule will not be rescheduled

        Repeated calls to this method just overwrite past calls.
        """
        self._pre_existing_events = list(events)
        self._preserve_schedule = preserve_schedule

    def not_within(self, task_a: "Task", task_b: "Task", bound: timedelta) -> None:
        """task_a and task_b must both not start or stop within `bound` of eachother."""
        task_a.not_within.append((task_b, bound))

    def populate(self, span: Span) -> List[Tag]:
        if not span.is_finite():
            raise ValueError("Schedules must have concrete, finite spans.")
        span = cast(FiniteSpan, span)

        event_times: Dict[str, EventTime] = {}

        for event in self._pre_existing_events:
            if event.name in event_times:
                other_event = cast(PreExistingEventTime, event_times[event.name])
                other_event.duplicate_event(event)
            else:
                event_times[event.name] = PreExistingEventTime(event)

        for task in self.tasks.values():
            if task.name in event_times and self._preserve_schedule:
                continue
            event_times[task.name] = EventTime(self.model, span, task)

        # No time overlapping
        self.model.AddNoOverlap(
            event_time.interval
            for event_time in event_times.values()
            if not event_time.is_pre_existing()
        )

        # Additional constraints
        for event_time in event_times.values():
            if event_time.is_pre_existing():
                continue  # We can't constrain a pre-existing event... it exists already! :)

            # event windows - pick one, and be in it.
            event_time.windows_constraint(self.event_windows(span))

            # pre-existing events
            event_time.pre_existing_constraint(self._pre_existing_events)

            # between intervals
            # 'between' refers to hours in the day, so this is basically just
            # another scheduling window constraint, but individualized per-task
            event_time.between_constraint()

            # by constraint
            # Same note here as for 'between'.
            event_time.by_constraint()

            # after constraint
            # Same note here as for 'between'.
            event_time.after_constraint(
                event_times[other_task.name] for other_task in event_time.task.after
            )

            # not-within bounds
            event_time.not_within_constraint(
                (event_times[other_task.name], bound)
                for other_task, bound in event_time.task.not_within
            )

        # And, now for the magic!
        solver = cp_model.CpSolver()
        status = solver.Solve(self.model)

        if status != cp_model.FEASIBLE:
            # TODO - much better error handling. Also, optional events!
            raise ValueError("Non-feasible scheduling problem, uhoh!")

        return [
            Tag(
                name=event_time.task.name,
                # TODO - category,
                valid_from=datetime.fromtimestamp(
                    solver.Value(event_time.start_time), timezone.utc
                ),
                valid_to=datetime.fromtimestamp(
                    solver.Value(event_time.stop_time), timezone.utc
                ),
            )
            for event_time in event_times.values()
            if not event_time.is_pre_existing()
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


class EventTime:
    """Encapsulation for constraint variables representing event times."""

    def __init__(self, model: cp_model.CpModel, span: FiniteSpan, task: Task) -> None:
        self.start_time: cp_model.IntVar = model.NewIntVar(
            int(span.begins_at.timestamp()),  # upper_bound
            int((span.finish_at - task.duration).timestamp()),  # lower_bound
            task.name,
        )

        self.stop_time: cp_model.IntVar = model.NewIntVar(
            int((span.begins_at + task.duration).timestamp()),  # upper_bound
            int(span.finish_at.timestamp()),  # lower_bound
            task.name,
        )

        self.interval: cp_model.IntVar = model.NewIntervalVar(
            self.start_time,
            int(task.duration.total_seconds()),
            self.stop_time,
            task.name,
        )

        # and some backrefs, because why not, and GC is 'cheap'
        self.model = model
        self.span = span
        self.task = task

    def windows_constraint(self, event_windows: Iterable[Span]) -> None:
        cons = []
        for i, window in enumerate(event_windows):
            start_cons = self.start_time > int(
                cast(datetime, window.begins_at).timestamp()
            )
            stop_cons = self.stop_time < int(
                cast(datetime, window.finish_at).timestamp()
            )
            this_window = self.model.NewBoolVar(f"{self.task.name}_window_{i}")
            self.model.Add(start_cons).OnlyEnforceIf(this_window)
            self.model.Add(stop_cons).OnlyEnforceIf(this_window)
            cons.append(this_window)

        if not cons:
            raise ValueError("All schedules must have at least one window")

        self.model.AddBoolXOr(cons)

    def between_constraint(self) -> None:
        if self.task.between is not None:
            cons = []
            daily_start = self.task.between[0]
            daily_stop = self.task.between[1]
            for i, day in enumerate(dates_between(self.span)):
                start = int(datetime.combine(day, daily_start).timestamp())
                stop = int(datetime.combine(day, daily_stop).timestamp())
                start_cons = self.start_time > start
                stop_cons = self.stop_time < stop
                this_day = self.model.NewBoolVar(f"day_{i}_between_{self.task.name}")
                self.model.Add(start_cons).OnlyEnforceIf(this_day)
                self.model.Add(stop_cons).OnlyEnforceIf(this_day)
                cons.append(this_day)
            self.model.AddBoolXOr(cons)

    def by_constraint(self) -> None:
        if self.task.by:
            days = []
            for i, day in enumerate(dates_between(self.span)):
                by_time = int(datetime.combine(day, self.task.by).timestamp())
                this_day = self.model.NewBoolVar(f"day_{i}_by_{self.task.name}")
                self.model.Add(self.stop_time < by_time).OnlyEnforceIf(this_day)
                days.append(this_day)
            self.model.AddBoolXOr(days)

    def after_constraint(self, other_times: Iterable["EventTime"]) -> None:
        if self.task.after:
            for other_time in other_times:
                if other_time.is_pre_existing():
                    other_time = cast(PreExistingEventTime, other_time)
                    self.model.Add(
                        self.start_time > int(other_time.stop_time.timestamp())
                    )
                else:
                    self.model.Add(self.start_time > other_time.stop_time)

    def not_within_constraint(
        self, other_times: Iterable[Tuple["EventTime", timedelta]]
    ) -> None:
        for other_time, bound in other_times:
            gap = int(bound.total_seconds())
            if other_time.is_pre_existing():
                other_time = cast(PreExistingEventTime, other_time)
                cons = []
                for i, event in enumerate(other_time.events):
                    smallest_stop = self.model.NewIntVar(
                        int(self.span.begins_at.timestamp()),
                        int(self.span.finish_at.timestamp()),
                        f"smallest_stop_{self.task.name}_{other_time.task.name}",
                    )
                    largest_start = self.model.NewIntVar(
                        int(self.span.begins_at.timestamp()),
                        int(self.span.finish_at.timestamp()),
                        f"largest_start_{self.task.name}_{other_time.task.name}",
                    )
                    this_preexisting_event = self.model.NewBoolVar(
                        f"nwi_preexist_{i}_{self.task.name}"
                    )

                    self.model.AddMinEquality(
                        smallest_stop,
                        [self.stop_time, int(other_time.stop_time.timestamp())],
                    )
                    self.model.AddMaxEquality(
                        largest_start,
                        [self.start_time, int(other_time.start_time.timestamp())],
                    )

                    self.model.Add(largest_start - smallest_stop > gap).OnlyEnforceIf(
                        this_preexisting_event
                    )
                    cons.append(this_preexisting_event)
                self.model.AddBoolXOr(cons)
            else:
                smallest_stop = self.model.NewIntVar(
                    int(self.span.begins_at.timestamp()),
                    int(self.span.finish_at.timestamp()),
                    f"smallest_stop_{self.task.name}_{other_time.task.name}",
                )
                largest_start = self.model.NewIntVar(
                    int(self.span.begins_at.timestamp()),
                    int(self.span.finish_at.timestamp()),
                    f"largest_start_{self.task.name}_{other_time.task.name}",
                )
                self.model.AddMinEquality(
                    smallest_stop, [self.stop_time, other_time.stop_time]
                )
                self.model.AddMaxEquality(
                    largest_start, [self.start_time, other_time.start_time]
                )

                self.model.Add(largest_start - smallest_stop > gap)

    def pre_existing_constraint(self, events: Iterable[Tag]) -> None:
        for i, event in enumerate(events):
            start_after = self.start_time > int(
                cast(datetime, event.valid_to).timestamp()
            )
            finish_before = self.stop_time < int(
                cast(datetime, event.valid_from).timestamp()
            )
            event_is_first = self.model.NewBoolVar(f"preexist_{i}_{self.task.name}")

            self.model.Add(start_after).OnlyEnforceIf(event_is_first)
            self.model.Add(finish_before).OnlyEnforceIf(event_is_first.Not())

    def is_pre_existing(self):
        return False


class PreExistingEventTime(EventTime):
    def __init__(self, event: Tag):
        self.events = [event]

    def is_pre_existing(self):
        return True

    def duplicate_event(self, event):
        # Unlike Hermes scheduled events, pre-existing events don't necessarily
        # have unique names. This facilty allows for that.
        self.events.append(event)

    @property
    def start_time(self) -> datetime:
        return min(cast(datetime, e.valid_from) for e in self.events)

    @property
    def stop_time(self) -> datetime:
        return max(cast(datetime, e.valid_to) for e in self.events)

    @property
    def span(self) -> FiniteSpan:  # type: ignore
        return FiniteSpan(begins_at=self.start_time, finish_at=self.stop_time)

    @property
    def interval(self):  # type: ignore
        raise NotImplementedError("Not implemented for pre-existing events!")

    @property
    def task(self):  # type: ignore
        raise NotImplementedError("Not implemented for pre-existing events!")

    @property
    def model(self):  # type: ignore
        raise NotImplementedError("Not implemented for pre-existing events!")
