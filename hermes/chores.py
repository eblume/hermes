# -*- coding: utf-8 -*-
import datetime as dt

from .schedule import Schedule
from .span import FiniteSpan
from .stochastics import Frequency
from .tag import Tag
from .timespan import TimeSpan


class Chore:
    def __init__(
        self,
        name: str,
        frequency: Frequency = None,
        duration: dt.timedelta = dt.timedelta(hours=1),
    ):
        self._name = name
        self._duration = duration
        if frequency is None:
            self._frequency = Frequency(mean=dt.timedelta(days=7))
        else:
            self._frequency = frequency

    def tension(self, elapsed: dt.timedelta) -> float:
        return self._frequency.tension(elapsed)


class ChoreStore:
    pass


class ChoreSchedule(Schedule):
    """Helper class - this schedule type (and its descendants) include a
    ChoreList, and can have chore times when being scheduled."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chores = []

    def add_chore(self, chore: Chore) -> None:
        return self._chores.append(chore)

    def add_chore_slots(
        self, limit: int, duration: dt.timedelta = dt.timedelta(hours=1)
    ):
        """Convenience method to automatically generate up to the specified
        number of chore slots per generated schedule. Will attempt to schedule
        as many as is possible."""
        self._chore_slot_limit = limit
        self._chore_slot_duration = duration

    def populate(self, span: FiniteSpan, *args, **kwargs) -> TimeSpan:
        chore_events = [
            self.add_event(
                name=f"Chore slot {slot}",
                duration=self._chore_slot_duration,
                optional=True,
            )
            for slot in range(min(self._chore_slot_limit, len(self._chores)))
        ]

        schedule = super().populate(span, *args, **kwargs)

        chore_events_by_tag = {
            event._tag: event for event in chore_events if event._tag is not None
        }

        newtags = []
        for tag in schedule.iter_tags():
            event = chore_events_by_tag.get(tag, None)
            if event is not None and event in chore_events:
                chore = self.pick_chore(tag, span)
                tag = self.update_tag_for_chore(tag, chore)
            newtags.append(tag)

        return TimeSpan(set(newtags))

    def pick_chore(self, tag: Tag, span: FiniteSpan) -> Chore:
        # TODO - pick the 'timedelta' some better way than this, like via
        # a persistant chore store. Basically, replace this entirely.
        assert tag.valid_from is not None
        elapsed = tag.valid_from - span.begins_at
        chores = sorted(self._chores, key=lambda c: c.tension(elapsed))
        self._chores = chores[1:]
        return chores[0]

    def update_tag_for_chore(self, tag: Tag, chore: Chore) -> Tag:
        # TODO duration change? Unclear
        # TODO mark chore as 'done'? ehhh
        return Tag(
            name=chore._name,
            valid_from=tag.valid_from,
            valid_to=tag.valid_to,
            category=tag.category,
        )
