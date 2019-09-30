# -*- coding: utf-8 -*-
import datetime as dt
from typing import Callable, Optional
from ortools.sat.python import cp_model
from scipy.stats import norm

from .schedule import ConstraintModel


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
    ):
        self.mean = mean
        if tolerance is None:
            # TODO - can we pick a default 'tolerance' interval better than this?
            # perhaps with norm.alpha() somehow?
            self.tolerance = dt.timedelta(seconds=mean.total_seconds() * 0.1)
        else:
            self.tolerance = tolerance

        self.min = minimum

    @property
    def dist(self):
        return norm(loc=self.mean.total_seconds(), scale=self.tolerance.total_seconds())

    def tension(self, elapsed: dt.timedelta) -> float:
        """Return a value in [0, 1] representing how 'tense' this frequency is.
        At exactly the mean frequency, the returned value will be exactly 0.5.
        """
        if not self.min < elapsed:
            return 0

        return self.dist.cdf(elapsed.total_seconds())

    def tension_solver(
        self, elapsed: cp_model.IntVar, model: ConstraintModel
    ) -> cp_model.IntVar:
        """Returns a scalar integer on the interval [INT_MIN, 3] which scales
        the score of this assignment based on how 'tense' it is. A higher value
        rewards more points and represents the least 'tension'. Negative scalars
        penalize the score. The further the assignment is from its mean frequency,
        the lower the scalar will be."""
        SCALAR_MAX = 3
        mean = int(self.mean.total_seconds())
        tolerance = int(self.tolerance.total_seconds())

        diff = model.make_var("tension_diff")
        model.add(diff == elapsed - mean)

        abs_diff = model.make_var("tension_diff_abs")
        model.add_abs(abs_diff, diff)

        scalar = model.make_var(
            "tension_scalar", lower_bound=cp_model.INT32_MIN, upper_bound=SCALAR_MAX
        )
        remainder = model.make_var("tension_remainder")
        model.add(abs_diff == (SCALAR_MAX - scalar) * tolerance + remainder)
        model.add(remainder < tolerance)
        return scalar
