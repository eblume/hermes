# -*- coding: utf-8 -*-
import datetime as dt
from typing import Optional, Iterable

from ortools.sat.python import cp_model
import pytz

from .expression import Variable
from .schedule import Event, Schedule
from ..tag import Tag
from ..span import FiniteSpan
from ..timespan import SqliteTimeSpan, BaseTimeSpan


class Solution:
    def __init__(self, solver: cp_model.CpSolver):
        self._solver = solver

    def resolve(self, event: Event) -> Optional[Tag]:
        is_present = self._solver.Value(event.is_present._var)
        if not is_present:
            return None

        start = dt.datetime.fromtimestamp(
            self._solver.Value(event.start_time._var), pytz.utc
        )
        stop = dt.datetime.fromtimestamp(
            self._solver.Value(event.stop_time._var), pytz.utc
        )
        # TODO - category?
        return Tag(name=event.name, valid_from=start, valid_to=stop)


class Model:
    def __init__(self):
        self._events: dict[str, Event] = {}

    def schedule(
        self,
        span: FiniteSpan,
        *schedules: Schedule,
        context: Iterable[BaseTimeSpan] = None,
        timeout: dt.timedelta = dt.timedelta(seconds=30),
    ) -> SqliteTimeSpan:
        """Return a timespan filled with new events by these schedules.

        The timespan will only have events that fit within the
        input `span`. Multiple schedules can be scheduled at once,
        by default the result depends on making the schedule as full as
        possible. More complex behaviors are possible.

        The `context`, if provided, contains events that may or may not
        correspond to events that might be scheduled. If they do correspond,
        the schedules can make decisions accordingly, for instance by assuming
        that the previously scheduled event will 'count towards' its scheduling
        needs. See the Schedule class for more info.

        This function can take a long time to return, so consider setting an
        appropriate `timeout` for your use case. This timeout is enforced
        by the constraint solver, which will attempt to return the best possible
        answer it has found within the timeout period. (It might go a bit over
        that timeout if it's about to find a new local solution.)
        """
        # TODO: async/await eventloop etc. version? futures/multip?

        # Register all previous existing events from their tag info.
        for pre_existing_timespan in context or []:
            for tag in pre_existing_timespan.iter_tags():
                self.add_event(Event.from_tag(tag))

        # Register all provided schedules and load their constraints.
        for schedule in schedules:
            self.add_schedule(schedule, span)

        # Build ("bake") the model, binding all expressions/variables to the model.
        model = self.bake(span)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = int(timeout.total_seconds())

        status = solver.Solve(model)  # TODO - CpSolverSolutionCallback
        if status not in {cp_model.FEASIBLE, cp_model.OPTIMAL}:
            raise ValueError(
                f"Non-feasible scheduling problem status: {solver.StatusName(status)}"
            )
        solution = Solution(solver)

        new_timespan = SqliteTimeSpan()
        for event in self._events.values():
            if not event.external:
                # External events by definition already are scheduled
                new_tag = self.event_to_tag(event, solution)
                if new_tag is not None:
                    new_timespan.insert_tag(new_tag)
        return new_timespan

    def event_to_tag(self, event: Event, solution: Solution) -> Optional[Tag]:
        """This is provided to allow subclasses to implement different tagging strategies, without having to alter scheduling."""
        return solution.resolve(event)

    def add_event(self, event: Event) -> Event:
        """Returns either the given event (after registering it), or a new
        event that combines existing event info."""
        if event.name not in self._events:
            self._events[event.name] = event
        else:
            if event != self._events[event.name]:
                raise KeyError("An event with this name already exists.")
            # TODO - This is totally recoverable. We need to combine constraints,
            # ensure there is only one agreed-upon set of variables, etc. Just need
            # to decide how smart to be. So for now, just error.
        return event

    def add_schedule(self, schedule: Schedule, span: FiniteSpan) -> None:
        """Register this schedule on this model"""
        for schedule_item in schedule._schedule_items:
            for event in schedule_item.events(span):
                self.add_event(event)

    def bake(self, span: FiniteSpan) -> cp_model.CpModel:
        model = cp_model.CpModel()
        # First, register each variable.
        for event in self._events.values():
            self.make_var(model, event.start_time, span)
            self.make_var(model, event.stop_time, span)
            self.make_bool(model, event.is_present)
            self.make_interval(
                model,
                event.interval,
                event.duration,
                event.start_time,
                event.stop_time,
                event.is_present,
            )

        # Then, for each event, register its constraints.
        for event in self._events.values():
            for constraint in event.constraints:
                model.Add(constraint.expression.apply()).OnlyEnforceIf(
                    constraint.sentinel.apply()
                )

        # One model, fresh from the oven. Ready to be run.
        return model

    def make_var(
        self, model: cp_model.CpModel, var: "Variable", span: FiniteSpan
    ) -> None:
        lb = int(span.begins_at.timestamp())
        ub = int(span.finish_at.timestamp())
        variable = model.NewIntVar(lb, ub, var.name)
        var.bind(variable)

    def make_bool(self, model: cp_model.CpModel, var: "Variable") -> None:
        variable = model.NewBoolVar(var.name)
        var.bind(variable)

    def make_interval(
        self,
        model: cp_model.CpModel,
        var: "Variable",
        duration: dt.timedelta,
        start: Variable,
        stop: Variable,
        is_present: Variable,
    ) -> None:
        variable = model.NewOptionalIntervalVar(
            start=start._var,
            size=int(duration.total_seconds()),
            end=stop._var,
            is_present=is_present._var,
            name=var.name,
        )
        var.bind(variable)
