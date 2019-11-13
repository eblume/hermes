# -*- coding: utf-8 -*-
import datetime as dt
from typing import Iterable, List, TYPE_CHECKING

from .expression import Variable, Expression
from ..span import FiniteSpan
from ..tag import Tag
from ..timespan import TimeSpan

if TYPE_CHECKING:
    # It's not totally clear to me why flake8 needs this, but here we are
    from .model import Model


DEFAULT_EVENT_DURATION = dt.timedelta(minutes=30)


class EventBase:
    """See 'Event' - the EventBase defines the non-DSL components."""

    def __init__(
        self,
        name: str,
        duration: dt.timedelta = DEFAULT_EVENT_DURATION,
        external: bool = False,
        optional: bool = True,
    ):
        self.duration = duration
        self.name = name

        self.start_time = Variable(f"{name}_start")
        self.stop_time = Variable(f"{name}_stop")
        self.is_present = Variable(f"{name}_interval")
        self.interval = Variable(f"{name}_start")

        self._external = external
        self._constraints: List["EventConstraint"] = []

        # TODO - Is there a better way perhaps to introduce the IntervalOverlap constraint
        # that supports polymorphism?
        if not external:
            # TODO - figure out this circular import roadbump
            from .constraint import IntervalOverlap

            self._constraints.append(IntervalOverlap(self))

    @classmethod
    def from_tag(cls, tag: Tag):
        pass

    def combine(self, other: "Event") -> "Event":
        """Returns a new event with combined metadata."""
        pass

    @property
    def external(self) -> bool:
        return self._external

    def bake(self, model: Model, span: FiniteSpan) -> None:
        """Binds all unbound variables belonging to the event to the model, and
        sets all registered constraints."""
        model.make_var(self.start_time, span)
        model.make_var(self.stop_time, span)
        model.make_bool(self.is_present)
        model.make_interval(
            self.interval,
            self.duration,
            self.start_time,
            self.stop_time,
            self.is_present,
        )

        for constraint in self._constraints:
            constraint.apply(model)

    def constrain(self, constraint: "EventConstraint") -> None:
        self._constraints.append(constraint)


class Event(EventBase):
    """The purpose of the Event is twofold:

    1. To store relevant event data necessary to create a Tag at model
    resolution time, and

    2. To provide a comprehensive python interface for constructing
    EventConstraints.

    EventConstraints should own the logic for resolving those constraints given
    a span, a model, and an Event. Essentially, Event's methods should, for the
    most part, define the scheduling syntax, but should NOT define the
    scheduling behavior.

    Every Tag in the final scheduling output can be mapped to a single unique
    Event. Not every Event maps to a tag at the end, though. Several factors
    control whether or not an Event becomes a Tag, but the most useful is
    generally the "is_present" class variable. During resolution, if
    "self.is_present.resolve(model, solution)" then the Event will map back to
    a unique Tag.
    """

    # TODO - check Variable.resolve() syntax in comment above when API has finalized

    def in_(self, span: FiniteSpan) -> "EventConstraint":
        expression = (self.start_time > span.begins_at) and (
            self.stop_time < span.finish_at
        )
        return EventConstraint(self, expression)


class ScheduleItem:
    """By default, a ScheduleItem's purpose is to combine with a span (see
    `events()`) in order to produce _a single_ Event. However, there are many
    situations where a ScheduleItem might produce multiple events, such as when
    a series of events must happen in sequence (like a sub-procedure or even a
    sub-Schedule).

    Indeed, it might be interesting to combine a ScheduleItem and a Schedule
    subclass that allows for automatic subscheduling in a nested behavior of
    sorts.

    By default, Events made by ScheduleItems will be restricted to being within
    the span they were created with.
    """

    # TODO - that idea sounds baller. do that.

    def __init__(self, name: str):
        self.name = name

    def events(self, span: FiniteSpan) -> Iterable[Event]:
        """May be subclassed to allow a ScheduleItem to produce multiple Events in a given window."""
        event = self.to_event()
        event.constrain(event.in_(span))
        yield event

    def to_event(self, **event_kwargs) -> Event:
        """Creates one single event for the given span. May be overriden by subclasses."""
        event_kwargs.setdefault("name", self.name)
        return Event(**event_kwargs)


class Schedule:
    def __init__(self, name: str, context: TimeSpan):
        self._context = context.filter(
            "Hermes" / name
        )  # TODO: filter name normalization? At least test it.
        self._name = name
        self._schedule_items: List[ScheduleItem] = []

    def add_schedule_item(self, item: ScheduleItem) -> None:
        self._schedule_items.append(item)

    def events(self, span: FiniteSpan) -> Iterable[Event]:
        for subspan in self.subspans(span):
            existing_events = {
                t.name for t in self._context.reslice_with_span(subspan).iter_tags()
            }
            for item in self._schedule_items:
                for event in item.events(subspan):
                    if event.name not in existing_events:
                        # TODO - more robust identity checking, beyond the name? Or maybe context filtering fixes that?
                        yield event

    def subspans(self, span: FiniteSpan) -> Iterable[FiniteSpan]:
        """Yields all valid scheduling windows over the given span. Note that
        scheduling windows may exceed the initial span. This method returns all
        scheduling windows that overlap on any portion with the initial span."""
        # TODO - include examples/docs on overriding this.
        yield span


class EventConstraint:
    def __init__(self, event: Event, constraint: Expression, sentinel: Variable = None):
        self._event = event
        self._constraint = constraint
        self._sentinel: Variable = sentinel or self._event.is_present

    def apply(self, model: "Model") -> None:
        """Apply this constraint to the model."""
        expr = self._constraint.bake(model, self._event, self._sentinel)
        sentinel = self._sentinel.bake()
        model._model.Add(expr).OnlyEnforceIf(sentinel)
