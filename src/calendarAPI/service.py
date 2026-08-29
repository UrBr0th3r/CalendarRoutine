# src/calendarAPI/service.py
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional, override

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError

from utilities.core import Paths, Serializable
from event import possibleAllTypes, FixedEvent, FocusedEvent, DailyTask, FullDayEvent
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3 import CalendarResource
    from googleapiclient._apis.tasks.v1 import TasksResource

class CalendarManager:
    
    credentials_path: Path
    token_path: Path

    calendar: CalendarResource
    tasks: TasksResource

    def __init__(self, credentials_path: str | Path = Paths.OAUTH / "credentials.json", token_path: str | Path = Paths.OAUTH / "token.json", *, port: int = 2212):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/tasks']
        
        if not self.credentials_path.exists():
            raise FileNotFoundError(f"File credenziali non trovato in: {self.credentials_path.resolve()}")

        creds = None
        # Il file token.json memorizza i token di accesso e di refresh dell'utente
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(str(self.token_path), scopes)

        # Se non ci sono credenziali valide disponibili, fai accedere l'utente
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path.absolute()), scopes)
                creds = flow.run_local_server(port=port)
            # Salva le credenziali per le successive esecuzioni
            if not os.path.exists(self.token_path.parent):
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())

        self.calendar = build('calendar', 'v3', credentials=creds)
        self.tasks = build('tasks', 'v1', credentials=creds)

    # def authenticate(self) -> Resource:
    # 
    #     if not self.credentials_path.exists():
    #         raise FileNotFoundError(f"File credenziali non trovato in: {self.credentials_path.resolve()}")
    # 
    #     creds = None
    #     # Il file token.json memorizza i token di accesso e di refresh dell'utente
    #     if os.path.exists(self.token_path):
    #         creds = Credentials.from_authorized_user_file(str(self.token_path), scopes)
    # 
    #     # Se non ci sono credenziali valide disponibili, fai accedere l'utente
    #     if not creds or not creds.valid:
    #         if creds and creds.expired and creds.refresh_token:
    #             creds.refresh(Request())
    #         else:
    #             flow = InstalledAppFlow.from_client_secrets_file(
    #                 str(self.credentials_path.absolute()), scopes)
    #             creds = flow.run_local_server(port=0)
    #         # Salva le credenziali per le successive esecuzioni
    #         if not os.path.exists(self.token_path.parent):
    #             self.token_path.parent.mkdir(parents=True, exist_ok=True)
    #         with open(self.token_path, 'w') as token:
    #             token.write(creds.to_json())
    # 
    #     return build('calendarAPI', 'v3', credentials=creds)

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_events(self, calendar_id: str = "primary", start: Optional[datetime] = None, end: Optional[datetime] = None, duration: Optional[timedelta] = None, max_results: int = 10) -> list[possibleAllTypes]:
        if start is None:
            start = datetime.now()
        if end is None and duration is not None:
            end = start + duration

        events_result = self.calendar.events().list(
            calendarId=calendar_id,  # 'primary' indica il calendario principale dell'utente
            timeMin=start.astimezone(timezone.utc).isoformat(),
            timeMax=end.astimezone(timezone.utc).isoformat() if end is not None else None,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        # print(events_result.get("items", []))
        return [ FocusedEvent.from_google(f) if f["eventType"] == "focusTime" else (FullDayEvent.from_google(f) if "date" in f["start"] else FixedEvent.from_google(f)) for f in events_result.get('items', [])]

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_tasks(self, tasklist_id: str = "@default", start: Optional[datetime] = None, end: Optional[datetime] = None, duration: Optional[timedelta] = None, max_results: int = 10):
        if start is None:
            start = datetime.now()
        if end is None and duration is not None:
            end = start + duration

        tasks_result = self.tasks.tasks().list(
            tasklist=tasklist_id,
            dueMin=start.astimezone(timezone.utc).isoformat(),
            dueMax=end.astimezone(timezone.utc).isoformat() if end is not None else None,
            maxResults=max_results,
        ).execute()

        return [DailyTask.from_google(t) for t in tasks_result.get('items', [])]

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def add_events(self, *events: Serializable, calendar_id: str = "primary"):
        for e in events:
            self.calendar.events().insert(calendarId=calendar_id, body=e.JSON()).execute()

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def add_tasks(self, *tasks: Serializable, tasks_id: str = "@default"):
        for t in tasks:
            self.tasks.tasks().insert(tasklist=tasks_id, body=t.JSON()).execute()

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_all_calendar_ids(self) -> dict[str, str]:
        """Restituisce un dizionario con la mappatura {Nome Calendario: ID Calendario}."""
        calendar_map = {}
        page_token = None

        while True:
            # Recupera la lista dei calendari dell'utente
            response = (
                self.calendar.calendarList()
                .list(pageToken=page_token)
                .execute()
            )

            for item in response.get("items", []):
                cal_id = item.get("id")
                summary = item.get("summary", "Senza Nome")
                # Se è il calendario principale, cal_id equivale a 'primary' o alla tua email
                calendar_map[summary] = cal_id

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return calendar_map

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_all_tasklist_ids(self) -> dict[str, str]:
        """Restituisce un dizionario con la mappatura {Nome TaskList: ID TaskList}."""
        tasklist_map = {}
        page_token = None

        while True:
            # Recupera la lista delle TaskList dell'utente
            response = (
                self.tasks.tasklists().list(pageToken=page_token).execute()
            )

            for item in response.get("items", []):
                list_id = item.get("id")
                title = item.get("title", "Senza Titolo")
                tasklist_map[title] = list_id

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return tasklist_map

    # Esempio d'uso:
    # tasklist_ids = get_all_tasklist_ids(cmg.tasks)
    # print(tasklist_ids)
    # Output: {'My Tasks': '@default', 'Lavoro': 'MDY2MDA0...', 'Spesa': 'MDI1Nzc...'}

