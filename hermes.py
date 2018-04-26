"""Hermes, the Time Accountant"""

__author__ = """Erich Blume"""
__email__ = "blume.erich@gmail.com"
__version__ = "0.1.1a"

import datetime as dt
import functools
from operator import attrgetter
from typing import Iterable, Set

import attr


class Spannable:

    def span(self) -> "Span":
        raise NotImplementedError("Subclasses must define this interface")

    def __contains__(self, other: "Spannable") -> bool:
        """`other` overlaps at least in part with this object"""
        selfspan = self.span()
        otherspan = other.span()
        try:
            if otherspan.begins_at < selfspan.begins_at:
                return otherspan.finish_at >= selfspan.begins_at

            elif otherspan.finish_at > selfspan.finish_at:
                return otherspan.begins_at <= selfspan.finish_at

            else:
                return True

        except:
            import pdb

            pdb.set_trace()


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Tag(Spannable):
    name: str
    valid_from: dt.datetime
    valid_to: dt.datetime

    def span(self):
        return Span(self.valid_from, self.valid_to)


@functools.total_ordering
@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Span(Spannable):
    begins_at: dt.datetime
    finish_at: dt.datetime

    def span(self) -> "Span":
        return self  # It's safe to just return self, due to immutability

    @property
    def duration(self) -> dt.timedelta:
        return self.finish_at - self.begins_at

    def __lt__(self, other: "Span") -> bool:
        return self.duration < other.duration

    def subspans(self, duration: dt.timedelta) -> Iterable["Span"]:
        selfspan = self.span()
        start = selfspan.begins_at
        while start < selfspan.finish_at:
            finish = min(start + duration, selfspan.finish_at)
            yield Span(start, finish)

            start = finish


class BaseTimeAccount(Spannable):

    def iter_tags(self) -> Iterable["Tag"]:
        raise NotImplementedError("Subclasses must define this interface.")

    def slice(
        self, begins_at: dt.datetime, finish_at: dt.datetime
    ) -> "BaseTimeAccount":
        raise NotImplementedError("Subclasses must define this interface.")

    def __len__(self):
        return len(list(self.iter_tags()))

    def __getitem__(self, key: slice) -> "BaseTimeAccount":
        return self.slice(key.start, key.stop)

    def slice_with_span(self, span: Span) -> "BaseTimeAccount":
        return self.slice(span.begins_at, span.finish_at)

    def subspans(self, duration: dt.timedelta) -> Iterable["BaseTimeAccount"]:
        yield from map(self.slice_with_span, self.span.subspans(duration))


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class TimeAccount(BaseTimeAccount):
    tags: Set[Tag]

    def iter_tags(self) -> Iterable["Tag"]:
        yield from self.tags

    def slice(
        self, begins_at: dt.datetime, finish_at: dt.datetime
    ) -> "BaseTimeAccount":
        selfspan = self.span
        newspan = Span(
            begins_at if begins_at is not None else selfspan.begins_at,
            finish_at if finish_at is not None else selfspan.finish_at,
        )
        tags = {t for t in self.tags if t in newspan}
        return TimeAccount(tags=tags)

    @property
    def span(self) -> "Span":
        tags = sorted(self.tags, key=attrgetter("valid_from"))
        oldest = min(tags, key=attrgetter("valid_from"))
        most_recent = max(tags, key=attrgetter("valid_to"))
        return Span(oldest.valid_from, most_recent.valid_to)

    @classmethod
    def combine(cls, *others: "BaseTimeAccount") -> "TimeAccount":
        tags = {t for other in others for t in other.iter_tags()}
        return TimeAccount(tags)
