import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from logger import summarize_today, summarize_week, app_usage_summary
from config import BREAK_DURATION, WORK_DURATION
from timer import start_phase_timer, tick, get_time_remaining
import threading
import psutil
import state
import os
import json

if not os.path.exists("data"):
    os.makedirs("data")

# Apply a dark theme for matplotlib consistent with Hatsune Miku colors
plt.style.use('dark_background')
plt.rcParams['text.color'] = '#E6FBFF'
plt.rcParams['axes.facecolor'] = '#071025'
plt.rcParams['figure.facecolor'] = '#071025'
plt.rcParams['savefig.facecolor'] = '#071025'

# Globals to track current charts
current_pie_fig = None
current_pie_canvas = None
current_bar_fig = None
current_bar_canvas = None

def update_pie_chart(app_usage, frame, width=4, height=4):
    global current_pie_fig, current_pie_canvas

    # Destroy previous pie chart if it exists
    if current_pie_canvas is not None:
        try:
            current_pie_canvas.get_tk_widget().destroy()
        except tk.TclError:
            pass
        current_pie_canvas = None

    if current_pie_fig is not None:
        try:
            plt.close(current_pie_fig)
        except Exception:
            pass
        current_pie_fig = None

    if not app_usage:  # nothing to show
        return None

    # Extract cycles separately so it doesn't become a slice
    cycles = app_usage.pop("cycles", 0)

    # Create new pie chart
    current_pie_fig, ax = plt.subplots(figsize=(width, height))
    labels = list(app_usage.keys())
    sizes = list(app_usage.values())

    if sum(sizes) > 0:
        # Draw donut-style pie chart
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            autopct='%1.1f%%',
            startangle=90,
            wedgeprops=dict(width=0.4)  # makes a hole in the middle
        )
    else:
        # Draw an empty circle instead of crashing
        circle = plt.Circle((0, 0), 0.7, color='lightgray', fill=False, linewidth=2)
        ax.add_artist(circle)

    # Place cycles in the center
    ax.text(
        0, 0, f"{cycles:.1f} cycles",
        ha='center', va='center',
        fontsize=12, fontweight='bold'
    )

    ax.set_title("App Usage Share")

    current_pie_canvas = FigureCanvasTkAgg(current_pie_fig, master=frame)
    current_pie_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    current_pie_canvas.draw()

    return current_pie_canvas

def plot_hourly_usage(hourly_usage, top_apps, frame, width=6, height=3):
    global current_bar_fig, current_bar_canvas

    # Destroy previous bar chart if it exists
    if current_bar_canvas is not None:
        try:
            current_bar_canvas.get_tk_widget().destroy()
        except tk.TclError:
            pass
        current_bar_canvas = None

    if current_bar_fig is not None:
        try:
            plt.close(current_bar_fig)
        except Exception:
            pass
        current_bar_fig = None

    hours = list(range(24))
    app_names = [app for app, _ in top_apps]
    data = {app: [hourly_usage[h].get(app, 0)/60 for h in hours] for app in app_names}

    current_bar_fig, ax = plt.subplots(figsize=(width, height))
    bottom = [0]*24
    for app in app_names:
        ax.bar(hours, data[app], bottom=bottom, label=app)
        bottom = [bottom[i]+data[app][i] for i in range(24)]

    ax.set_xticks(hours)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Minutes Used")
    ax.set_title("App Usage by Hour")
    ax.legend()
    ax.grid(True, axis='y', linestyle='--', alpha=0.5)

    current_bar_canvas = FigureCanvasTkAgg(current_bar_fig, master=frame)
    current_bar_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    current_bar_canvas.draw()

    # Immediately close to avoid memory leak
    plt.close(current_bar_fig)

    return current_bar_canvas

def show_kill_warning(root, pname):
    win = tk.Toplevel(root)
    win.title("App Blocked")
    win.geometry("300x150")
    win.resizable(False, False)

    msg = tk.Label(win, text=f"{pname} was blocked and closed.", wraplength=280)
    msg.pack(pady=10)

    dont_show_var = tk.BooleanVar()

    chk = tk.Checkbutton(win, text="Don't show this again", variable=dont_show_var)
    chk.pack()

    def close_warning():
        if dont_show_var.get():
            state.show_warnings = False
        win.destroy()

    ok_btn = tk.Button(win, text="OK", command=close_warning)
    ok_btn.pack(pady=5)

    # keep it above the main window
    win.transient(root)
    win.grab_set()
    root.wait_window(win)

def start_gui(get_phase, get_afk, get_time_remaining, toggle_pause, is_unscheduled, get_overtime, set_phase, stop_event=None, root=None):
    if root is None:
        root = tk.Tk()
    root.title("Pomodoro Tracker")
    root.geometry("520x720")
    root.resizable(True, True)

    # Hatsune Miku dark-mode palette
    main_bg = "#071025"      # deep blue-black
    card_bg = "#0f2330"      # slightly lighter card background
    accent = "#00C2D1"       # main teal/turquoise accent
    accent_light = "#7CE7F4" # lighter aqua
    text_fg = "#E6FBFF"      # very light cyan for text
    sub_text = "#BFEFF6"     # secondary text

    root.configure(bg=main_bg)

    # Fonts & styles
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    default_font = tkfont.Font(family="Segoe UI", size=11)
    title_font = tkfont.Font(family="Segoe UI Semibold", size=18)
    timer_font = tkfont.Font(family="Segoe UI", size=22, weight="bold")

    # Card and label styling
    style.configure("Card.TFrame", background=card_bg, relief="flat")
    style.configure("Header.TLabel", background=main_bg, foreground=accent, font=title_font)
    style.configure("Status.TLabel", background=card_bg, foreground=text_fg, font=default_font)
    style.configure("Timer.TLabel", background=card_bg, foreground=text_fg, font=timer_font)
    style.configure("Stats.TLabel", background=card_bg, foreground=sub_text, font=default_font)
    style.configure("TButton", padding=6)
    style.configure("Accent.TButton", background=accent, foreground="#062027", font=default_font, padding=8)
    style.map("Accent.TButton",
              background=[('active', accent_light), ('!disabled', accent)],
              foreground=[('active', '#062027'), ('!disabled', '#062027')])

    style.configure("TLabel", background=main_bg, foreground=text_fg)
    style.configure("TRadiobutton", background=card_bg, foreground=sub_text)

    # Variables
    status_var = tk.StringVar()
    timer_var = tk.StringVar()
    stats_var = tk.StringVar()
    view_var = tk.StringVar(value="daily")

    # Create canvas and scrollbar
    canvas = tk.Canvas(root, bg=main_bg, highlightthickness=0)
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Create scrollable frame inside canvas
    scrollable_frame = ttk.Frame(canvas, style="Card.TFrame")
    window_id = canvas.create_window((0,0), window=scrollable_frame, anchor="nw")

    # Make the canvas scrollable
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    scrollable_frame.bind("<Configure>", on_frame_configure)

    # Make the scrollable frame width match canvas width
    def on_canvas_resize(event):
        canvas.itemconfig(window_id, width=event.width)
    canvas.bind("<Configure>", on_canvas_resize)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Top: header
    header = ttk.Label(scrollable_frame, text="Pomodoro Tracker", style="Header.TLabel")
    header.pack(pady=(8,12))

    # Status card: phase + timer
    status_card = ttk.Frame(scrollable_frame, padding=12, style="Card.TFrame")
    status_card.pack(fill=tk.X, padx=10, pady=8)
    ttk.Label(status_card, textvariable=status_var, style="Status.TLabel").pack(anchor="center", pady=(2,4))
    ttk.Label(status_card, textvariable=timer_var, style="Timer.TLabel").pack(anchor="center", pady=(2,6))

    # Middle: pie chart
    chart_card = ttk.Frame(scrollable_frame, padding=10, style="Card.TFrame")
    chart_card.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

    # View toggle buttons
    toggle_frame = ttk.Frame(scrollable_frame, style="Card.TFrame")
    toggle_frame.pack(pady=8)

    # Bottom: stats + pause button (outside scrollable frame so always visible)
    bottom_card = ttk.Frame(root, padding=10, style="Card.TFrame")
    bottom_card.pack(fill=tk.X, padx=10, pady=10, side="bottom")
    bottom_card.columnconfigure(0, weight=1)
    bottom_card.columnconfigure(1, weight=0)

    stats_label = ttk.Label(bottom_card, textvariable=stats_var, style="Stats.TLabel", justify="left")
    stats_label.grid(row=0, column=0, sticky="w")

    btn_pause = ttk.Button(bottom_card, text="Pause", command=toggle_pause, style="Accent.TButton")
    btn_pause.grid(row=0, column=1, sticky="e", padx=6)

    pie_update_counter = 0

    auto_var = tk.BooleanVar(value=state.auto_phase)

    def toggle_auto():
        state.auto_phase = auto_var.get()
    
    # Checkbutton styling
    style.configure(
        "Miku.TCheckbutton",
        background=card_bg,
        foreground=sub_text,
        font=default_font,
        focuscolor=card_bg
    )

    style.map(
        "Miku.TCheckbutton",
        background=[('active', card_bg), ('selected', card_bg)],
        foreground=[('active', accent_light), ('selected', accent)]
    )

    chk_auto = ttk.Checkbutton(
        bottom_card,
        text="Auto phase changes",
        variable=auto_var,
        command=toggle_auto,
        style="Miku.TCheckbutton"
    )

    chk_auto.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8,0))

    after_ids = []

    def gui_tick():
        tick(is_afk=get_afk)

        # Check for auto-phase
        if state.auto_phase and get_time_remaining() <= 0:
            next_phase()

        after_ids.append(root.after(1000, gui_tick))

    def next_phase():
        global time_elapsed, phase_duration
        phase = get_phase()  # current phase

        if get_time_remaining() > 0:
            return  # cannot skip phase early

        if phase == "work":
            set_phase("break")
            phase_duration = state.BREAK_DURATION  # use updated value
        elif phase == "break":
            set_phase("work")
            phase_duration = state.WORK_DURATION  # use updated value
        else:
            return

        time_elapsed = 0
        start_phase_timer(phase_duration)
        state.notified = False

    ttk.Button(bottom_card, text="Next Phase", command=next_phase, style="Accent.TButton").grid(row=0, column=2)

    # Duration settings card
    duration_card = ttk.Frame(scrollable_frame, padding=12, style="Card.TFrame")
    duration_card.pack(fill=tk.X, padx=10, pady=8)

    ttk.Label(duration_card, text="Work Duration (min):", style="Status.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(duration_card, text="Break Duration (min):", style="Status.TLabel").grid(row=1, column=0, sticky="w")

    work_var = tk.IntVar(value=state.WORK_DURATION // 60)
    break_var = tk.IntVar(value=state.BREAK_DURATION // 60)

    work_spin = tk.Spinbox(duration_card, from_=10, to=180, increment=1, textvariable=work_var, width=5)
    work_spin.grid(row=0, column=1, padx=5, pady=2)

    break_spin = tk.Spinbox(duration_card, from_=5, to=60, increment=1, textvariable=break_var, width=5)
    break_spin.grid(row=1, column=1, padx=5, pady=2)

    def apply_durations():
        state.WORK_DURATION = work_var.get() * 60
        state.BREAK_DURATION = break_var.get() * 60

        # Reset current timer if in that phase
        if state.current_phase == "work":
            start_phase_timer(state.WORK_DURATION)
        elif state.current_phase == "break":
            start_phase_timer(state.BREAK_DURATION)

    ttk.Button(duration_card, text="Apply", command=apply_durations, style="Accent.TButton").grid(row=2, column=0, columnspan=2, pady=5)

    BLOCKED_APPS_FILE = "blocked_apps.json"

    # Load blocked apps from disk or start empty
    if os.path.exists(BLOCKED_APPS_FILE):
        with open(BLOCKED_APPS_FILE, "r") as f:
            state.blocked_apps = json.load(f)
    else:
        state.blocked_apps = []

    PROTECTED_APPS = ["explorer.exe", "taskmgr.exe", "svchost.exe", "csrss.exe"]

    # Blocker card
    block_card = ttk.Frame(scrollable_frame, padding=12, style="Card.TFrame")
    block_card.pack(fill=tk.X, padx=10, pady=8)
    ttk.Label(block_card, text="Apps to Block During Work:", style="Status.TLabel").pack(anchor="w")

    blocked_apps_frame = ttk.Frame(block_card)
    blocked_apps_frame.pack(fill=tk.X, pady=5)

    checkbox_vars = {}

    def save_blocked_apps():
        with open(BLOCKED_APPS_FILE, "w") as f:
            json.dump(state.blocked_apps, f, indent=2)

    def refresh_blocked_apps_list():
        for widget in blocked_apps_frame.winfo_children():
            widget.destroy()
        checkbox_vars.clear()
        
        for app in state.blocked_apps:
            var = tk.BooleanVar(value=True)
            cb = ttk.Checkbutton(blocked_apps_frame, text=app, variable=var, style="Miku.TCheckbutton")
            cb.pack(anchor="w")
            checkbox_vars[app] = var

    def add_app():
        def choose_browse():
            dialog.destroy()
            file_path = filedialog.askopenfilename(
                title="Select App to Block",
                filetypes=[("Executables", "*.exe")],
            )
            if not file_path:
                return
            app_name = os.path.basename(file_path).lower()
            add_to_blocklist(app_name)

        def choose_type():
            dialog.destroy()
            app_name = tk.simpledialog.askstring(
                "Add App Manually",
                "Enter app executable name (e.g., chrome.exe):"
            )
            if not app_name:
                return
            app_name = app_name.strip().lower()
            add_to_blocklist(app_name)

        def add_to_blocklist(app_name):
            # Check protected list
            if app_name in PROTECTED_APPS:
                messagebox.showwarning(
                    "Warning",
                    f"{app_name} is a critical system process and cannot be blocked."
                )
                return

            # Add if not already there
            if app_name not in state.blocked_apps:
                state.blocked_apps.append(app_name)
                refresh_blocked_apps_list()
                save_blocked_apps()

        # Create dialog
        dialog = tk.Toplevel(root)
        dialog.title("Add App")
        dialog.geometry("300x100")
        dialog.resizable(False, False)

        tk.Label(dialog, text="How would you like to add the app?").pack(pady=10)
        tk.Button(dialog, text="Browse", width=10, command=choose_browse).pack(side="left", padx=20, pady=10)
        tk.Button(dialog, text="Type", width=10, command=choose_type).pack(side="right", padx=20, pady=10)

    def remove_unchecked_apps():
        to_remove = []
        for app, var in checkbox_vars.items():
            if not var.get():
                if app.lower() in PROTECTED_APPS:
                    messagebox.showwarning(
                        "Warning",
                        f"{app} is a critical system process and cannot be removed."
                    )
                else:
                    to_remove.append(app)
        
        for app in to_remove:
            state.blocked_apps.remove(app)
        
        refresh_blocked_apps_list()
        save_blocked_apps()

    ttk.Button(block_card, text="Add App", command=add_app, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
    ttk.Button(block_card, text="Remove Unchecked", command=remove_unchecked_apps, style="Accent.TButton").pack(side=tk.LEFT, padx=5)

    # Initial refresh
    refresh_blocked_apps_list()

    after_id = None
    current_app_canvas = None

    def on_view_change():
        # Reset counter so the chart updates immediately
        nonlocal pie_update_counter
        pie_update_counter = 0
        update_gui()  # force immediate GUI update

    ttk.Radiobutton(toggle_frame, text="Daily", variable=view_var, value="daily", style="TRadiobutton", command=on_view_change).pack(side=tk.LEFT, padx=8)
    ttk.Radiobutton(toggle_frame, text="Weekly", variable=view_var, value="weekly", style="TRadiobutton", command=on_view_change).pack(side=tk.LEFT, padx=8)

    current_pie_canvas = None

    def update_gui():
        nonlocal pie_update_counter, after_id
        global current_pie_canvas, current_bar_canvas
        overtime = get_overtime()
        phase = get_phase()
        paused = is_unscheduled()
        remaining = get_time_remaining()

        status = "Paused / AFK (unscheduled)" if paused else "Active"

        try:
            status_var.set(f"Phase: {phase.upper()}  |  Status: {status}")
            timer_var.set(f"Time Left: {int(remaining//60):02d}:{int(remaining%60):02d} | Overtime: {int(overtime)}s")
            btn_pause.config(text="Resume" if paused else "Pause")
        except tk.TclError:
            return

        if pie_update_counter % 60 == 0:
            data = summarize_today() if view_var.get() == "daily" else summarize_week()

            # Pie chart
            current_pie_canvas = update_pie_chart(data, chart_card)
            # Stats text
            stats = summarize_today() if view_var.get() == "daily" else summarize_week()

            work_time = stats["work"]
            break_time = stats["break"]
            unscheduled_time = stats["unscheduled"]
            cycles = stats["cycles"]

            stats_var.set(
                f"{view_var.get().capitalize()} Summary:\n"
                f"Work: {work_time // 60} min\n"
                f"Break: {break_time // 60} min\n"
                f"Unscheduled: {unscheduled_time // 60} min\n"
                f"Cycles: {cycles:.1f}"
            )

            # App usage bar graph
            top_apps, hourly_usage = (
                app_usage_summary("daily") if view_var.get() == "daily" else app_usage_summary("weekly")
            )
            current_bar_canvas = plot_hourly_usage(hourly_usage, top_apps, chart_card)
        pie_update_counter += 1
        after_id = root.after(1000, update_gui)

    def on_close():
        if stop_event:
            stop_event.set()

        # Cancel any scheduled after calls
        try:
            if after_id:
                root.after_cancel(after_id)
        except tk.TclError:
            pass

        # Destroy pie chart safely
        if current_pie_canvas is not None:
            try:
                current_pie_canvas.get_tk_widget().destroy()
            except tk.TclError:
                pass

        # Destroy app usage bar graph safely
        if current_bar_canvas is not None:
            try:
                current_bar_canvas.get_tk_widget().destroy()
            except tk.TclError:
                pass

        # Close matplotlib figures
        try:
            plt.close("all")
        except Exception:
            pass

        # Destroy the Tk root window
        try:
            root.destroy()
        except tk.TclError:
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)

    gui_tick()
    update_gui()
    
    def check_stop():
        if stop_event and stop_event.is_set():
            on_close()
        else:
            root.after(100, check_stop)  # check every 100ms

    root.after(100, check_stop)
    root.mainloop()