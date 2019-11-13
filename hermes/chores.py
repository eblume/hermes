# -*- coding: utf-8 -*-
import datetime as dt
from enum import Enum
from pathlib import Path
from typing import Iterable, Tuple

import apsw
from ortools.sat.python import cp_model
import pytz

from .schedule import ConstraintModel, EventScoredForSeconds, ScheduleScoredForSeconds
from .span import FiniteSpan
from .stochastics import Frequency
from .tag import Tag


# When a chore hasn't ever been completed, we take the beginning of the span and
# go back this many days an use that as the 'last completed' date.
DEFAULT_CHORE_INTERVAL = dt.timedelta(days=30)


class ChoreStatus(Enum):
    ASSIGNED = 1
    COMPLETED = 2
    CANCELED = 3

    @property
    def terminal(self) -> bool:
        return self.value in {ChoreStatus.COMPLETED.value, ChoreStatus.CANCELED.value}


class Chore:
    def __init__(
        self,
        name: str,
        frequency: Frequency = None,
        duration: dt.timedelta = dt.timedelta(hours=1),
    ):
        self.name = name
        self.duration = duration
        if frequency is None:
            self.frequency = Frequency(mean=dt.timedelta(days=7))
        else:
            self.frequency = frequency

    def tension(self, elapsed: dt.timedelta) -> float:
        return self.frequency.tension(elapsed)

    def tension_solver(
        self,
        name: str,
        elapsed: cp_model.IntVar,
        is_present: cp_model.IntVar,
        model: ConstraintModel,
    ) -> cp_model.IntVar:
        reward = model.make_var(f"{name}_tension_reward", lower_bound=0)
        scalar = self.frequency.tension_solver(name, elapsed, is_present, model)
        model.add(reward == scalar * int(self.duration.total_seconds()), is_present)
        return reward


class ChoreStore:
    def __init__(self, filename: Path = None):
        self.filename = filename
        if filename is None:
            self._sqlite_db = apsw.Connection(":memory:")
        else:
            self._sqlite_db = apsw.Connection(str(filename))
        self._create_tables()

    def _create_tables(self) -> None:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chores (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    duration NUMBER,
                    freq_mean NUMBER,
                    freq_tolerance NUMBER,
                    freq_min NUMBER,
                    active INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chore_instances (
                    id INTEGER PRIMARY KEY,
                    chore_id INTEGER NOT NULL,
                    status INTEGER NOT NULL,
                    updated TIMESTAMP NOT NULL,
                    FOREIGN KEY(chore_id) REFERENCES chores(id)
                )
                """
            )

    def write_to(self, filename: Path, continue_with_copy: bool = None) -> None:
        if filename.exists():
            raise ValueError("File already exists", filename)

        file_db = apsw.Connection(str(filename))
        # TODO - verify these arguments, they are copied over from timespan.py
        with file_db.backup("main", self._sqlite_db, "main") as backup:
            backup.step()

        if continue_with_copy or (continue_with_copy is None and self.filename is None):
            self._sqlite_db = file_db

    def add_chore(self, chore: Chore) -> None:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            conn.execute(
                """
                INSERT INTO
                chores (name, duration, freq_mean, freq_tolerance, freq_min, active)
                VALUES (
                    :name,
                    :duration,
                    :freq_mean,
                    :freq_tolerance,
                    :freq_min,
                    1
                )
                """,
                {
                    "name": chore.name,
                    "duration": chore.duration.total_seconds(),
                    "freq_mean": chore.frequency.mean.total_seconds(),
                    "freq_tolerance": chore.frequency.tolerance.total_seconds(),
                    "freq_min": chore.frequency.min.total_seconds(),
                },
            )

    def applicable_chores(
        self, span: FiniteSpan
    ) -> Iterable[Tuple[Chore, dt.datetime]]:
        """Iterates over chores which could potentially be done now, ie are 'due'"""
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            result = conn.execute(
                """
                SELECT
                    c.id as cid,
                    c.name as name,
                    c.duration as duration,
                    c.freq_mean as mean,
                    c.freq_tolerance as tolerance,
                    c.freq_min as min,
                    MAX(ci.updated) as updated
                FROM chores AS c
                LEFT OUTER JOIN chore_instances AS ci
                    ON ci.chore_id=c.id
                WHERE
                    c.active=1 AND (ci.status IS NULL OR ci.status<>:canceled_status)
                GROUP BY c.id
                """,
                {"canceled_status": ChoreStatus.CANCELED.value},
            )
            for row in result:
                name = row[1]
                duration = dt.timedelta(seconds=row[2])
                mean = dt.timedelta(seconds=row[3])
                tolerance = dt.timedelta(seconds=row[4])
                _min = dt.timedelta(seconds=row[5])
                updated = (
                    dt.datetime.fromtimestamp(int(row[6]), tz=pytz.utc)
                    if row[6]
                    else span.begins_at - DEFAULT_CHORE_INTERVAL
                )

                if updated + _min >= span.finish_at:
                    continue

                freq = Frequency(mean=mean, tolerance=tolerance, minimum=_min)
                chore = Chore(name, frequency=freq, duration=duration)
                yield chore, updated

    def start_chore(self, cid: int, tag: Tag) -> int:
        assert tag.valid_from is not None  # True by definition of an event tag
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            conn.execute(
                """
                INSERT INTO
                chore_instances (chore_id, status, updated)
                VALUES (:chore_id, :status, datetime(:updated))
                """,
                {
                    "chore_id": cid,
                    "status": ChoreStatus.ASSIGNED.value,
                    "updated": tag.valid_from.timestamp(),
                },
            )
        return self._sqlite_db.last_insert_rowid()

    def __len__(self) -> int:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            result = conn.execute(
                """
                SELECT COUNT(*)
                FROM chores
                WHERE active=1
                """
            )
            return list(result)[0][0]

    def __iter__(self) -> Iterable[Chore]:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            result = conn.execute(
                """
                SELECT
                    c.name as name,
                    c.duration as duration,
                    c.freq_mean as mean,
                    c.freq_tolerance as tolerance
                FROM chores AS c
                WHERE
                    c.active=1
                """
            )
            for row in result:
                name = row[0]
                duration = dt.timedelta(seconds=row[1])
                mean = dt.timedelta(seconds=row[2])
                tolerance = dt.timedelta(seconds=row[3])

                freq = Frequency(mean=mean, tolerance=tolerance)
                yield Chore(name, frequency=freq, duration=duration)

    def reset(self) -> None:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            conn.execute("DROP TABLE IF EXISTS chores")
            conn.execute("DROP TABLE IF EXISTS chore_instances")
        self._create_tables()


class ChoreEvent(EventScoredForSeconds):
    """Helper class - Source of scores of chore scores. Of course."""

    def __init__(
        self, *args, chore: Chore = None, updated: dt.datetime = None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self._chore = chore
        self._updated = updated

    def score(self, model: ConstraintModel = None, **kwargs) -> cp_model.IntVar:
        assert model is not None
        assert self._chore is not None
        assert self._updated is not None
        base_score = super().score(model=model, **kwargs)
        elapsed = model.make_var(f"{self._chore.name}_elapsed_time")
        model.add(elapsed == self.start_time - int(self._updated.timestamp()))

        score = model.make_var(f"{self._chore.name}_chore_event_score")
        model.add(
            score
            == self._chore.tension_solver(
                self._chore.name, elapsed, self.is_present, model
            )
            + base_score
        )
        return score


class ChoreSchedule(ScheduleScoredForSeconds):
    def add_chore(self, chore: Chore, updated: dt.datetime):
        self.add_event(
            name=chore.name,
            duration=chore.duration,
            optional=False,
            chore=chore,
            updated=updated,
            event_class=ChoreEvent,
        )

    def populate(self, span: FiniteSpan = None, **kwargs):  # type: ignore
        assert span is not None
        chore_store = kwargs.get("chore_store", None)
        assert chore_store is not None
        for chore, updated in chore_store.applicable_chores(span):
            self.add_chore(chore, updated)
        return super().populate(span=span, **kwargs)
