# -*- coding: utf-8 -*-
import datetime as dt
from enum import Enum
from pathlib import Path

import apsw

from .schedule import Schedule, Event
from .span import FiniteSpan
from .stochastics import Frequency
from .tag import Tag
from .timespan import date_parse, TimeSpan


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


class ChoreStore:
    def __init__(self, filename: Path = None):
        if filename is None:
            self._sqlite_db = apsw.Connection(":memory:")
            with self._sqlite_db:
                conn = self._sqlite_db.cursor()
                self._create_tables(conn)
        else:
            self._sqlite_db = apsw.Connection(str(filename))

    def _create_tables(self, conn) -> None:
        conn.execute(
            """
            CREATE TABLE chores (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                duration NUMBER,
                freq_mean NUMBER,
                freq_tolerance NUMBER,
                freq_min NUMBER,
                freq_max NUMBER,
                active INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE chore_instances (
                id INTEGER PRIMARY KEY,
                chore_id INTEGER NOT NULL,
                status INTEGER NOT NULL,
                updated DATETIME NOT NULL,
                FOREIGN KEY(chore_id) REFERENCES chores(id)
            )
            """
        )

    def write_to(self, filename: Path) -> None:
        if filename.exists():
            raise ValueError("File already exists", filename)

        file_db = apsw.Connection(str(filename))
        # TODO - verify these arguments, they are copied over from timespan.py
        with file_db.backup("main", self._sqlite_db, "main") as backup:
            backup.step()

        self._sqlite_db = file_db

    def add_chore(self, chore: Chore) -> None:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            conn.execute(
                """
                INSERT INTO
                chores (name, duration, freq_mean, freq_tolerance, freq_min, freq_max, active)
                VALUES (
                    :name,
                    :duration,
                    :freq_mean,
                    :freq_tolerance,
                    :freq_min,
                    :freq_max,
                    1
                )
                """,
                {
                    "name": chore.name,
                    "duration": chore.duration.total_seconds(),
                    "freq_mean": chore.frequency.mean.total_seconds(),
                    "freq_tolerance": chore.frequency.tolerance.total_seconds(),
                    "freq_min": chore.frequency.min.total_seconds(),
                    "freq_max": chore.frequency.max.total_seconds(),
                },
            )

    # TODO: Maybe all of this chore-instance code should be removed and
    # 'scribe' should take its place? IE a chore-only timeline?

    def pick_chore(self, event: Event, tag: Tag) -> Chore:
        assert tag.valid_from is not None  # True by definition of an event tag
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            chores = []
            result = conn.execute(
                """
                SELECT
                    c.id as cid,
                    c.name as name,
                    c.duration as duration,
                    c.freq_mean as mean,
                    c.freq_tolerance as tolerance,
                    MAX(ci.updated) as updated
                FROM chores AS c
                LEFT JOIN chore_instances AS ci
                    ON ci.chore_id=c.id
                WHERE
                    c.active=1 AND
                    (ci.status<>:canceled_status OR ci.chore_id IS NULL)
                GROUP BY c.id
                """,
                {"canceled_status": ChoreStatus.CANCELED.value},
            )
            for row in result:
                cid = row[0]
                name = row[1]
                duration = dt.timedelta(seconds=row[2])
                mean = dt.timedelta(seconds=row[3])
                tolerance = dt.timedelta(seconds=row[4])
                if row[5] is not None:
                    updated = date_parse(row[5])
                    elapsed = tag.valid_from - updated
                else:
                    elapsed = dt.timedelta(seconds=0)

                freq = Frequency(mean=mean, tolerance=tolerance)
                chore = Chore(name, frequency=freq, duration=duration)
                tension = chore.tension(elapsed)
                chores.append((tension, chore, cid))

        pick = sorted(chores, key=lambda c: c[0])[0]
        self.start_chore(pick[2], tag)
        return pick[1]

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
                    "updated": tag.valid_from.isoformat(),
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


class ChoreSchedule(Schedule):
    """Helper class - this schedule type (and its descendants) include a
    ChoreList, and can have chore times when being scheduled."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chores = []

    def add_chore_slots(
        self, limit: int, duration: dt.timedelta = dt.timedelta(hours=1)
    ):
        """Convenience method to automatically generate up to the specified
        number of chore slots per generated schedule. Will attempt to schedule
        as many as is possible."""
        self._chore_slot_limit = limit
        self._chore_slot_duration = duration

    def populate(
        self, span: FiniteSpan, chore_store: ChoreStore = None, *args, **kwargs
    ) -> TimeSpan:
        assert (
            chore_store is not None
        )  # TODO - there needs to be a better way to type this
        chore_events = [
            self.add_event(
                name=f"Chore slot {slot}",
                duration=self._chore_slot_duration,
                optional=True,
            )
            for slot in range(min(self._chore_slot_limit, len(chore_store)))
        ]

        schedule = super().populate(span, *args, **kwargs)

        chore_events_by_tag = {
            event._tag: event for event in chore_events if event._tag is not None
        }

        newtags = []
        for tag in schedule.iter_tags():
            event = chore_events_by_tag.get(tag, None)
            if event is not None and event in chore_events:
                chore = chore_store.pick_chore(event, tag)
                tag = self._update_tag_for_chore(tag, chore)
            newtags.append(tag)

        return TimeSpan(set(newtags))

    def _update_tag_for_chore(self, tag: Tag, chore: Chore) -> Tag:
        # TODO duration change? Unclear
        return Tag(
            name=chore.name,
            valid_from=tag.valid_from,
            valid_to=tag.valid_to,
            category=tag.category,
        )
