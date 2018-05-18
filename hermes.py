"""Hermes, the Time Accountant"""

__author__ = """Erich Blume"""
__email__ = "blume.erich@gmail.com"
__version__ = "0.1.1a"

import datetime as dt
import functools
import re
import sqlite3
from operator import attrgetter
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping
from typing import Optional
from typing import Set
from typing import Union
from typing import cast
from typing import overload

from appdirs import user_data_dir  # type: ignore

import attr

from dateutil.parser import parse as date_parse

from googleapiclient import discovery  # type: ignore
from googleapiclient.http import build_http  # type: ignore

from oauth2client import client as oauth2_client  # type: ignore
from oauth2client import file  # type: ignore
from oauth2client import tools  # type: ignore


class Spannable:

    @property
    def span(self) -> "Span":
        raise NotImplementedError("Subclasses must define this interface")

    def __contains__(self, other: "Spannable") -> bool:
        """`other` overlaps at least in part with this object"""
        self_begins = self.span.begins_at or dt.datetime.min
        other_begins = other.span.begins_at or dt.datetime.min
        self_finish = self.span.finish_at or dt.datetime.max
        other_finish = other.span.finish_at or dt.datetime.max

        if other_begins < self_begins:
            return other_finish >= self_begins

        elif other_finish > self_finish:
            return other_begins <= self_finish

        else:
            return True


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Tag(Spannable):
    name: str
    category: Optional["Category"]
    valid_from: Optional[dt.datetime]
    valid_to: Optional[dt.datetime]

    @property
    def span(self):
        return Span(
            self.valid_from or dt.datetime.max, self.valid_to or dt.datetime.max
        )


@functools.total_ordering
@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Span(Spannable):
    """A time span, from one time to another.

    `begins_at` and `finish_at` may be set to None to signal a timespan of
    infinite duration. The Span itself still uses `None` to represent this
    case, but calling code may choose to use `dt.datetime.min`/`max`, or
    `dt.timedelta.max`, as needed. They may be set to the _same_ time to
    represent a single instant in time (this is also not handled specially).
    """
    begins_at: Optional[dt.datetime]
    finish_at: Optional[dt.datetime]

    @property
    def span(self) -> "Span":
        return self  # It's safe to just return self, due to immutability

    @property
    def duration(self) -> dt.timedelta:
        if self.finish_at is None or self.begins_at is None:
            return dt.timedelta.max

        return self.finish_at - self.begins_at

    def subspans(self, duration: dt.timedelta) -> Iterable["Span"]:
        start = self.span.begins_at or dt.datetime.min
        final_finish = self.span.finish_at or dt.datetime.max
        while start < final_finish:
            finish = min(start + duration, final_finish)
            yield Span(start, finish)

            start = finish


class BaseTimeAccount(Spannable):

    @property
    def category_pool(self) -> "CategoryPool":
        raise NotImplementedError("Subclasses must define this interface.")

    def iter_tags(self) -> Iterable["Tag"]:
        raise NotImplementedError("Subclasses must define this interface.")

    def filter(self, category: Union["Category", str]) -> "BaseTimeAccount":
        raise NotImplementedError("Subclasses must define this interface.")

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeAccount":
        raise NotImplementedError("Subclasses must define this interface.")

    def __len__(self):
        return len(list(self.iter_tags()))

    def __getitem__(  # noqa: F811
        self, key: Union[Optional[int], slice]
    ) -> "BaseTimeAccount":
        # Do a little type casting safety dance. Let's find a better way.
        type_error = key is None
        type_error |= not isinstance(key, slice)
        if type_error:
            raise TypeError("BaseTimeAccount objects must be sliced with datetime")

        key = cast(slice, key)

        # And a safety dance for our friends slice.start and slice.stop
        type_error |= key.start is not None and not isinstance(key.start, dt.datetime)
        type_error |= key.stop is not None and not isinstance(key.stop, dt.datetime)
        if type_error:
            raise TypeError("BaseTimeAccount objects must be sliced with datetime")

        start = cast(dt.datetime, key.start)
        stop = cast(dt.datetime, key.stop)

        return self.reslice(start, stop)

    def slice_with_span(self, span: Span) -> "BaseTimeAccount":
        return self.reslice(
            span.begins_at or dt.datetime.min, span.finish_at or dt.datetime.max
        )

    def subspans(self, duration: dt.timedelta) -> Iterable["BaseTimeAccount"]:
        for subspan in self.span.subspans(duration):
            yield self.slice_with_span(subspan)


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class TimeAccount(BaseTimeAccount):
    tags: Set[Tag]

    @property
    def category_pool(self):
        return CategoryPool(
            stored_categories={
                tag.category.fullpath: tag.category for tag in self.iter_tags()
            }
        )

    def iter_tags(self) -> Iterable["Tag"]:
        yield from self.tags

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "TimeAccount":
        selfspan = self.span
        newspan = Span(
            begins_at if begins_at is not None else selfspan.begins_at,
            finish_at if finish_at is not None else selfspan.finish_at,
        )
        tags = {t for t in self.tags if t in newspan}
        return TimeAccount(tags=tags)

    @property
    def span(self) -> "Span":
        tags = sorted(self.tags, key=attrgetter("valid_from"))
        oldest = min(tags, key=attrgetter("valid_from"))
        most_recent = max(tags, key=attrgetter("valid_to"))
        return Span(oldest.valid_from, most_recent.valid_to)

    def filter(self, category: Union["Category", str]) -> "BaseTimeAccount":
        if category is None:
            return self  # safe to return self due to immutability

        if isinstance(category, str):
            category = self.category_pool.get_category(category)
        cast(Category, category)

        return TimeAccount(tags={tag for tag in self.iter_tags() if tag in category})

    @classmethod
    def combine(cls, *others: "BaseTimeAccount") -> "TimeAccount":
        tags = {t for other in others for t in other.iter_tags()}
        return TimeAccount(tags)


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Category:
    name: str = attr.ib()
    parent: Optional["Category"]

    @name.validator
    def _check_name(self, _, value: str):
        pattern = r"[a-zA-Z][a-zA-Z0-9:\- ]*$"
        if not re.match(pattern, value):
            raise ValueError(f'Category name {value} must match "{pattern}"')

    def __truediv__(self, other: str):
        """Create a new category as a subcategory of this one.
        """
        return Category(other, parent=self)

    @property
    def fullpath(self):
        if self.parent is None:
            return self.name

        else:
            return f"{self.parent.fullpath}/{self.name}"

    def __contains__(self, tag: Tag) -> bool:
        tag_cat = tag.category
        while tag_cat is not None:
            if tag_cat == self:
                return True

            tag_cat = tag_cat.parent
        return False


class BaseCategoryPool:

    @property
    def categories(self) -> Mapping[str, Category]:
        raise NotImplementedError("Subclasses must define this interface")

    def __contains__(self, other: Any) -> bool:
        if not isinstance(other, Category):
            raise TypeError("CategoryPools contain only Category objects")

        other = cast(Category, other)
        return other.fullpath in self.categories

    def get_category(self, category_path: str) -> Category:
        """Return a Category using existing types stored in this pool.

        `category_path` must be a "/"-seperated string. Each substring will be
        a category name. As much as possible, this will use categories already
        stored in the category pool, and then new categories will be constructed.
        """
        category_names = [name.strip() for name in category_path.split("/")]
        if not category_names or not all(category_names):
            raise ValueError("Invalid category_path")

        return self._get_category_inner(category_names)

    def _get_category_inner(self, category_names: List[str]) -> Category:
        category_path = "/".join(category_names)
        if category_path in self.categories:
            return self.categories[category_path]

        else:
            parent_cat = None
            if len(category_names) > 1:
                parent_cat = self._get_category_inner(category_names[:-1])
            return Category(category_names[0], parent_cat)


class MutableCategoryPool(BaseCategoryPool):

    def __init__(self) -> None:
        self._categories: Dict[str, Category] = {}

    @property
    def categories(self) -> Mapping[str, Category]:
        return self._categories

    def get_category(self, category_path: str, create: bool = False) -> Category:
        if not create:
            return super().get_category(category_path)

        if category_path in self._categories:
            return self._categories[category_path]

        category_names = [name.strip() for name in category_path.split("/")]
        if not category_names or not all(category_names):
            raise ValueError("Invalid category_path")

        return self._create_categories(category_names)

    def _create_categories(self, category_names: List[str]) -> Category:
        """category_names is assumed to NOT exist in the pool yet"""
        parent_names = category_names[:-1]
        parent_path = "/".join(parent_names)
        parent: Optional[Category] = self._categories.get(parent_path, None)
        if parent_path and not parent:
            parent = self._create_categories(category_names[:-1])

        category = Category(category_names[-1], parent)
        self._categories["/".join(category_names)] = category
        return category


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class CategoryPool(BaseCategoryPool):
    """Pool of cached categories, searchable by name
    """
    stored_categories: Mapping[str, Category]

    @property
    def categories(self) -> Mapping[str, Category]:
        return self.stored_categories


# TODO - move this to some sort of external/plugin system where we are more
# comfortable with less code coverage, or something like that.


class GoogleCalendarTimeAccount(BaseTimeAccount):
    """GoogleCalendar loaded in a Hermes interface.

    Use the `load_gcal` class method to load a TimeAccount with tag
    data directly. By instantiating an object of this class
    directly, the underlying TimeAccount will be cached for the
    lifetime of this wrapper. Either way works, pick the flavor
    you're more comfortable with.
    """

    def __init__(self):
        self._cached_acct: BaseTimeAccount = type(self).load_gcal()

    @property
    def category_pool(self) -> CategoryPool:
        return self._cached_acct.category_pool

    def iter_tags(self) -> Iterable["Tag"]:
        yield from self._cached_acct.iter_tags()

    def filter(self, category: Union["Category", str]) -> "BaseTimeAccount":
        return self._cached_acct.filter(category)

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeAccount":
        return self._cached_acct.reslice(begins_at, finish_at)

    @classmethod
    def load_gcal(
        cls,
        oauth_config: Optional[Path] = None,
        base_category: Category = Category("GCal", None),
    ) -> BaseTimeAccount:
        """Create a TimeAccount from the specified `ouath_config` file.

        `oauth_config` should be a file that contains google OAuth
        credentials. Currently, ALL calendar events from ALL calendars are
        downloaded, but filtering options will be available in the future. If
        left as `None`, the default will be used from `appdirs`, which uses
        OS-aware configuration directory schemes. See `appdir` for more
        information. The default config file must be named `'gcal.json'` inside
        the `user_data_dir()`, which is typically one of:

        'C:\\Users\\erich\\AppData\\Local\\Hermes\\HermesCLI'
        '/home/erich/.config/hermescli'
        '/Users/erich/Library/Application Support/HermesCLI'
        """
        appname = "HermesCLI"
        appauthor = "Hermes"
        service_name = "calendar"
        version = "v3"

        if oauth_config is None:
            config_dir: str = user_data_dir(appname, appauthor)
            oauth_config = Path(config_dir) / "gcal.json"
        client_secrets = str(oauth_config)
        flow = oauth2_client.flow_from_clientsecrets(
            client_secrets,
            scope="https://www.googleapis.com/auth/calendar.readonly",
            message=tools.message_if_missing(client_secrets),
        )

        storage = file.Storage(service_name + ".dat")
        credentials = storage.get()
        if credentials is None or credentials.invalid:
            credentials = tools.run_flow(flow, storage)
        http = credentials.authorize(http=build_http())

        # TODO - support offline discovery file
        # (see discovery.build_from_document)
        service = discovery.build(service_name, version, http=http)
        return SqliteTimeAccount(
            set(cls._tag_events_from_service(base_category, service))
        )

    @classmethod
    def _tag_events_from_service(cls, root_category, service) -> Iterable["Tag"]:
        page_token = None
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            for i, calendar in enumerate(calendar_list["items"]):
                title = calendar.get(
                    "summaryOverride", calendar.get("summary", f"Imported GCal {i}")
                )
                title = re.sub("[^a-zA-Z0-9:\- ]*", "", title)
                # TODO check for a valid title (sorry future me)
                category = Category(title, root_category)
                # calendar_resource = service.calendars().get(calendarId=calendar['id']).execute()
                # ^ unclear if there's anything useful there, I think we get the same data from calendarList
                # details that are different:
                # * etag is different. Totally unclear what this is.
                # * missing from calendar_resource: summaryOverride, backgroundColor, defaultReminders, accessRole, foregroundColor, colorId
                # * (none missing in reverse)
                # Conclusion: for at least some calendars, we get nothing useful
                for event in cls._retrieve_events_from_calendar(calendar, service):
                    start = event.get("start")
                    end = event.get("end")
                    valid_from = date_parse(
                        start.get("dateTime", start.get("date", None))
                    ) if start else None
                    valid_to = date_parse(
                        end.get("dateTime", end.get("date", None))
                    ) if end else None
                    yield Tag(
                        name=event.get("summary", event.get("id")),
                        category=category,
                        valid_from=valid_from,
                        valid_to=valid_to,
                    )

            page_token = calendar_list.get("nextPageToken")
            if not page_token:
                break

    @classmethod
    def _retrieve_events_from_calendar(cls, calendar, service):
        # https://developers.google.com/calendar/v3/reference/events/list
        page_token = None
        while True:
            query_params = {"calendarId": calendar["id"], "timeZone": "Etc/UTC"}
            # There are tons of other query params to look in to. Also, live syncing!
            # (notable, 'timeMin' and 'timeMax' - also 'updatedMin', etc.)
            if page_token:
                query_params["pageToken"] = page_token

            events = service.events().list(**query_params).execute()
            yield from events["items"]

            page_token = events.get("nextPageToken", None)
            if page_token is None:
                break


class SqliteTimeAccount(BaseTimeAccount):
    """Sqlite-backed TimeAccount"""

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
    def category_pool(self) -> CategoryPool:
        return cast(CategoryPool, self._category_pool)

    def iter_tags(self) -> Iterable["Tag"]:
        cursor = self._sqlite_db.cursor()
        result = cursor.execute("SELECT valid_from, valid_to, name, category FROM tags")
        for row in result:
            yield self._tag_from_row(row)

    def filter(self, category: Union["Category", str]) -> "BaseTimeAccount":
        if isinstance(category, str):
            category = self._category_pool.get_category(category)

        return SqliteTimeAccount(tags=[t for t in self.iter_tags() if t in category])

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeAccount":
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

        return SqliteTimeAccount(tags=tags)

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
