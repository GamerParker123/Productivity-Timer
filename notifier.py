from winotify import Notification, audio
import os
import threading
import time

def _show_notification(title, message):
    icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
    toast = Notification(
        app_id="Pomodoro Timer",
        title=title,
        msg=message,
        icon=icon_path  # optional
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    time.sleep(0.1)  # ensures Windows displays it

def notify(title, message):
    """Thread-safe notification call."""
    threading.Thread(target=_show_notification, args=(title, message), daemon=True).start()
