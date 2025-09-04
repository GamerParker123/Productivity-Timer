# timer.py
import state
from config import WORK_DURATION, BREAK_DURATION
from notifier import notify

def tick(is_afk):
    manual_pause = state.paused
    afk_pause = is_afk() and state.current_phase == "work"

    # Determine whether the timer should count
    timer_paused = manual_pause or afk_pause
    if not timer_paused:
        state.time_elapsed += 1

    # Overtime adjustments
    if timer_paused:
        # Overtime goes down by 1 per second when paused
        state.overtime -= 1

    elif state.current_phase == "work":
        if state.time_elapsed >= state.WORK_DURATION:
            # Overtime goes up at scaled rate
            state.overtime += state.BREAK_DURATION / state.WORK_DURATION

            if not state.notified:
                msg = (
                    "Work session complete! Take a break. Remember to transfer phases"
                    if not state.auto_phase else
                    "Work session complete! Taking a break automatically."
                )
                notify("Pomodoro Timer", msg)
                state.notified = True

    elif state.current_phase == "break":
        if state.time_elapsed >= state.BREAK_DURATION:
            # Overtime goes down by 1 per second after break ends
            state.overtime -= 1

            if not state.notified:
                msg = (
                    "Break over! Time to get back to work. Remember to transfer phases"
                    if not state.auto_phase else
                    "Break over! Starting next work session automatically."
                )
                notify("Pomodoro Timer", msg)
                state.notified = True

def get_time_remaining():
    remaining = state.phase_duration - state.time_elapsed
    return max(0, remaining)

def start_phase_timer(duration):
    state.phase_duration = duration
    state.time_elapsed = 0
    state.notified = False
