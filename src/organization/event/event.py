import json
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING, overload, Literal, Annotated, Union, Self
from abc import ABC, abstractmethod

import pytz
from pytz import timezone as pytz_timezone
import yaml

from utilities.core import Singleton

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3 import Event as CalendarEvent
    from googleapiclient._apis.tasks.v1 import Task as CalendarTask
from pydantic import BaseModel, model_validator, TypeAdapter, Field, field_validator, ValidationError

class Reminder(BaseModel):
    method: str = "popup"
    minutes: int


class ResidualEvent(BaseModel):
    """Rappresenta un evento parzialmente schedulato di cui rimane del tempo da
    collocare nei giorni successivi."""

    # original_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    # remaining_duration: timedelta
    min: Optional[datetime] = None  # Limite inferiore originario
    max: Optional[datetime] = None  # Limite superiore originario
    event_type: int # se è -1 allora è ShiftableEvent, se è 0 allora è SplittableEvent. questo numero serve anche come index per i vari Splitted
    priority: int = -1
    start: datetime
    seconds_left: timedelta
    reminders: list[Reminder] = []
    # calendar_name: str = "primary"

    @classmethod
    def from_event(cls, event: "SplittableEvent | ShiftableEvent", seconds_left: timedelta) -> "ResidualEvent":
        """Factory method per estrarre solo i dati necessari da un evento
        tagliato."""
        return cls(
            # original_id=getattr(event, "id", None),
            title=f"{event.title} [REMAINING]",
            description=getattr(event, "description", None),
            # remaining_duration=timedelta(seconds=seconds_left),
            min=getattr(event, "min", None),
            max=getattr(event, "max", None),
            event_type=0 if event.__class__.__name__ == "SplittableEvent" else -1,
            priority=event.priority,
            start=event.start,
            seconds_left=seconds_left,
            reminders=event.reminders
        )

class EventSession(metaclass=Singleton):
    missing_time: list[ResidualEvent]
    min_day: Optional[datetime] = None
    max_day: Optional[datetime] = None
    def __init__(self):
        self.missing_time = []

    def set_min_max_day(self, max_date: datetime, min_day: datetime):
        self.min_day = min_day
        self.max_day = max_date

    def add_event(self, event: "SplittableEvent | ShiftableEvent", seconds_left: timedelta):
        self.missing_time.append(ResidualEvent.from_event(event, seconds_left))

    def save(self, filepath: Path = "./pending.json"):
        data = [e.model_dump(mode="json") for e in self.missing_time]
        filepath.write_text(json.dumps(data, indent=4, ensure_ascii=False))

    def load(self, filepath: Path = "./pending.json"):
        if not filepath.exists():
            return
        data = json.loads(filepath.read_text())
        self.missing_time = [ResidualEvent.model_validate(item) for item in data]


eventSession = EventSession()


_DATETIME_ADAPTER = TypeAdapter(datetime)
_TIMEDELTA_ADAPTER = TypeAdapter(timedelta)

def parse_italian_date(value: datetime|str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            pass
    return _DATETIME_ADAPTER.validate_python(value)

def parse_value_to_datetime(value: datetime|timedelta|str, now_time: Optional[datetime] = None) -> datetime:
    if now_time is None:
        now_time = datetime.now()

    if isinstance(value, datetime):
        return value
    elif isinstance(value, timedelta):
        return now_time + value
    elif isinstance(value, str):
        try:
            return now_time + _TIMEDELTA_ADAPTER.validate_python(value) # ERROR: IMPORTANTE! quando io faccio min, non devo mettere 25/07/2027 09:00:23, ma devo mettere solo 09:00:23 PERCHE' AGGIORNA IL GIORNO
        except ValidationError:
            return parse_italian_date(value)
    else:
        raise TypeError("day_min must be datetime or timedelta or a validating string")


class Serializable(ABC):
    @abstractmethod
    def JSON(self) -> dict[str, Any]:
        ...


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
    def _parse_italian_date(cls, value):
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass  # lascia che pydantic tenti il parsing standard (ISO)
        return value

    @classmethod
    def from_google(cls, task: CalendarTask ):
        return cls(
            id=task["id"],
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
    def _parse_italian_date(cls, value):
        return parse_italian_date(value)

    @classmethod
    def from_google(cls, event: CalendarEvent):
        return cls(
            id=event["id"],
            title=event["summary"],
            description=event.get("description",None),
            day=date.fromisoformat(event["start"]["date"]),
            reminders=[Reminder(method=r["method"], minutes=r["minutes"]) for r in event.get("reminders", {}).get("overrides", [])]
        )

# TODO: usa gli eventi full day / le tasks (quando implementano gli orari) come condizionali, tipo se festa -> non aggiungere studio
#  e DOING: IMPORTANTISSIMO: Crea il "periodo di giorno" ovvero le 16/17 ore di attività in cui si possono spreaddare gli elementi, altrimenti devono cercare un altro posto

class TimedEvent(BaseModel, Serializable, ABC):
    """
    Generic class for all events
    """
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    start: datetime
    end: datetime
    # now: Optional[datetime] = None
    reminders: list[Reminder] = []
    priority: int = -1 # TODO

    # @property
    # def start(self) -> datetime:
    #     return self._start
    #
    # @property
    # def end(self) -> datetime:
    #     return self._end

    @model_validator(mode="before")
    @classmethod
    def _parse_start_end(cls, data: Any) -> Any:
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
        now_raw: Optional[str | datetime] = data.get("now_time", None)
        if now_raw is None:
            now_time = datetime.now()
        else:
            now_time = parse_italian_date(now_raw)

        shift_start: timedelta = _TIMEDELTA_ADAPTER.validate_python(data.pop("shift_start"))
        shift_end: Optional[Any] = data.pop("shift_end", None)
        duration: Optional[Any] = data.pop("duration", None)

        # if (duration is None) == (shift_end is None):
        #     raise ValueError("Devi passare esattamente uno tra 'duration' e 'shift_end'.")
        if shift_end is not None:
            shift_end = _TIMEDELTA_ADAPTER.validate_python(shift_end)
        else:
            shift_end = shift_start + _TIMEDELTA_ADAPTER.validate_python(duration) # TODO: errori personalizzati

        data["start"] = now_time + shift_start
        data["end"] = now_time + shift_end
        data["now"] = now_time
        if data.get("priority", None) is None:
            data["priority"] = -1
        return data

    @field_validator("start", "end", mode="before")
    @classmethod
    def _parse_italian_date(cls, value):
        return parse_italian_date(value)

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
            id=event["id"],
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
                 reminders: Optional[list[Reminder]] = None,
                 priority: int = -1,
                 ):
        ...

    @overload
    @classmethod
    def relative(cls, *, shift_start: timedelta, duration: timedelta, now_time: datetime,
                 title: str,
                 description: Optional[str] = None,
                 reminders: Optional[list[Reminder]] = None,
                 priority: int = -1,
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
            reminders: Optional[list[Reminder]] = None,
            priority: int = -1, **data
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
            reminders=reminders,
            priority=priority,
            **data
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

class FixedEvent(TimedEvent):
    kind: Literal["Fixed"] = "Fixed"
    pass

class MovableEvent(TimedEvent, ABC):
    min: Optional[datetime] = None
    max: Optional[datetime] = None

    @classmethod
    @overload
    def relative(cls, *, shift_start: timedelta, shift_end: timedelta, now_time: datetime,
                 title: str,
                 description: Optional[str] = None,
                 reminders: Optional[list[Reminder]] = None,
                 min_time: Optional[timedelta] = None,
                 max_time: Optional[timedelta] = None,
                 priority: int = -1,
                 **data
                 ):
        ...

    @overload
    @classmethod
    def relative(cls, *, shift_start: timedelta, duration: timedelta, now_time: datetime,
                 title: str,
                 description: Optional[str] = None,
                 reminders: Optional[list[Reminder]] = None,
                 min_time: Optional[timedelta] = None,
                 max_time: Optional[timedelta] = None,
                 priority: int = -1,
                 **data
                 ):
        ...

    @overload
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
            reminders: Optional[list[Reminder]] = None,
            min_time: Optional[timedelta] = None,
            max_time: Optional[timedelta] = None,
            priority: int = -1,
            **data
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
            reminders=reminders,
            min=min_time,
            max=max_time,
            priority=priority,
            **data
        )

    @classmethod
    def from_residual(cls, event: ResidualEvent, start: datetime, end: datetime, **kwargs):
        return cls(
            title=kwargs.pop("title", event.title),
            description=kwargs.pop("description", event.description),
            start=start,
            end=end,
            reminders=kwargs.pop("reminders", event.reminders),
            priority=kwargs.pop("priority", event.priority),
            min=kwargs.pop("min", event.min),
            max=kwargs.pop("max", event.max),
            **kwargs,

        )

    @model_validator(mode="before")
    @classmethod
    def _parse_bounds(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

            # 1. Risoluzione di now_time (con timezone fallback dal padre se gestita)
        now_raw = data.get("now_time")
        if now_raw is None:
            now_time = datetime.now()
        elif isinstance(now_raw, str):
            now_time = cls._parse_italian_date(now_raw)
        else:
            now_time = now_raw

        # 2. Parsing ed estensione di min / max (gestisce sia timedelta che datetime)
        for field_name, alt_key in [("min", "min_time"), ("max", "max_time")]:
            val = data.get(field_name) if field_name in data else data.pop(alt_key)
            if val is not None:
                if isinstance(val, timedelta):
                    # Se è un timedelta, lo applichiamo a now_time
                    data[field_name] = now_time + val
                # elif isinstance(val, datetime):
                #     Se è datetime o stringa, ci pensa il validator standard di Pydantic/padre
                #     data[field_name] = val
                elif isinstance(val, str):
                    try:
                        data[field_name] = now_time + _TIMEDELTA_ADAPTER.validate_python(val)
                    except ValidationError:
                        data[field_name] = cls._parse_italian_date(val)
                else:
                    data[field_name] = val

        return data

class ShiftableEvent(MovableEvent):
    kind: Literal["Shiftable"] = "Shiftable"

    def resolve_shift_and_fit(
            self,
            shifts: tuple[tuple[datetime, datetime],...],
            min_day: datetime,
            max_day: datetime,
    ) -> tuple[timedelta, Optional[timedelta]]:
        """Calcola lo shift ottimale per l'evento rispettando i limiti [min_day,
        max_day].

        Returns:
            tuple[timedelta, Optional[timedelta]]:
                - shift: il delta di tempo da applicare all'evento.
                - residual_duration: None se l'evento entra interamente, oppure il
                timedelta
                  del tempo rimanente che è stato tagliato e che andrà schedulato
                  nei giorni successivi.
        """
        assert all(
            e > s for s, e in shifts
        ), "Ogni shift deve avere end > start"

        # 1. Merging degli intervalli occupati/sovrapposti
        sorted_shifts = sorted(shifts, key=lambda t: t[0])
        ordered_shifts: list[tuple[datetime, datetime]] = []
        for s, e in sorted_shifts:
            if not ordered_shifts or s > ordered_shifts[-1][1]:
                ordered_shifts.append((s, e))
            else:
                last_s, last_e = ordered_shifts[-1]
                ordered_shifts[-1] = (last_s, max(last_e, e))

        # 2. Individuazione del primo ostacolo che interseca l'evento
        index: int = -1
        for i, (start, end) in enumerate(ordered_shifts):
            if end <= self.start or start >= self.end:
                continue
            index = i
            break

        # Se non collide con nessun ostacolo esistente
        if index == -1:
            initial_shift = timedelta(0)
        else:
            # Scelta della direzione preferita in base al centro gravrazionale
            start, end = ordered_shifts[index]
            half_this = self.start + (self.end - self.start) / 2
            half_that = start + (end - start) / 2

            if half_this < half_that:
                initial_shift = -(self.end - start)
            else:
                initial_shift = end - self.start

        # --- Helper per cercare uno slot in una direzione specifica ---
        def find_slot_in_direction(
                start_index: int, initial_shift: timedelta, direction: int
        ) -> timedelta:
            shift = initial_shift
            curr_idx = start_index

            while 0 <= curr_idx < len(ordered_shifts):
                curr_start, curr_end = ordered_shifts[curr_idx]
                proj_start = self.start + shift
                proj_end = self.end + shift

                if direction > 0:
                    # Spostamento verso DESTRA
                    if proj_start < curr_end and proj_end > curr_start:
                        shift = curr_end - self.start
                    else:
                        break
                else:
                    # Spostamento verso SINISTRA
                    if proj_end > curr_start and proj_start < curr_end:
                        shift = curr_start - self.end
                    else:
                        break
                curr_idx += direction

            return shift

        # --- Helper per verificare la validità dello shift rispetto a [min_day, max_day] ---
        def is_within_bounds(shift: timedelta) -> bool:
            return (self.start + shift >= min_day) and (
                    self.end + shift <= max_day
            )

        # 3. TENTATIVO 1: Direzione preferita
        dir1 = -1 if initial_shift < timedelta(0) else 1
        shift1 = (
            find_slot_in_direction(index, initial_shift, dir1)
            if index != -1
            else initial_shift
        )

        if is_within_bounds(shift1):
            return shift1, None  # Perfetto: l'evento entra del tutto

        # 4. TENTATIVO 2: Inversione della direzione (Opposta)
        dir2 = -dir1
        # Per la direzione opposta ricalcoliamo il jump iniziale dall'ostacolo di partenza
        if index != -1:
            start_obs, end_obs = ordered_shifts[index]
            init_shift2 = (
                (end_obs - self.start)
                if dir2 > 0
                else -(self.end - start_obs)
            )
            shift2 = find_slot_in_direction(index, init_shift2, dir2)
        else:
            shift2 = initial_shift

        if is_within_bounds(shift2):
            return shift2, None  # L'altra direzione funziona senza tagliare!

        # 5. FALLBACK: Entrambe le direzioni sbroccano dai limiti del giorno.
        # Calcoliamo quale dei due tentativi sfora di MENO (minor overrun).
        def calculate_overflow(shift: timedelta) -> timedelta:
            proj_start = self.start + shift
            proj_end = self.end + shift

            underflow = (
                (min_day - proj_start)
                if proj_start < min_day
                else timedelta(0)
            )
            overflow = (
                (proj_end - max_day) if proj_end > max_day else timedelta(0)
            )
            return underflow + overflow

        over1 = calculate_overflow(shift1)
        over2 = calculate_overflow(shift2)

        best_shift = shift1 if over1 <= over2 else shift2

        # 6. Esecuzione del Taglio (Clipping)
        # Aggustiamo lo shift per appiccicarlo al limite del giorno se necessario
        final_start = max(min_day, self.start + best_shift)
        final_end = min(max_day, self.end + best_shift)

        # Se lo slot rimanente è nullo o negativo (giornata piena)
        if final_end <= final_start:
            original_duration = self.end - self.start
            return timedelta(0), original_duration

        actual_duration = final_end - final_start
        original_duration = self.end - self.start
        residual_duration = original_duration - actual_duration

        final_shift = final_start - self.start

        return final_shift, residual_duration


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
        # assert all(e > s for s, e in shifts), "Ogni shift deve avere end > start"
        # sorted_shifts = sorted(shifts, key=lambda t: t[0])
        # ordered_shifts: list[tuple[datetime, datetime]] = []
        # for s, e in sorted_shifts:
        #     if not ordered_shifts or s > ordered_shifts[-1][1]:
        #         ordered_shifts.append((s, e))
        #     else:
        #         last_s, last_e = ordered_shifts[-1]
        #         ordered_shifts[-1] = (last_s, max(last_e, e))
        #
        # # it = iter(ordered_shifts)
        # # while x := next(it, None):
        # index: int = -1
        # for i, (start, end) in enumerate(ordered_shifts):
        #     if end <= self.start:
        #         continue
        #     elif start >= self.end:
        #         continue
        #     index = i
        #     break
        #
        # if index == -1:
        #     return self.shift_time(timedelta(0))
        #
        # start = ordered_shifts[index][0]
        # end = ordered_shifts[index][1]
        # # if self.end <= start or self.start >= end:
        # #     return self
        # half_this = self.start + (self.end - self.start) / 2
        # half_that = start + (end - start) / 2
        #
        # if half_this < half_that:
        #     shift = -(self.end - start)
        # else:
        #     shift = end - self.start
        #
        # increment = -1 if shift < timedelta(0) else 1
        # index += increment
        #
        # while -1 < index < len(ordered_shifts):
        #     # if self.start + shift < ordered_shifts[index][1]:
        #     #     shift += increment * (ordered_shifts[index - increment][max(0, increment)] - ordered_shifts[index][max(0, increment)])
        #     curr_start, curr_end = ordered_shifts[index]
        #
        #     proj_start = self.start + shift
        #     proj_end = self.end + shift
        #
        #
        #
        #     # Se lo shift attuale collide ancora con l'evento `index`, eseguiamo il JUMP
        #     if increment > 0:
        #         # Direzione DESTRA: collide se lo start proiettato è prima della fine dell'ostacolo
        #         if proj_start < curr_end and proj_end > curr_start:
        #             shift = curr_end - self.start  # Jump alla fine dell'ostacolo corrente
        #         else:
        #             break # no collisione = buono shift
        #     else:
        #         # Direzione SINISTRA: collide se la fine proiettata è dopo l'inizio dell'ostacolo
        #         if proj_end > curr_start and proj_start < curr_end:
        #             shift = curr_start - self.end  # Jump all'inizio dell'ostacolo corrente
        #         else:
        #             break
        #     index += increment
        #
        # if self.end + shift < eventSession.min_day:
        #     missing_delta = self.end - self.start

        shift, res = self.resolve_shift_and_fit(shifts, eventSession.min_day, eventSession.max_day)
        if res is not None and res > timedelta(0):
            eventSession.add_event(self, res)

        return self.shift_time(shift)


class SplittableEvent(MovableEvent):
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
    # def split(self, *splits: tuple[datetime, datetime]) -> list["SplittableEvent"]:
    #     if not splits:
    #         return [
    #             SplittableEvent(
    #                 title=self.title,
    #                 description=self.description,
    #                 start=self.start,
    #                 end=self.end,
    #                 reminders=self.reminders,
    #             )
    #         ]
    #
    #     # 1. Validazione
    #     assert all(e > s for s, e in splits), "Ogni split deve avere end > start"
    #     sorted_splits = sorted(splits, key=lambda t: t[0])
    #     ordered_splits: list[tuple[datetime, datetime]] = []
    #     # check = True
    #     # first = True
    #     # while check:
    #     #     ordered_splits = []
    #     #
    #     #     check = False
    #     #     for (s1, e1), (s2, e2) in zip(sorted_splits, sorted_splits[1:]):
    #     #         # assert (
    #     #         #         e1 <= s2
    #     #         # ), f"Gli split {(s1, e1)} e {(s2, e2)} si sovrappongono tra loro
    #     #         if e1 >= s2:
    #     #             ordered_splits.append((s1, max(e1, e2)))
    #     #             check = True
    #     #             continue
    #     #         if first:
    #     #             ordered_splits.append((s1, e1))
    #     #             first = False
    #     #         ordered_splits.append((s2, e2))
    #     #     sorted_splits = ordered_splits
    #     for s, e in sorted_splits:
    #         if not ordered_splits or s > ordered_splits[-1][1]:
    #             ordered_splits.append((s, e))
    #         else:
    #             last_s, last_e = ordered_splits[-1]
    #             ordered_splits[-1] = (last_s, max(last_e, e))
    #
    #
    #     # 2. Calcolo dell'overlap effettivo dentro l'evento originale
    #     # total_duration = self.end - self.start
    #     overlap = timedelta(0)
    #     for s, e in ordered_splits:
    #         o = min(e, self.end) - max(s, self.start)
    #         if o > timedelta(0):
    #             overlap += o
    #
    #     # Se gli splits non intersecano l'evento, non c'è nulla da recuperare
    #     if overlap == timedelta(0):
    #         # Basta tagliare l'evento attorno agli splits che cadono nel mezzo
    #         pass
    #
    #     needed_left = overlap / 2
    #     needed_right = overlap / 2
    #
    #     # 3. ESPANSIONE A SINISTRA (dall'origine self.start andando all'indietro)
    #     left_pieces: list[tuple[datetime, datetime]] = []
    #     cursor_left = self.start
    #
    #     while needed_left > timedelta(0) and cursor_left > eventSession.min_day: # ERROR: il cursore SALTA prima di min_day, quindi non si ferma a min day
    #         # Troviamo lo split immediatamente prima di cursor_left (se interseca o blocca)
    #         # Se cursor_left è dentro uno split, facciamo il jump all'inizio dello split
    #         blocking_split = next(
    #             (s for s in reversed(ordered_splits) if s[0] < cursor_left < s[1]),
    #             None,
    #         )
    #         if blocking_split:
    #             cursor_left = blocking_split[0]
    #
    #         # Il prossimo ostacolo a sinistra
    #         prev_split = next(
    #             (s for s in reversed(ordered_splits) if s[1] <= cursor_left),
    #             None,
    #         )
    #         obstacle_time = prev_split[1] if prev_split else datetime.min.replace(tzinfo=cursor_left.tzinfo)
    #
    #         available_chunk = cursor_left - obstacle_time
    #         alloc = min(needed_left, available_chunk)
    #
    #         chunk_start = cursor_left - alloc
    #         chunk_end = cursor_left
    #         left_pieces.append((chunk_start, chunk_end))
    #
    #         needed_left -= alloc
    #         cursor_left = chunk_start
    #
    #         # Se siamo arrivati all'ostacolo e serve ancora tempo, saltiamo lo split verso sinistra
    #         if needed_left > timedelta(0) and prev_split and cursor_left == prev_split[1]:
    #             cursor_left = prev_split[0]
    #
    #     if cursor_left < eventSession.min_day:
    #         left_pieces[-1] = (eventSession.min_day, left_pieces[-1][1])
    #         needed_left += eventSession.min_day - cursor_left
    #
    #     # 4. ESPANSIONE A DESTRA (dalla fine self.end andando in avanti)
    #     needed_right += needed_left
    #     right_pieces: list[tuple[datetime, datetime]] = []
    #     cursor_right = self.end
    #
    #     while needed_right > timedelta(0) and cursor_right < eventSession.max_day:
    #         # Se cursor_right è dentro uno split, jump alla fine dello split
    #         blocking_split = next(
    #             (s for s in ordered_splits if s[0] < cursor_right < s[1]),
    #             None,
    #         )
    #         if blocking_split:
    #             cursor_right = blocking_split[1]
    #
    #         # Il prossimo ostacolo a destra
    #         next_split = next(
    #             (s for s in ordered_splits if s[0] >= cursor_right), None
    #         )
    #         obstacle_time = next_split[0] if next_split else datetime.max
    #
    #         available_chunk = obstacle_time - cursor_right
    #         alloc = min(needed_right, available_chunk)
    #
    #         chunk_start = cursor_right
    #         chunk_end = cursor_right + alloc
    #         right_pieces.append((chunk_start, chunk_end))
    #
    #         needed_right -= alloc
    #         cursor_right = chunk_end
    #
    #         # Se siamo arrivati all'ostacolo e serve ancora tempo, saltiamo lo split verso destra
    #         if needed_right > timedelta(0) and next_split and cursor_right == next_split[0]:
    #             cursor_right = next_split[1]
    #
    #     if cursor_right > eventSession.max_day:
    #         right_pieces[-1] = (right_pieces[-1][0], eventSession.max_day )
    #         needed_right += cursor_right - eventSession.max_day
    #     if needed_right > timedelta(0):
    #         eventSession.add_event(self, needed_right)
    #
    #     # 5. COSTRUZIONE DEI PEZZI INTERNI (La parte originale dell'evento non coperta da splits)
    #     # Uniamo tutti i pezzi ottenuti (Sinistra + Interni + Destra)
    #     effective_start = left_pieces[-1][0] if left_pieces else self.start
    #     effective_end = right_pieces[-1][1] if right_pieces else self.end
    #
    #     # Troviamo tutte le finestre valide tra effective_start ed effective_end
    #     raw_pieces: list[tuple[datetime, datetime]] = []
    #     curr = effective_start
    #
    #     for s, e in ordered_splits:
    #         if e <= curr:
    #             continue
    #         if s >= effective_end:
    #             break
    #         if s > curr:
    #             raw_pieces.append((curr, s))
    #         curr = max(curr, e)
    #
    #     if curr < effective_end:
    #         raw_pieces.append((curr, effective_end))
    #
    #     # 6. Merge finale e istanziazione
    #     return [
    #         SplittableEvent(
    #             title=f"{self.title} ({i + 1})",
    #             description=self.description,
    #             start=p_start,
    #             end=p_end,
    #             reminders=self.reminders,
    #         )
    #         for i, (p_start, p_end) in enumerate(raw_pieces)
    #     ]
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

        # 1. Validazione e merging degli splits sovrapposti
        assert all(e > s for s, e in splits), "Ogni split deve avere end > start"
        sorted_splits = sorted(splits, key=lambda t: t[0])
        ordered_splits: list[tuple[datetime, datetime]] = []

        for s, e in sorted_splits:
            if not ordered_splits or s > ordered_splits[-1][1]:
                ordered_splits.append((s, e))
            else:
                last_s, last_e = ordered_splits[-1]
                ordered_splits[-1] = (last_s, max(last_e, e))

        # 2. Calcolo dell'overlap effettivo dentro l'evento originale
        overlap = timedelta(0)
        for s, e in ordered_splits:
            o = min(e, self.end) - max(s, self.start)
            if o > timedelta(0):
                overlap += o

        # Se non c'è overlap, restituisce l'evento originale (o tagliato se intersecato)
        if overlap == timedelta(0):
            needed_left = timedelta(0)
            needed_right = timedelta(0)
        else:
            needed_left = overlap / 2
            needed_right = overlap / 2

        # 3. ESPANSIONE A SINISTRA (dall'origine self.start andando all'indietro)
        left_pieces: list[tuple[datetime, datetime]] = []
        cursor_left = self.start

        while (
                needed_left > timedelta(0) and cursor_left > eventSession.min_day
        ):
            # Se cursor_left è dentro uno split, jump all'inizio dello split
            blocking_split = next(
                (
                    s
                    for s in reversed(ordered_splits)
                    if s[0] < cursor_left < s[1]
                ),
                None,
            )
            if blocking_split:
                cursor_left = blocking_split[0]

            # Il prossimo ostacolo a sinistra
            prev_split = next(
                (s for s in reversed(ordered_splits) if s[1] <= cursor_left),
                None,
            )
            obstacle_time = (
                prev_split[1]
                if prev_split
                else datetime.min.replace(tzinfo=cursor_left.tzinfo)
            )
            # Rispettiamo anche min_day come ostacolo insuperabile
            effective_obstacle = max(obstacle_time, eventSession.min_day)

            available_chunk = cursor_left - effective_obstacle
            if available_chunk <= timedelta(0):
                break

            alloc = min(needed_left, available_chunk)
            chunk_start = cursor_left - alloc
            chunk_end = cursor_left

            left_pieces.append((chunk_start, chunk_end))

            needed_left -= alloc
            cursor_left = chunk_start

            # Jump oltre lo split a sinistra se serve ancora tempo
            if (
                    needed_left > timedelta(0)
                    and prev_split
                    and cursor_left == prev_split[1]
            ):
                cursor_left = prev_split[0]

        # Se min_day ha bloccato l'espansione a sinistra, trasferiamo il tempo residuo a destra
        if needed_left > timedelta(0):
            needed_right += needed_left

        # 4. ESPANSIONE A DESTRA (dalla fine self.end andando in avanti)
        right_pieces: list[tuple[datetime, datetime]] = []
        cursor_right = self.end

        while (
                needed_right > timedelta(0) and cursor_right < eventSession.max_day
        ):
            # Se cursor_right è dentro uno split, jump alla fine dello split
            blocking_split = next(
                (s for s in ordered_splits if s[0] < cursor_right < s[1]),
                None,
            )
            if blocking_split:
                cursor_right = blocking_split[1]

            # Il prossimo ostacolo a destra (con FIX per Timezone su datetime.max)
            next_split = next(
                (s for s in ordered_splits if s[0] >= cursor_right), None
            )
            obstacle_time = (
                next_split[0]
                if next_split
                else datetime.max.replace(tzinfo=cursor_right.tzinfo)
            )
            # Rispettiamo max_day come ostacolo insuperabile
            effective_obstacle = min(obstacle_time, eventSession.max_day)

            available_chunk = effective_obstacle - cursor_right
            if available_chunk <= timedelta(0):
                break

            alloc = min(needed_right, available_chunk)
            chunk_start = cursor_right
            chunk_end = cursor_right + alloc

            right_pieces.append((chunk_start, chunk_end))

            needed_right -= alloc
            cursor_right = chunk_end

            # Jump oltre lo split a destra se serve ancora tempo
            if (
                    needed_right > timedelta(0)
                    and next_split
                    and cursor_right == next_split[0]
            ):
                cursor_right = next_split[1]

        # Se ancora non è bastato lo spazio nella giornata, tracciamo l'evento incompleto
        if needed_right > timedelta(0):
            eventSession.add_event(self, needed_right)

        # 5. COSTRUZIONE DEI PEZZI INTERNI E RE-ASSEMBLAGGIO
        # left_pieces contiene i pezzi dal passato; l'estremo sinistro è l'ultimo aggiunto
        effective_start = left_pieces[-1][0] if left_pieces else self.start
        effective_end = right_pieces[-1][1] if right_pieces else self.end

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

        # 6. Istanziazione delle sottoclassi
        return [
            SplittableEvent(
                title=f"{self.title} ({i + 1})" if len(raw_pieces) > 1 else self.title,
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

_movableOrders: dict[type, int] = {
    ShiftableEvent: 3,
    SplittableEvent: 2,
    FixedEvent: 1,
}

def _order_events(event: TimedEvent):
    return event.priority, _movableOrders.get(type(event), 0)

def _order_residual(residual: ResidualEvent):
    return -residual.priority, -_movableOrders.get(ShiftableEvent if residual.event_type == -1 else SplittableEvent, 0), residual.start, residual.seconds_left

class EventFactory:

    # TODO: sistema config min-max day come elemento esterno, senza dover parsare lo yaml
    
    @classmethod
    def parse_yaml(cls, filepath: Path, *, override_now_time: Optional[datetime] = None) -> list[possibleAllTypes]:
        with open(filepath) as f:
            all_data = yaml.safe_load(f)
        config_data = all_data.get("config")
        data = all_data.get("events")
        now_time_raw = config_data.get("now_time", None)
        if override_now_time is None and now_time_raw is None:
            override_now_time = datetime.now()
        elif override_now_time is None:
            override_now_time = parse_italian_date(now_time_raw)
        dur_raw = config_data.get("day_duration", None)
        max_day_raw = config_data.get("day_max", None)
        min_day_raw = config_data.get("day_min", None)
        if min_day_raw is None:
            min_day: datetime = override_now_time
        else:
            min_day: datetime = parse_value_to_datetime(min_day_raw, override_now_time)
        duration: timedelta = _TIMEDELTA_ADAPTER.validate_python(dur_raw) if dur_raw is not None else timedelta(hours=24)
        if max_day_raw is None:
            max_day: datetime = min_day + duration
        else:
            max_day: datetime = parse_value_to_datetime(max_day_raw, override_now_time)
        eventSession.set_min_max_day(max_day, min_day)
        return _adapter.validate_python([
            {"now_time": override_now_time, **d} if d.get("shift_start", None) is not None else d for d in data
        ])

    @staticmethod
    def _find_holes(*events: TimedEvent) -> list[tuple[datetime, datetime]]:
        holes: list[tuple[datetime, datetime]] = []
        cursor: datetime = eventSession.min_day
        for event in sorted(events, key=lambda e: e.start):
            if cursor < event.start:
                holes.append((cursor, event.start))
            cursor = event.end
        if cursor < eventSession.max_day:
            holes.append((cursor, eventSession.max_day))
        return holes


    @classmethod
    def organize(cls, *events: TimedEvent) -> list[TimedEvent]:

        movable: list[ShiftableEvent | SplittableEvent] = []
        # splittable: list[SplittableEvent] = []
        others: list[TimedEvent] = []

        for event in events:
            if isinstance(event, SplittableEvent) or isinstance(event, ShiftableEvent):
                movable.append(event)
            # elif :
            #     shiftable.append(event) # CHECK: si possono overlappare se shiftati male
            else:
                others.append(event)

        srtd = sorted(movable, key=_order_events, reverse=True)

        res: list[TimedEvent] = others.copy()

        for event in srtd:
            if isinstance(event, ShiftableEvent):
                res.append(event.shift_from(*[(o.start, o.end) for o in res]))
            elif isinstance(event, SplittableEvent):
                res += (event.split(*[(o.start, o.end) for o in res]))
        # others += shiftable


        holes = cls._find_holes(*res)
        if holes and len(holes) > 0:
            srtd_residuals = sorted(eventSession.missing_time, key=_order_residual)
            for hole in holes:
                hole_time_left = hole[1] - hole[0]

                # Scorriamo i task disponibili
                for task in list(srtd_residuals):
                    if hole_time_left <= timedelta(0):
                        break  # Buco riempito completamente

                    if task.event_type == -1: # SHIFTABLE
                        # Va inserito solo se entra INTERAMENTE
                        if task.seconds_left <= hole_time_left:
                            hole_time_left -= task.seconds_left
                            srtd_residuals.remove(task)
                            res.append(ShiftableEvent.from_residual(task, hole[0], hole[1]))

                    elif task.event_type >= 0:
                        # Può essere spezzettato
                        if task.seconds_left <= hole_time_left:
                            hole_time_left -= task.seconds_left
                            srtd_residuals.remove(task)
                            res.append(ShiftableEvent.from_residual(task, hole[0], hole[1]))

                        else:
                            # Consuma solo la parte che entra nel buco
                            task.seconds_left -= hole_time_left
                            task.event_type += 1
                            res.append(ShiftableEvent.from_residual(task, hole[0], hole[0]+hole_time_left, title=f"{task.title} ({task.event_type})"))
                            hole_time_left = timedelta(0)


        # DOING: for events in eventSession.missing : priority: priority -> Shiftable -> Splittable
        # others += splittable

        return sorted(res, key=lambda x: x.start)

    @classmethod
    def create_event(cls, kind: Literal["FullDay", "Shiftable", "Fixed", "Splittable"], **data) -> TimedEvent:
        return _adapter.validate_python([{ **data, "kind": kind,}])[0]
