"""Hermes, the Time Accountant"""

import datetime as dt
from operator import attrgetter

__author__ = """Erich Blume"""
__email__ = 'blume.erich@gmail.com'
__version__ = '0.0.1'


class TimeAccount:
    '''An accounting window of time.'''

    def __init__(self, tags=None):
        self.tags = [] if tags is None else tags

    def combined_with(self, other):
        return CombinedTimeAccount(self, other)

    def __len__(self):
        return len(self.tags)

    @property
    def span(self):
        # TODO optimize this (index? cache?)
        oldest = min(self.tags, key=attrgetter('valid_from'))
        most_recent = max(self.tags, key=attrgetter('valid_to'))
        return Span(oldest.valid_from, most_recent.valid_to)

    def __getitem__(self, key):
        if not isinstance(key, slice):
            raise TypeError('invalid type for key', key)

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

    def __iter__(self):
        yield from self.tags

    def __eq__(self, other):
        return all(paired for tag, paired in self.combined_with(other))


class CombinedTimeAccount(TimeAccount):

    def __init__(self, *accounts, **init_kwargs):
        self.accounts = accounts
        super().__init__(**init_kwargs)

    def __iter__(self):
        yield (Tag("Fake Tag 1"), True)
        yield (Tag("Fake Tag 2"), True)
        yield (Tag("Fake Tag 3"), True)


class Tag:
    '''A tag on the timeline. Could be an event, could be an annotation.'''
    def __init__(self, name=None, valid_from=None, valid_to=None, **data):
        self.name = self._validate_name(name)
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.data = data

    def _validate_name(self, name):
        return name or f"tag_{id(self)}"  # TODO don't leak memory address here

    def __repr__(self):
        return f"Tag('{self.name}')"


class Span:
    '''A span of time, to which tags may or may not belong. Utility class.'''
    def __init__(self, begins_at, finish_at):
        self.begins_at = begins_at
        self.finish_at = finish_at

    def __contains__(self, tag):
        return bool(
            tag.valid_to > self.begins_at and
            tag.valid_from < self.finish_at
        )

    def subspans(self, duration):
        '''yield Span objects that fit within this span.'''
        # TODO there has to be some fancy itertools way to do this
        sliding_start = self.begins_at
        while sliding_start < self.finish_at:
            yield Span(sliding_start, sliding_start + duration)
            sliding_start += duration
