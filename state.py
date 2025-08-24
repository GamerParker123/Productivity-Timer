from config import WORK_DURATION, BREAK_DURATION

current_phase = "work"
time_elapsed = 0
paused = False
overtime = 7200
phase_duration = WORK_DURATION
notified = False
auto_phase = False
blocked_apps = []
show_warnings = True