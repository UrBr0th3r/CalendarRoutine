"""
File di gestione e configurazione del server
Attende la richiesta inviata dal cellulare, per permettere l'avvio dello scheduler
"""
from pathlib import Path
from typing import Optional

import uvicorn

import organization
from calendarAPI import CalendarManager
from datetime import datetime, timezone, timedelta

from organization import load
from organization.event import *
import requests
from fastapi import FastAPI, HTTPException
from pathlib import Path
from organization.event.event import TimedEvent

app = FastAPI(title="Calendar Routine API")
DEFAULT_YAML_PATH = Path(r"C:\Users\popis\PycharmProjects\Calendar\resources\events.yaml")
@app.post("/sync")
def sync_calendar(yaml_path: Optional[str] = None):
    """
    Esegue la sincronizzazione del calendario partendo da un path locale YAML.
    Se non specificato, usa il file di default.
    """
    target_path = Path(yaml_path) if yaml_path else DEFAULT_YAML_PATH

    if not target_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File YAML non trovato al percorso: {target_path}"
        )

    try:
        load(target_path)
        return {
            "status": "success",
            "message": "Synchronization completed",
            "file_processed": str(target_path)
        }
    except Exception as e:
        # Registra l'eccezione nei log se necessario
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':

    uvicorn.run(
        app,  # Modifica "main" con il nome reale del tuo file .py (es: "api:app")
        host="127.0.0.1",
        port=2442,
        # reload=True  # Ricarica automatica in fase di sviluppo al salvataggio
    )

    pass
    # DOING: APRI FASTAPI
    # cmg = CalendarManager()

    # now = datetime.now(timezone.utc)

    # Esegue la chiamata per ottenere i primi 10 eventi
    # events_result = cmg.calendar.events().list(
    #     calendarId='primary',  # 'primary' indica il calendario principale dell'utente
    #     timeMin=now.isoformat(),
    #     timeMax=(now+timedelta(hours=72)).isoformat(),
    #     maxResults=10,
    #     singleEvents=True,
    #     orderBy='startTime'
    # ).execute()
    #
    # events = events_result.get('items', [])

    # for event in cmg.get_events():
        # start = event['start'].get('dateTime', event['start'].get('date'))
        # print(f"ID: {event['id']} | Inizio: {start} | Titolo: {event.get('summary')}")
        # print(event)

    # for task in cmg.get_tasks("TXNsRGFWcDViN2RVb290eQ"):
    #     print(task)

    # for tl in cmg.tasks.tasklists().list().execute().get('items', []):
    #     print(tl)


    # new_p = DailyTask(
    #     title="test",
    #     due=datetime(2026, 8, 22, hour=14, minute=30),
    #     notes="bcbcb"
    # )
    #
    # created_task = cmg.tasks.tasks().insert(tasklist='TXNsRGFWcDViN2RVb290eQ', body=new_p.JSON()).execute()
    #
    # print(f"Evento Focus creato con ID: {created_task.get('id')}")
    #
    # new_e = TimedEvent(
    #     title="prova",
    #     description="prova_desc",
    #     start=datetime(2026, 8, 22, hour=12, minute=30),
    #     end=datetime(2026, 8, 22, hour=13, minute=30),
    # )
    #
    # created_event = cmg.calendar.events().insert(calendarId='primary', body=new_e.JSON()).execute()
    #
    # print(f"Evento creato con ID: {created_event.get('id')}")

    # found = EventFactory.parse_yaml(Path(r"C:\Users\popis\PycharmProjects\Calendar\resources\events.yaml"), override_now_time=datetime(year=now.year, month=now.month, day=now.day, hour=7, minute=30))
    # for f in found:
    #     print(type(f), f)
    #
    # print()
    #
    # ret = EventFactory.organize(*[f for f in found if isinstance(f, TimedEvent)])
    # for e in ret:
    #     print(type(e), e)
    #     # cmg.calendar.events().insert(calendarId='primary', body=e.JSON()).execute()
    #
    # print()
    #
    # print(EventFactory.create_event(title="prova",
    #     description="prova_desc",
    #     start=datetime(2026, 8, 22, hour=12, minute=30),
    #     end=datetime(2026, 8, 22, hour=13, minute=30), kind="Fixed"))


    # print("Done")
    # print(help(cmg.service.events().list))

    # load(Path(r"C:\Users\popis\PycharmProjects\Calendar\resources\events.yaml"))
