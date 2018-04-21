import datetime as dt
import pytest

from hermes.timeaccount import TimeAccount
from hermes.tag import Tag


# list all of the fixtures - hacky, let's metaprogram this out
__all__ = [
    'simple_account',
    'complex_account',
    'complex_account_tags',
]


@pytest.fixture
def simple_account():
    '''Blank account, very simple'''
    return TimeAccount([])


@pytest.fixture
def complex_account_tags():
    '''Four main tags with various overlaps and data for unit testing'''

    # tagname |  0 | 0.5|  1 | 1.5|  2 | 2.5|  3 | 3.5|  4
    #  Tag A  |####|####|####|####|    |    |    |    |
    #  Tag B  |    |    |    |####|    |    |    |    |
    #  Tag C  |    |    |####|####|####|####|    |    |
    #  Tag D  |    |    |    |    |####|####|####|####|

    t0h = dt.datetime(2018, 4, 16, 6, 43, 15, 13)  # when doesn't matter
    t1h = t0h + dt.timedelta(hours=1)
    t15 = t0h + dt.timedelta(hours=1, minutes=30)
    t2h = t0h + dt.timedelta(hours=2)
    t3h = t0h + dt.timedelta(hours=3)
    t4h = t0h + dt.timedelta(hours=4)
    return [
        Tag(  # A tag from T=0 hours to T=1 hour
            'Tag A',
            valid_from=t0h,
            valid_to=t2h,
        ),
        Tag(   # a tag from T=1.5 to T=2
            'Tag B',
            valid_from=t15,
            valid_to=t2h,
        ),
        Tag(  # a tag from T=1 to T=3  (2 hours!)
            'Tag C',
            valid_from=t1h,
            valid_to=t3h,
        ),
        Tag(  # a tag from T=2 to T=4
            'Tag D',
            valid_from=t2h,
            valid_to=t4h,
        )
    ]


@pytest.fixture
def complex_account(complex_account_tags):
    '''An account with four main tags, for unit testing'''
    return TimeAccount(list_tags=complex_account_tags)
