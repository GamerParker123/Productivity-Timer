# logger.py
import csv
import os
from datetime import datetime, date, timedelta
from config import WORK_DURATION, LOG_PATH
from collections import defaultdict, Counter
import threading

# Separate locks: one for the in-memory buffer, none for CSV reads.
buffer_lock = threading.Lock()
log_buffer = []

# Flush less often; 30–60s is plenty.
BUFFER_FLUSH_INTERVAL = 30  # seconds
# Compact no more than once per hour
_COMPACT_EVERY_SECS = 3600
_last_compact_ts = 0

def init_log():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_start", "timestamp_end", "duration_secs", "app_name", "window_title", "phase"])

def _append_rows(rows):
    """Append rows atomically by opening in append mode (single writer)."""
    if not rows:
        return
    with open(LOG_PATH, mode="a", newline='', encoding='utf-8') as f:
        fieldnames = ["timestamp_start", "timestamp_end", "duration_secs", "app_name", "window_title", "phase"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        # Header already exists
        writer.writerows(rows)

def flush_buffer():
    """Fast flush: pop the memory buffer and append rows. No global CSV lock."""
    global _last_compact_ts
    # Pop entries quickly under buffer lock
    with buffer_lock:
        if not log_buffer:
            return
        to_write = list(log_buffer)
        log_buffer.clear()

    # Append to disk (fast)
    _append_rows(to_write)

def maybe_compact():
    """
    Occasionally prune rows older than 30 days.
    Do this infrequently and NEVER on the GUI thread.
    """
    global _last_compact_ts
    now = datetime.now().timestamp()
    if now - _last_compact_ts < _COMPACT_EVERY_SECS:
        return
    _last_compact_ts = now

    cutoff = datetime.now() - timedelta(days=30)
    tmp_path = LOG_PATH + ".tmp"

    try:
        with open(LOG_PATH, newline='', encoding='utf-8') as src, \
             open(tmp_path, mode='w', newline='', encoding='utf-8') as dst:
            reader = csv.DictReader(src)
            fieldnames = reader.fieldnames or ["timestamp_start", "timestamp_end", "duration_secs", "app_name", "window_title", "phase"]
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                try:
                    row_end = datetime.strptime(row["timestamp_end"], "%Y-%m-%d %H:%M:%S")
                    if row_end >= cutoff:
                        writer.writerow(row)
                except Exception:
                    # If a row is malformed, keep it (safer than data loss)
                    writer.writerow(row)
        # Atomic replace so readers never see a half-written file
        os.replace(tmp_path, LOG_PATH)
    except FileNotFoundError:
        # Nothing to compact
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    except Exception:
        # On any error, try to clean temp; leave original file untouched
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def log_event(start_time, end_time, app_name, window_title, phase, paused=False):
    if paused:
        phase = "unscheduled"

    duration = int((end_time - start_time).total_seconds())
    if duration < 1:
        return

    entry = {
        "timestamp_start": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp_end": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_secs": str(duration),
        "app_name": app_name,
        "window_title": window_title,
        "phase": phase
    }

    # Only protect memory buffer (tiny critical section)
    with buffer_lock:
        log_buffer.append(entry)

# app_usage_summary / summarize_today / summarize_week:
# - remove `with csv_lock:`
# - keep the rest as-is

def app_usage_summary(period="daily"):
    from collections import defaultdict, Counter
    from datetime import datetime, date, timedelta

    today = date.today()
    start_date = today if period == "daily" else (today - timedelta(days=today.weekday()))

    top_apps_counter = Counter()
    hourly_usage = defaultdict(lambda: defaultdict(int))

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

                end_time = datetime.strptime(row["timestamp_end"], "%Y-%m-%d %H:%M:%S")
                current = row_start
                while current < end_time:
                    hour = current.hour
                    next_hour = (current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                    segment_end = min(next_hour, end_time)
                    duration_sec = int((segment_end - current).total_seconds())
                    if duration_sec > 0:
                        hourly_usage[hour][app_name] += duration_sec
                    current = segment_end
    except FileNotFoundError:
        pass

    return top_apps_counter.most_common(5), hourly_usage

def summarize_today():
    today_str = date.today().strftime("%Y-%m-%d")
    work_time = break_time = unscheduled_time = 0

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
