# -*- coding: utf-8 -*-
import datetime as dt
import re
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from appdirs import user_data_dir

from dateutil.parser import parse as date_parse

from googleapiclient import discovery
from googleapiclient.http import build_http

from oauth2client import client as oauth2_client, file, tools

from ..categorypool import BaseCategoryPool
from ..span import Span
from ..tag import Category, Tag
from ..timespan import BaseTimeSpan, SqliteTimeSpan


class GoogleServiceClient:
    # Subclasses should change to implement a service
    SERVICE_NAME = "DefaultService"  # will be part of a file name
    SERVICE_SCOPE = "http://www.example.com/api"

    # Probably won't need to change ever
    SERVICE_APP_NAME = "HermesCLI"
    SERVICE_APP_AUTHOR = "Hermes"
    SERVICE_APP_VERSION = "v3"

    def __init__(self, oauth_config: Optional[Path] = None):
        self.oauth_config_path = oauth_config
        self._service = None

    @property
    def service(self):  # type?
        if self._service:
            return self._service

        appname = self.SERVICE_APP_NAME
        appauthor = self.SERVICE_APP_AUTHOR
        service_name = self.SERVICE_NAME
        version = "v3"

        if self.oauth_config_path is None:
            config_dir: str = user_data_dir(appname, appauthor)
            # Eventually this needs to be replaced with an OAUTH service auth
            # (or something? maybe this already works??)
            self.oauth_config_path = Path(config_dir) / "gcal.json"
        client_secrets = str(self.oauth_config_path)

        token_store = file.Storage(service_name + ".token")
        with warnings.catch_warnings():
            # This warns on 'file not found' which is handled below.
            credentials = token_store.get()
        if credentials is None or credentials.invalid:
            flow = oauth2_client.flow_from_clientsecrets(
                client_secrets,
                scope=self.SERVICE_SCOPE,
                message=tools.message_if_missing(client_secrets),
            )
            credentials = tools.run_flow(flow, token_store)
        http = credentials.authorize(http=build_http())

        # TODO - support offline discovery file
        # (see discovery.build_from_document)
        self._service = discovery.build(
            service_name, version, http=http, cache_discovery=False
        )
        return self._service


class GoogleCalendarClient(GoogleServiceClient):
    SERVICE_NAME = "calendar"
    SERVICE_SCOPE = "https://www.googleapis.com/auth/calendar"

    DEFAULT_BASE_CATEGORY = Category("GCal", None)

    def __init__(
        self,
        begins_at: Optional[dt.datetime] = None,
        finish_at: Optional[dt.datetime] = None,
        calendar_id: Optional[str] = None,
        base_category: Category = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self.begins_at: Optional[dt.datetime] = begins_at
        self.finish_at: Optional[dt.datetime] = finish_at
        self.calendar_id: Optional[str] = calendar_id
        self.base_category: Optional[
            Category
        ] = base_category or self.DEFAULT_BASE_CATEGORY

    def calendars(self) -> Iterable[str]:
        page_token = None
        while True:
            calendar_list = (
                self.service.calendarList().list(pageToken=page_token).execute()
            )
            yield from calendar_list["items"]
            page_token = calendar_list.get("nextPageToken")
            if page_token is None:
                break

    def calendar(self, calendar_id: str = "primary") -> Dict[str, Any]:
        # Note that the info returned by calendars() is slightly disjoint.
        return self.service.calendars().get(calendarId=calendar_id).execute()

    def load_gcal(self, calendar_id: str = "primary") -> SqliteTimeSpan:
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
        return SqliteTimeSpan(set(self._tag_events_from_service(calendar_id)))

    def _tag_events_from_service(self, calendar_id: str) -> Iterable["Tag"]:
        calendar = self.calendar(calendar_id)
        title = calendar.get("summary", f"Imported GCal")
        title = re.sub(r"[^a-zA-Z0-9:\- ]*", "", title)
        category = Category(title, self.base_category)
        # calendar_resource = service.calendars().get(calendarId=calendar['id']).execute()
        # ^ unclear if there's anything useful there, I think we get the same data from calendarList
        # details that are different:
        # * etag is different. Totally unclear what this is.
        # * missing from calendar_resource: summaryOverride, backgroundColor, defaultReminders, accessRole, foregroundColor, colorId
        # * (none missing in reverse)
        # Conclusion: for at least some calendars, we get nothing useful
        for event in self._retrieve_events_from_calendar(calendar_id):
            start = event.get("start")
            end = event.get("end")
            valid_from = (
                date_parse(
                    start.get("dateTime", start.get("date", None)), ignoretz=True
                )
                if start
                else None
            )
            valid_to = (
                date_parse(end.get("dateTime", end.get("date", None)), ignoretz=True)
                if end
                else None
            )
            yield Tag(
                name=event.get("summary", event.get("id")),
                category=category,
                valid_from=valid_from,
                valid_to=valid_to,
            )

    def _retrieve_events_from_calendar(self, calendar_id: str):
        # https://developers.google.com/calendar/v3/reference/events/list
        begins_at: Optional[str] = None
        if self.begins_at is not None:
            begins_at = self.begins_at.isoformat() + (
                "Z" if self.begins_at.tzinfo is None else ""
            )

        finish_at: Optional[str] = None
        if self.finish_at is not None:
            finish_at = self.finish_at.isoformat() + (
                "Z" if self.finish_at.tzinfo is None else ""
            )

        page_token = None
        while True:
            query_params = {
                "calendarId": calendar_id,
                "timeZone": "Etc/UTC",  # TODO - figure out how to get this to play nice with dateutil
                "maxResults": 2500,
            }
            # There are tons of other query params to look in to. Also, live syncing!
            if begins_at:
                query_params["timeMin"] = begins_at
            if finish_at:
                query_params["timeMax"] = finish_at
            if page_token:
                query_params["pageToken"] = page_token

            events = self.service.events().list(**query_params).execute()
            yield from events["items"]

            page_token = events.get("nextPageToken", None)
            if page_token is None:
                break


class GoogleCalendarTimeSpan(BaseTimeSpan):
    "Convenience wrapper that bridges from the GoogleCalendarClient to a TimeSpan."

    def __init__(
        self,
        client: Optional[GoogleCalendarClient] = None,
        calendar_id: str = "primary",
    ):
        if client is None:
            self.client = GoogleCalendarClient()
        else:
            self.client = client
        self.calendar_id = calendar_id

        if calendar_id is not None:
            self._cached_timespan = self.client.load_gcal(self.calendar_id)
        else:
            self._cached_timespan = SqliteTimeSpan()

        self.client = GoogleCalendarClient()

    @property
    def span(self) -> Span:
        return self._cached_timespan.span

    @property
    def category_pool(self) -> BaseCategoryPool:
        return self._cached_timespan.category_pool

    def iter_tags(self) -> Iterable["Tag"]:
        return self._cached_timespan.iter_tags()

    def filter(self, category: Union["Category", str]) -> BaseTimeSpan:
        return self._cached_timespan.filter(category)

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "BaseTimeSpan":
        return self._cached_timespan.reslice(begins_at, finish_at)
