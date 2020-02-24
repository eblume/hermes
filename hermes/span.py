# -*- coding: utf-8 -*-
import abc
import datetime as dt
from typing import cast, Iterable, Optional

import attr
from dateutil.tz import tzlocal


class Spannable:
    @property
    @abc.abstractmethod
    def span(self) -> "Span":
        raise NotImplementedError("Subclasses must define this interface")

    def __contains__(self, other: object) -> bool:
        """`other` overlaps at least in part with this object"""
        if not isinstance(other, Spannable):
            return False

        self_begins = self.span.begins_at or dt.datetime.min.replace(
            tzinfo=dt.timezone.utc
        )
        other_begins = other.span.begins_at or dt.datetime.min.replace(
            tzinfo=dt.timezone.utc
        )
        self_finish = self.span.finish_at or dt.datetime.max.replace(
            tzinfo=dt.timezone.utc
        )
        other_finish = other.span.finish_at or dt.datetime.max.replace(
            tzinfo=dt.timezone.utc
        )

        if other_begins < self_begins:
            return other_finish >= self_begins

        elif other_finish > self_finish:
            return other_begins <= self_finish

        else:
            return True

    def during(self, other: "Spannable") -> bool:
        """This span is entirely within `other`, IE, is a proper subset."""
        self_begins = self.span.begins_at or dt.datetime.min.replace(
            tzinfo=dt.timezone.utc
        )
        other_begins = other.span.begins_at or dt.datetime.min.replace(
            tzinfo=dt.timezone.utc
        )
        self_finish = self.span.finish_at or dt.datetime.max.replace(
            tzinfo=dt.timezone.utc
        )
        other_finish = other.span.finish_at or dt.datetime.max.replace(
            tzinfo=dt.timezone.utc
        )

        return other_begins <= self_begins and other_finish >= self_finish


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Span(Spannable):
    """A time span, from one time to another.

    `begins_at` and `finish_at` may be set to None to signal a timespan of
    infinite duration. The Span itself still uses `None` to represent this
    case, but calling code may choose to use `dt.datetime.min`/`max`, or
    `dt.timedelta.max`, as needed. They may be set to the _same_ time to
    represent a single instant in time (this is also not handled specially).
    """

    begins_at: Optional[dt.datetime]
    finish_at: Optional[dt.datetime]

    @property
    def span(self) -> "Span":
        return self  # It's safe to just return self, due to immutability

    @property
    def duration(self) -> dt.timedelta:
        if self.finish_at is None or self.begins_at is None:
            return dt.timedelta.max

        return self.finish_at - self.begins_at

    def subspans(self, duration: dt.timedelta) -> Iterable["Span"]:
        start = self.span.begins_at or dt.datetime.min
        final_finish = self.span.finish_at or dt.datetime.max
        while start < final_finish:
            finish = min(start + duration, final_finish)
            yield Span(start, finish)

            start = finish

    def is_finite(self) -> bool:
        return self.begins_at is not None and self.finish_at is not None

    @classmethod
    def from_date(cls, date: dt.date, tzinfo: Optional[dt.tzinfo] = None) -> "Span":
        """Assumes the local timezone, as understood by the OS, unless otherwise specified."""
        start = dt.datetime.combine(
            date,
            dt.time(hour=0, minute=0, second=0, microsecond=0),
            tzinfo=tzinfo or tzlocal(),
        )
        stop = start + dt.timedelta(days=1, microseconds=-1)
        return cls(begins_at=start, finish_at=stop)

    def dates_between(self) -> Iterable[dt.date]:
        if not self.is_finite():
            raise ValueError("Span must be concrete and finite")
        begins_at: dt.datetime = cast(dt.datetime, self.begins_at)
        finish_at: dt.datetime = cast(dt.datetime, self.finish_at)

        if begins_at.tzinfo != finish_at.tzinfo:
            finish_at = finish_at.astimezone(tz=begins_at.tzinfo)

        day: dt.date = begins_at.date()
        while (
            dt.datetime.combine(
                day,
                dt.time(hour=0, minute=0, second=0, microsecond=0),
                tzinfo=begins_at.tzinfo,
            )
            < finish_at
        ):
            yield day
            day += dt.timedelta(days=1)

    def before(self, other: "Span") -> bool:
        if self.begins_at is None:
            return other.begins_at is not None
        if other.begins_at is None:
            return self.begins_at is not None
        return self.begins_at < other.begins_at

    def after(self, other: "Span") -> bool:
        if self.finish_at is None:
            return other.finish_at is not None
        if other.finish_at is None:
            return self.finish_at is not None
        return self.finish_at > other.finish_at


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class FiniteSpan(Span):
    """A span that is definitely finite."""

    begins_at: dt.datetime
    finish_at: dt.datetime

    def is_finite(self) -> bool:
        return True
