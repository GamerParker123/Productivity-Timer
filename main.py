import threading
from timer import get_time_remaining
from tracker import track_foreground
from idle_tracker import get_idle_duration
from gui import start_gui, show_kill_warning
import state
from config import AFK_TIMEOUT
import time
import psutil
import os
import tkinter as tk
from tkinter import messagebox

current_pid = os.getpid()

def enforce_blocked_apps(root):
    """Kill any blocked apps if we're in a work phase."""
    if state.current_phase != "work":
        return

    blocked = {app.lower() for app in state.blocked_apps}
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            pname = (proc.info['name'] or "").lower()
            if pname in blocked and proc.info['pid'] != os.getpid():
                proc.kill()
                if state.show_warnings:
                    root.after(0, lambda p=pname: show_kill_warning(root, p))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def block_apps_loop(stop_event, root):
    """Thread loop that enforces blocked apps every second."""
    while not stop_event.is_set():
        enforce_blocked_apps(root)
        time.sleep(1)

# TODO: Add idle timer pause toggle (if you don't want the timer to pause while idle)

def get_phase():
    return state.current_phase

def get_afk():
    return get_idle_duration() >= AFK_TIMEOUT if state.current_phase == "work" else False

def toggle_pause():
    state.paused = not state.paused
    return state.paused

def is_unscheduled():
    return state.paused or get_afk()

if __name__ == "__main__":
    root = tk.Tk()

    stop_event = threading.Event()

    tracker_thread = threading.Thread(
        target=track_foreground, 
        args=(get_phase, is_unscheduled, stop_event),
        daemon=True
    )
    tracker_thread.start()

    block_thread = threading.Thread(
        target=block_apps_loop, 
        args=(stop_event, root),
        daemon=True
    )
    block_thread.start()

    # Start GUI
    start_gui(
        get_phase,
        get_afk,
        get_time_remaining,
        toggle_pause,
        is_unscheduled,
        get_overtime=lambda: state.overtime,
        set_phase=lambda new_phase: setattr(state, 'current_phase', new_phase),
        stop_event=stop_event,
        root=root  # <-- add this
    )

    # GUI closed → stop tracking
    stop_event.set()
    tracker_thread.join()
