from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from datetime import date, timedelta
import pandas as pd

taskmanager_bp = Blueprint("taskmanager", __name__)

columns = ["Task/Assignment", "Time required", "Priority (high/medium/low)"]
rows = []
# below: same tasks but storing minutes as a number in order to create schedule
task_list = []
# day task mins and priority
schedule = {}

priority_ranking = {"high": 0, "medium": 1, "low": 2}

# get opens the task page , post runs when the form is submitted, reads form data, saves the task, then redirects back to get
@taskmanager_bp.route("/tasks", methods=["POST", "GET"])
def tasks():
    if request.method == "POST":
        task = request.form["task"]
        hours = int(request.form["hours"])
        minutes = int(request.form["minutes"])
        time = f"{hours}:{minutes:02d}"
        priority = request.form["priority"].lower()
        rows.append([task, time, priority])
        task_list.append({"task": task, "minutes": hours * 60 + minutes, "priority": priority})
        return redirect(url_for(".tasks"))

    df = pd.DataFrame(rows, columns=columns)
    return render_template("taskmanager.html",
                           table=df.to_html(index=False, classes="task-table"),
                           table_has_tasks=len(task_list) > 0)

@taskmanager_bp.route("/schedule")
def make_schedule():
    if not task_list:
        return redirect(url_for(".tasks"))

    schedule.clear()
    sorted_tasks = sorted(task_list, key=lambda t: priority_ranking.get(t["priority"], 3))

    day = date.today()
    for t in sorted_tasks:
        schedule[day.isoformat()] = [t]
        day += timedelta(days=1)

    return redirect(url_for("calendar"))

@taskmanager_bp.route("/api/schedule")
def get_schedule():
    return jsonify(schedule)