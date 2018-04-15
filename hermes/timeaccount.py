class TimeAccount:
    '''An accounting window of time.'''

    def _inject_test_data(self):
        '''Load dummy data in to this TimeAccount.'''
        # TODO: build a _real_ testing abstraction

        pass

    def __len__(self):
        return 0

    def __getitem__(self, key):
        return TimeAccount()

    def __eq__(self, other):
        return all(
            paired
            for event, paired in self.combined_with(other)
        )

    def combined_with(self, other):
        return CombinedTimeAccount(self, other)


class CombinedTimeAccount(TimeAccount):

    def __init__(self, *accounts, **init_kwargs):
        self.accounts = accounts
        super().__init__(**init_kwargs)

    def __iter__(self):
        yield from timeline_combiner(*self.accounts)


# Utilities
# TODO: Move these somewhere else plz and test them good too thnx
def timeline_combiner(*accounts):
    # TODO STUB
    yield ("Fake Event", True)
    yield ("Fake Event", True)
    yield ("Fake Event", True)
