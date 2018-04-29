"""Hermes, the Time Accountant"""

__author__ = """Erich Blume"""
__email__ = "blume.erich@gmail.com"
__version__ = "0.1.1a"

import datetime as dt
import functools
from operator import attrgetter
from typing import Iterable, Optional, Set, Union, cast, overload

import attr


class Spannable:

    @property
    def span(self) -> "Span":
        raise NotImplementedError("Subclasses must define this interface")

    def __contains__(self, other: "Spannable") -> bool:
        """`other` overlaps at least in part with this object"""
        selfspan = self.span
        otherspan = other.span
        if otherspan.begins_at < selfspan.begins_at:
            return otherspan.finish_at >= selfspan.begins_at

        elif otherspan.finish_at > selfspan.finish_at:
            return otherspan.begins_at <= selfspan.finish_at

        else:
            return True


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Tag(Spannable):
    name: str
    category: Optional["Category"]
    valid_from: dt.datetime
    valid_to: dt.datetime

    @property
    def span(self):
        return Span(self.valid_from, self.valid_to)


@functools.total_ordering
@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Span(Spannable):
    begins_at: dt.datetime
    finish_at: dt.datetime

    @property
    def span(self) -> "Span":
        return self  # It's safe to just return self, due to immutability

    @property
    def duration(self) -> dt.timedelta:
        return self.finish_at - self.begins_at

    def __lt__(self, other: "Span") -> bool:
        return self.duration < other.duration

    def subspans(self, duration: dt.timedelta) -> Iterable["Span"]:
        selfspan = self.span
        start = selfspan.begins_at
        while start < selfspan.finish_at:
            finish = min(start + duration, selfspan.finish_at)
            yield Span(start, finish)

            start = finish


class BaseTimeAccount(Spannable):

    @property
    def category_pool(self):
        raise NotImplementedError("Subclasses must define this interface.")

    def iter_tags(self) -> Iterable["Tag"]:
        raise NotImplementedError("Subclasses must define this interface.")

    def reslice(
        self, begins_at: dt.datetime, finish_at: dt.datetime
    ) -> "BaseTimeAccount":
        raise NotImplementedError("Subclasses must define this interface.")

    def __len__(self):
        return len(list(self.iter_tags()))

    # The next two overloads let mypy be comfortable with the abuse we're
    # giving to python's slice syntax. It's clunky as hell, but that's the
    # price you pay when you muck around with things like indexing.

    @overload
    def __getitem__(self, key: int) -> "BaseTimeAccount":
        pass

    @overload  # noqa: F811
    def __getitem__(self, key: slice) -> "BaseTimeAccount":
        pass

    def __getitem__(  # noqa: F811
        self, key: Union[Optional[int], slice]
    ) -> "BaseTimeAccount":
        # Do a little type casting safety dance. Let's find a better way.
        type_error = key is None
        type_error |= not isinstance(key, slice)
        if type_error:
            raise TypeError("BaseTimeAccount objects must be sliced with datetime")

        key = cast(slice, key)

        # And a safety dance for our friends slice.start and slice.stop
        type_error |= key.start is not None and not isinstance(key.start, dt.datetime)
        type_error |= key.stop is not None and not isinstance(key.stop, dt.datetime)
        if type_error:
            raise TypeError("BaseTimeAccount objects must be sliced with datetime")

        start = cast(dt.datetime, key.start)
        stop = cast(dt.datetime, key.stop)

        return self.reslice(start, stop)

    def slice_with_span(self, span: Span) -> "BaseTimeAccount":
        return self.reslice(span.begins_at, span.finish_at)

    def subspans(self, duration: dt.timedelta) -> Iterable["BaseTimeAccount"]:
        for subspan in self.span.subspans(duration):
            yield self.slice_with_span(subspan)


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class TimeAccount(BaseTimeAccount):
    tags: Set[Tag]

    @property
    def category_pool(self):
        return CategoryPool(categories={tag.category for tag in self.iter_tags()})

    def iter_tags(self) -> Iterable["Tag"]:
        yield from self.tags

    def reslice(
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


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Category:
    name: str
    parent: Optional["Category"]


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class CategoryPool:
    """Pool of cached categories, searchable by name

    >>> pool = account.category_pool
    >>> sorted(cat.name for cat in pool.categories)
    ['A', 'B', 'C']
    """
    categories: Set[Category]
