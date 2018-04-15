class TimeAccount:
    '''An accounting window of time.'''

    def __init__(self, tags=None, direction=True):
        self.tags = [] if tags is None else tags
        self.direction = direction  # True = 'Forward'... maybe?

    def combined_with(self, other):
        return CombinedTimeAccount(self, other)

    def __reversed__(self):
        # TODO: don't create a whole new timeaccount, but rather query smarter
        # (this is like super duper important and is the entire reason for the
        # way Hermes is built the way it is, btw. So get this right, please.)
        return TimeAccount(tags=self.tags[::-1], direction=not self.direction)

    def _inject_test_data(self):
        '''Load dummy data in to this TimeAccount.'''
        # TODO: build a _real_ testing abstraction

        self.tags = [Tag(f'Fake Tag {n}') for n in range(1, 5)]

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
        direction=None,
        distinguish=1
    ):
        if direction is None:
            direction = self.direction

        return self.tags[0]


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
