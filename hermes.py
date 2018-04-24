"""Hermes, the Time Accountant"""

__author__ = """Erich Blume"""
__email__ = "blume.erich@gmail.com"
__version__ = "0.1.1a"

import datetime as dt
from operator import attrgetter
from typing import Set

import attr


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Tag:
    name: str
    valid_from: dt.datetime
    valid_to: dt.datetime


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Span:
    begins_at: dt.datetime
    finish_at: dt.datetime

    def __contains__(self, tag: Tag) -> bool:
        return bool(
            (self.begins_at is None or tag.valid_to >= self.begins_at)
            and (self.finish_at is None or tag.valid_from <= self.finish_at)
        )


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class TimeAccount:
    tags: Set[Tag]

    def slice(self, begins_at: dt.datetime, finish_at: dt.datetime) -> "TimeAccount":
        newspan = Span(begins_at, finish_at)
        return TimeAccount({t for t in self.tags if t in newspan})

    @property
    def span(self) -> Span:
        tags = sorted(self.tags, key=attrgetter("valid_from"))
        oldest = min(tags, key=attrgetter("valid_from"))
        most_recent = max(tags, key=attrgetter("valid_to"))
        return Span(oldest.valid_from, most_recent.valid_to)

    def __len__(self):
        return len(self.tags)

    def __getitem__(self, key: slice) -> "TimeAccount":
        return self.slice(key.start, key.stop)
