"""Hermes, the Time Accountant"""

import datetime as dt

__author__ = """Erich Blume"""
__email__ = 'blume.erich@gmail.com'
__version__ = '0.0.1'


class TimeAccount:
    '''An accounting window of time.'''

    def __init__(self, tags=None):
        self.tags = [] if tags is None else tags

    def combined_with(self, other):
        return CombinedTimeAccount(self, other)

    def __reversed__(self):
        # TODO: don't create a whole new timeaccount, but rather query smarter
        return TimeAccount(tags=self.tags[::-1])

    def __len__(self):
        return len(self.tags)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.tags[key]
        if isinstance(key, slice):
            return self._slice(
                slice_from=key.start,
                slice_to=key.stop,
                direction=key.step is None or key.step < 0,
                distinguish=abs(key.step) if key.step is not None else 1,
            )
        raise TypeError('invalid type for key', key)

    def __eq__(self, other):
        return all(
            paired
            for tag, paired in self.combined_with(other)
        )

    def _slice(
        self, slice_from=None, slice_to=None,
        direction=True,  # true is 'forward' from ref. of window
        distinguish=1
    ):
        # TODO: build a real time slicer, temporal db style! this is it!
        # (Instead we're just going to do some int-index stuff.)
        return self.tags[::1 if direction else -1]


class CombinedTimeAccount(TimeAccount):

    def __init__(self, *accounts, **init_kwargs):
        self.accounts = accounts
        super().__init__(**init_kwargs)

    def __iter__(self):
        yield (Tag("Fake Tag 1"), True)
        yield (Tag("Fake Tag 2"), True)
        yield (Tag("Fake Tag 3"), True)


class Tag:

    def __init__(self, name=None, valid_from=None, valid_to=None):
        self.name = self._validate_name(name)
        self.valid_from = valid_from
        self.valid_to = valid_to

    def _validate_name(self, name):
        return name or f"tag_{id(self)}"  # TODO don't leak memory address here

    def __repr__(self):
        return f"Tag('{self.name}')"
