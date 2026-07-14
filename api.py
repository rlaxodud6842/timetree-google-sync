"""Unofficial API client for TimeTree."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import requests

_LOGGER = logging.getLogger(__name__)

WEB_BASEURI = "https://timetreeapp.com"
API_BASEURI = "https://timetreeapp.com/api/v1"
API_USER_AGENT = "web/2.1.0/en"
DEFAULT_TIMEOUT = 10


class TimeTreeApiError(Exception):
    """Raised when the TimeTree API returns an unexpected response."""


class TimeTreeAuthError(TimeTreeApiError):
    """Raised when login fails."""


class _CsrfTokenParser(HTMLParser):
    """Extract the Rails CSRF token from TimeTree's HTML shell."""

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        attr_map = dict(attrs)
        if attr_map.get("name") == "csrf-token":
            self.token = attr_map.get("content")


class TimeTreeApi:
    """TimeTree API client.

    The client mirrors the TimeTree web app's internal API. It can be used
    directly, or with Home Assistant by passing a ``hass`` object that exposes
    ``async_add_executor_job``.
    """

    _RAW_UPDATE_FIELDS = {
        "all_day",
        "attendees",
        "category",
        "end_at",
        "end_timezone",
        "label_id",
        "location",
        "note",
        "recurrences",
        "start_at",
        "start_timezone",
        "title",
        "type",
        "url",
    }

    def __init__(
        self,
        hass: Any | None,
        email: str,
        password: str,
        *,
        session: requests.Session | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._hass = hass
        self._email = email
        self._password = password
        self._session_id: str | None = None
        self._csrf_token: str | None = None
        self._user_id: int | None = None
        self._session = session or requests.Session()
        self._timeout = timeout

    @property
    def session_id(self) -> str | None:
        """Return the current TimeTree session id, if logged in."""
        return self._session_id

    def _headers(
        self, *, json_content: bool = False, csrf_token: str | None = None
    ) -> dict[str, str]:
        headers = {"X-Timetreea": API_USER_AGENT}
        if json_content:
            headers["Content-Type"] = "application/json"
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        return headers

    def _login(self) -> bool:
        """Log in to TimeTree and get a session id."""
        url = f"{API_BASEURI}/auth/email/signin"
        payload = {
            "uid": self._email,
            "password": self._password,
            "uuid": uuid.uuid4().hex,
        }
        headers = self._headers(json_content=True)

        _LOGGER.debug("Attempting login for user: %s", self._email)

        try:
            response = self._session.put(
                url, json=payload, headers=headers, timeout=self._timeout
            )
        except requests.RequestException as err:
            _LOGGER.error("Login connection error: %s", err)
            raise TimeTreeAuthError(f"Connection error: {err}") from err

        if response.status_code != 200:
            _LOGGER.error(
                "Login failed. Status: %s, Response: %s",
                response.status_code,
                response.text,
            )
            raise TimeTreeAuthError("Invalid credentials")

        self._session_id = response.cookies.get("_session_id")
        if not self._session_id:
            self._session_id = self._session.cookies.get("_session_id")
        if not self._session_id:
            raise TimeTreeAuthError("Login succeeded but no session cookie was returned")

        self._session.cookies.set("_session_id", self._session_id)
        _LOGGER.debug("Login successful. Session ID acquired.")
        return True

    def _get_csrf_token(self) -> str:
        """Get and cache a CSRF token required for mutating requests."""
        if self._csrf_token:
            return self._csrf_token
        if not self._session_id:
            self._login()

        response = self._session.get(
            f"{WEB_BASEURI}/calendars",
            headers=self._headers(),
            timeout=self._timeout,
        )

        if response.status_code == 401:
            _LOGGER.debug("Token expired during CSRF fetch. Re-logging in.")
            self._login()
            response = self._session.get(
                f"{WEB_BASEURI}/calendars",
                headers=self._headers(),
                timeout=self._timeout,
            )

        if response.status_code != 200:
            raise TimeTreeApiError(
                f"Could not fetch CSRF token. Status {response.status_code}: {response.text}"
            )

        parser = _CsrfTokenParser()
        parser.feed(response.text)
        if not parser.token:
            raise TimeTreeApiError("Could not find CSRF token in TimeTree HTML")

        self._csrf_token = parser.token
        return self._csrf_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Mapping[str, Any] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        retry_auth: bool = True,
        json_content: bool | None = None,
    ) -> Any:
        """Perform an authenticated TimeTree request."""
        if not self._session_id:
            self._login()

        method = method.upper()
        unsafe_method = method in {"POST", "PUT", "DELETE"}
        if json_content is None:
            json_content = json_payload is not None or unsafe_method
        csrf_token = self._get_csrf_token() if unsafe_method else None

        response = self._session.request(
            method,
            f"{API_BASEURI}{path}",
            headers=self._headers(json_content=json_content, csrf_token=csrf_token),
            json=json_payload,
            timeout=self._timeout,
        )

        if response.status_code == 401 and retry_auth:
            _LOGGER.debug("Token expired during %s %s. Re-logging in.", method, path)
            self._csrf_token = None
            self._login()
            csrf_token = self._get_csrf_token() if unsafe_method else None
            response = self._session.request(
                method,
                f"{API_BASEURI}{path}",
                headers=self._headers(json_content=json_content, csrf_token=csrf_token),
                json=json_payload,
                timeout=self._timeout,
            )

        if response.status_code == 422 and retry_auth and unsafe_method:
            _LOGGER.debug("Refreshing CSRF token after 422 on %s %s.", method, path)
            self._csrf_token = None
            csrf_token = self._get_csrf_token()
            response = self._session.request(
                method,
                f"{API_BASEURI}{path}",
                headers=self._headers(json_content=json_content, csrf_token=csrf_token),
                json=json_payload,
                timeout=self._timeout,
            )

        if response.status_code not in expected_statuses:
            _LOGGER.error(
                "TimeTree API error on %s %s. Status: %s, Body: %s",
                method,
                path,
                response.status_code,
                response.text,
            )
            raise TimeTreeApiError(f"API Error {response.status_code}: {response.text}")

        if not response.text:
            return {}

        try:
            return response.json()
        except ValueError:
            return response.text

    def _get_calendars(self) -> list[dict[str, Any]]:
        """Get the user's active calendars."""
        _LOGGER.debug("Fetching calendars...")
        data = self._request("GET", "/calendars?since=0")
        return [
            {"id": c["id"], "name": c["name"], "code": c.get("alias_code")}
            for c in data.get("calendars", [])
            if c.get("deactivated_at") is None
        ]

    def _get_user(self) -> dict[str, Any]:
        """Get the signed-in TimeTree user."""
        data = self._request("GET", "/user")
        user = data.get("user", {})
        if "id" in user:
            self._user_id = user["id"]
        return user

    def _get_user_id(self) -> int:
        """Get and cache the signed-in TimeTree user id."""
        if self._user_id is None:
            self._get_user()
        if self._user_id is None:
            raise TimeTreeApiError("Could not determine the signed-in user id")
        return self._user_id

    def _get_events_recur(self, calendar_id: str | int, since: int) -> list[dict[str, Any]]:
        """Fetch chunked events recursively."""
        _LOGGER.debug("Fetching chunked events since: %s", since)
        data = self._request(
            "GET", f"/calendar/{calendar_id}/events/sync?since={since}"
        )
        events = data.get("events", [])
        if data.get("chunk") is True:
            events.extend(self._get_events_recur(calendar_id, data["since"]))
        return events

    def _get_events(self, calendar_id: str | int) -> list[dict[str, Any]]:
        """Fetch all events for a calendar."""
        _LOGGER.debug("Fetching events for calendar: %s", calendar_id)
        data = self._request("GET", f"/calendar/{calendar_id}/events/sync")
        events = data.get("events", [])
        if data.get("chunk") is True:
            events.extend(self._get_events_recur(calendar_id, data["since"]))
        _LOGGER.debug("Fetched %s events.", len(events))
        return events

    def _build_create_payload(self, event_data: Mapping[str, Any]) -> dict[str, Any]:
        """Build the TimeTree payload for creating an event."""
        timezone = event_data.get("timezone", "UTC")
        payload = {
            "title": event_data.get("title", event_data.get("summary", "New Event")),
            "all_day": event_data.get("all_day", False),
            "start_at": event_data.get("start_at"),
            "start_timezone": event_data.get("start_timezone", timezone),
            "end_at": event_data.get("end_at"),
            "end_timezone": event_data.get("end_timezone", timezone),
            "label_id": event_data.get("label_id", 1),
            "note": event_data.get("note", event_data.get("description", "")),
            "location": event_data.get("location", ""),
            "attendees": event_data.get("attendees", [self._get_user_id()]),
            "recurrences": event_data.get("recurrences", []),
            "alerts": event_data.get("alerts", []),
            "attachment": event_data.get("attachment", {"virtual_user_attendees": []}),
            "category": event_data.get("category", 1),
        }

        for key in ("type", "url"):
            if key in event_data:
                payload[key] = event_data[key]

        return payload

    def _build_update_payload(self, event_data: Mapping[str, Any]) -> dict[str, Any]:
        """Build a partial TimeTree payload for updating an event."""
        payload: dict[str, Any] = {}

        for key in self._RAW_UPDATE_FIELDS:
            if key in event_data:
                payload[key] = event_data[key]

        aliases = {
            "summary": "title",
            "description": "note",
        }
        for source, target in aliases.items():
            if source in event_data:
                payload[target] = event_data[source]

        timezone = event_data.get("timezone")
        if timezone is not None:
            if "start_timezone" not in payload:
                payload["start_timezone"] = timezone
            if "end_timezone" not in payload:
                payload["end_timezone"] = timezone

        self._copy_datetime_fields(event_data, payload)
        return payload

    def _copy_datetime_fields(
        self, event_data: Mapping[str, Any], payload: dict[str, Any]
    ) -> None:
        """Accept Home Assistant-style date fields as a convenience."""
        start_dt = event_data.get("start_date_time")
        end_dt = event_data.get("end_date_time")
        timezone = str(event_data.get("timezone", "UTC"))

        if start_dt is not None or end_dt is not None:
            if start_dt is not None:
                payload["start_at"] = int(start_dt.timestamp() * 1000)
            if end_dt is not None:
                payload["end_at"] = int(end_dt.timestamp() * 1000)
            payload.setdefault("all_day", False)
            payload.setdefault("start_timezone", timezone)
            payload.setdefault("end_timezone", timezone)
            return

        start_date = event_data.get("start_date")
        end_date = event_data.get("end_date")
        if start_date is None and end_date is None:
            return

        tz = ZoneInfo(timezone)
        if start_date is not None:
            payload["start_at"] = self._date_to_ms(start_date, tz)
        if end_date is not None:
            payload["end_at"] = self._date_to_ms(end_date, tz)
        payload.setdefault("all_day", True)
        payload.setdefault("start_timezone", timezone)
        payload.setdefault("end_timezone", timezone)

    @staticmethod
    def _date_to_ms(value: date, timezone: ZoneInfo) -> int:
        dt_value = datetime.combine(value, time.min).replace(tzinfo=timezone)
        return int(dt_value.timestamp() * 1000)

    def _create_event(self, calendar_id: str | int, event_data: Mapping[str, Any]) -> Any:
        """Create a new event in TimeTree."""
        payload = self._build_create_payload(event_data)
        _LOGGER.debug("Sending create event payload: %s", json.dumps(payload, default=str))
        response = self._request(
            "POST",
            f"/calendar/{calendar_id}/event",
            json_payload=payload,
            expected_statuses=(200, 201),
        )
        _LOGGER.debug("TimeTree create response: %s", json.dumps(response, default=str))
        return response

    def _update_event(
        self, calendar_id: str | int, event_id: str, event_data: Mapping[str, Any]
    ) -> Any:
        """Update an event in TimeTree.

        TimeTree's web app sends a partial JSON object to this endpoint. For
        example, changing only the title uses ``{"title": "New title"}``.
        """
        payload = self._build_update_payload(event_data)
        if not payload:
            raise ValueError("event_data must contain at least one update field")

        _LOGGER.debug("Sending update event payload: %s", json.dumps(payload, default=str))
        response = self._request(
            "PUT",
            f"/calendar/{calendar_id}/event/{event_id}",
            json_payload=payload,
        )
        _LOGGER.debug("TimeTree update response: %s", json.dumps(response, default=str))
        return response

    def _delete_event(self, calendar_id: str | int, event_id: str) -> Any:
        """Delete an event from TimeTree."""
        _LOGGER.debug("Deleting event %s from calendar %s", event_id, calendar_id)
        response = self._request(
            "DELETE",
            f"/calendar/{calendar_id}/event/{event_id}",
            expected_statuses=(200, 204),
        )
        _LOGGER.debug("TimeTree delete response: %s", json.dumps(response, default=str))
        return response

    async def _run_in_executor(self, func: Any, *args: Any) -> Any:
        if self._hass is not None and hasattr(self._hass, "async_add_executor_job"):
            return await self._hass.async_add_executor_job(func, *args)
        return await asyncio.to_thread(func, *args)

    async def async_validate_and_get_calendars(self) -> list[dict[str, Any]]:
        return await self._run_in_executor(self._do_validate)

    def _do_validate(self) -> list[dict[str, Any]]:
        self._login()
        return self._get_calendars()

    async def async_get_events(self, calendar_id: str | int) -> list[dict[str, Any]]:
        return await self._run_in_executor(self._get_events, calendar_id)

    async def async_get_user(self) -> dict[str, Any]:
        return await self._run_in_executor(self._get_user)

    async def async_create_event(
        self, calendar_id: str | int, event_payload: Mapping[str, Any]
    ) -> Any:
        return await self._run_in_executor(self._create_event, calendar_id, event_payload)

    async def async_update_event(
        self, calendar_id: str | int, event_id: str, event_payload: Mapping[str, Any]
    ) -> Any:
        return await self._run_in_executor(
            self._update_event, calendar_id, event_id, event_payload
        )

    async def async_delete_event(self, calendar_id: str | int, event_id: str) -> Any:
        return await self._run_in_executor(self._delete_event, calendar_id, event_id)

    @staticmethod
    def parse_event(event_data: Mapping[str, Any]) -> dict[str, Any]:
        """Transform a raw TimeTree event into a calendar-friendly dict."""
        start_ts = event_data.get("start_at", 0)
        end_ts = event_data.get("end_at", 0)
        start_tz = event_data.get("start_timezone", "UTC")
        end_tz = event_data.get("end_timezone", "UTC")
        all_day = event_data.get("all_day", False)

        def convert_ts(ts: int, tz_name: str) -> datetime:
            try:
                if ts >= 0:
                    return datetime.fromtimestamp(ts / 1000, ZoneInfo(tz_name))
                return datetime.fromtimestamp(0, ZoneInfo(tz_name)) + timedelta(
                    seconds=int(ts / 1000)
                )
            except Exception:
                return datetime.now(ZoneInfo(tz_name))

        start_dt = convert_ts(start_ts, start_tz)
        end_dt = convert_ts(end_ts, end_tz)

        if all_day:
            start_val = start_dt.date()
            end_val = end_dt.date()
        else:
            start_val = start_dt
            end_val = end_dt

        event_id = event_data.get("uuid") or event_data.get("id")
        return {
            "id": event_data.get("id") or event_id,
            "uid": event_id,
            "summary": event_data.get("title", "No Title"),
            "start": start_val,
            "end": end_val,
            "all_day": all_day,
            "location": event_data.get("location"),
            "description": event_data.get("note"),
            "recurrences": event_data.get("recurrences"),
            "updated_at": event_data.get("updated_at"),
        }
