# -*- coding: utf-8 -*-
import datetime as dt
import re
import warnings
from pathlib import Path
from typing import Iterable, Optional, Union

from appdirs import user_data_dir

from dateutil.parser import parse as date_parse

from googleapiclient import discovery
from googleapiclient.http import build_http

from oauth2client import client as oauth2_client, file, tools

from ..categorypool import BaseCategoryPool
from ..tag import Category, Tag
from ..timespan import BaseTimeSpan, SqliteTimeSpan


class GoogleCalendarTimeSpan(BaseTimeSpan):
    """GoogleCalendar loaded in a Hermes interface.

    Use the `load_gcal` class method to load a TimeSpan with tag data directly.
    By instantiating an object of this class directly, the underlying TimeSpan
    will be cached for the lifetime of this wrapper. Either way works, pick the
    flavor you're more comfortable with.
    """

    DEFAULT_BASE_CATEGORY = Category("GCal", None)

    def __init__(
        self,
        begins_at: Optional[dt.datetime] = None,
        finish_at: Optional[dt.datetime] = None,
        oauth_config: Optional[Path] = None,
        base_category: Category = None,
    ) -> None:
        self._cached_timespan: Optional[BaseTimeSpan] = None

        self.begins_at: Optional[dt.datetime] = begins_at
        self.finish_at: Optional[dt.datetime] = finish_at
        self.oauth_config_path: Optional[Path] = oauth_config
        self.base_category: Optional[
            Category
        ] = base_category or self.DEFAULT_BASE_CATEGORY

    def _warm_cache(self) -> SqliteTimeSpan:
        cache = self.load_gcal()
        self._cached_timespan = cache
        return cache

    @property
    def span(self):
        cache = self._warm_cache()
        return cache.span

    @property
    def category_pool(self) -> BaseCategoryPool:
        cache = self._warm_cache()
        return cache.category_pool

    def iter_tags(self) -> Iterable["Tag"]:
        cache = self._warm_cache()
        yield from cache.iter_tags()

    def filter(self, category: Union["Category", str]) -> "BaseTimeSpan":
        cache = self._warm_cache()
        return cache.filter(category)

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "GoogleCalendarTimeSpan":
        self.begins_at = begins_at
        self.finish_at = finish_at
        self._cached_timespan = self.load_gcal()
        return self

    def load_gcal(
        self,
        begins_at: Optional[dt.datetime] = None,
        finish_at: Optional[dt.datetime] = None,
        oauth_config: Optional[Path] = None,
        base_category: Category = None,
    ) -> SqliteTimeSpan:
        """Create a TimeSpan from the specified `ouath_config` file.

        THIS WILL BLOCK AND REQUIRE USER INPUT on the first time that it is run
        on your system, in order to sign you in!

        `oauth_config` should be a file that contains google OAuth credentials.
        Currently, ALL calendar events from ALL calendars are downloaded, but
        filtering options will be available in the future. If left as `None`,
        the default will be used from `appdirs`, which uses OS-aware
        configuration directory schemes. See `appdirs` for more information.
        The default config file must be named 'gcal.json' inside the
        `appdirs.user_data_dir()`, which is typically one of:

        'C:\\Users\\erich\\AppData\\Local\\Hermes\\HermesCLI'
        '/home/erich/.local/share/HermesCLI'
        '/Users/erich/Library/Application Support/HermesCLI'
        """
        begins_at = begins_at or self.begins_at
        finish_at = finish_at or self.finish_at
        base_category = (
            base_category or self.base_category or self.DEFAULT_BASE_CATEGORY
        )
        oauth_config = oauth_config or self.oauth_config_path

        # TODO - figure out a nicer way to handle OAuth cycle
        appname = "HermesCLI"
        appauthor = "Hermes"
        service_name = "calendar"
        version = "v3"

        if oauth_config is None:
            config_dir: str = user_data_dir(appname, appauthor)
            oauth_config = Path(config_dir) / "gcal.json"
        client_secrets = str(oauth_config)

        token_store = file.Storage(service_name + ".token")
        with warnings.catch_warnings():
            # This warns on 'file not found' which is handled below.
            credentials = token_store.get()
        if credentials is None or credentials.invalid:
            flow = oauth2_client.flow_from_clientsecrets(
                client_secrets,
                scope="https://www.googleapis.com/auth/calendar.readonly",
                message=tools.message_if_missing(client_secrets),
            )
            credentials = tools.run_flow(flow, token_store)
        http = credentials.authorize(http=build_http())

        # TODO - support offline discovery file
        # (see discovery.build_from_document)
        service = discovery.build(
            service_name, version, http=http, cache_discovery=False
        )
        return SqliteTimeSpan(
            set(
                self._tag_events_from_service(
                    begins_at, finish_at, base_category, service
                )
            )
        )

    def _tag_events_from_service(
        self,
        begins_at: Optional[dt.datetime],
        finish_at: Optional[dt.datetime],
        root_category: Category,
        service,
    ) -> Iterable["Tag"]:
        page_token = None
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            for i, calendar in enumerate(calendar_list["items"]):
                title = calendar.get(
                    "summaryOverride", calendar.get("summary", f"Imported GCal {i}")
                )
                title = re.sub(r"[^a-zA-Z0-9:\- ]*", "", title)
                category = Category(title, root_category)
                # calendar_resource = service.calendars().get(calendarId=calendar['id']).execute()
                # ^ unclear if there's anything useful there, I think we get the same data from calendarList
                # details that are different:
                # * etag is different. Totally unclear what this is.
                # * missing from calendar_resource: summaryOverride, backgroundColor, defaultReminders, accessRole, foregroundColor, colorId
                # * (none missing in reverse)
                # Conclusion: for at least some calendars, we get nothing useful
                for event in self._retrieve_events_from_calendar(
                    calendar, service, begins_at, finish_at
                ):
                    start = event.get("start")
                    end = event.get("end")
                    valid_from = (
                        date_parse(
                            start.get("dateTime", start.get("date", None)),
                            ignoretz=True,
                        )
                        if start
                        else None
                    )
                    valid_to = (
                        date_parse(
                            end.get("dateTime", end.get("date", None)), ignoretz=True
                        )
                        if end
                        else None
                    )
                    yield Tag(
                        name=event.get("summary", event.get("id")),
                        category=category,
                        valid_from=valid_from,
                        valid_to=valid_to,
                    )

            page_token = calendar_list.get("nextPageToken")
            if not page_token:
                break

    def _retrieve_events_from_calendar(
        self,
        calendar,
        service,
        begins_at: Optional[dt.datetime] = None,
        finish_at: Optional[dt.datetime] = None,
    ):
        # https://developers.google.com/calendar/v3/reference/events/list
        page_token = None
        while True:
            query_params = {
                "calendarId": calendar["id"],
                "timeZone": "Etc/UTC",  # TODO - figure out how to get this to play nice with dateutil
                "maxResults": 2500,
            }
            # There are tons of other query params to look in to. Also, live syncing!
            if begins_at:
                query_params["timeMin"] = begins_at.isoformat()
            if finish_at:
                query_params["timeMax"] = finish_at.isoformat()
            if page_token:
                query_params["pageToken"] = page_token

            events = service.events().list(**query_params).execute()
            yield from events["items"]

            page_token = events.get("nextPageToken", None)
            if page_token is None:
                break
