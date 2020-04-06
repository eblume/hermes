# -*- coding: utf-8 -*-
from .expression import Expression, Action
from .schedule import EventConstraint, Event


class IntervalOverlap(EventConstraint):
    """By default, prevents this event from overlapping with any other event
    that has been similarly constrained."""

    def __init__(self, event: Event):
        super().__init__(
            event, Expression(Action.OVERLAP, event.start_time, event.stop_time)
        )

    def __repr__(self) -> str:
        return f"IntervalOverlap('{self._event.name}')"
