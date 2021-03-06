# -*- coding: utf-8 -*-
import datetime as dt
from typing import Iterable, List, Any

from .expression import Variable, Expression
from ..span import FiniteSpan
from ..tag import Tag  # , Category
from ..timespan import TimeSpan


DEFAULT_EVENT_DURATION = dt.timedelta(minutes=30)


class Event:
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

    def __init__(
        self,
        name: str,
        duration: dt.timedelta = DEFAULT_EVENT_DURATION,
        external: bool = False,
        optional: bool = True,
    ):
        self.duration = duration
        self.name = name
        self.constraints: List["EventConstraint"] = []

        self.start_time = Variable(f"{name}_start")
        self.stop_time = Variable(f"{name}_stop")
        self.is_present = Variable(f"{name}_is_present")
        self.interval = Variable(f"{name}_interval")

        self._external = external

    @classmethod
    def from_tag(cls, tag: Tag):
        pass  # TODO`

    def combine(self, other: "Event") -> "Event":
        """Returns a new event with combined metadata."""
        pass  # TODO

    @property
    def external(self) -> bool:
        return self._external

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Event):
            return False
        return all(
            (
                self.name == other.name,
                self.start_time == other.start_time,
                self.stop_time == other.stop_time,
                self.is_present == other.is_present,
                self.interval == other.interval,
            )
        )

    def __repr__(self) -> str:
        return f"Event<'{self.name}', constraints: {len(self.constraints)}>"

    def in_(self, span: FiniteSpan) -> "EventConstraint":
        starts_after = self.start_time.after(span.begins_at)
        ends_before = self.stop_time.before(span.finish_at)
        return EventConstraint(self, starts_after.and_(ends_before))


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
        event.constraints.append(event.in_(span))
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
    def __init__(self, event: Event, constraint: Expression, sentinel: Variable = None):
        self._event = event
        self._constraint = constraint
        self._sentinel: Variable = sentinel or self._event.is_present

    @property
    def expression(self) -> Expression:
        return self._constraint

    @property
    def sentinel(self) -> Variable:
        return self._sentinel

    def __repr__(self) -> str:
        return f"EventConstraint<'{self._event.name}', {self._constraint}, {self._sentinel}>"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, EventConstraint):
            return False
        # Why can't we just compare self._constraint == other._constraint?
        # Because of the DSL, `self._constraint == other._constraint` returns
        # a new expression, not a boolean. I may want to rethink this.
        return all(
            (
                self._event == other._event,
                self._sentinel.name == other._sentinel.name,
                self._constraint._action == other._constraint._action,
                self._constraint._args == other._constraint._args,
            )
        )
