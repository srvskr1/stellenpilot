"""Fictional sample data so anyone can try the dashboard without keys or network."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from .db import DB, today
from .text import dedupe_key

D = date.today()


def _iso(days_ago: int) -> str:
    return (D - timedelta(days=days_ago)).isoformat()


def _local_at(wall: datetime) -> datetime:
    """A wall time with the offset that really applies then, summer or winter time included.

    `datetime.now().astimezone()` keeps today's offset, so a time in the other summer or
    winter time would be stored an hour off. The wall time stays as given.
    """
    return datetime.fromtimestamp(time.mktime(wall.timetuple())).astimezone()


INTERVIEW_AT = _local_at((datetime.now() + timedelta(days=4)).replace(hour=8, minute=0, second=0, microsecond=0)).isoformat()


SAMPLES = [
    dict(id="demo-1", source="Bundesagentur für Arbeit", title="Working Student Data Engineering", company="Nordlicht Energy GmbH",
         location="Essen, Nordrhein Westfalen", job_type="Werkstudent", match=86, fit="Strong", lang="English",
         why="Python, SQL and AWS pipelines match your project work closely.", gaps="No Snowflake yet.",
         gap_tags=["Snowflake"], status="ready", folder="", url="https://example.com/jobs/1"),
    dict(id="demo-2", source="Arbeitnow", title="Werkstudent Data Analytics", company="Rhein Mobility AG",
         location="Remote, Düsseldorf", remote=True, job_type="Werkstudent", match=78, fit="Strong", lang="English",
         why="Remote. Power BI and SQL reporting are the core of the role.", gaps="Asks for dbt.",
         gap_tags=["dbt"], status="new", url="https://example.com/jobs/2"),
    dict(id="demo-3", source="Adzuna", title="Junior Data Engineer", company="Ruhr Logistics SE",
         location="Dortmund", job_type="Full time", match=74, fit="Possible", lang="English",
         why="Airflow and Docker experience fits their batch pipelines.", gaps="Kafka and Terraform are new to you.",
         gap_tags=["Kafka", "Terraform"], status="applied", status_source="manual", url="https://example.com/jobs/3"),
    dict(id="demo-4", source="TheirStack", title="Working Student BI", company="Kölner Retail Tech",
         location="Köln", job_type="Werkstudent", match=69, fit="Possible", lang="English",
         why="Dashboard work in Power BI.", gaps="Retail domain and dbt.", gap_tags=["dbt"],
         status="interview", interview_at=INTERVIEW_AT,
         prep="## About Kölner Retail Tech\nA fictional company used for the demo.\n## Likely questions\n- Walk us through a pipeline you built\n- How do you check data quality?\n## Questions to ask them\n- What does the BI stack look like?",
         url="https://example.com/jobs/4"),
    dict(id="demo-5", source="Bundesagentur für Arbeit", title="Werkstudent Datenmanagement", company="Westfalen Stadtwerke",
         location="Bochum", job_type="Werkstudent", match=58, fit="Stretch", lang="German needed",
         why="Data cleaning in SAP.", gaps="Asks for fluent German.", gap_tags=["German", "SAP"],
         status="skipped", status_note="Ad asks for fluent German", url="https://example.com/jobs/5"),
    dict(id="demo-6", source="Arbeitnow", title="Data Analyst Intern (paid)", company="Spree Insights",
         location="Remote, Berlin", remote=True, job_type="", match=64, fit="Possible", lang="English",
         why="Remote. SQL and Python analysis.", gaps="dbt and Looker.", gap_tags=["dbt", "Looker"],
         status="rejected", status_source="gmail", status_note="Rejection email", url="https://example.com/jobs/6"),
]


def load_demo(settings) -> int:
    db = DB(settings.db_path)
    try:
        return _load(db)
    finally:
        db.conn.close()


def _load(db: DB) -> int:
    for i, job in enumerate(SAMPLES):
        job = {**job, "found_at": _iso(i % 3), "posted_at": _iso(i % 3 + 1),
               "dedupe_key": dedupe_key(job["company"], job["title"])}
        db.insert_job(job)
    db.run_update(today(), found=42, added=6, shortlisted=3, docs_made=3, gmail_updates=1,
                  notes="Demo data", stage="done")
    db.log_run(today(), found=42, added=6, shortlisted=3, docs_made=3, gmail_updates=1, notes="Demo data")
    return len(SAMPLES)
