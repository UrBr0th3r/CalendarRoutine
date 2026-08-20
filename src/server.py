"""
File di gestione e configurazione del server
Attende la richiesta inviata dal cellulare, per permettere l'avvio dello scheduler
"""

from calendarAPI import CalendarManager
from datetime import datetime, timezone, timedelta
import requests




if __name__ == '__main__':
    cmg = CalendarManager()

    now = datetime.now(timezone.utc)

    # Esegue la chiamata per ottenere i primi 10 eventi
    events_result = cmg.service.events().list(
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
    # print("Done")
    # print(help(cmg.service.events().list))
