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


###  TEST CASE LEGEND
# T=0        1         2         3         4         5         6         7
#  |---------+---------+---------+---------+---------+---------+---------|
#            [ Span A ~]
#                                [ Span B ~~~~~~~~~~~~~~~~~~~~~]
#  [ Span C ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~]
#            [ Span D ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~]
#                       [ Span E ~~~~~~~~~~]
#            [ Span F ~]


@pytest.fixture
def span_times(an_hour):
    return [an_hour.begins_at + i * td(minutes=15) for i in range(8)]


@pytest.fixture
def span_a(span_times):
    return FiniteSpan(begins_at=span_times[1], finish_at=span_times[2])


@pytest.fixture
def span_b(span_times):
    return FiniteSpan(begins_at=span_times[3], finish_at=span_times[6])


@pytest.fixture
def span_c(span_times):
    return FiniteSpan(begins_at=span_times[0], finish_at=span_times[7])


@pytest.fixture
def span_d(span_times):
    return FiniteSpan(begins_at=span_times[1], finish_at=span_times[5])


@pytest.fixture
def span_e(span_times):
    return FiniteSpan(begins_at=span_times[2], finish_at=span_times[4])


@pytest.fixture
def span_f(span_times):
    return FiniteSpan(begins_at=span_times[1], finish_at=span_times[2])


#            [ Span A ~]
#                                [ Span B ~~~~~~~~~~~~~~~~~~~~~]
def test_span_base_case(span_a, span_b):
    # Ordinality
    assert span_a.before(span_b)
    assert span_b.after(span_a)
    assert not span_a.after(span_b)
    assert not span_b.before(span_a)

    # Containment
    assert span_a not in span_b
    assert span_b not in span_a

    # (In)Equality
    assert span_a < span_b
    assert span_a <= span_b
    assert span_b > span_a
    assert span_b >= span_a
    assert not span_a == span_b
    assert span_a != span_b


#            [ Span A ~]
#            [ Span F ~]
def test_span_exactly_equal(span_a, span_f):
    # Ordinality
    assert not span_a.before(span_f)
    assert not span_f.after(span_a)
    assert not span_a.after(span_f)
    assert not span_f.before(span_a)

    # Containment
    assert span_a in span_f
    assert span_f in span_a

    # (In)Equality
    assert not span_a < span_f
    assert span_a <= span_f
    assert not span_f > span_a
    assert span_f >= span_a
    assert span_a == span_f
    assert not span_a != span_f


#  [ Span C ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~]
#            [ Span D ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~]
def test_span_containment(span_c, span_d):
    # Ordinality
    assert span_c.before(span_d)
    assert span_d.after(span_c)
    assert not span_c.after(span_d)
    assert not span_d.before(span_c)

    # Containment
    assert span_c not in span_d
    assert span_d in span_c

    # (In)Equality
    assert not span_c < span_d
    assert not span_c <= span_d
    assert not span_d > span_c
    assert not span_d >= span_c
    assert not span_c == span_d
    assert span_c != span_d


#                      [ Span E ~~~~~~~~~~~]
#            [ Span F ~]
def test_span_contiguous(span_e, span_f):
    # Ordinality
    assert not span_e.before(span_f)
    assert not span_f.after(span_e)
    assert span_e.after(span_f)
    assert span_f.before(span_e)

    # Containment
    assert span_e not in span_f
    assert span_f not in span_e

    # (In)Equality
    assert not span_e < span_f
    assert not span_e <= span_f
    assert not span_f > span_e
    assert not span_f >= span_e
    assert not span_e == span_f
    assert span_e != span_f


###  TEST CASE LEGEND
# T=0        1         2         3         4         5         6         7
#  |---------+---------+---------+---------+---------+---------+---------|
#            [ Span A ~]
#                                [ Span B ~~~~~~~~~~~~~~~~~~~~~]
#  [ Span C ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~]
#            [ Span D ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~]
#                      [ Span E ~~~~~~~~~~~]
#            [ Span F ~]
