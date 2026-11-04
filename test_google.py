from google_calendar import get_calendar_service

service = get_calendar_service()

result = service.calendarList().list().execute()

for calendar in result.get("items", []):
    print(calendar["summary"])

print("Google Calendar 인증 성공!")