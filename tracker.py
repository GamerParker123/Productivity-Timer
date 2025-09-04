import win32gui
import win32process
import psutil
from datetime import datetime
from logger import log_event, init_log, flush_buffer, maybe_compact
import threading
import time

def get_active_window_info():
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        app_name = process.name()
        window_title = win32gui.GetWindowText(hwnd)
        return app_name, window_title
    except Exception:
        return None, None

def track_foreground(get_phase, is_unscheduled_func, stop_event, interval=1, flush_interval=30):
    init_log()
    last_app, last_title = get_active_window_info()
    last_phase = get_phase()
    start_time = datetime.now()
    last_flush = time.time()

    while not stop_event.is_set():
        stop_event.wait(interval)
        if stop_event.is_set():
            break

        app, title = get_active_window_info()
        phase = get_phase()
        if is_unscheduled_func() and phase == "work":
            phase = "unscheduled"

        end_time = datetime.now()
        if last_app and last_title:
            log_event(start_time, end_time, last_app, last_title, last_phase, paused=(phase=="unscheduled"))

        last_app, last_title, last_phase, start_time = app, title, phase, end_time

        # Periodic flush & rare compaction (both are quick now)
        if time.time() - last_flush >= flush_interval:
            flush_buffer()
            maybe_compact()
            last_flush = time.time()

    flush_buffer()
