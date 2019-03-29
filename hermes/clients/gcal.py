# -*- coding: utf-8 -*-
import datetime as dt
import re
import warnings
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, Optional, Tuple, Type, TypeVar, Union

from appdirs import user_data_dir

from googleapiclient import discovery
from googleapiclient.http import build_http

from oauth2client import client as oauth2_client, file, tools

from ..categorypool import BaseCategoryPool
from ..span import Span, Spannable
from ..tag import Category, Tag
from ..timespan import (
    BaseTimeSpan,
    InsertableTimeSpan,
    RemovableTimeSpan,
    SqliteTimeSpan,
    date_parse,
)


class GoogleServiceClient:
    # Subclasses should change to implement a service
    SERVICE_NAME = "DefaultService"  # will be part of a file name
    SERVICE_SCOPE: Union[str, Iterable[str]] = "http://www.example.com/api"

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


class GoogleCalendarClient(GoogleServiceClient, Spannable):
    SERVICE_NAME = "calendar"
    SERVICE_SCOPE = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]

    DEFAULT_BASE_CATEGORY = Category("GCal", None)

    def __init__(
        self,
        begins_at: Optional[dt.datetime] = None,
        finish_at: Optional[dt.datetime] = None,
        base_category: Category = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self.begins_at: Optional[dt.datetime] = begins_at.astimezone(
            dt.timezone.utc
        ) if begins_at else None
        self.finish_at: Optional[dt.datetime] = finish_at.astimezone(
            dt.timezone.utc
        ) if finish_at else None
        self.base_category: Optional[
            Category
        ] = base_category or self.DEFAULT_BASE_CATEGORY

    @property
    def span(self) -> Span:
        return Span(begins_at=self.begins_at, finish_at=self.finish_at)

    def calendars(self) -> Iterable[Dict[str, Any]]:
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

    def calendar_by_name(self, calendar: str) -> Optional[Dict[str, Any]]:
        calendars = {c['summary']: c for c in self.calendars()}
        return calendars.get(calendar, None)

    def create_event(self, tag: Tag, calendar_id: str) -> Dict[str, Any]:
        if tag.valid_from is None or tag.valid_to is None:
            raise ValueError("Events must have concrete start and end times")
        start: dt.datetime = tag.valid_from
        end: dt.datetime = tag.valid_to
        event = {
            "summary": tag.name,
            "description": tag.category.fullpath if tag.category else "",
            "start": {"dateTime": start.isoformat(), "timeZone": start.tzname()},
            "end": {"dateTime": end.isoformat(), "timeZone": end.tzname()},
        }
        return (
            self.service.events().insert(calendarId=calendar_id, body=event).execute()
        )

    def remove_events(self, tag: Tag, calendar_id: str) -> None:
        if tag.valid_from is None or tag.valid_to is None:
            raise ValueError("Events must have concrete start and end times")
        start: str = tag.valid_from.isoformat()
        end: str = tag.valid_to.isoformat()
        page_token: Optional[str] = None
        while True:
            events = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    pageToken=page_token,
                    timeMax=end,
                    timeMin=start,
                    timeZone=tag.valid_from.tzname(),
                )
                .execute()
            )
            page_token = events.get("nextPageToken")
            for event in events["items"]:
                self.service.events().delete(
                    calendarId=calendar_id, eventId=event["id"]
                ).execute()
                # TODO - check success?
            if page_token is None:
                break

    def load_gcal(self, calendar_id: Optional[str] = None, progress: Optional[Callable[..., Iterable[Dict[str, Any]]]] = None) -> SqliteTimeSpan:
        """Create a TimeSpan from the specified `ouath_config` file.

        If `progress` is specified, it will wrap the download process, to (eg)
        allow for a progress bar to be displayed.

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
        return SqliteTimeSpan(
            set(self._tag_events_from_service(calendar_id or "primary", progress=progress))
        )

    def _tag_events_from_service(self, calendar_id: str, progress: Optional[Callable[..., Iterable[Dict[str, Any]]]] = None) -> Iterable["Tag"]:
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

        def _wrap_for_progress(events: Iterable[Dict[str, Any]]):
            if progress is None:
                yield from events
            else:
                last_event = None
                with progress(events) as bar:
                    for event in bar:
                        if last_event is not None:
                            bar.update((event['valid_from'] - last_event['valid_from']).total_seconds())
                        yield event
                        last_event = event

        for event in _wrap_for_progress(self._retrieve_events_from_calendar(calendar_id)):
            yield Tag(
                name=event.get("summary", event.get("id")),
                category=category,
                valid_from=event['valid_from'],
                valid_to=event['valid_to'],
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
                "singleEvents": "true",  # Don't expand recurring events (hermes doesn't use them anyway)
                "orderBy": "startTime",  # requires singleEvents = True
            }
            # There are tons of other query params to look in to. Also, live syncing!
            if begins_at:
                query_params["timeMin"] = begins_at
            if finish_at:
                query_params["timeMax"] = finish_at
            if page_token:
                query_params["pageToken"] = page_token

            events = self.service.events().list(**query_params).execute()
            for event in events["items"]:
                # Hide some goodies to avoid doing this multiple times
                start = event.get("start")
                end = event.get("end")
                event['valid_from'] = (
                    date_parse(start.get("dateTime", start.get("date", None)))
                    if start
                    else None
                )
                event['valid_to'] = (
                    date_parse(end.get("dateTime", end.get("date", None))) if end else None
                )
                yield event

            page_token = events.get("nextPageToken", None)
            if page_token is None:
                break


T = TypeVar("T", bound="GoogleCalendarTimeSpan")


class GoogleCalendarTimeSpan(InsertableTimeSpan, RemovableTimeSpan):
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

        calendar = self.client.calendar(self.calendar_id)
        self.calendar_name = calendar.get(
            "summary", f"Unknown Calendar: {self.calendar_id}"
        )

        self._cached_timespan = self.client.load_gcal(self.calendar_id)

        # Item( is_insert, tag ) -- is_insert == False means is delete
        self.dirty_queue: Deque[Tuple[bool, Tag]] = deque()

    @classmethod
    def calendar_by_name(
        cls: Type[T], calendar_name: str, ignore_case: bool = True, **client_kwargs
    ) -> T:
        client = GoogleCalendarClient(**client_kwargs)

        search_cal = calendar_name.lower() if ignore_case else calendar_name
        calendar_id: Optional[str] = None
        for calendar in client.calendars():
            title = calendar.get("summary", "")
            if ignore_case:
                title = title.lower()
            if title.startswith(search_cal):
                calendar_id = calendar.get("id")
                break

        if calendar_id is None:
            raise KeyError("Calendar not found")

        return cls(calendar_id=calendar_id, client=client)

    @property
    def span(self) -> Span:
        # TODO - do we need to enforce this span on the cached timeline?
        return self.client.span

    @property
    def category_pool(self) -> BaseCategoryPool:
        return self._cached_timespan.category_pool

    def iter_tags(self) -> Iterable["Tag"]:
        return self._cached_timespan.iter_tags()

    def filter(self, category: Union["Category", str]) -> BaseTimeSpan:
        """Note: This returns a NON-NETWORKED sqlite-backed timespan. It does
        NOT retain the google service connection. Filtering a google calendar
        is not currently supported, but you can use this method to approximate
        it by creating a new google calendar with the resulting timespan."""
        return self._cached_timespan.filter(category)

    def reslice(
        self, begins_at: Optional[dt.datetime], finish_at: Optional[dt.datetime]
    ) -> "GoogleCalendarTimeSpan":
        newclient = GoogleCalendarClient(
            begins_at=begins_at,
            finish_at=finish_at,
            base_category=self.client.base_category,
        )
        return GoogleCalendarTimeSpan(client=newclient, calendar_id=self.calendar_id)

    def insert_tag(self, tag: Tag) -> None:
        self._cached_timespan.insert_tag(tag)  # TODO - support rollbacks?
        self.dirty_queue.append((True, tag))

    def remove_tag(self, tag: Tag) -> bool:
        success = self._cached_timespan.remove_tag(tag)  # TODO - support rollbacks?
        self.dirty_queue.append((False, tag))
        return success

    def add_event(
        self, event_name: str, when: dt.datetime, duration: dt.timedelta
    ) -> Tag:
        start = when.astimezone(dt.timezone.utc)
        tag = Tag(
            name=event_name,
            category=self.client.base_category / self.calendar_name,
            valid_from=start,
            valid_to=start + duration,
        )
        self.insert_tag(tag)
        return tag

    def remove_events(
        self,
        event_name: Optional[str] = None,
        begins_at: Optional[dt.datetime] = None,
        finish_at: Optional[dt.datetime] = None,
    ) -> None:
        window = self._cached_timespan[begins_at:finish_at]  # type: ignore
        for tag in window.iter_tags():
            if event_name is None or tag.name == event_name:
                self.remove_tag(tag)

    def flush(self):
        """Write all pending changes to Google Calendar, and then re-sync."""
        # TODO - instead of a full resync, maybe use the streaming updates API?
        for is_insert, event in self.dirty_queue:
            if is_insert:
                # TODO - grab event id? not sure how to use it...
                self.client.create_event(tag=event, calendar_id=self.calendar_id)
            else:
                self.client.remove_events(tag=event, calendar_id=self.calendar_id)
        self.dirty_queue.clear()
        self._cached_timespan = self.client.load_gcal(self.calendar_id)
