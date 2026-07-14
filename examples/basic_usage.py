"""Basic TimeTree unofficial API usage.

Run from the repository root:

    export TIMETREE_EMAIL="you@example.com"
    export TIMETREE_PASSWORD="your-password"
    python3 examples/basic_usage.py
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from api import TimeTreeApi


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    email = require_env("TIMETREE_EMAIL")
    password = require_env("TIMETREE_PASSWORD")

    api = TimeTreeApi(None, email, password)
    calendars = api._get_calendars()
    if not calendars:
        raise SystemExit("No active TimeTree calendars found.")

    calendar = calendars[0]
    calendar_id = calendar["id"]
    print(f"Using calendar: {calendar['name']} ({calendar_id})")

    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(hours=1)

    event_id = None
    try:
        created = api._create_event(
            calendar_id,
            {
                "summary": "TimeTree API sample",
                "description": "Created by examples/basic_usage.py",
                "start_at": int(start.timestamp() * 1000),
                "end_at": int(end.timestamp() * 1000),
                "timezone": "UTC",
            },
        )
        event = created["event"]
        event_id = event["id"]
        print(f"Created event: {event_id}")

        updated = api._update_event(
            calendar_id,
            event_id,
            {"summary": "TimeTree API sample - updated"},
        )
        print(f"Updated title: {updated['event']['title']}")
    finally:
        if event_id:
            api._delete_event(calendar_id, event_id)
            print(f"Deleted event: {event_id}")


if __name__ == "__main__":
    main()
