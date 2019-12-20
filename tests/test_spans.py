# -*- coding: utf-8 -*-
from datetime import date, timedelta as td

from hermes.span import FiniteSpan
import pytest


@pytest.fixture
def a_day():
    return FiniteSpan.from_date(date.today())


@pytest.fixture
def an_hour(a_day):
    assert a_day.duration >= td(hours=4)
    return next(a_day.subspans(td(hours=1)))


@pytest.mark.skip(reason="Potential refactor in progress in another branch")
def test_proper_subset_vs_smaller_vs_sooner(a_day, an_hour):
    assert an_hour.span.duration == an_hour.duration
    assert an_hour < a_day
    assert an_hour in a_day

    earlier = FiniteSpan(
        begins_at=an_hour.begins_at - td(minutes=30),
        finish_at=an_hour.finish_at - td(minutes=30),
    )

    assert earlier.span.duration == an_hour.duration
    assert not an_hour < a_day
    assert earlier in a_day
