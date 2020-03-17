# -*- coding: utf-8 -*-
from .expression import Expression, Action
from .schedule import EventConstraint, EventBase


class IntervalOverlap(EventConstraint):
    """By default, prevents this event from overlapping with any other event
    that has been similarly constrained."""

    def __init__(self, event: EventBase):
        super().__init__(event, Expression(Action.OVERLAP, event))

    def __repr__(self) -> str:
        return f"IntervalOverlap('{self._event.name}')"
