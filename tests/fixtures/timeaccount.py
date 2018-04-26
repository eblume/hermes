import datetime as dt

from hermes import Tag, TimeAccount

import pytest


# list all of the fixtures - hacky, let's metaprogram this out
__all__ = ["simple_account", "complex_account", "complex_account_tags"]


@pytest.fixture
def simple_account():
    """Blank account, very simple"""
    return TimeAccount({})


@pytest.fixture
def complex_account_tags():
    """Four main tags with various overlaps and data for unit testing"""

    # tagname |  0 | 0.5|  1 | 1.5|  2 | 2.5|  3 | 3.5|  4 |
    #  Tag A  |####|####|####|    |    |    |    |    |    |
    #  Tag B  |    |####|####|    |    |    |    |    |    |
    #  Tag C  |    |    |####|####|####|####|    |    |    |
    #  Tag D  |    |    |    |    |    |####|####|####|####|

    t0h = dt.datetime(2018, 4, 16, 6, 43, 15, 13)  # when doesn't matter
    t05 = t0h + dt.timedelta(hours=0, minutes=30)
    t1h = t0h + dt.timedelta(hours=1)
    t15 = t0h + dt.timedelta(hours=1, minutes=30)
    t2h = t0h + dt.timedelta(hours=2)
    t25 = t0h + dt.timedelta(hours=2, minutes=30)
    t3h = t0h + dt.timedelta(hours=3)
    t4h = t0h + dt.timedelta(hours=4)
    return {
        Tag("Tag A", valid_from=t0h, valid_to=t1h),
        Tag("Tag B", valid_from=t05, valid_to=t1h),
        Tag("Tag C", valid_from=t1h, valid_to=t25),
        Tag("Tag D", valid_from=t25, valid_to=t4h),
    }


@pytest.fixture
def complex_account(complex_account_tags):
    """An account with four main tags, for unit testing"""
    return TimeAccount(complex_account_tags)
