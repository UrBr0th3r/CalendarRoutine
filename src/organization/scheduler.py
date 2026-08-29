from datetime import datetime, timezone, timedelta
from pathlib import Path

from calendarAPI import CalendarManager
from event import EventFactory
from event import TimedEvent


cmg = CalendarManager()

def load(filepath: Path):
    now = datetime.now(timezone.utc)

    es = []
    for id in cmg.get_all_calendar_ids().values():
        es += (cmg.get_events(id, start=now, end=now+timedelta(days=1)))
    # ts = cmg.get_tasks()

    found = EventFactory.parse_yaml(filepath, override_now_time=now)

    ret = EventFactory.organize(*([f for f in es+found if isinstance(f, TimedEvent)]))
    print(ret)

    for e in ret:
        if e.id is None:
            e.description = f"[ DYNAMICALLY ADDED ]{" "+e.description if e.description else ""}"
            print("Added",e)
            cmg.add_events(e)
        else:
            print("Skipped",e)
