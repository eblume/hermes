# -*- coding: utf-8 -*-
from collections import deque
import datetime as dt
import json
import os
from pathlib import Path
import re
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    NewType,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)
import warnings

from appdirs import user_data_dir
from google.auth.transport import Request
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from requests.utils import quote  # type: ignore    # mypy, plz....

from ..categorypool import BaseCategoryPool
from ..span import Span
from ..tag import Category, Tag
from ..timespan import (
    BaseTimeSpan,
    date_parse,
    InsertableTimeSpan,
    RemovableTimeSpan,
    SqliteTimeSpan,
)


class GoogleClient:
    """Google API client for OAuth2 User/Client credentials."""

    SERVICE_APP_NAME = "HermesCLI"
    SERVICE_APP_AUTHOR = "Hermes"
    SERVICE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    SERVICE_AUTH_URL = "https://oauth2.googleapis.com/o/oauth2/auth"
    SERVICE_SCOPES = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    DEFAULT_CLIENT_SECRETS_FILE = (
        Path(user_data_dir(SERVICE_APP_NAME, SERVICE_APP_AUTHOR)) / "gcal.json"
    )

    T = TypeVar("T", bound="GoogleClient")

    def __init__(self, session: AuthorizedSession, credentials: Credentials) -> None:
        """Use the `from_*` class methods to construct this client."""
        self._session = session
        self._credentials = credentials

    @property
    def session(self) -> AuthorizedSession:
        return self._session

    @property
    def credentials(self) -> Credentials:
        # TODO - refresh? is valid check?
        return self._credentials

    @property
    def access_token(self) -> Dict[str, Any]:
        return {
            "access_token": self.credentials.token,
            "refresh_token": self.credentials.refresh_token,
            "token_uri": self.SERVICE_TOKEN_URL,
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
        }

    def write_authorized_user_file(
        self, file: Path = None, redirect_uris: List[str] = None
    ) -> None:
        """Write a client_secrets file to the specified Path. A sensible default
        is chosen using app_dirs, on linux it is "~/.local/share/HermesCLI/gcal.json"

        THESE CREDENTIALS NEED TO BE KEPT SECURE! If you believe your
        credentials have been compromised, it is YOUR responsibility to
        deactivate them from the google cloud console:

            https://console.cloud.google.com/apis/credentials
        """
        if file is None:
            file = self.DEFAULT_CLIENT_SECRETS_FILE
            if not file.parent.exists():
                os.makedirs(file.parent)

        key_type = "web"
        if redirect_uris is None:
            key_type = "installed"
            redirect_uris = ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"]

        data = {
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
            "redirect_uris": redirect_uris,
            "auth_uri": self.SERVICE_AUTH_URL,
            "token_uri": self.SERVICE_TOKEN_URL,
        }

        file.write_text(json.dumps({key_type: data}))

    def write_access_token_file(self, file: Path) -> None:
        """Write the access token to a file. Note that this file is effectively
        a password, so keep it safe and secure! You should generally avoid
        using this and instead prefer to use the `from_local_web_server` or
        `from_console` constructors to avoid saving a token locally, but
        this can be useful in some cases. Example: this is used to automate
        integration testing in Hermes.

        No default path is given to force you to think about this. :)
        """
        file.write_text(json.dumps(self.access_token))

    @classmethod
    def from_access_token(
        cls: Type[T],
        refresh_callback: Callable[[T], None] = None,
        access_token: str = None,
        refresh_token: str = None,
        token_uri: str = SERVICE_TOKEN_URL,
        client_id: str = None,
        client_secret: str = None,
    ) -> T:
        """If the optional fields are all supplied, the token will auto-refresh when expired.

        If the token is refreshed and `refresh_callback` has been set, the callback
        will be called with a reference to the newly created client.
        """
        credentials = Credentials(
            access_token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=cls.SERVICE_SCOPES,
        )
        refreshed = False
        if credentials.expired:
            credentials.refresh(Request())
            refreshed = True
        session = AuthorizedSession(credentials)
        client = cls(session, credentials)
        if refreshed and refresh_callback is not None:
            refresh_callback(client)
        return client

    @classmethod
    def from_access_token_file(cls: Type[T], file: Path, update_file: bool = True) -> T:
        """Load the specified file as an access token for a new client.

        If `update_file` is `True` (default), then the specified file will be
        created if it did not exist (after prompting the user via a web browser
        popup dialog). If the file did exist (and `update_file` is True), and
        if the file's token was out of date and needed refreshing, then the
        file will be rewritten with the refreshed token."""
        if not file.exists() and update_file:
            client = cls.from_local_web_server()
            client.write_access_token_file(file)
        else:
            token = json.loads(file.read_text())

            def _refresh_cb(cb_client: "GoogleClient.T") -> None:
                if update_file:
                    cb_client.write_access_token_file(file)

            client = cls.from_access_token(**token)
        return client

    @classmethod
    def from_local_web_server(cls: Type[T], secrets_file: Path = None) -> T:
        """Create a GoogleClient by running the web server flow. Spawns a
        short-lived local web server to receive the OAuth2 callback. Attempts
        to open the user's browser, or else prompts them to go to a URL."""
        if secrets_file is None:
            secrets_file = cls.DEFAULT_CLIENT_SECRETS_FILE
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_file), scopes=cls.SERVICE_SCOPES
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 'scope creep'
            flow.run_local_server()  # NB: there are a lot of options that could be passed here.
        session = flow.authorized_session()
        return cls(session, flow.credentials)

    @classmethod
    def from_console(cls: Type[T], secrets_file: Path = None) -> T:
        """Create a GoogleClient by running the in-console flow. Blocks on user
        input."""
        if secrets_file is None:
            secrets_file = cls.DEFAULT_CLIENT_SECRETS_FILE
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_file), scopes=cls.SERVICE_SCOPES
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 'scope creep'
            flow.run_console()
        session = flow.authorized_session()
        return cls(session, flow.credentials)


CalendarID = NewType("CalendarID", str)
primary = CalendarID("primary")


class GoogleCalendarAPI:
    API_PREFIX = "https://www.googleapis.com/calendar/v3"
    DEFAULT_BASE_CATEGORY = Category("GCal", None)

    def __init__(self, client: GoogleClient, base_category: Category = None) -> None:
        self._client = client
        self.base_category = base_category or self.DEFAULT_BASE_CATEGORY

    def _get(self, endpoint: str, params: Dict[str, str] = None) -> Dict[str, Any]:
        return self._client.session.get(
            f"{self.API_PREFIX}{endpoint}", params=params
        ).json()

    def _paginated_get(
        self, endpoint: str, params: Dict[str, str] = None
    ) -> Iterable[Dict[str, Any]]:
        _params = dict(params) if params else {}
        while True:
            response = self._get(endpoint, params=_params)
            yield from response["items"]
            page_token = response.get("nextPageToken", None)
            if not page_token:
                break
            _params["pageToken"] = page_token

    def _post(
        self, endpoint: str, params: Dict[str, str] = None, data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        rv = self._client.session.post(
            f"{self.API_PREFIX}{endpoint}",
            params=params,
            data=json.dumps(data),
            headers={"content-type": "application/json"},
        )
        assert rv.status_code == 200
        return rv.json()

    def _delete(self, endpoint: str, params: Dict[str, str] = None) -> None:
        return self._client.session.delete(
            f"{self.API_PREFIX}{endpoint}", params=params
        )

    # Public members

    def calendars(self) -> Iterable[CalendarID]:
        for item in self._paginated_get("/users/me/calendarList"):
            yield CalendarID(item["id"])

    def calendar_info(self, calendar_id: CalendarID = primary) -> Dict[str, Any]:
        return self._get(f"/calendars/{quote(calendar_id)}")

    def calendar_info_by_name(self, name: str) -> Dict[str, Any]:
        for item in self._paginated_get("/users/me/calendarList"):
            if item["summary"] == name:
                # TODO - the calendarList / calendar.get info is disjoint,
                # maybe we can do better by combining it?
                return self.calendar_info(item["id"])
        raise KeyError("Specified name was not found", name)

    def create_event(
        self, tag: Tag, calendar_id: CalendarID = primary
    ) -> Dict[str, Any]:
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
        return self._post(f"/calendars/{quote(calendar_id)}/events", data=event)

    def remove_events(self, tag: Tag, calendar_id: CalendarID = primary) -> None:
        """Remove all events that exactly correspond to this tag."""
        start = tag.valid_from
        end = tag.valid_to
        if start is None or end is None:
            raise ValueError("Events must have concrete start and end times")
        if end.tzinfo != start.tzinfo:
            end = end.astimezone(start.tzinfo)

        for event_info in self._paginated_get(
            f"/calendars/{quote(calendar_id)}/events",
            params={"timeMax": end.isoformat(), "timeMin": start.isoformat()},
        ):
            self._delete(
                f"/calendars/{quote(calendar_id)}/events/{quote(event_info['id'])}"
            )

    def load_timespan(
        self, calendar_id: CalendarID = primary, span: Span = None
    ) -> SqliteTimeSpan:
        return SqliteTimeSpan(tags=self.events(calendar_id, span))

    def events(
        self, calendar_id: CalendarID = None, span: Span = None
    ) -> Iterable[Tag]:
        if calendar_id is None:
            calendar_ids = list(self.calendars())
        else:
            calendar_ids = [calendar_id]

        if span is None:
            span = Span(None, None)

        for cid in calendar_ids:
            calendar = self.calendar_info(cid)
            title = calendar.get("summary", f"Imported GCal")
            title = re.sub(r"[^a-zA-Z0-9:\- ]*", "", title)
            category = self.base_category / title

            query_params = {
                "calendarId": cid,
                "timeZone": "Etc/UTC",  # TODO - figure out how to get this to play nice with dateutil
                "maxResults": "2500",
                "singleEvents": "true",  # Don't expand recurring events (hermes doesn't use them anyway)
                "orderBy": "startTime",  # requires singleEvents = True
            }
            begins_at = ""
            if span.begins_at is not None:
                begins_at = span.begins_at.isoformat() + (
                    "Z" if span.begins_at.tzinfo is None else ""
                )

            finish_at = ""
            if span.finish_at is not None:
                finish_at = span.finish_at.isoformat() + (
                    "Z" if span.finish_at.tzinfo is None else ""
                )
            if begins_at:
                query_params["timeMin"] = begins_at
            if finish_at:
                query_params["timeMax"] = finish_at

            for event in self._paginated_get(
                f"/calendars/{quote(calendar_id)}/events", params=query_params
            ):
                start = event.get("start")
                end = event.get("end")
                valid_from = (
                    date_parse(start.get("dateTime", start.get("date", None)))
                    if start
                    else None
                )
                valid_to = (
                    date_parse(end.get("dateTime", end.get("date", None)))
                    if end
                    else None
                )
                yield Tag(
                    name=event.get("summary", event.get("id")),
                    category=category,
                    valid_from=valid_from,
                    valid_to=valid_to,
                )


T = TypeVar("T", bound="GoogleCalendarTimeSpan")


class GoogleCalendarTimeSpan(InsertableTimeSpan, RemovableTimeSpan):
    "Convenience wrapper that bridges from the GoogleCalendarClient to a TimeSpan."

    def __init__(
        self,
        calendar_id: CalendarID = primary,
        load_events: bool = True,
        load_span: Span = None,
        client: GoogleCalendarAPI = None,
    ):
        """Load the specified calendar. load_events=False can be useful to insert events without loading existing ones."""
        if client is None:
            client = GoogleCalendarAPI(GoogleClient.from_local_web_server())
        else:
            self.client = client
        self.calendar_id = calendar_id
        self._span = load_span if load_span is not None else Span(None, None)

        calendar_info = self.client.calendar_info(calendar_id)
        self.calendar_name = calendar_info.get(
            "summary", f"Unknown Calendar: {self.calendar_id}"
        )

        if load_events:
            self._cached_timespan = self.client.load_timespan(calendar_id, self._span)
        else:
            self._cached_timespan = SqliteTimeSpan()

        # Item( is_insert, tag ) -- is_insert == False means is delete
        self.dirty_queue: Deque[Tuple[bool, Tag]] = deque()

    @classmethod
    def calendar_by_name(
        cls: Type[T],
        calendar_name: str,
        ignore_case: bool = True,
        client: GoogleCalendarAPI = None,
        **kwargs,
    ) -> T:
        if client is None:
            client = GoogleCalendarAPI(GoogleClient.from_local_web_server())

        search_cal = calendar_name.lower() if ignore_case else calendar_name
        found_cal_id: Optional[CalendarID] = None
        for calendar_id in client.calendars():
            calendar_info = client.calendar_info(calendar_id)
            title = calendar_info.get("summary", "")
            if ignore_case:
                title = title.lower()
            if title.startswith(search_cal):
                found_cal_id = calendar_info.get("id")  # type: ignore
                break

        if found_cal_id is None:
            raise KeyError("Calendar not found")

        return cls(calendar_id=found_cal_id, client=client, **kwargs)

    @property
    def span(self) -> Span:
        return self._span

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
        return GoogleCalendarTimeSpan(
            calendar_id=self.calendar_id,
            load_span=Span(begins_at, finish_at),
            client=self.client,
        )

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
        if tag.span not in self.span:
            raise ValueError(
                "This event isn't within this timespan. Maybe try reslicing?"
            )
        self.insert_tag(tag)
        return tag

    def remove_events(
        self, event_name: Optional[str] = None, during: Optional[Span] = None
    ) -> None:
        if during is not None:
            window = self._cached_timespan.slice_with_span(during)
        else:
            window = self._cached_timespan

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
        self._cached_timespan = self.client.load_timespan(self.calendar_id, self.span)
