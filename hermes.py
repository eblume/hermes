"""Hermes, the Time Accountant"""

__author__ = """Erich Blume"""
__email__ = "blume.erich@gmail.com"
__version__ = "0.1.1a"

import datetime as dt
from functools import partial
from operator import attrgetter
from typing import Iterable, List, Set, Union

import attr


immutable = partial(attr.s, slots=True, frozen=True, auto_attribs=True, hash=True)


@immutable
class Tag:
    """A tag on the timeline. Could be an event, could be an annotation."""
    name: str
    valid_from: dt.datetime
    valid_to: dt.datetime


class BaseTimeAccount:
    """Abstract base interface for TimeAccount classes.
    """

    # TODO - think about how new subclasses might register for an opportunity
    # to be the default underlying model, and not TimeAccount. For now, one
    # can just override these methods to use a new default model, and that's
    # not likely to change soon, but I want to call that out now before this
    # becomes TOO tightly coupled to TimeAccount.

    def __init__(self):
        raise _subclass_iface_error()

    @property
    def tags(self) -> Iterable[Tag]:
        raise _subclass_iface_error()

    @property
    def span(self) -> "Span":
        oldest = min(self.tags, key=attrgetter("valid_from"))
        most_recent = max(self.tags, key=attrgetter("valid_to"))
        return Span(oldest.valid_from, most_recent.valid_to)

    def __len__(self) -> int:
        """Return the number of tags stored in this BaseTimeAccount.

        Subclasses will probably want to redefine this to be more efficient.
        """
        return len(self.tags)

    def __eq__(self, other: "TimeAccount") -> bool:
        return set(self.tags) == set(other.tags)

    def __getitem__(self, key: slice) -> Union["TimeAccount", Iterable["TimeAccount"]]:
        if not isinstance(key, slice):
            raise TypeError(
                "TimeAccount objects must be sliced with `datetime.datetime`"
            )

        slice_from = key.start or self.span.begins_at
        slice_to = key.stop or self.span.finish_at
        slice_span = Span(slice_from, slice_to)

        if key.step is not None:
            # TODO - do we want to just not support step?
            if not isinstance(key.step, dt.timedelta):
                raise TypeError(
                    "TimeAccount 'step' slices must use `datetime.timedelta`"
                )

            accounts = []
            for subspan in slice_span.subspans(key.step):
                new_account = TimeAccount([t for t in self.tags if t in subspan])
                accounts.append(new_account)
            return accounts

        else:
            return TimeAccount(t for t in self.tags if t in slice_span)


@attr.s(
    slots=True,
    auto_attribs=True,
    frozen=True,
    cmp=False,  # Sorry attribs, we've got _nasty_ plans for equality, etc.
)  # note that this is basically @immutable  -- TODO builder pattern?
class TimeAccount(BaseTimeAccount):
    """Reference TimeAccount implementation that is backed with attrs.

    All subclasses of this TimeAccount will be forced to adopt,  and support
    the data implementation of TimeAccount. If you would like to not use attrs,
    you'll need to subclass BaseTimeAccount.
    """

    list_tags: List[Tag]

    @property
    def tags(self) -> Iterable[Tag]:
        yield from self.list_tags

    def __len__(self) -> int:
        return len(self.list_tags)


class CombinedTimeAccount(BaseTimeAccount):
    accounts: List[TimeAccount]

    def __init__(self, *accounts):
        self.accounts = list(accounts)

    @property
    def tags(self) -> Set[Tag]:
        return set(tag for account in self.accounts for tag in account.tags)

    def __len__(self) -> int:
        return len(self.tags)


@immutable
class Span:
    """Helper class for timespans in TimeAccount objects."""
    begins_at: dt.datetime
    finish_at: dt.datetime

    def __contains__(self, tag: Tag) -> bool:
        return bool(tag.valid_to > self.begins_at and tag.valid_from < self.finish_at)

    def subspans(self, duration: dt.timedelta) -> Iterable["Span"]:
        """yield Span objects that fit within this span."""
        sliding_start = self.begins_at
        while sliding_start < self.finish_at:
            yield Span(sliding_start, sliding_start + duration)

            sliding_start += duration


def _subclass_iface_error():
    return NotImplementedError(
        "subclasses of BaseTimeAccount must support the full interface"
    )
