from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from zoneinfo import ZoneInfo


@dataclass
class Event:
    SYNC_SOURCE: ClassVar[str] = "timetree-sync-action"

    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str | None = None
    description: str | None = None
    recurrences: list[str] | None = None

    @classmethod
    def from_timetree(cls, event: dict):
        start_tz = ZoneInfo(event["start_timezone"])
        end_tz = ZoneInfo(event["end_timezone"])

        recurrences = [
            str(recurrence).strip()
            for recurrence in (event.get("recurrences") or [])
            if recurrence
        ]

        return cls(
            id=event["id"],
            title=event["title"],
            start=datetime.fromtimestamp(
                event["start_at"] / 1000,
                tz=start_tz,
            ),
            end=datetime.fromtimestamp(
                event["end_at"] / 1000,
                tz=end_tz,
            ),
            all_day=event["all_day"],
            location=event.get("location") or None,
            description=event.get("note") or None,
            recurrences=recurrences or None,
        )

    def google_recurrences(self) -> list[str]:
        if not self.recurrences:
            return []

        result = []

        for recurrence in self.recurrences:
            line = recurrence.strip()

            # For timed events, RFC 5545 requires UNTIL to be UTC when
            # DTSTART has a timezone. TimeTree can provide a date-only UNTIL,
            # so convert it to the end of that local day in UTC.
            if not self.all_day and line.upper().startswith("RRULE:"):
                parts = line.split(";")

                for index, part in enumerate(parts):
                    if not part.upper().startswith("UNTIL="):
                        continue

                    value = part.split("=", 1)[1]

                    if len(value) == 8 and value.isdigit():
                        local_until = datetime.strptime(
                            value,
                            "%Y%m%d",
                        ).replace(
                            hour=23,
                            minute=59,
                            second=59,
                            tzinfo=self.start.tzinfo,
                        )

                        utc_until = local_until.astimezone(
                            ZoneInfo("UTC")
                        ).strftime("%Y%m%dT%H%M%SZ")

                        parts[index] = f"UNTIL={utc_until}"

                line = ";".join(parts)

            result.append(line)

        return result

    def to_google(self, calendar_code: str) -> dict:
        event = {
            "summary": self.title,
            "extendedProperties": {
                "private": {
                    "sync_source": self.SYNC_SOURCE,
                    "timetree_calendar_code": calendar_code,
                    "timetree_id": self.id,
                }
            },
        }

        if self.all_day:
            event["start"] = {
                "date": self.start.strftime("%Y-%m-%d"),
            }
            event["end"] = {
                "date": self.end.strftime("%Y-%m-%d"),
            }
        else:
            event["start"] = {
                "dateTime": self.start.isoformat(),
                "timeZone": "Asia/Tokyo",
            }
            event["end"] = {
                "dateTime": self.end.isoformat(),
                "timeZone": "Asia/Tokyo",
            }

        if self.location:
            event["location"] = self.location

        if self.description:
            event["description"] = self.description

        recurrences = self.google_recurrences()
        if recurrences:
            event["recurrence"] = recurrences

        return event

    def equals_google(self, google_event: dict, calendar_code: str) -> bool:
        google = self.to_google(calendar_code)

        return (
            google.get("summary") == google_event.get("summary")
            and google.get("location") == google_event.get("location")
            and google.get("description") == google_event.get("description")
            and google.get("start") == google_event.get("start")
            and google.get("end") == google_event.get("end")
            and sorted(google.get("recurrence") or [])
            == sorted(google_event.get("recurrence") or [])
        )
