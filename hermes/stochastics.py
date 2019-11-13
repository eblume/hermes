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
        self,
        name: str,
        elapsed: cp_model.IntVar,
        is_present: cp_model.IntVar,
        model: ConstraintModel,
    ) -> cp_model.IntVar:
        """Return a value in [1, 3] representing a 'reward' scalar."""
        score = model.make_var(f"{name}_tension_score", lower_bound=1, upper_bound=3)
        too_early = model.make_var(f"{name}_tension_too_early", boolean=True)
        too_late = model.make_var(f"{name}_tension_too_late", boolean=True)
        just_right = model.make_var(f"{name}_tension_just_right", boolean=True)
        model.add(too_early + too_late + just_right == 1, is_present)
        model.add(score == 1, too_early)
        model.add(score == 2, too_late)
        model.add(score == 3, just_right)
        return score
