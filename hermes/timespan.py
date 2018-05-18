import datetime as dt
import sqlite3
from operator import attrgetter
from typing import Iterable, Optional, Set, Union, cast

import attr

from dateutil.parser import parse as date_parse

from .categorypool import BaseCategoryPool, CategoryPool, MutableCategoryPool
from .span import Span, Spannable
from .tag import Category, Tag


class BaseTimeSpan(Spannable):

    @property
    def category_pool(self) -> BaseCategoryPool:
        raise NotImplementedError("Subclasses must define this interface.")

    def iter_tags(self) -> Iterable["Tag"]:
        raise NotImplementedError("Subclasses must define this interface.")

    def filter(self, category: Union["Category", str]) -> "BaseTimeSpan":
        raise NotImplementedError("Subclasses must define this interface.")

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeSpan":
        raise NotImplementedError("Subclasses must define this interface.")

    def __len__(self):
        return len(list(self.iter_tags()))

    def __getitem__(  # noqa: F811
        self, key: Union[Optional[int], slice]
    ) -> "BaseTimeSpan":
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

        start = cast(dt.datetime, key.start)
        stop = cast(dt.datetime, key.stop)

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


class SqliteTimeSpan(BaseTimeSpan):
    """Sqlite-backed TimeSpan"""

    # The goal for this implementation is that it should be a really solid
    # performer for almost any use case, so long as the number of tags can
    # reasonably fit in memory. This particular class is a good candidate for
    # optimizations at the expense of readibility.

    def __init__(self, tags: Optional[Iterable[Tag]] = None) -> None:
        self._sqlite_db: sqlite3.Connection = sqlite3.connect(":memory:")
        self._category_pool: MutableCategoryPool = MutableCategoryPool()

        self._sqlite_db.row_factory = sqlite3.Row

        with self._sqlite_db as conn:
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
                    self.insert(tag)

    @property
    def category_pool(self) -> BaseCategoryPool:
        return cast(BaseCategoryPool, self._category_pool)

    def iter_tags(self) -> Iterable["Tag"]:
        cursor = self._sqlite_db.cursor()
        result = cursor.execute("SELECT valid_from, valid_to, name, category FROM tags")
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
        with self._sqlite_db as conn:
            query = """
            SELECT valid_from, valid_to, name, category
            FROM tags
            WHERE
                (valid_to IS NULL AND valid_from IS NULL) OR
                (valid_to IS NULL AND valid_from <= :finish_at) OR
                (valid_to >= :begins_at AND valid_from IS NULL) OR
                (valid_to >= :begins_at AND valid_from <= :finish_at)
            """
            result = conn.execute(
                query, {"begins_at": begins_at, "finish_at": finish_at}
            )
            for row in result:
                tags.append(self._tag_from_row(row))

        return SqliteTimeSpan(tags=tags)

    def _tag_from_row(self, row: sqlite3.Row) -> Tag:
        category = self._category_pool.get_category(row["category"])
        return Tag(
            valid_from=date_parse(row["valid_from"]),
            valid_to=date_parse(row["valid_to"]),
            name=row["name"],
            category=category,
        )

    def insert(self, tag: Tag) -> None:
        with self._sqlite_db as conn:
            category_str = tag.category.fullpath if tag.category else "sqlite3"
            category = self._category_pool.get_category(category_str, create=True)
            conn.execute(
                "INSERT INTO tags VALUES (:valid_from, :valid_to, :name, :category)",
                {
                    "valid_from": tag.valid_from,
                    "valid_to": tag.valid_to,
                    "name": tag.name,
                    "category": category.fullpath,
                },
            )
