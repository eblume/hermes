"""Hermes, the Time Accountant"""

import attr
import datetime as dt
from functools import partial
from operator import attrgetter
from typing import List, Iterable

__author__ = """Erich Blume"""
__email__ = 'blume.erich@gmail.com'
__version__ = '0.0.1'


dataclass = partial(attr.s, slots=True, auto_attribs=True, frozen=True)


@dataclass
class Tag:
    '''A tag on the timeline. Could be an event, could be an annotation.'''

    name: str
    valid_from: dt.datetime
    valid_to: dt.datetime


@dataclass
class Span:
    '''A span of time, to which tags may or may not belong. Utility class.'''

    begins_at: dt.datetime
    finish_at: dt.datetime

    def __contains__(self, tag: Tag) -> bool:
        return bool(
            tag.valid_to > self.begins_at and
            tag.valid_from < self.finish_at
        )

    def subspans(self, duration: dt.timedelta) -> Iterable['Span']:
        '''yield Span objects that fit within this span.'''
        sliding_start = self.begins_at
        while sliding_start < self.finish_at:
            yield Span(sliding_start, sliding_start + duration)
            sliding_start += duration


@dataclass
class TimeAccount:
    '''An accounting window of time.'''

    # TODO - check up on https://github.com/python-attrs/attrs/pull/281
    # it is a PR to allow me to set this to have a default val without leaking
    # too much of the attrs abstraction particulars down the call chain.
    tags: List[Tag]  # = attr.ib(default=[])

    def __len__(self) -> int:
        return len(self.tags)

    @property
    def span(self) -> Span:
        oldest = min(self.tags, key=attrgetter('valid_from'))
        most_recent = max(self.tags, key=attrgetter('valid_to'))
        return Span(oldest.valid_from, most_recent.valid_to)

    def __getitem__(self, key: slice) -> 'TimeAccount':
        slice_from = key.start or self.span.begins_at
        slice_to = key.stop or self.span.finish_at
        slice_span = Span(slice_from, slice_to)

        if key.step is not None:
            accounts = []
            for subspan in slice_span.subspans(key.step):
                new_account = TimeAccount(tags=[
                    t for t in self.tags
                    if t in subspan
                ])
                accounts.append(new_account)
            return accounts

        return TimeAccount(tags=[
            t for t in self.tags
            if t in slice_span
        ])

    def __iter__(self) -> Iterable[Tag]:
        yield from self.tags

    def __eq__(self, other) -> bool:
        return all(paired for tag, paired in CombinedTimeAccount(self, other))


@dataclass
class CombinedTimeAccount(TimeAccount):

    accounts: List[TimeAccount]

    def __iter__(self) -> Iterable[Tag]:
        # TODO STUB
        yield (Tag("Fake Tag 1"), True)
        yield (Tag("Fake Tag 2"), True)
        yield (Tag("Fake Tag 3"), True)
