import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from calendarAPI import CalendarManager
from event import EventFactory
from event import TimedEvent

from dotenv import load_dotenv

from utilities.core import Paths

cmg = CalendarManager()
load_dotenv(Paths.ENV)
cname = os.getenv("CALENDAR_NAME")
if cname:
    sched_cid = cmg.get_all_calendar_ids().get(cname, None)
else:
    sched_cid = None

def load(filepath: Path):
    global sched_cid
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
            sched_cid = os.getenv("CALENDAR_ID") if not sched_cid else sched_cid
            cmg.add_events(e, calendar_id=sched_cid if sched_cid else "primary") # CHECK: se pubblicato deve essere rimosso
        else:
            print("Skipped",e)
