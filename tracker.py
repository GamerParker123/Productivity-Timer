import win32gui
import win32process
import psutil
from datetime import datetime
from logger import log_event, init_log, flush_buffer
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

def track_foreground(get_phase, is_unscheduled_func, stop_event, interval=1, flush_interval=10):
    """
    Tracks foreground app usage, logging time into hourly bins.
    Automatically counts AFK/paused as unscheduled.
    """
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

        # Log the interval
        if last_app and last_title:
            log_event(start_time, end_time, last_app, last_title, last_phase, paused=(phase=="unscheduled"))

        last_app, last_title, last_phase, start_time = app, title, phase, end_time

        # Periodically flush buffered events to disk
        if time.time() - last_flush >= flush_interval:
            flush_buffer()
            last_flush = time.time()

    # Final flush on stop
    flush_buffer()
