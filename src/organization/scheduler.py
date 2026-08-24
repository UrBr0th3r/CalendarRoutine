from datetime import datetime, timezone
from pathlib import Path

from calendarAPI import CalendarManager
from organization.event import EventFactory
from organization.event.event import TimedEvent


cmg = CalendarManager()

def load(filepath: Path):
    now = datetime.now(timezone.utc)

    es = []
    for id in cmg.get_all_calendar_ids().values():
        es += (cmg.get_events(id))
    # ts = cmg.get_tasks()

    found = EventFactory.parse_yaml(filepath, override_now_time=now)

    ret = EventFactory.organize(*([f for f in es+found if isinstance(f, TimedEvent)]))

    for e in ret:
        if e.id is None:
            print("Added",e)
            cmg.add_events(e)
        else:
            print("Skipped",e)
