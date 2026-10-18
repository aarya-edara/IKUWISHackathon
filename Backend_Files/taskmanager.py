from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from datetime import date, timedelta
import pandas as pd

taskmanager_bp = Blueprint("taskmanager", __name__)

columns = ["Task/Assignment", "Time required", "Priority (high/medium/low)", "Timeframe"]
rows = []
# below: same tasks but storing minutes as a number in order to create schedule
task_list = []
# day -> list of {task, minutes, priority}
schedule = {}

priority_ranking = {"high": 0, "medium": 1, "low": 2}

# most minutes of work to put on one day
MAX_MINUTES_PER_DAY = 240


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# get opens the task page , post runs when the form is submitted, reads form data, saves the task, then redirects back to get
@taskmanager_bp.route("/tasks", methods=["GET", "POST"])
def tasks():
    if request.method == "POST":
        task = request.form.get("task", "").strip()
        hours = to_int(request.form.get("hours"))
        minutes = to_int(request.form.get("minutes"))
        priority = request.form.get("priority", "medium").lower()
        start = request.form.get("start_date") or date.today().isoformat()
        end = request.form.get("end_date") or (date.today() + timedelta(days=6)).isoformat()
        skip_weekends = "skip_weekends" in request.form

        if task:
            rows.append([task, f"{hours}:{minutes:02d}", priority, f"{start} to {end}"])
            task_list.append({"task": task, "minutes": hours * 60 + minutes, "priority": priority,
                              "start": start, "end": end, "skip_weekends": skip_weekends})
        return redirect(url_for("taskmanager.tasks"))

    df = pd.DataFrame(rows, columns=columns)
    return render_template("taskmanager.html",
                           table=df.to_html(index=False, classes="task-table"),
                           table_has_tasks=len(task_list) > 0)


def book(day_key, t, minutes, used):
    schedule.setdefault(day_key, []).append(
        {"task": t["task"], "minutes": minutes, "priority": t["priority"]})
    used[day_key] = used.get(day_key, 0) + minutes


@taskmanager_bp.route("/schedule")
def make_schedule():
    if not task_list:
        return redirect(url_for("taskmanager.tasks"))

    schedule.clear()
    used = {}

    sorted_tasks = sorted(task_list, key=lambda t: (priority_ranking.get(t["priority"], 3), t["end"]))

    for t in sorted_tasks:
        if t["minutes"] <= 0:
            continue

        start = date.fromisoformat(t["start"])
        end = date.fromisoformat(t["end"])
        if end < start:
            start, end = end, start

        days = []
        d = start
        while d <= end:
            if not (t["skip_weekends"] and d.weekday() >= 5):
                days.append(d.isoformat())
            d += timedelta(days=1)
        if not days:
            continue

        days.sort(key=lambda k: (used.get(k, 0) > 0, used.get(k, 0), k))

        remaining = t["minutes"]
        for k in days:
            if remaining <= 0:
                break
            free = MAX_MINUTES_PER_DAY - used.get(k, 0)
            if free <= 0:
                continue
            m = min(free, remaining)
            book(k, t, m, used)
            remaining -= m

        if remaining > 0:
            book(min(days, key=lambda k: used.get(k, 0)), t, remaining, used)

    return redirect(url_for("dashboard"))


@taskmanager_bp.route("/api/schedule")
def get_schedule():
    return jsonify(schedule)