from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING, overload, Literal, Annotated, Union
from abc import ABC, abstractmethod
from pytz import timezone as pytz_timezone
import yaml

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3 import Event as CalendarEvent
    from googleapiclient._apis.tasks.v1 import Task as CalendarTask
from pydantic import BaseModel, model_validator, TypeAdapter, Field, field_validator


class Serializable(ABC):
    @abstractmethod
    def JSON(self) -> dict[str, Any]:
        ...

class Reminder(BaseModel):
    method: str = "popup"
    minutes: int

class DailyTask(BaseModel, Serializable):
    kind: Literal["Task"] = "Task"
    title: str

    due: datetime
    notes: Optional[str] = None

    def JSON(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "due": self.due.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "notes": self.notes
        }

    @field_validator("due", mode="before")
    @classmethod
    def parse_italian_date(cls, value):
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass  # lascia che pydantic tenti il parsing standard (ISO)
        return value

    @classmethod
    def from_google(cls, task: CalendarTask ):
        return cls(
            title=task["title"],
            notes=task.get("notes", None),
            due=datetime.fromisoformat(task["due"])
        )


class FullDayEvent(BaseModel, Serializable):
    kind: Literal["FullDay"] = "FullDay"

    title: str
    description: Optional[str] = None
    day: date
    reminders: list[Reminder] = []

    def JSON(self) -> dict[str, Any]:
        return {
            "eventType": "default",
            "summary": self.title,
            "description": self.description,
            "start": {
                "date": self.day.isoformat(),
            },
            "end": {
                "date": (self.day + timedelta(days=1)).isoformat(),
            },
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": r.method, "minutes": r.minutes} for r in self.reminders]
            },
        }

    @field_validator("day", mode="before")
    @classmethod
    def parse_italian_date(cls, value):
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%d/%m/%Y")
            except ValueError:
                pass  # lascia che pydantic tenti il parsing standard (ISO)
        return value

    @classmethod
    def from_google(cls, event: CalendarEvent):
        return cls(
            title=event["summary"],
            description=event.get("description",None),
            day=date.fromisoformat(event["start"]["date"]),
            reminders=[Reminder(method=r.method, minutes=r.minutes) for r in event.get("reminders", {}).get("overrides", [])]
        )

class TimedEvent(BaseModel, Serializable, ABC):
    """
    Generic class for all events
    """
    title: str
    description: Optional[str] = None
    start: datetime
    end: datetime
    reminders: list[Reminder] = []

    # @property
    # def start(self) -> datetime:
    #     return self._start
    #
    # @property
    # def end(self) -> datetime:
    #     return self._end

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_italian_date(cls, value):
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass  # lascia che pydantic tenti il parsing standard (ISO)
        return value


    def JSON(self) -> dict[str, Any]:
        return {
            "eventType": "default",
            "summary": self.title,
            "description": self.description,
            "start": {
                "dateTime": self.start.isoformat(),
                "timeZone": "Europe/Rome",
            },
            "end": {
                "dateTime": self.end.isoformat(),
                "timeZone": "Europe/Rome",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": r.method, "minutes": r.minutes} for r in self.reminders]
            },
        }

class FocusedEvent(TimedEvent):
    kind: Literal["FocusTime"] = "FocusTime"

    def JSON(self) -> dict[str, Any]:
        org = super().JSON()
        org["eventType"] = "focusTime"
        org["focusTimeProperties"]= {'autoDeclineMode': 'declineNone'}
        return org



class AbsoluteEvent(TimedEvent):

    @classmethod
    def from_google(cls, event: CalendarEvent):
        return cls(
            title=event["summary"],
            description=event.get("description",None),
            start=datetime.fromisoformat(event["start"]["dateTime"]).astimezone(
                pytz_timezone(event["start"]["timeZone"])),
            end=datetime.fromisoformat(event["end"]["dateTime"]).astimezone(pytz_timezone(event["end"]["timeZone"])),
            reminders=[Reminder(method=r.method, minutes=r.minutes) for r in
                       event.get("reminders", {}).get("overrides", [])]

        )

class RelativeEvent(TimedEvent, ABC):

    @model_validator(mode="before")
    @classmethod
    def parse_relative_args(cls, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return data

            # 1. BLOCCO: Impedisce di passare start/end direttamente
        if "start" in data or "end" in data:
            raise ValueError(
                "Non puoi passare 'start' o 'end' a un RelativeEvent! "
                "Usa 'shift_start', 'now_time' e 'duration'/'shift_end'."
            )

            # 2. Estrazione parametri relativi
        now_time: datetime = data.pop("now_time")
        shift_start: timedelta = data.pop("shift_start")
        shift_end: Optional[timedelta] = data.pop("shift_end", None)
        duration: Optional[timedelta] = data.pop("duration", None)

        if (duration is None and shift_end is None) or (
                duration is not None and shift_end is not None
        ):
            raise ValueError(
                "Devi passare esattamente uno tra 'duration' e 'shift_end'."
            )

        if duration is not None:
            shift_end = shift_start + duration

        # 3. Inietta start ed end per il TimedEvent padre
        data["start"] = now_time + shift_start
        data["end"] = now_time + shift_end

        return data

    @overload
    def __init__(self, *, shift_start: timedelta, shift_end: timedelta, now_time: datetime,
                 title: str,
                 description: Optional[str] = None,
                 reminders: Optional[list[Reminder]] = None
                 ): ...

    @overload
    def __init__(self, *, shift_start: timedelta, duration: timedelta, now_time: datetime,
                 title: str,
                 description: Optional[str] = None,
                 reminders: Optional[list[Reminder]] = None
                 ): ...

    def __init__(
            self,
            *,
            shift_start: timedelta,
            shift_end: Optional[timedelta] = None,
            duration: Optional[timedelta] = None,
            now_time: datetime,
            title: str,
            description: Optional[str] = None,
            reminders: Optional[list[Reminder]] = None
    ) -> None:
        # Nessun calcolo qui: passa tutto grezzo, ci pensa il model_validator.
        super().__init__(
            shift_start=shift_start,
            shift_end=shift_end,
            duration=duration,
            now_time=now_time,
            title=title,
            description=description,
            reminders=reminders
        )

class ShiftableEvent(RelativeEvent):
    kind: Literal["Shiftable"] = "Shiftable"

    
    def shift_time(self, shift: timedelta):
        self.start += shift
        self.end += shift

class FixedEvent(RelativeEvent):
    kind: Literal["Fixed"] = "Fixed"
    pass

possibleEventTypes = Union[FixedEvent, ShiftableEvent, FocusedEvent, FullDayEvent, DailyTask]
_adapter = TypeAdapter(list[Annotated[possibleEventTypes, Field(discriminator="kind")]])


class EventFactory:
    @classmethod
    def parse_yaml(cls, filepath: Path) -> list[possibleEventTypes]:
        with open(filepath) as f:
            return _adapter.validate_python(yaml.safe_load(f))