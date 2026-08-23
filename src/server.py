"""
File di gestione e configurazione del server
Attende la richiesta inviata dal cellulare, per permettere l'avvio dello scheduler
"""

from calendarAPI import CalendarManager
from datetime import datetime, timezone, timedelta
from organization.event import *
import requests




if __name__ == '__main__':
    cmg = CalendarManager()

    now = datetime.now(timezone.utc)

    # Esegue la chiamata per ottenere i primi 10 eventi
    events_result = cmg.calendar.events().list(
        calendarId='primary',  # 'primary' indica il calendario principale dell'utente
        timeMin=now.isoformat(),
        timeMax=(now+timedelta(hours=72)).isoformat(),
        maxResults=10,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        # print(f"ID: {event['id']} | Inizio: {start} | Titolo: {event.get('summary')}")
        print(event)

    tasks_result = cmg.tasks.tasks().list(
        tasklist='TXNsRGFWcDViN2RVb290eQ',  # 'primary' indica il calendario principale dell'utente
        dueMin=now.isoformat(),
        dueMax=(now + timedelta(hours=72)).isoformat(),
        maxResults=10,
        # singleEvents=True,
        # orderBy='startTime'
    ).execute()

    tasks = tasks_result.get('items', [])

    for task in tasks:
        print(task)

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




    # print("Done")
    # print(help(cmg.service.events().list))
