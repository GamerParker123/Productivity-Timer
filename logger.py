import csv
import os
from datetime import datetime, date, timedelta
from config import WORK_DURATION, LOG_PATH
from collections import defaultdict, Counter
import threading
import state

csv_lock = threading.Lock()
log_buffer = []
BUFFER_FLUSH_INTERVAL = 10  # seconds

def init_log():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_start", "timestamp_end", "duration_secs", "app_name", "window_title", "phase"])

def flush_buffer():
    if not log_buffer:
        return
    with csv_lock:
        rows = []
        cutoff = datetime.now() - timedelta(days=30)
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_end = datetime.strptime(row["timestamp_end"], "%Y-%m-%d %H:%M:%S")
                    if row_end >= cutoff:
                        rows.append(row)

        # Merge buffered events by hour + app + window + phase
        merge_dict = {}
        for r in rows:
            hour_start = datetime.strptime(r["timestamp_start"], "%Y-%m-%d %H:%M:%S").replace(minute=0, second=0, microsecond=0)
            key = (hour_start, r["app_name"], r["window_title"], r["phase"])
            merge_dict[key] = r

        for entry in log_buffer:
            hour_start = datetime.strptime(entry["timestamp_start"], "%Y-%m-%d %H:%M:%S").replace(minute=0, second=0, microsecond=0)
            key = (hour_start, entry["app_name"], entry["window_title"], entry["phase"])
            if key in merge_dict:
                merge_dict[key]["duration_secs"] = str(
                    int(merge_dict[key]["duration_secs"]) + int(entry["duration_secs"])
                )
                if entry["timestamp_end"] > merge_dict[key]["timestamp_end"]:
                    merge_dict[key]["timestamp_end"] = entry["timestamp_end"]
            else:
                merge_dict[key] = entry

        # Write back
        with open(LOG_PATH, mode="w", newline='', encoding='utf-8') as f:
            fieldnames = ["timestamp_start", "timestamp_end", "duration_secs", "app_name", "window_title", "phase"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(merge_dict.values())

        log_buffer.clear()

def log_event(start_time, end_time, app_name, window_title, phase, paused=False):
    if paused:
        phase = "unscheduled"

    duration = int((end_time - start_time).total_seconds())
    if duration < 1:  # skip tiny intervals
        return

    entry = {
        "timestamp_start": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp_end": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_secs": str(duration),
        "app_name": app_name,
        "window_title": window_title,
        "phase": phase
    }

    log_buffer.append(entry)

def app_usage_summary(period="daily"):
    """
    Returns a summary of app usage:
      top_apps: list of (app_name, total_seconds)
      hourly_usage: dict of hour -> dict(app_name -> seconds)
    period: "daily" or "weekly"
    """
    today = date.today()
    if period == "daily":
        start_date = today
    else:  # weekly
        start_date = today - timedelta(days=today.weekday())

    top_apps_counter = Counter()
    hourly_usage = defaultdict(lambda: defaultdict(int))  # hour -> app -> seconds

    with csv_lock:
        try:
            with open(LOG_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_start = datetime.strptime(row["timestamp_start"], "%Y-%m-%d %H:%M:%S")
                    if row_start.date() < start_date:
                        continue
                    app_name = row["app_name"]
                    duration = int(row.get("duration_secs", 0))
                    top_apps_counter[app_name] += duration

                    # Split duration by hour
                    end_time = datetime.strptime(row["timestamp_end"], "%Y-%m-%d %H:%M:%S")
                    current = row_start
                    while current < end_time:
                        hour = current.hour
                        # next full hour boundary
                        next_hour = (current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                        segment_end = min(next_hour, end_time)
                        duration_sec = int((segment_end - current).total_seconds())
                        if duration_sec > 0:
                            hourly_usage[hour][app_name] += duration_sec
                        current = segment_end
        except FileNotFoundError:
            pass

    # Top 5 apps
    top_apps = top_apps_counter.most_common(5)
    return top_apps, hourly_usage

def summarize_today():
    today_str = date.today().strftime("%Y-%m-%d")
    work_time = break_time = unscheduled_time = 0

    with csv_lock:
        try:
            with open(LOG_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["timestamp_start"].startswith(today_str):
                        try:
                            duration = int(row["duration_secs"])
                        except ValueError:
                            duration = 0
                        phase = row.get("phase", "unscheduled")
                        if phase == "work":
                            work_time += duration
                        elif phase == "break":
                            break_time += duration
                        elif phase == "unscheduled":
                            unscheduled_time += duration
        except FileNotFoundError:
            pass

    cycles = work_time / WORK_DURATION if WORK_DURATION > 0 else 0

    return {
        "work": work_time,
        "break": break_time,
        "unscheduled": unscheduled_time,
        "cycles": cycles,
    }

def summarize_week():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week_str = start_of_week.strftime("%Y-%m-%d")

    work_time = break_time = unscheduled_time = 0

    with csv_lock:
        try:
            with open(LOG_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["timestamp_start"][:10] >= start_of_week_str:
                        try:
                            duration = int(row["duration_secs"])
                        except ValueError:
                            duration = 0
                        phase = row.get("phase", "unscheduled")
                        if phase == "work":
                            work_time += duration
                        elif phase == "break":
                            break_time += duration
                        elif phase == "unscheduled":
                            unscheduled_time += duration
        except FileNotFoundError:
            pass

    cycles = work_time / WORK_DURATION if WORK_DURATION > 0 else 0

    return {
        "work": work_time,
        "break": break_time,
        "unscheduled": unscheduled_time,
        "cycles": cycles,
    }
