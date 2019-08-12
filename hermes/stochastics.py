# -*- coding: utf-8 -*-
import datetime as dt
from typing import Callable, Optional
from scipy.stats import norm


class Variable:
    def __init__(self, experiment: Callable):
        self._experiment = experiment

    def test(self, *args):
        return self._experiment(*args)


class Frequency(Variable):
    def __init__(
        self,
        mean: dt.timedelta = dt.timedelta(seconds=1),
        tolerance: Optional[dt.timedelta] = None,
        minimum: dt.timedelta = dt.timedelta.resolution,
        maximum: dt.timedelta = dt.timedelta.max,
    ):
        if tolerance is None:
            # TODO - can we pick a default 'tolerance' interval better than this?
            # perhaps with norm.alpha() somehow?
            tolerance = dt.timedelta(seconds=mean.seconds * 0.1)

        self._dist = norm(loc=mean.total_seconds(), scale=tolerance.total_seconds())
        self._min = minimum
        self._max = maximum

    def tension(self, elapsed: dt.timedelta) -> float:
        """Return a value on in [0, 1] representing how 'tense' this frequency is.
        At exactly the mean frequency, the returned value will be exactly 0.5."""
        if not self._min < elapsed < self._max:
            return 0

        return self._dist.cdf(elapsed.total_seconds())
