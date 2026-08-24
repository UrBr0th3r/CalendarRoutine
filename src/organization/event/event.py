from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING, overload, Literal, Annotated, Union, Self
from abc import ABC, abstractmethod

import pytz
from pytz import timezone as pytz_timezone
import yaml

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3 import Event as CalendarEvent
    from googleapiclient._apis.tasks.v1 import Task as CalendarTask
from pydantic import BaseModel, model_validator, TypeAdapter, Field, field_validator

_DATETIME_ADAPTER = TypeAdapter(datetime)
_TIMEDELTA_ADAPTER = TypeAdapter(timedelta)

class Serializable(ABC):
    @abstractmethod
    def JSON(self) -> dict[str, Any]:
        ...

class Reminder(BaseModel):
    method: str = "popup"
    minutes: int

class DailyTask(BaseModel, Serializable):
    id: Optional[str] = None
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
    id: Optional[str] = None
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
            } if self.reminders else {"useDefault": True},
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
            reminders=[Reminder(method=r["method"], minutes=r["minutes"]) for r in event.get("reminders", {}).get("overrides", [])]
        )

# TODO: usa gli eventi full day / le tasks (quando implementano gli orari) come condizionali, tipo se festa -> non aggiungere studio

class TimedEvent(BaseModel, Serializable, ABC):
    """
    Generic class for all events
    """
    id: Optional[str] = None
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

    @model_validator(mode="before")
    @classmethod
    def parse_start_end(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        has_relative = "shift_start" in data
        has_absolute = "start" in data

        if has_relative and has_absolute:
            raise ValueError("Non puoi mischiare 'start' assoluto e 'shift_start' relativo.")
        if not has_relative and not has_absolute:
            raise ValueError("Serve 'start' (assoluto) oppure 'shift_start' (relativo).")

        if has_absolute:
            return data  # già nel formato finale, non c'è nulla da fare

        # formato relativo: converte in start/end assoluti
        now_raw: Optional[str | datetime] = data.pop("now_time", None)
        if now_raw is None:
            now_time = datetime.now()
        else:
            now_time = cls._parse_italian_date(now_raw)

        shift_start: timedelta = _TIMEDELTA_ADAPTER.validate_python(data.pop("shift_start"))
        shift_end: Optional[timedelta] = data.pop("shift_end", None)
        duration: Optional[timedelta] = data.pop("duration", None)

        if (duration is None) == (shift_end is None):
            raise ValueError("Devi passare esattamente uno tra 'duration' e 'shift_end'.")
        if duration is not None:
            shift_end = shift_start + _TIMEDELTA_ADAPTER.validate_python(duration)
        else:
            shift_end = _TIMEDELTA_ADAPTER.validate_python(shift_end)

        data["start"] = now_time + shift_start
        data["end"] = now_time + shift_end
        return data

    @field_validator("start", "end", mode="before")
    @classmethod
    def _parse_italian_date(cls, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass
        return _DATETIME_ADAPTER.validate_python(value)

    @model_validator(mode="after")
    def _check_start_before_end(self) -> Self:
        if self.start > self.end:
            raise ValueError(
                f"'start' ({self.start}) deve essere precedente a 'end' ({self.end})"
            )
        return self


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

    @classmethod
    def from_google(cls, event: CalendarEvent):
        return cls(
            title=event["summary"],
            description=event.get("description", None),
            start=datetime.fromisoformat(event["start"]["dateTime"]).astimezone(
                pytz_timezone(event["start"]["timeZone"])),
            end=datetime.fromisoformat(event["end"]["dateTime"]).astimezone(pytz_timezone(event["end"]["timeZone"])),
            reminders=[Reminder(method=r["method"], minutes=r["minutes"]) for r in
                       event.get("reminders", {}).get("overrides", [])]

        )

    @classmethod
    @overload
    def relative(cls, *, shift_start: timedelta, shift_end: timedelta, now_time: datetime,
                 title: str,
                 description: Optional[str] = None,
                 reminders: Optional[list[Reminder]] = None
                 ):
        ...

    @overload
    @classmethod
    def relative(cls, *, shift_start: timedelta, duration: timedelta, now_time: datetime,
                 title: str,
                 description: Optional[str] = None,
                 reminders: Optional[list[Reminder]] = None
                 ):
        ...

    @classmethod
    def relative(
            cls,
            *,
            shift_start: timedelta,
            shift_end: Optional[timedelta] = None,
            duration: Optional[timedelta] = None,
            now_time: Optional[datetime] = None,
            title: str,
            description: Optional[str] = None,
            reminders: Optional[list[Reminder]] = None, **data
    ) -> Self:
        # Nessun calcolo qui: passa tutto grezzo, ci pensa il model_validator.
        if now_time is None:
            now_time = datetime.now()
        return cls(
            shift_start=shift_start,
            shift_end=shift_end,
            duration=duration,
            now_time=now_time,
            title=title,
            description=description,
            reminders=reminders, **data
        )

    def __str__(self):
        return f"{f"[{self.kind}] " if hasattr(self, "kind") else ""}{self.title}{f": {self.description}" if self.description else ""}. {self.start.strftime('%d/%m/%Y %H:%M:%S')} - {self.end.strftime('%d/%m/%Y %H:%M:%S')}"

class FocusedEvent(TimedEvent):
    kind: Literal["FocusTime"] = "FocusTime"

    def JSON(self) -> dict[str, Any]:
        org = super().JSON()
        org["eventType"] = "focusTime"
        org["focusTimeProperties"]= {'autoDeclineMode': 'declineNone'}
        return org

class ShiftableEvent(TimedEvent):
    kind: Literal["Shiftable"] = "Shiftable"


    def shift_time(self, shift: timedelta) -> "ShiftableEvent":
        # self.start += shift
        # self.end += shift
        return ShiftableEvent(
            title=self.title,
            description=self.description,
            start=self.start + shift,
            end=self.end + shift,
            reminders=self.reminders
        )

    def shift_from(self, *shifts: tuple[datetime, datetime]) -> "ShiftableEvent":
        assert all(e > s for s, e in shifts), "Ogni shift deve avere end > start"
        sorted_shifts = sorted(shifts, key=lambda t: t[0])
        ordered_shifts: list[tuple[datetime, datetime]] = []
        for s, e in sorted_shifts:
            if not ordered_shifts or s > ordered_shifts[-1][1]:
                ordered_shifts.append((s, e))
            else:
                last_s, last_e = ordered_shifts[-1]
                ordered_shifts[-1] = (last_s, max(last_e, e))

        # it = iter(ordered_shifts)
        # while x := next(it, None):
        index: int = -1
        for i, (start, end) in enumerate(ordered_shifts):
            if end <= self.start:
                continue
            elif start >= self.end:
                continue
            index = i
            break

        if index == -1:
            return self.shift_time(timedelta(0))

        start = ordered_shifts[index][0]
        end = ordered_shifts[index][1]
        # if self.end <= start or self.start >= end:
        #     return self
        half_this = self.start + (self.end - self.start) / 2
        half_that = start + (end - start) / 2

        if half_this < half_that:
            shift = -(self.end - start)
        else:
            shift = end - self.start

        increment = -1 if shift < timedelta(0) else 1
        while True:
            index += increment
            if not (-1 < index < len(ordered_shifts)):
                break
            # if self.start + shift < ordered_shifts[index][1]:
            #     shift += increment * (ordered_shifts[index - increment][max(0, increment)] - ordered_shifts[index][max(0, increment)])
            curr_start, curr_end = ordered_shifts[index]

            proj_start = self.start + shift
            proj_end = self.end + shift

            # Se lo shift attuale collide ancora con l'evento `index`, eseguiamo il JUMP
            if increment > 0:
                # Direzione DESTRA: collide se lo start proiettato è prima della fine dell'ostacolo
                if proj_start < curr_end and proj_end > curr_start:
                    shift = curr_end - self.start  # Jump alla fine dell'ostacolo corrente
            else:
                # Direzione SINISTRA: collide se la fine proiettata è dopo l'inizio dell'ostacolo
                if proj_end > curr_start and proj_start < curr_end:
                    shift = curr_start - self.end  # Jump all'inizio dell'ostacolo corrente

        return self.shift_time(shift)

class FixedEvent(TimedEvent):
    kind: Literal["Fixed"] = "Fixed"
    pass

class SplittableEvent(TimedEvent):
    kind: Literal["Splittable"] = "Splittable"

    # def split(self, *splits: tuple[datetime, datetime]) -> list["SplittableEvent"]:
        # if not splits:
        #     return [self]
        # assert all(e > s for s, e in splits), "Ogni split deve avere end > start"
        #
        # ordered = sorted(splits, key=lambda t: t[0])
        # for (s1, e1), (s2, e2) in zip(ordered, ordered[1:]):
        #     assert e1 <= s2, f"Gli split {(s1, e1)} e {(s2, e2)} si sovrappongono tra loro"
        #
        # overlap = timedelta(0)
        # start: Optional[datetime] = None
        # end: datetime = self.end
        # for s, e in ordered:
        #     o = min(e, self.end) - max(s, self.start)
        #     if o > timedelta(0):
        #         overlap += o
        #
        #     if e > self.start and start is None:
        #         start = min(s, self.start)
        #
        #     if s < self.end:
        #         end = max(e, self.end)
        #
        #
        # new_start = start - overlap / 2
        # new_end = end + overlap / 2
        #
        # pieces: list[tuple[datetime, datetime]] = []
        # cursor = new_start
        # for s, e in ordered:
        #     if s > cursor:
        #         pieces.append((cursor, min(s, new_end)))
        #     cursor = max(cursor, e)
        # if cursor < new_end:
        #     pieces.append((cursor, new_end))
        #
        # return [
        #     SplittableEvent(
        #         title=self.title+f" {i}",
        #         description=self.description,
        #         start=s[0],
        #         end=s[1],
        #         reminders=self.reminders
        #     ) for i, s in enumerate(pieces)
        # ]
    def split(self, *splits: tuple[datetime, datetime]) -> list["SplittableEvent"]:
        if not splits:
            return [
                SplittableEvent(
                    title=self.title,
                    description=self.description,
                    start=self.start,
                    end=self.end,
                    reminders=self.reminders,
                )
            ]

        # 1. Validazione
        assert all(e > s for s, e in splits), "Ogni split deve avere end > start"
        sorted_splits = sorted(splits, key=lambda t: t[0])
        ordered_splits: list[tuple[datetime, datetime]] = []
        # check = True
        # first = True
        # while check:
        #     ordered_splits = []
        #
        #     check = False
        #     for (s1, e1), (s2, e2) in zip(sorted_splits, sorted_splits[1:]):
        #         # assert (
        #         #         e1 <= s2
        #         # ), f"Gli split {(s1, e1)} e {(s2, e2)} si sovrappongono tra loro
        #         if e1 >= s2:
        #             ordered_splits.append((s1, max(e1, e2)))
        #             check = True
        #             continue
        #         if first:
        #             ordered_splits.append((s1, e1))
        #             first = False
        #         ordered_splits.append((s2, e2))
        #     sorted_splits = ordered_splits
        for s, e in sorted_splits:
            if not ordered_splits or s > ordered_splits[-1][1]:
                ordered_splits.append((s, e))
            else:
                last_s, last_e = ordered_splits[-1]
                ordered_splits[-1] = (last_s, max(last_e, e))


        # 2. Calcolo dell'overlap effettivo dentro l'evento originale
        # total_duration = self.end - self.start
        overlap = timedelta(0)
        for s, e in ordered_splits:
            o = min(e, self.end) - max(s, self.start)
            if o > timedelta(0):
                overlap += o

        # Se gli splits non intersecano l'evento, non c'è nulla da recuperare
        if overlap == timedelta(0):
            # Basta tagliare l'evento attorno agli splits che cadono nel mezzo
            pass

        needed_left = overlap / 2
        needed_right = overlap / 2

        # 3. ESPANSIONE A SINISTRA (dall'origine self.start andando all'indietro)
        left_pieces: list[tuple[datetime, datetime]] = []
        cursor_left = self.start

        while needed_left > timedelta(0):
            # Troviamo lo split immediatamente prima di cursor_left (se interseca o blocca)
            # Se cursor_left è dentro uno split, facciamo il jump all'inizio dello split
            blocking_split = next(
                (s for s in reversed(ordered_splits) if s[0] < cursor_left < s[1]),
                None,
            )
            if blocking_split:
                cursor_left = blocking_split[0]

            # Il prossimo ostacolo a sinistra
            prev_split = next(
                (s for s in reversed(ordered_splits) if s[1] <= cursor_left),
                None,
            )
            obstacle_time = prev_split[1] if prev_split else datetime.min.replace(tzinfo=cursor_left.tzinfo)

            available_chunk = cursor_left - obstacle_time
            alloc = min(needed_left, available_chunk)

            chunk_start = cursor_left - alloc
            chunk_end = cursor_left
            left_pieces.append((chunk_start, chunk_end))

            needed_left -= alloc
            cursor_left = chunk_start

            # Se siamo arrivati all'ostacolo e serve ancora tempo, saltiamo lo split verso sinistra
            if needed_left > timedelta(0) and prev_split and cursor_left == prev_split[1]:
                cursor_left = prev_split[0]

        # 4. ESPANSIONE A DESTRA (dalla fine self.end andando in avanti)
        right_pieces: list[tuple[datetime, datetime]] = []
        cursor_right = self.end

        while needed_right > timedelta(0):
            # Se cursor_right è dentro uno split, jump alla fine dello split
            blocking_split = next(
                (s for s in ordered_splits if s[0] < cursor_right < s[1]),
                None,
            )
            if blocking_split:
                cursor_right = blocking_split[1]

            # Il prossimo ostacolo a destra
            next_split = next(
                (s for s in ordered_splits if s[0] >= cursor_right), None
            )
            obstacle_time = next_split[0] if next_split else datetime.max

            available_chunk = obstacle_time - cursor_right
            alloc = min(needed_right, available_chunk)

            chunk_start = cursor_right
            chunk_end = cursor_right + alloc
            right_pieces.append((chunk_start, chunk_end))

            needed_right -= alloc
            cursor_right = chunk_end

            # Se siamo arrivati all'ostacolo e serve ancora tempo, saltiamo lo split verso destra
            if needed_right > timedelta(0) and next_split and cursor_right == next_split[0]:
                cursor_right = next_split[1]

        # 5. COSTRUZIONE DEI PEZZI INTERNI (La parte originale dell'evento non coperta da splits)
        # Uniamo tutti i pezzi ottenuti (Sinistra + Interni + Destra)
        effective_start = left_pieces[-1][0] if left_pieces else self.start
        effective_end = right_pieces[-1][1] if right_pieces else self.end

        # Troviamo tutte le finestre valide tra effective_start ed effective_end
        raw_pieces: list[tuple[datetime, datetime]] = []
        curr = effective_start

        for s, e in ordered_splits:
            if e <= curr:
                continue
            if s >= effective_end:
                break
            if s > curr:
                raw_pieces.append((curr, s))
            curr = max(curr, e)

        if curr < effective_end:
            raw_pieces.append((curr, effective_end))

        # 6. Merge finale e istanziazione
        return [
            SplittableEvent(
                title=f"{self.title} ({i + 1})",
                description=self.description,
                start=p_start,
                end=p_end,
                reminders=self.reminders,
            )
            for i, (p_start, p_end) in enumerate(raw_pieces)
        ]




possibleAllTypes = Union[FixedEvent, ShiftableEvent, FocusedEvent, FullDayEvent, DailyTask, SplittableEvent]
possibleEventTypes = Union[FixedEvent, ShiftableEvent, FullDayEvent, SplittableEvent]
_adapter = TypeAdapter(list[Annotated[possibleAllTypes, Field(discriminator="kind")]])


class EventFactory:
    @classmethod
    def parse_yaml(cls, filepath: Path, *, override_now_time: Optional[datetime] = None) -> list[possibleAllTypes]:
        with open(filepath) as f:
            data = yaml.safe_load(f)
        if override_now_time is not None:
            return _adapter.validate_python([
                {"now_time": override_now_time, **d} if d.get("shift_start", None) is not None else d for d in data
            ])
        return _adapter.validate_python(data)

    @classmethod
    def organize(cls, *events: TimedEvent) -> list[TimedEvent]:

        shiftable: list[ShiftableEvent] = []
        splittable: list[SplittableEvent] = []
        others: list[TimedEvent] = []

        for event in events:
            if isinstance(event, SplittableEvent):
                splittable.append(event)
            elif isinstance(event, ShiftableEvent):
                shiftable.append(event) # CHECK: si possono overlappare se shiftati male
            else:
                others.append(event)

        res: list[TimedEvent] = others.copy()

        for shift in shiftable:
            res.append(shift.shift_from(*[(o.start, o.end) for o in res]))

        # others += shiftable

        for split in splittable:
            res += (split.split(*[(o.start, o.end) for o in res]))

        # others += splittable

        return sorted(res, key=lambda x: x.start)

    @classmethod
    def create_event(cls, kind: Literal["FullDay", "Shiftable", "Fixed", "Splittable"], **data) -> TimedEvent:
        return _adapter.validate_python([{ **data, "kind": kind,}])[0]
