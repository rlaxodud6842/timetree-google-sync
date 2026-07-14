# TimeTree Unofficial API

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![HTTP client](https://img.shields.io/badge/http-requests-2c7.svg)](https://requests.readthedocs.io/)
[![Tests](https://img.shields.io/badge/tests-unittest-brightgreen.svg)](#testing)
[![Status](https://img.shields.io/badge/status-experimental-orange.svg)](#disclaimer)

An unofficial Python client for the TimeTree web API.

This project was built by inspecting the current TimeTree web app behavior. It supports signing in with email/password, listing calendars, syncing events, creating events, updating events, and deleting events.

## Disclaimer

This is not an official TimeTree SDK. It uses internal web endpoints that may change without notice. Use it for personal automation and expect occasional maintenance when TimeTree changes its web app.

Do not commit real TimeTree credentials to GitHub. Use environment variables, a local `.env` file, or your own secret manager.

## Features

- Email/password login using the TimeTree web session API
- Automatic session cookie handling
- Automatic CSRF token discovery for create/update/delete requests
- Calendar listing
- Event sync with chunked pagination support
- Event creation
- Partial event updates
- Event deletion
- Async wrappers compatible with Home Assistant-style executor usage

## Installation

Clone the repository and install the only runtime dependency:

```bash
pip install -r requirements.txt
```

The client is currently a single-file module:

```python
from api import TimeTreeApi
```

## Quick Start

```python
from datetime import datetime, timedelta, timezone

from api import TimeTreeApi

api = TimeTreeApi(None, "you@example.com", "your-password")

calendar = api._get_calendars()[0]
calendar_id = calendar["id"]

start = datetime.now(timezone.utc) + timedelta(days=1)
end = start + timedelta(hours=1)

created = api._create_event(
    calendar_id,
    {
        "summary": "Coffee with Alex",
        "description": "Created from Python",
        "start_at": int(start.timestamp() * 1000),
        "end_at": int(end.timestamp() * 1000),
        "timezone": "UTC",
    },
)

event = created["event"]
event_id = event["id"]

api._update_event(calendar_id, event_id, {"summary": "Coffee with Alex - updated"})
api._delete_event(calendar_id, event_id)
```

For a runnable example that reads credentials from environment variables, see [examples/basic_usage.py](examples/basic_usage.py).

## Usage

### Authenticate and List Calendars

```python
api = TimeTreeApi(None, email, password)
calendars = api._get_calendars()
```

Each calendar item contains:

```python
{
    "id": 1071319023,
    "name": "Family",
    "code": "aliasCode"
}
```

### Fetch Events

```python
raw_events = api._get_events(calendar_id)
events = [api.parse_event(event) for event in raw_events]
```

`parse_event` returns calendar-friendly fields such as `uid`, `summary`, `start`, `end`, `location`, `description`, and `recurrences`.

### Create an Event

TimeTree expects timestamps in Unix milliseconds.

```python
api._create_event(
    calendar_id,
    {
        "summary": "Dentist",
        "description": "Bring insurance card",
        "location": "Clinic",
        "all_day": False,
        "start_at": 1783987200000,
        "end_at": 1783990800000,
        "timezone": "Asia/Tokyo",
    },
)
```

The client fills default fields used by the current TimeTree web app, including `label_id`, `attendees`, `recurrences`, `alerts`, and `attachment`.

### Update an Event

Updates are partial. Send only the fields you want to change:

```python
api._update_event(
    calendar_id,
    event_id,
    {
        "summary": "Dentist - rescheduled",
        "description": "New note text",
    },
)
```

Common aliases:

- `summary` becomes TimeTree `title`
- `description` becomes TimeTree `note`
- `timezone` fills `start_timezone` and `end_timezone` when needed

### Delete an Event

```python
api._delete_event(calendar_id, event_id)
```

### Async Methods

The async wrappers run the blocking HTTP work in an executor:

```python
await api.async_get_events(calendar_id)
await api.async_create_event(calendar_id, payload)
await api.async_update_event(calendar_id, event_id, payload)
await api.async_delete_event(calendar_id, event_id)
```

If a Home Assistant `hass` object is passed, the client uses `hass.async_add_executor_job`. Otherwise it falls back to `asyncio.to_thread`.

## Example

Run the sample script from the repository root:

```bash
cp .env.example .env
export TIMETREE_EMAIL="you@example.com"
export TIMETREE_PASSWORD="your-password"
python3 examples/basic_usage.py
```

The sample reads environment variables from your shell. If you use `.env`, load it with your preferred shell or dotenv tool first. By default the sample creates a temporary event, updates it, and deletes it in a `finally` block.

## Testing

Run the unit tests:

```bash
python3 -m unittest discover -s tests
```

Optionally compile-check the source:

```bash
python3 -m compileall api.py tests examples
```

## Notes for Maintainers

The current web app endpoints observed with Playwright are:

- `PUT /api/v1/auth/email/signin`
- `GET /api/v1/calendars?since=0`
- `GET /api/v1/calendar/{calendar_id}/events/sync`
- `POST /api/v1/calendar/{calendar_id}/event`
- `PUT /api/v1/calendar/{calendar_id}/event/{event_id}`
- `DELETE /api/v1/calendar/{calendar_id}/event/{event_id}`

Mutating requests require `X-CSRF-Token`. The client fetches it from the TimeTree HTML shell at `/calendars`.
