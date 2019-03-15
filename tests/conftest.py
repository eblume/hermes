# -*- coding: utf-8 -*-
import datetime as dt

from hermes.timespan import Category, SqliteTimeSpan, Tag, TimeSpan

import pytest


@pytest.fixture(scope="function")
def simple_account():
    """Blank account, very simple"""
    return TimeSpan({})


@pytest.fixture(scope="module")
def complex_timespan_tags():
    """Four main tags with various overlaps and data for unit testing"""

    # tagname |  0 | 0.5|  1 | 1.5|  2 | 2.5|  3 | 3.5|  4 |
    #  Tag A  |####|####|####|    |    |    |    |    |    |
    #  Tag B  |    |####|####|    |    |    |    |    |    |
    #  Tag C  |    |    |####|####|####|####|    |    |    |
    #  Tag D  |    |    |    |    |    |####|####|####|####|

    t0h = dt.datetime(2018, 4, 16, 6, 43, 15, 13).astimezone(
        dt.timezone.utc
    )  # when doesn't matter
    t05 = t0h + dt.timedelta(hours=0, minutes=30)
    t1h = t0h + dt.timedelta(hours=1)
    # t15 = t0h + dt.timedelta(hours=1, minutes=30)
    # t2h = t0h + dt.timedelta(hours=2)
    t25 = t0h + dt.timedelta(hours=2, minutes=30)
    # t3h = t0h + dt.timedelta(hours=3)
    t4h = t0h + dt.timedelta(hours=4)

    a_cat = Category("A", None)
    b_cat = Category("B", a_cat)
    c_cat = Category("C", b_cat)

    return {
        Tag("Tag A", category=a_cat, valid_from=t0h, valid_to=t1h),
        Tag("Tag B", category=b_cat, valid_from=t05, valid_to=t1h),
        Tag("Tag C", category=c_cat, valid_from=t1h, valid_to=t25),
        Tag("Tag D", category=a_cat, valid_from=t25, valid_to=t4h),
    }


@pytest.fixture(scope="module")
def complex_timespan(complex_timespan_tags):
    """An account with four main tags, for unit testing"""
    return TimeSpan(complex_timespan_tags)


@pytest.fixture(scope="function")
def sqlite_timespan(complex_timespan_tags):
    return SqliteTimeSpan(complex_timespan_tags)


GENERIC_RO_TIMESPANS = {
    "base": lambda tags: TimeSpan(tags),
    "sqlite": lambda tags: SqliteTimeSpan(tags),
}


@pytest.fixture
def generic_ro_timespan(request, complex_timespan_tags):
    global GENERIC_RO_TIMESPANS
    if request.param not in GENERIC_RO_TIMESPANS:
        raise ValueError("Not in GENERIC_RO_TIMESPANS:", request.param)

    return GENERIC_RO_TIMESPANS[request.param](complex_timespan_tags)
