# -*- coding: utf-8 -*-
import datetime as dt
from typing import Iterable, List, TYPE_CHECKING

from .expression import Variable, Expression, Constant
from ..span import FiniteSpan
from ..tag import Tag  # , Category
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

        # TODO - Is there a better way perhaps to introduce the IntervalOverlap
        # constraint that supports polymorphism?
        if not external:
            # TODO - figure out this circular import roadbump
            from .constraint import IntervalOverlap

            self._constraints.append(IntervalOverlap(self))

    @classmethod
    def from_tag(cls, tag: Tag):
        pass  # TODO`

    def combine(self, other: "Event") -> "Event":
        """Returns a new event with combined metadata."""
        pass  # TODO

    @property
    def external(self) -> bool:
        return self._external

    def bake(self, model: "Model", span: FiniteSpan) -> None:
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
        begins_at = Constant(
            f"{self.name}_in_span_left", int(span.begins_at.timestamp())
        )
        finish_at = Constant(
            f"{self.name}_in_span_right", int(span.finish_at.timestamp())
        )
        expression = (self.start_time > begins_at) and (self.stop_time < finish_at)
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
    """A Schedule is a contextual grouping of ScheduleItems that can be used to
    create an applicable set of properly constrained Events, which can then be
    converted in to Tags via a Solution (typically provided by a Model).

    Schedules turn ScheduleItems in to (0+) Events. Solutions turn Events in
    to (0 or 1) Tags.

    Other than assigned ScheduleItems, Schedules are only aware of one other
    thing: a `context` timespan. The tags of this timespan are available for
    use in contextual decisionmaking when generating Events.

    All schedules include a notion of 'subspans' aka. 'scheduling windows',
    which are an abstract notion of "When should I schedule things, if I was
    told to schedule things during such a span?". An example alternative logic
    could be a Workday Scheduler that retricts scheduling windows to regular
    'work hours'.
    """

    def __init__(self, name: str, context: TimeSpan = None):
        if context is None:
            context = TimeSpan(set())

        # category = Category("Hermes", None) / name
        self._context = context.filter(name)
        self._name = name
        self._schedule_items: List[ScheduleItem] = []

    def add_schedule_items(self, *items: ScheduleItem) -> None:
        for item in items:
            self._schedule_items.append(item)

    def events(self, span: FiniteSpan) -> Iterable[Event]:
        for subspan in self.subspans(span):
            existing_tag_names = {
                t.name for t in self._context.slice_with_span(subspan).iter_tags()
            }
            for item in self._schedule_items:
                for event in item.events(subspan):
                    if event.name not in existing_tag_names:
                        # TODO - additional consistency beyond just name checking?
                        yield event

    def subspans(self, span: FiniteSpan) -> Iterable[FiniteSpan]:
        """Yields all valid scheduling windows over the given span"""
        # TODO - include examples/docs on overriding this.
        yield span


class EventConstraint:
    def __init__(
        self, event: EventBase, constraint: Expression, sentinel: Variable = None
    ):
        self._event = event
        self._constraint = constraint
        self._sentinel: Variable = sentinel or self._event.is_present

    def apply(self, model: "Model") -> None:
        """Apply this constraint to the model."""
        expr = self._constraint.apply(model, self._event, self._sentinel)
        sentinel = self._sentinel.apply()
        model._model.Add(expr).OnlyEnforceIf(sentinel)
