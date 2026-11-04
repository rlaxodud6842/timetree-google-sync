
import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]
KST = ZoneInfo("Asia/Seoul")


def get_calendar_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json", SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def insert_event(service, calendar_id, event):
    start = event["start"]
    end = event["end"]

    google_event = {
        "summary": event["summary"],
        "extendedProperties": {
            "private": {
                "timetree_id": str(event["id"])
            }
        }
    }

    if event.get("location"):
        google_event["location"] = event["location"]

    if event.get("description"):
        google_event["description"] = event["description"]

    if event["all_day"]:
        google_event["start"] = {
            "date": start.isoformat()
        }
        google_event["end"] = {
            "date": (end + timedelta(days=1)).isoformat()
        }
    else:
        if start.tzinfo is None:
            start = start.replace(tzinfo=KST)
        if end.tzinfo is None:
            end = end.replace(tzinfo=KST)

        google_event["start"] = {
            "dateTime": start.isoformat()
        }
        google_event["end"] = {
            "dateTime": end.isoformat()
        }

    result = service.events().insert(
        calendarId=calendar_id,
        body=google_event
    ).execute()

    print("등록 완료:", result["summary"])
    return result


def get_existing_timetree_ids(service, calendar_id):
    existing_ids = set()
    page_token = None

    while True:
        result = service.events().list(
            calendarId=calendar_id,
            pageToken=page_token
        ).execute()

        for item in result.get("items", []):
            timetree_id = (
                item.get("extendedProperties", {})
                .get("private", {})
                .get("timetree_id")
            )

            if timetree_id:
                existing_ids.add(str(timetree_id))

        page_token = result.get("nextPageToken")

        if not page_token:
            break

    return existing_ids
