# -*- coding: utf-8 -*-
import datetime as dt
import re
from pathlib import Path
from typing import Iterable, Optional, Union, cast

from appdirs import user_data_dir  # type: ignore

from dateutil.parser import parse as date_parse

from googleapiclient import discovery  # type: ignore
from googleapiclient.http import build_http  # type: ignore

from oauth2client import client as oauth2_client, file, tools  # type: ignore

from .categorypool import BaseCategoryPool
from .tag import Category, Tag
from .timespan import BaseTimeSpan, SqliteTimeSpan


class GoogleCalendarTimeSpan(BaseTimeSpan):
    """GoogleCalendar loaded in a Hermes interface.

    Use the `load_gcal` class method to load a TimeSpan with tag
    data directly. By instantiating an object of this class
    directly, the underlying TimeSpan will be cached for the
    lifetime of this wrapper. Either way works, pick the flavor
    you're more comfortable with.
    """

    def __init__(self):
        self._cached_timespan: BaseTimeSpan = type(self).load_gcal()

    @property
    def category_pool(self) -> BaseCategoryPool:
        return cast(BaseCategoryPool, self._cached_timespan.category_pool)

    def iter_tags(self) -> Iterable["Tag"]:
        yield from self._cached_timespan.iter_tags()

    def filter(self, category: Union["Category", str]) -> "BaseTimeSpan":
        return self._cached_timespan.filter(category)

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeSpan":
        return self._cached_timespan.reslice(begins_at, finish_at)

    @classmethod
    def load_gcal(
        cls,
        oauth_config: Optional[Path] = None,
        base_category: Category = Category("GCal", None),
    ) -> BaseTimeSpan:
        """Create a TimeSpan from the specified `ouath_config` file.

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
        return SqliteTimeSpan(set(cls._tag_events_from_service(base_category, service)))

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
