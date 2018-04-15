class TimeAccount:
    '''An accounting window of time.'''

    def __init__(self):
        self.tags = []

    def _inject_test_data(self):
        '''Load dummy data in to this TimeAccount.'''
        # TODO: build a _real_ testing abstraction

        self.tags = [Tag('Fake Tag') for _ in range(4)]

    def __len__(self):
        return len(self.tags)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.tags[key]
        if isinstance(key, slice):
            return self._slice(
                key.start,
                key.stop,
                key.step is None or key.step < 0,
                abs(key.step) if key.step is not None else 1,
            )
        raise TypeError('invalid type for key', key)

    def __eq__(self, other):
        return all(
            paired
            for tag, paired in self.combined_with(other)
        )

    def _slice(self, slice_from, slice_to, slice_forward=True, slice_distinguish=1):
        return self.tags[0]

    def combined_with(self, other):
        return CombinedTimeAccount(self, other)


class CombinedTimeAccount(TimeAccount):

    def __init__(self, *accounts, **init_kwargs):
        self.accounts = accounts
        super().__init__(**init_kwargs)

    def __iter__(self):
        yield from timeline_combiner(*self.accounts)


class Tag:

    def __init__(self, name=None, valid_from=None, valid_to=None):
        self.name = self._validate_name(name)
        self.valid_from = valid_from
        self.valid_to = valid_to

    def _validate_name(self, name):
        return name or f"tag_{id(self)}"  # TODO don't leak memory address here

    def __repr__(self):
        return f"Tag('{self.name}')"


# Utilities
# TODO: Move these somewhere else plz and test them good too thnx


def timeline_combiner(*accounts):
    # TODO STUB
    yield (Tag("Fake Tag"), True)
    yield (Tag("Fake Tag"), True)
    yield (Tag("Fake Tag"), True)
