from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session
from datetime import date, timedelta
import pandas as pd

taskmanager_bp = Blueprint("taskmanager", __name__)

columns = ["Task/Assignment", "Time required", "Priority (high/medium/low)", "Timeframe"]

priority_ranking = {"high": 0, "medium": 1, "low": 2}

# most minutes of work to put on one day
MAX_MINUTES_PER_DAY = 240


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# tasks are kept in the user's session so they survive server restarts
# and work when the live site runs more than one worker
def get_task_list():
    return session.get("tasks", [])


def save_task_list(task_list):
    session["tasks"] = task_list
    session.modified = True


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
            task_list = get_task_list()
            task_list.append({"task": task, "minutes": hours * 60 + minutes, "priority": priority,
                              "start": start, "end": end, "skip_weekends": skip_weekends})
            save_task_list(task_list)
        return redirect(url_for("taskmanager.tasks"))

    task_list = get_task_list()
    rows = [[t["task"], f"{t['minutes'] // 60}:{t['minutes'] % 60:02d}", t["priority"],
             f"{t['start']} to {t['end']}"] for t in task_list]
    df = pd.DataFrame(rows, columns=columns)
    return render_template("taskmanager.html",
                           table=df.to_html(index=False, classes="task-table"),
                           table_has_tasks=len(task_list) > 0)


@taskmanager_bp.route("/tasks/clear", methods=["POST"])
def clear_tasks():
    save_task_list([])
    return redirect(url_for("taskmanager.tasks"))


def build_schedule(task_list):
    # day -> list of {task, minutes, priority}
    schedule = {}
    used = {}

    def book(day_key, t, minutes):
        schedule.setdefault(day_key, []).append(
            {"task": t["task"], "minutes": minutes, "priority": t["priority"]})
        used[day_key] = used.get(day_key, 0) + minutes

    # high priority first, then earliest deadline
    sorted_tasks = sorted(task_list, key=lambda t: (priority_ranking.get(t["priority"], 3), t["end"]))

    for t in sorted_tasks:
        if t["minutes"] <= 0:
            continue

        try:
            start = date.fromisoformat(t["start"])
            end = date.fromisoformat(t["end"])
        except ValueError:
            continue
        if end < start:
            start, end = end, start

        # every allowed day in the timeframe
        days = []
        d = start
        while d <= end:
            if not (t["skip_weekends"] and d.weekday() >= 5):
                days.append(d.isoformat())
            d += timedelta(days=1)
        if not days:
            continue

        # completely free days first (earliest first), then the least busy days
        days.sort(key=lambda k: (used.get(k, 0) > 0, used.get(k, 0), k))

        remaining = t["minutes"]
        for k in days:
            if remaining <= 0:
                break
            free = MAX_MINUTES_PER_DAY - used.get(k, 0)
            if free <= 0:
                continue
            m = min(free, remaining)
            book(k, t, m)
            remaining -= m

        # didn't fit: put the rest on the least busy day
        if remaining > 0:
            book(min(days, key=lambda k: used.get(k, 0)), t, remaining)

    return schedule


@taskmanager_bp.route("/schedule")
def make_schedule():
    if not get_task_list():
        return redirect(url_for("taskmanager.tasks"))

    return redirect(url_for("dashboard"))


@taskmanager_bp.route("/api/schedule")
def get_schedule():
    return jsonify(build_schedule(get_task_list()))