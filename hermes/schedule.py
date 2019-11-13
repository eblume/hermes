# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta, timezone
import sys
from typing import (
    cast,
    ClassVar,
    Dict,
    Iterable,
    List,
    NewType,
    Optional,
    Tuple,
    Type,
    TypeVar,
)

from dateutil.tz import tzlocal
from ortools.sat.python import cp_model

from .span import FiniteSpan, Span
from .tag import Tag
from .timespan import BaseTimeSpan, TimeSpan


EventType = TypeVar("EventType", bound="Event")
EventName = NewType("EventName", str)


class Event:
    def __init__(
        self,
        name: EventName,
        start_time: cp_model.IntVar,
        stop_time: cp_model.IntVar,
        is_present: cp_model.IntVar,
        interval: cp_model.IntVar,
        **kwargs,
    ):
        self.name = EventName(name)
        self.start_time = start_time
        self.stop_time = stop_time
        self.is_present = is_present
        self.interval = interval

        # internal flags for things like scheduling constraints
        self._dont_schedule = False
        self._pinned = False
        self._not_within: List[Tuple["Event", timedelta]] = []
        self._by: Optional[time] = None
        self._between: Optional[Tuple[time, time]] = None
        self._after: List["Event"] = []
        self._tag: Optional[Tag] = None

    def not_within(self, model: "ConstraintModel") -> None:
        for other_time, bound in self._not_within:
            gap = int(bound.total_seconds())
            first_stop = model.min_equality(self.stop_time, other_time.stop_time)
            last_start = model.max_equality(self.start_time, other_time.start_time)
            model.add(last_start - first_stop >= gap, sentinel=self.is_present)

    def by(self, model: "ConstraintModel", span: FiniteSpan) -> None:
        if self._by is not None:
            days = []
            for i, day in enumerate(span.dates_between()):
                by_time = int(datetime.combine(day, self._by).timestamp())
                this_day = model.make_var(f"{self.name}_day_{i}_by", boolean=True)
                model.add(self.stop_time < by_time, sentinel=this_day)
                days.append(this_day)
            if days:
                model.add(sum(days) == 1, sentinel=self.is_present)

    def between(self, model: "ConstraintModel", span: Span) -> None:
        if self._between is not None:
            cons = []
            daily_start, daily_stop = self._between
            for i, day in enumerate(span.dates_between()):
                start = int(datetime.combine(day, daily_start).timestamp())
                stop = int(datetime.combine(day, daily_stop).timestamp())
                start_cons = self.start_time > start
                stop_cons = self.stop_time < stop
                this_day = model.make_var(f"{self.name}_day_{i}_between", boolean=True)
                model.add(start_cons, sentinel=this_day)
                model.add(stop_cons, sentinel=this_day)
                cons.append(this_day)
            if cons:
                model.add(sum(cons) == 1, sentinel=self.is_present)

    def after(self, model: "ConstraintModel") -> None:
        for other_event in self._after:
            model.add(self.start_time > other_event.stop_time, sentinel=self.is_present)

    def pin_to_tag(self, model: "ConstraintModel", tag: Tag) -> None:
        if not self._pinned:
            model.add(
                self.start_time == int(cast(datetime, tag.valid_from).timestamp()),
                sentinel=self.is_present,
            )
            # In theory, the interval duration should handle the finish_at portion...
            # model.add(self.stop_time == int(cast(datetime, tag.valid_to).timestamp()))
            self._pinned = True
        # We only allow the first 'pin' - other 'pins' might be an error but might just
        # be weird cruft in the calendar. Either way, we don't do it again.

    def no_pick_first(
        self,
        model: "ConstraintModel",
        no_pick_first: datetime,
        events: Iterable["Event"],
    ) -> None:
        constraints = []
        pick_after = int(no_pick_first.timestamp())
        for event in events:
            if event.name == self.name:
                continue
            other_is_first = model.make_var(
                f"{self.name}_to_{event.name}_npf", boolean=True
            )
            model.add(self.start_time > event.stop_time, sentinel=other_is_first)
            model.add(event.start_time >= pick_after, sentinel=other_is_first)
            constraints.append(other_is_first)
        if constraints:
            model.add(sum(constraints) > 0, sentinel=self.is_present)

    def choose_window(
        self, model: "ConstraintModel", windows: Iterable[FiniteSpan]
    ) -> None:
        constraints = []
        for i, window in enumerate(windows):
            start_cons = self.start_time >= int(
                cast(datetime, window.begins_at).timestamp()
            )
            stop_cons = self.stop_time <= int(
                cast(datetime, window.finish_at).timestamp()
            )
            this_window = model.make_var(f"{self.name}_window_{i}", boolean=True)
            model.add(start_cons, sentinel=this_window)
            model.add(stop_cons, sentinel=this_window)
            constraints.append(this_window)
        if constraints:
            model.add(sum(constraints) == 1, sentinel=self.is_present)

    def score(self, model: "ConstraintModel", **kwargs) -> cp_model.IntVar:
        """Return a base 'score' for this event. Any score can be used, but the
        model will attempt to maximize this value across all events.

        This will be called after the model has made some assignments (although
        the assignments will still be in flux and not yet converged to a solution!),
        so you are encouraged to use those values.

        The result of this function must be a cp_model.IntVar that will be bound
        to the value of the calculated score during the calculation. It's a little
        complex, I know... I'm working on it.
        """
        return self.is_present


class Schedule:
    DEFAULT_DURATION: ClassVar[timedelta] = timedelta(minutes=30)
    DEFINED_SCHEDULES: ClassVar[Dict[str, Type["Schedule"]]] = {}

    def __init__(self, **kwargs):
        if kwargs:
            raise ValueError("Unrecognized kwargs", kwargs)
        self.model = ConstraintModel()
        self.events: Dict["EventName", "Event"] = {}

    def event_windows(self, overall: FiniteSpan) -> Iterable[FiniteSpan]:
        yield overall

    def add_event(
        self,
        name: str,
        duration: Optional[timedelta] = None,
        optional: bool = True,
        between: Optional[Tuple[time, time]] = None,
        after: Optional["Event"] = None,
        by: Optional[time] = None,
        event_class: Type["Event"] = Event,
        **event_kwargs,
    ) -> "Event":
        name = cast(EventName, name)
        if name in self.events:
            raise ValueError(f"Already have a defined event called {name}")

        if duration is None:
            duration = self.DEFAULT_DURATION

        start_time = self.model.make_var(f"{name}_start_time")
        stop_time = self.model.make_var(f"{name}_stop_time")
        is_present = self.model.make_var(f"{name}_is_present", boolean=True)
        if not optional:
            self.model.add(is_present == 1)

        interval = self.model.make_interval(
            start_time, duration, stop_time, is_present, f"{name}_interval"
        )

        event = event_class(
            name=name,
            start_time=start_time,
            stop_time=stop_time,
            is_present=is_present,
            interval=interval,
            **event_kwargs,
        )
        self.events[name] = event

        if between is not None:
            one, two = between
            if one.tzinfo is None:
                one.replace(tzinfo=tzlocal())
            if two.tzinfo is None:
                two.replace(tzinfo=tzlocal())
            event._between = (one, two)

        if by is not None:
            if between is not None:
                raise ValueError("Cannot specify both `by` and `between`")
            if by.tzinfo is None:
                by = by.replace(tzinfo=tzlocal())
            event._by = by

        if after is not None:
            if after.name not in self.events:
                raise ValueError("Somehow, this event doesn't exist yet.")
            event._after.append(after)

        return event

    def not_within(self, event_a: "Event", event_b: "Event", bound: timedelta) -> None:
        event_a._not_within.append((event_b, bound))

    def populate(
        self,
        span: FiniteSpan = None,
        pre_existing_timespans: Optional[Iterable[BaseTimeSpan]] = None,
        no_pick_first: Optional[Dict[str, datetime]] = None,
        **kwargs,
    ) -> TimeSpan:
        assert span is not None
        if no_pick_first is None:
            _no_pick_first: Dict[EventName, datetime] = {}
        else:
            _no_pick_first = {EventName(npf): dt for npf, dt in no_pick_first.items()}

        if all(key in _no_pick_first for key in self.events.keys()):
            raise ValueError(
                "In order to not pick something first there must be other things to pick."
            )

        # Establish pre-existing event boundaries
        if pre_existing_timespans:
            for timespan in pre_existing_timespans:
                for tag in timespan.iter_tags():
                    tag_name = EventName(tag.name)
                    if tag_name in self.events:
                        event = self.events[tag_name]
                    else:
                        event = self.add_event(
                            tag_name, tag.span.duration, optional=False
                        )
                        event._dont_schedule = True
                    event.pin_to_tag(self.model, tag)

        # Constrain the events
        for event in self.events.values():
            self.constrain(event, span, _no_pick_first.get(event.name, None))

        # No interval overlapping (yet)
        self.model.add_no_overlap(self.events.values())

        # Set the objective
        self.objective()

        # Do the magic
        return self.make_timespan(self.model.solve())

    def make_timespan(self, solver: cp_model.CpSolver) -> TimeSpan:
        tags = []

        for event in self.events.values():
            if not event._dont_schedule and solver.Value(event.is_present) == 1:
                event._tag = Tag(
                    name=event.name,
                    # TODO - category
                    valid_from=datetime.fromtimestamp(
                        solver.Value(event.start_time), timezone.utc
                    ),
                    valid_to=datetime.fromtimestamp(
                        solver.Value(event.stop_time), timezone.utc
                    ),
                )
                tags.append(event._tag)
        return TimeSpan(set(tags))

    def constrain(
        self, event: "Event", span: FiniteSpan, no_pick_first: Optional[datetime]
    ) -> None:
        if no_pick_first is not None:
            event.no_pick_first(self.model, no_pick_first, self.events.values())
        event.choose_window(self.model, self.event_windows(span))
        event.not_within(self.model)
        event.by(self.model, span)
        event.between(self.model, span)
        event.after(self.model)

    def objective(self) -> None:
        """Default objective: schedule as many optional events as possible"""
        self.model.maximize(self.events.values())

    # Implicit classmethod
    def __init_subclass__(cls, **kwargs) -> None:
        # This behavior breaks unit tests, and we are comfortable it ONLY
        # breaks unit tests.
        if cls.__name__ in Schedule.DEFINED_SCHEDULES and "pytest" not in sys.modules:
            raise ValueError("A schedule with this class name already exists.")
        Schedule.DEFINED_SCHEDULES[cls.__name__] = cls


class DailySchedule(Schedule):
    """Helper class - this schedule type (and its descendants) only assign
    events during the day."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.day_start = time(hour=7)  # if needed, just overwrite these directly.
        self.day_end = time(hour=22)

    def event_windows(self, overall: FiniteSpan) -> Iterable[FiniteSpan]:
        for day in overall.dates_between():
            start = datetime.combine(
                day, self.day_start, tzinfo=self.day_start.tzinfo or tzlocal()
            )
            stop = datetime.combine(
                day, self.day_end, tzinfo=self.day_end.tzinfo or tzlocal()
            )
            yield FiniteSpan(
                begins_at=max(start, overall.begins_at),
                finish_at=min(stop, overall.finish_at),
            )


class ConstraintModel:
    """Wrapper for cp_model from google or-tools, which is a CP-SAT general purpose solver."""

    def __init__(self):
        self._model = cp_model.CpModel()
        self._variables: Dict[str, cp_model.IntVar] = {}

    def make_var(
        self,
        name: str,
        boolean: bool = False,
        lower_bound: int = 0,
        upper_bound: int = cp_model.INT32_MAX * 32,
    ) -> cp_model.IntVar:
        if boolean:
            variable = self._model.NewBoolVar(name)
        else:
            variable = self._model.NewIntVar(lower_bound, upper_bound, name)
        self._variables[name] = variable
        return variable

    def make_interval(
        self,
        start: cp_model.IntVar,
        duration: timedelta,
        stop: cp_model.IntVar,
        is_present: cp_model.IntVar,
        name: str,
    ) -> cp_model.IntVar:
        variable = self._model.NewOptionalIntervalVar(
            start, int(duration.total_seconds()), stop, is_present, name
        )
        self._variables[name] = variable
        return variable

    def add(
        self,
        expression: cp_model.LinearExpr,
        sentinel: Optional[cp_model.IntVar] = None,
    ) -> None:
        constraint = self._model.Add(expression)
        if sentinel is not None:
            constraint = constraint.OnlyEnforceIf(sentinel)

    def add_abs(
        self,
        target: cp_model.IntVar,
        expression: cp_model.LinearExpr,
        sentinel: Optional[cp_model.IntVar] = None,
    ) -> None:
        constraint = self._model.AddAbsEquality(target, expression)
        if sentinel is not None:
            constraint = constraint.OnlyEnforceIf(sentinel)

    def add_no_overlap(self, events: Iterable["Event"]) -> None:
        self._model.AddNoOverlap(event.interval for event in events)

    def solve(self, timeout: int = 30, with_solution_handler=True) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout
        if with_solution_handler:
            solution_handler = ConstraintModelSolutionHandler(self._variables.values())
            status = solver.SolveWithSolutionCallback(self._model, solution_handler)
        else:
            status = solver.Solve(self._model)

        if status not in {cp_model.FEASIBLE, cp_model.OPTIMAL}:
            # TODO - custom error reporting
            raise ValueError(
                f"Non-feasible scheduling problem status: {solver.StatusName(status)}"
            )
        return solver

    def _tabulate(self, events: Iterable["Event"]) -> Iterable[cp_model.IntVar]:
        for event in events:
            # TODO - what if an event was named ConstraintModel
            # (sentinel value implication)
            score = self.make_var(f"ConstraintModel_{event.name}_final_score")
            self.add(score == event.score(model=self), event.is_present)
            self.add(score == 0, event.is_present.Not())
            yield score

    def minimize(self, events: Iterable["Event"]) -> None:
        self._model.Minimize(sum(self._tabulate(events)))

    def maximize(self, events: Iterable["Event"]) -> None:
        self._model.Maximize(sum(self._tabulate(events)))

    def min_equality(
        self, first: cp_model.IntVar, second: cp_model.IntVar
    ) -> cp_model.IntVar:
        variable = self.make_var(f"ConstraintModel_min_{first}_{second})")
        self._model.AddMinEquality(variable, [first, second])
        return variable

    def max_equality(
        self, first: cp_model.IntVar, second: cp_model.IntVar
    ) -> cp_model.IntVar:
        variable = self.make_var(f"ConstraintModel_max_{first}_{second})")
        self._model.AddMaxEquality(variable, [first, second])
        return variable


class ConstraintModelSolutionHandler(cp_model.CpSolverSolutionCallback):
    """Helper class for debugging purposes"""

    def __init__(self, variables: Iterable[cp_model.IntVar]) -> None:
        self.variables = variables
        super().__init__()
        self.solution_count = 0
        self.updates: List[Dict] = []

    def on_solution_callback(self):
        update = {
            "solution_count": self.solution_count,
            "objective_value": self.ObjectiveValue(),
            "best_objective_bound": self.BestObjectiveBound(),
            "num_booleans": self.NumBooleans(),
            "num_conflicts": self.NumConflicts(),
            "num_branches": self.NumBranches(),
            "wall_time": self.WallTime(),
            "user_time": self.UserTime(),
            "variables": {
                variable: self.Value(variable) for variable in self.variables
            },
        }
        self.updates.append(update)
        self.solution_count += 1
        from pprint import pprint

        pprint(update)
        # pprint({variable: self.Value(variable)
        #         for variable in self.variables
        #         if 'chore' in variable.Name()
        #         })


class EventScoredForSeconds(Event):
    """An example utility Event subclass that scores events by the number of
    seconds scheduled rather than by a simple 1 or 0 for present/not-present.
    """

    def score(self, model: ConstraintModel, **kwargs) -> cp_model.IntVar:
        score = model.make_var(f"{self.name}_event_score_by_seconds")
        model.add(score == self.stop_time - self.start_time, self.is_present)
        return score


class ScheduleScoredForSeconds(Schedule):
    """An example utility Schedule subclass that uses EventScoredForSeconds-type
    events. See EventScoredForSeconds for details.
    """

    def add_event(self, *args, **kwargs) -> "Event":
        kwargs.setdefault("event_class", EventScoredForSeconds)
        return super().add_event(*args, **kwargs)
