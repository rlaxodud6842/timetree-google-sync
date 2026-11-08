
from datetime import timedelta
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]

KST = ZoneInfo("Asia/Seoul")


def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        "service-account.json",
        scopes=SCOPES
    )

    return build(
        "calendar",
        "v3",
        credentials=creds
    )


# TimeTree 일정을 Google Calendar 형식으로 변환
def make_google_event(event):
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

    return google_event


# 신규 일정 등록
def insert_event(service, calendar_id, event):
    google_event = make_google_event(event)

    result = service.events().insert(
        calendarId=calendar_id,
        body=google_event
    ).execute()

    print("등록 완료:", result["summary"])
    return result


# 기존 일정 수정
def update_event(service, calendar_id, google_event_id, event):
    google_event = make_google_event(event)

    result = service.events().update(
        calendarId=calendar_id,
        eventId=google_event_id,
        body=google_event
    ).execute()

    print("수정 완료:", result["summary"])
    return result


# 기존 일정 삭제
def delete_event(service, calendar_id, google_event_id):
    service.events().delete(
        calendarId=calendar_id,
        eventId=google_event_id
    ).execute()

    print("삭제 완료:", google_event_id)


# Google Calendar의 TimeTree 동기화 일정 조회
def get_existing_timetree_events(service, calendar_id):
    existing_events = {}
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
                existing_events[str(timetree_id)] = item

        page_token = result.get("nextPageToken")

        if not page_token:
            break

    return existing_events


# 기존 함수와의 호환성을 위해 유지
def get_existing_timetree_ids(service, calendar_id):
    return set(
        get_existing_timetree_events(
            service,
            calendar_id
        ).keys()
    )


# 기존 일정과 새 일정의 내용 비교
def is_event_changed(existing, new_event):
    new_google_event = make_google_event(new_event)

    if existing.get("summary") != new_google_event.get("summary"):
        return True

    if existing.get("location", "") != new_google_event.get("location", ""):
        return True

    if existing.get("description", "") != new_google_event.get("description", ""):
        return True

    old_start = existing.get("start", {})
    old_end = existing.get("end", {})

    new_start = new_google_event["start"]
    new_end = new_google_event["end"]

    if old_start.get("date") != new_start.get("date"):
        if old_start.get("dateTime") != new_start.get("dateTime"):
            return True

    if old_end.get("date") != new_end.get("date"):
        if old_end.get("dateTime") != new_end.get("dateTime"):
            return True

    return False
