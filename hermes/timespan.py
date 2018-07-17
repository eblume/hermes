# -*- coding: utf-8 -*-
import abc
import datetime as dt
from operator import attrgetter
from pathlib import Path
from typing import Any, Iterable, Optional, Set, Union, cast

import apsw

import attr

from dateutil.parser import parse as date_parse

from .categorypool import BaseCategoryPool, CategoryPool, MutableCategoryPool
from .span import Span, Spannable
from .tag import Category, Tag


class BaseTimeSpan(Spannable, metaclass=abc.ABCMeta):
    @abc.abstractproperty
    @property
    def category_pool(self) -> BaseCategoryPool:
        raise NotImplementedError("Subclasses must define this interface.")

    @abc.abstractmethod
    def iter_tags(self) -> Iterable["Tag"]:
        raise NotImplementedError("Subclasses must define this interface.")

    @abc.abstractmethod
    def filter(self, category: Union["Category", str]) -> "BaseTimeSpan":
        raise NotImplementedError("Subclasses must define this interface.")

    @abc.abstractmethod
    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeSpan":
        raise NotImplementedError("Subclasses must define this interface.")

    def has_tag(self, tag: Tag) -> bool:
        return tag in set(self.iter_tags())

    def __len__(self):
        return len(list(self.iter_tags()))

    def __getitem__(self, key: Union[Optional[int], slice]) -> "BaseTimeSpan":
        # Do a little type casting safety dance. Let's find a better way.
        type_error = key is None
        type_error |= not isinstance(key, slice)
        if type_error:
            raise TypeError("BaseTimeSpan objects must be sliced with datetime")

        key = cast(slice, key)

        # And a safety dance for our friends slice.start and slice.stop
        type_error |= key.start is not None and not isinstance(key.start, dt.datetime)
        type_error |= key.stop is not None and not isinstance(key.stop, dt.datetime)
        if type_error:
            raise TypeError("BaseTimeSpan objects must be sliced with datetime")

        start = cast(Optional[dt.datetime], key.start)
        stop = cast(Optional[dt.datetime], key.stop)

        return self.reslice(start, stop)

    def slice_with_span(self, span: Span) -> "BaseTimeSpan":
        return self.reslice(
            span.begins_at or dt.datetime.min, span.finish_at or dt.datetime.max
        )

    def subspans(self, duration: dt.timedelta) -> Iterable["BaseTimeSpan"]:
        for subspan in self.span.subspans(duration):
            yield self.slice_with_span(subspan)


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class TimeSpan(BaseTimeSpan):
    tags: Set[Tag]

    @property
    def category_pool(self) -> CategoryPool:
        return CategoryPool(
            stored_categories={
                tag.category.fullpath: tag.category
                for tag in self.iter_tags()
                if tag.category is not None
            }
        )

    def iter_tags(self) -> Iterable["Tag"]:
        yield from self.tags

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "TimeSpan":
        selfspan = self.span
        newspan = Span(
            begins_at if begins_at is not None else selfspan.begins_at,
            finish_at if finish_at is not None else selfspan.finish_at,
        )
        tags = {t for t in self.tags if t in newspan}
        return TimeSpan(tags=tags)

    @property
    def span(self) -> "Span":
        tags = sorted(self.tags, key=attrgetter("valid_from"))
        oldest = min(tags, key=attrgetter("valid_from"))
        most_recent = max(tags, key=attrgetter("valid_to"))
        return Span(oldest.valid_from, most_recent.valid_to)

    def filter(self, category: Union["Category", str]) -> "BaseTimeSpan":
        if category is None:
            return self  # safe to return self due to immutability

        if isinstance(category, str):
            category = self.category_pool.get_category(category)
        cast(Category, category)

        return TimeSpan(tags={tag for tag in self.iter_tags() if tag in category})

    @classmethod
    def combine(cls, *others: "BaseTimeSpan") -> "TimeSpan":
        tags = {t for other in others for t in other.iter_tags()}
        return TimeSpan(tags)


class InsertableTimeSpan(BaseTimeSpan):
    def insert_tag(self, tag: Tag) -> None:
        raise NotImplementedError("Subclasses must define this interface.")


class RemovableTimeSpan(BaseTimeSpan):
    def remove_tag(self, tag: Tag) -> bool:
        """Remove the specified tag. Return true iff the tag was found."""
        raise NotImplementedError("Subclasses must define this interface.")


class WriteableTimeSpan(BaseTimeSpan):
    def write_to(self, filename: Path) -> None:
        raise NotImplementedError("Subclasses must define this interface.")

    @classmethod
    def read_from(cls, filename: Path) -> BaseTimeSpan:
        raise NotImplementedError("Subclasses must define this interface.")


class SqliteTimeSpan(InsertableTimeSpan, RemovableTimeSpan, WriteableTimeSpan):
    """Sqlite-backed TimeSpan"""

    # The goal for this implementation is that it should be a really solid
    # performer for almost any use case, so long as the number of tags can
    # reasonably fit in memory. This particular class is a good candidate for
    # optimizations at the expense of readibility.

    def __init__(self, tags: Optional[Iterable[Tag]] = None) -> None:
        self._sqlite_db: apsw.Connection = apsw.Connection(":memory:")
        self._category_pool: MutableCategoryPool = MutableCategoryPool()

        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            conn.execute(
                """
                CREATE TABLE tags (
                    valid_from datetime,
                    valid_to datetime,
                    name text,
                    category text
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX tags_idx ON tags (valid_from, valid_to, name)
                """
            )

            if tags:
                for tag in tags:
                    self.insert_tag(tag)

    def insert_tag(self, tag: Tag) -> None:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            category_str = tag.category.fullpath if tag.category else "sqlite3"
            category = self._category_pool.get_category(category_str, create=True)
            conn.execute(
                "INSERT INTO tags VALUES (:valid_from, :valid_to, :name, :category)",
                {
                    "valid_from": tag.valid_from.isoformat()
                    if tag.valid_from
                    else None,
                    "valid_to": tag.valid_to.isoformat() if tag.valid_to else None,
                    "name": tag.name,
                    "category": category.fullpath,
                },
            )

    def remove_tag(self, tag: Tag) -> bool:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            conn.execute(
                "DELETE FROM tags WHERE valid_from = :valid_from AND valid_to = :valid_to AND name = :name",
                {
                    "valid_from": tag.valid_from.isoformat()
                    if tag.valid_from is not None
                    else None,
                    "valid_to": tag.valid_to.isoformat()
                    if tag.valid_to is not None
                    else None,
                    "name": tag.name,
                },
            )
        return True  # TODO - apsw does not support rowcount, do we care?

    @property
    def category_pool(self) -> BaseCategoryPool:
        return cast(BaseCategoryPool, self._category_pool)

    def iter_tags(self) -> Iterable["Tag"]:
        with self._sqlite_db:
            cursor = self._sqlite_db.cursor()
            result = cursor.execute(
                "SELECT valid_from, valid_to, name, category FROM tags"
            )
            for row in result:
                yield self._tag_from_row(row)

    def filter(self, category: Union["Category", str]) -> "BaseTimeSpan":
        if isinstance(category, str):
            category = self._category_pool.get_category(category)

        return SqliteTimeSpan(tags=[t for t in self.iter_tags() if t in category])

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeSpan":
        tags = []
        query_start = """
        SELECT valid_from, valid_to, name, category
        FROM tags
        WHERE
        """
        tag_is_infinite = "(valid_to IS NULL AND valid_from IS NULL)"

        query_parts = [tag_is_infinite]

        if begins_at is None and finish_at is None:
            return SqliteTimeSpan(self.iter_tags())

        elif begins_at is None:
            query_parts += ["(valid_from IS NULL OR valid_from <= :finish_at)"]
        elif finish_at is None:
            query_parts += ["(valid_to IS NULL OR valid_to <= :begins_at)"]
        else:
            query_parts += [
                "(valid_to >= :begins_at AND valid_from IS NULL)",
                "(valid_to IS NULL AND valid_from <= :finish_at)",
                "(valid_to >= :begins_at AND valid_from <= :finish_at)",
            ]

        query = f"{query_start} {' OR '.join(query_parts)}"

        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            result = conn.execute(
                query,
                {
                    "begins_at": begins_at.isoformat()
                    if begins_at is not None
                    else None,
                    "finish_at": finish_at.isoformat()
                    if finish_at is not None
                    else None,
                },
            )
            for row in result:
                tags.append(self._tag_from_row(row))

        return SqliteTimeSpan(tags=tags)

    @property
    def span(self) -> "Span":
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            result = conn.execute("SELECT min(valid_from), max(valid_to) FROM tags")
            earliest, latest = result.fetchone()
            begins_at = None if earliest is None else date_parse(earliest)
            finish_at = None if latest is None else date_parse(latest)
            return Span(begins_at, finish_at)

    def has_tag(self, tag: Tag) -> bool:
        with self._sqlite_db:
            conn = self._sqlite_db.cursor()
            query = """
            SELECT count(*)
            FROM tags
            WHERE
                (valid_to = :valid_to) AND
                (valid_from = :valid_from) AND
                (category = :category)
            """
            result = conn.execute(
                query,
                {
                    "valid_to": tag.valid_to.isoformat()
                    if tag.valid_to is not None
                    else None,
                    "valid_from": tag.valid_from.isoformat()
                    if tag.valid_from is not None
                    else None,
                    "category": tag.category.fullpath if tag.category else None,
                },
            )
            row = result.fetchone()
            # We could do consistency checking here - there SHOULD be
            # only one, ever, but we could check...
            return row[0] > 0

    # TODO - do better than 'any' here please
    def _tag_from_row(self, row: Any) -> Tag:
        category = self._category_pool.get_category(row[3])
        return Tag(
            valid_from=None if row[0] is None else date_parse(row[0]),
            valid_to=None if row[1] is None else date_parse(row[1]),
            name=row[2],
            category=category,
        )

    def write_to(self, filename: Path) -> None:
        if filename.exists():
            raise ValueError("File already exists", filename)

        file_db = apsw.Connection(str(filename))
        with file_db.backup("main", self._sqlite_db, "main") as backup:
            backup.step()  # This can be split in to chunks if need be

    @classmethod
    def read_from(cls, filename: Path) -> "SqliteTimeSpan":
        file_db = apsw.Connection(str(filename))
        new_timespan = SqliteTimeSpan()
        with new_timespan._sqlite_db.backup("main", file_db, "main") as backup:
            backup.step()  # This can be split in to chunks if need be
        return new_timespan
