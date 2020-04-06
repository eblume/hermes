# -*- coding: utf-8 -*-
from .expression import Expression, Action
from .schedule import EventConstraint, Event


class IntervalOverlap(EventConstraint):
    """By default, prevents this event from overlapping with any other event
    that has been similarly constrained."""

    # TODO - This is currently UNUSED and DOES NOT WORK. I'm leaving it briefly
    # as I refactor the scheduler system, as an example for when I build other,
    # real constraints. Instead, non-overlapping of events is built in to the
    # make_interval variable type.

    def __init__(self, event: Event):
        super().__init__(
            event, Expression(Action.IDENTITY, event.start_time, event.stop_time)
        )

    def __repr__(self) -> str:
        return f"IntervalOverlap('{self._event.name}')"
