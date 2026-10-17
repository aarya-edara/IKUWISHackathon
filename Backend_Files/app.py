import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from Backend_Files.calendar_export import generate_ics_content
from Backend_Files.Database_Functions.UserDatabaseFunctions import (
    add_commitment,
    add_module,
    add_task,
    delete_commitment,
    delete_module,
    delete_task,
    get_commitments,
    get_latest_recommendation,
    get_modules,
    get_schedule_blocks,
    get_tasks,
    init_db,
    save_recommendation,
)
from Backend_Files.gemini_service import analyze_schedule_and_feedback, parse_natural_language_task
from Backend_Files.google_calendar_service import (
    disconnect_google_calendar,
    fetch_google_freebusy,
    get_authorization_url,
    get_connection_status,
    handle_oauth_callback,
    sync_and_detect_conflicts,
    undo_last_displacement,
    write_blocks_to_google_calendar,
)
from Backend_Files.scheduler_engine import run_scheduler
from flask import redirect, url_for

app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))

# Initialize database on startup
init_db()


# ---------------------------------------------------------
# Web Page Routes
# ---------------------------------------------------------
@app.route("/")
def launch_page():
    """Preserve existing launch page."""
    return render_template("index.html")


@app.route("/planner")
@app.route("/tasks")
def planner_dashboard():
    """Dedicated interactive student scheduling and task dashboard."""
    return render_template("tasks_dashboard.html")


# ---------------------------------------------------------
# Modules API
# ---------------------------------------------------------
@app.route("/api/modules", methods=["GET"])
def list_modules():
    return jsonify(get_modules())


@app.route("/api/modules", methods=["POST"])
def create_module():
    data = request.get_json() or {}
    code = data.get("code", "").strip().upper()
    name = data.get("name", "").strip()
    color = data.get("color", "#4f46e5")
    weekly_hours = float(data.get("weekly_target_hours", 4.0))

    if not code or not name:
        return jsonify({"error": "Module code and name are required."}), 400

    mod_id = add_module(code, name, color, weekly_hours)
    return jsonify({"success": True, "id": mod_id}), 201


@app.route("/api/modules/<int:mod_id>", methods=["DELETE"])
def remove_module(mod_id: int):
    success = delete_module(mod_id)
    return jsonify({"success": success})


# ---------------------------------------------------------
# Tasks API
# ---------------------------------------------------------
@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    status = request.args.get("status")
    return jsonify(get_tasks(status=status))


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    module_id = data.get("module_id")
    priority = data.get("priority", "medium")
    deadline = data.get("deadline", "")
    hours = float(data.get("estimated_hours", 2.0))
    notes = data.get("notes", "")

    if not title or not deadline:
        return jsonify({"error": "Task title and deadline are required."}), 400

    task_id = add_task(title, module_id, priority, deadline, hours, notes)
    return jsonify({"success": True, "id": task_id}), 201


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def remove_task(task_id: int):
    success = delete_task(task_id)
    return jsonify({"success": success})


# ---------------------------------------------------------
# Commitments API (Fixed lectures, shifts, gym)
# ---------------------------------------------------------
@app.route("/api/commitments", methods=["GET"])
def list_commitments():
    return jsonify(get_commitments())


@app.route("/api/commitments", methods=["POST"])
def create_commitment():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    start_time = data.get("start_time", "")
    end_time = data.get("end_time", "")
    recurrence = data.get("recurrence", "none")

    if not title or not start_time or not end_time:
        return jsonify({"error": "Title, start_time, and end_time are required."}), 400

    comm_id = add_commitment(title, start_time, end_time, recurrence)
    return jsonify({"success": True, "id": comm_id}), 201


@app.route("/api/commitments/<int:comm_id>", methods=["DELETE"])
def remove_commitment(comm_id: int):
    success = delete_commitment(comm_id)
    return jsonify({"success": success})


# ---------------------------------------------------------
# Gemini AI: NLP Task Extraction
# ---------------------------------------------------------
@app.route("/api/tasks/parse-nl", methods=["POST"])
def parse_nlp():
    data = request.get_json() or {}
    prompt_text = data.get("prompt", "").strip()
    if not prompt_text:
        return jsonify({"error": "Prompt text is required."}), 400

    modules = get_modules()
    parsed_task = parse_natural_language_task(prompt_text, modules)
    return jsonify(parsed_task)


# ---------------------------------------------------------
# Scheduler API: AI & Algorithmic Timetable Generation
# ---------------------------------------------------------
@app.route("/api/schedule/generate", methods=["POST"])
def generate_schedule():
    result = run_scheduler(days_ahead=7)
    return jsonify(result)


@app.route("/api/schedule/events", methods=["GET"])
def get_calendar_events():
    """Returns combined events for FullCalendar rendering."""
    commitments = get_commitments()
    study_blocks = get_schedule_blocks()

    events = []

    # Add Fixed Commitments
    for c in commitments:
        events.append({
            "id": f"comm-{c['id']}",
            "title": f"📌 {c['title']}",
            "start": c["start_time"],
            "end": c["end_time"],
            "backgroundColor": "#334155",
            "borderColor": "#1e293b",
            "textColor": "#ffffff",
            "extendedProps": {
                "type": "commitment",
                "reason": "Fixed personal or academic event from your calendar.",
            },
        })

    # Add AI Scheduled Study Blocks
    for b in study_blocks:
        events.append({
            "id": f"block-{b['id']}",
            "title": f"📚 {b['title']}",
            "start": b["start_time"],
            "end": b["end_time"],
            "backgroundColor": b.get("color", "#4f46e5"),
            "borderColor": b.get("color", "#4f46e5"),
            "textColor": "#ffffff",
            "extendedProps": {
                "type": "study",
                "task_id": b.get("task_id"),
                "module_code": b.get("module_code"),
                "reason": b.get("reason"),
                "is_locked": bool(b.get("is_locked")),
            },
        })

    tasks = get_tasks(status="pending")
    advice = analyze_schedule_and_feedback(tasks, commitments)
    deadline_risks = advice.get("recommendations", []) if advice.get("risk_level") in ("warning", "critical") else []

    return jsonify({
        "events": events,
        "deadline_risks": [r for r in deadline_risks if "RISK" in r or "CRUNCH" in r or "DEADLINE" in r or "OVERDUE" in r],
    })


# ---------------------------------------------------------
# Gemini AI: Feedback Loop & Recommendations
# ---------------------------------------------------------
@app.route("/api/recommendations/feedback", methods=["POST"])
def handle_feedback():
    data = request.get_json() or {}
    feedback_text = data.get("feedback", "").strip()

    tasks = get_tasks(status="pending")
    commitments = get_commitments()

    analysis = analyze_schedule_and_feedback(tasks, commitments, user_feedback=feedback_text)
    save_recommendation(
        user_feedback=feedback_text,
        ai_advice=analysis.get("coach_message", ""),
        risk_level=analysis.get("risk_level", "normal"),
    )
    return jsonify(analysis)


# ---------------------------------------------------------
# Calendar Export: Google Calendar compatible .ics file
# ---------------------------------------------------------
@app.route("/api/calendar/export-ics", methods=["GET"])
def export_ics():
    content = generate_ics_content()
    return Response(
        content,
        mimetype="text/calendar",
        headers={"Content-Disposition": "attachment; filename=study_timetable.ics"},
    )


# ---------------------------------------------------------
# Settings: Gemini API Key Config
# ---------------------------------------------------------
@app.route("/api/settings/gemini-key", methods=["POST"])
def save_gemini_key():
    data = request.get_json() or {}
    key = data.get("api_key", "").strip()
    if key:
        os.environ["GEMINI_API_KEY"] = key
        # Persist to .env in project root
        env_path = PROJECT_ROOT / ".env"
        with open(env_path, "a") as f:
            f.write("\nGEMINI_API_KEY=" + key + "\n")
    return jsonify({"success": True})


# ---------------------------------------------------------
# Google Calendar: OAuth 2.0 Flow
# ---------------------------------------------------------
@app.route("/auth/google")
def google_auth_start():
    redirect_uri = request.host_url.rstrip("/") + url_for("google_auth_callback")
    auth_url, err = get_authorization_url(redirect_uri)
    if err or not auth_url:
        return redirect("/planner?google_error=" + (err or "config_missing"))
    return redirect(auth_url)


@app.route("/auth/google/callback")
def google_auth_callback():
    code = request.args.get("code")
    if not code:
        return redirect("/planner?google_error=no_code_provided")

    redirect_uri = request.host_url.rstrip("/") + url_for("google_auth_callback")
    success, result = handle_oauth_callback(code, redirect_uri)
    if success:
        return redirect("/planner?google_connected=true")
    return redirect(f"/planner?google_error={result}")


@app.route("/api/google/status", methods=["GET"])
def google_status():
    return jsonify(get_connection_status())


@app.route("/api/google/disconnect", methods=["POST"])
def google_disconnect():
    disconnect_google_calendar()
    return jsonify({"success": True})


# ---------------------------------------------------------
# Google Calendar: Two-Way Sync & Conflict Re-Planning
# ---------------------------------------------------------
@app.route("/api/google/sync", methods=["POST"])
def google_sync():
    """Polls Google Calendar freebusy and detects clashes with existing study blocks."""
    result = sync_and_detect_conflicts()
    return jsonify(result)


@app.route("/api/google/push-events", methods=["POST"])
def google_push_events():
    """Writes confirmed study blocks directly to the student's Google Calendar."""
    result = write_blocks_to_google_calendar()
    return jsonify(result)


@app.route("/api/google/simulate-clash", methods=["POST"])
def google_simulate_clash():
    """Simulates an unexpected Google Calendar event clashing with a study block."""
    blocks = get_schedule_blocks()
    if not blocks:
        return jsonify({"error": "No scheduled study blocks to clash with. Please add a task first!"}), 400

    target_block = next((b for b in blocks if not b.get("is_locked")), blocks[0])
    clash_event = {
        "title": "Urgent Group Project Meeting",
        "start_time": target_block["start_time"],
        "end_time": target_block["end_time"],
    }

    result = sync_and_detect_conflicts(simulated_clash_event=clash_event)
    result["simulated_event"] = clash_event
    return jsonify(result)


@app.route("/api/google/undo-displacement", methods=["POST"])
def google_undo_displacement():
    """Reverts the last conflict displacement to maintain user control."""
    success = undo_last_displacement()
    return jsonify({"success": success})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
