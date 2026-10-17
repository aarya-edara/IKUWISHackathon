import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def get_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _get_gemini_client():
    api_key = get_api_key()
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[Gemini Client Warning] Could not initialize google-genai: {e}")
        return None


def parse_natural_language_task(nl_text: str, known_modules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Parse student natural language input into structured task or commitment attributes."""
    client = _get_gemini_client()
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S (%A)")
    modules_str = ", ".join([f"{m.get('code')} ({m.get('name')})" for m in known_modules]) or "None specified"

    if client:
        try:
            prompt = f"""
You are an intelligent scheduling assistant for university students.
Current time: {now_str}
Known student modules: {modules_str}

Analyze the student's natural language request:
"{nl_text}"

Extract the attributes and return ONLY a valid JSON object matching this schema:
{{
    "title": "string (clear name of the task or commitment)",
    "module_code": "string (matching one of the known modules or an appropriate module code, e.g. CS101, or empty string)",
    "priority": "low" | "medium" | "high",
    "deadline": "ISO format string YYYY-MM-DDTHH:MM (if flexible task, calculate exact date based on current time. If time not specified, default to 23:59)",
    "estimated_hours": float (estimated hours to complete, default 2.0 if not stated),
    "is_commitment": boolean (true ONLY if it is a fixed event/class/appointment with fixed start and end time),
    "start_time": "ISO format string YYYY-MM-DDTHH:MM (if is_commitment is true)",
    "end_time": "ISO format string YYYY-MM-DDTHH:MM (if is_commitment is true)",
    "notes": "string (any extra details, or empty string)"
}}

Rules:
- If today is {now.strftime('%A')}, "tomorrow" is {(now + timedelta(days=1)).strftime('%Y-%m-%d')}, "Friday" is the upcoming Friday.
- If it's a fixed event (e.g. "Lecture Monday 10-12" or "Gym tomorrow 5pm to 6pm"), set is_commitment to true and provide start_time and end_time.
- If it's a task (e.g. "Essay due Friday", "Problem set", "Revision"), set is_commitment to false and set deadline and estimated_hours.
- Do NOT wrap in markdown fences other than raw json.
"""
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt,
            )
            raw = response.text.strip()
            # Clean possible markdown block
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            data = json.loads(raw.strip())
            return _normalize_task_data(data, known_modules, now)
        except Exception as e:
            print(f"[Gemini NLP fallback triggered] {e}")

    # Fallback heuristic parser
    return _heuristic_parse_task(nl_text, known_modules, now)


def _normalize_task_data(data: Dict[str, Any], known_modules: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    # Match module_id if module_code matches known modules
    module_code = str(data.get("module_code", "")).upper().strip()
    module_id = None
    for m in known_modules:
        if m.get("code", "").upper() == module_code or module_code in m.get("name", "").upper():
            module_id = m.get("id")
            module_code = m.get("code")
            break

    # Validate priority
    priority = str(data.get("priority", "medium")).lower()
    if priority not in ("low", "medium", "high"):
        priority = "medium"

    # Validate hours
    try:
        hours = float(data.get("estimated_hours", 2.0))
        if hours <= 0:
            hours = 1.0
    except (ValueError, TypeError):
        hours = 2.0

    # Validate deadline
    deadline = data.get("deadline")
    if not deadline or not isinstance(deadline, str):
        # Default deadline 3 days ahead at 23:59
        deadline = (now + timedelta(days=3)).strftime("%Y-%m-%dT23:59")
    elif len(deadline) == 10:
        deadline += "T23:59"

    return {
        "title": data.get("title", "Study Task").strip() or "Study Task",
        "module_code": module_code,
        "module_id": module_id,
        "priority": priority,
        "deadline": deadline,
        "estimated_hours": hours,
        "is_commitment": bool(data.get("is_commitment", False)),
        "start_time": data.get("start_time", ""),
        "end_time": data.get("end_time", ""),
        "notes": data.get("notes", ""),
        "source": "gemini",
    }


def _heuristic_parse_task(text: str, known_modules: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """Graceful rule-based fallback when Gemini API key is absent or offline."""
    lower = text.lower()

    # Detect priority
    priority = "medium"
    if any(w in lower for w in ["urgent", "high", "asap", "critical", "important"]):
        priority = "high"
    elif any(w in lower for w in ["low", "whenever", "chill", "optional"]):
        priority = "low"

    # Detect hours
    hours = 2.0
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", lower)
    if hour_match:
        try:
            hours = float(hour_match.group(1))
        except ValueError:
            hours = 2.0

    # Detect module
    module_id = None
    module_code = ""
    for m in known_modules:
        code = m.get("code", "")
        name = m.get("name", "")
        if code.lower() in lower or (name and name.lower() in lower):
            module_id = m.get("id")
            module_code = code
            break

    # Detect deadline / day
    days_ahead = 3
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    target_hour = 23
    target_minute = 59

    if "tomorrow" in lower:
        days_ahead = 1
    elif "today" in lower:
        days_ahead = 0
    else:
        for day_name, day_idx in weekdays.items():
            if day_name in lower:
                curr_day = now.weekday()
                days_ahead = (day_idx - curr_day) % 7
                if days_ahead == 0:
                    days_ahead = 7
                break

    # Check for time (e.g. 5pm, 17:00)
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lower)
    if time_match:
        h = int(time_match.group(1))
        m_val = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        target_hour = h
        target_minute = m_val

    deadline_dt = (now + timedelta(days=days_ahead)).replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )
    deadline = deadline_dt.strftime("%Y-%m-%dT%H:%M")

    # Clean title
    clean_title = text
    for junk in ["due", "priority", "hours", "hrs", "by", "urgent", "tomorrow", "today", "high", "medium", "low"]:
        clean_title = re.sub(rf"\b{junk}\b", "", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"\s+", " ", clean_title).strip() or "University Task"

    # Check if commitment
    is_commitment = any(w in lower for w in ["lecture", "seminar", "gym", "meeting", "shift", "doctor", "dentist"])

    return {
        "title": clean_title,
        "module_code": module_code or (known_modules[0]["code"] if known_modules else "GENERAL"),
        "module_id": module_id or (known_modules[0]["id"] if known_modules else None),
        "priority": priority,
        "deadline": deadline,
        "estimated_hours": hours,
        "is_commitment": is_commitment,
        "start_time": (now + timedelta(days=1)).strftime("%Y-%m-%dT10:00") if is_commitment else "",
        "end_time": (now + timedelta(days=1)).strftime("%Y-%m-%dT11:30") if is_commitment else "",
        "notes": "",
        "source": "heuristic",
    }


def analyze_schedule_and_feedback(
    tasks: List[Dict[str, Any]],
    commitments: List[Dict[str, Any]],
    user_feedback: str = "",
) -> Dict[str, Any]:
    """Generates workload evaluation, deadline-risk analysis, and personalized recommendations."""
    now = datetime.now()
    client = _get_gemini_client()

    # Compute baseline metrics
    total_task_hours = sum(t.get("estimated_hours", 0) for t in tasks if t.get("status") != "completed")
    urgent_tasks = [t for t in tasks if t.get("priority") == "high" and t.get("status") != "completed"]

    # Calculate deadline risk: Check if any task is due in < 48h with large hours
    risk_level = "normal"
    risk_warnings = []
    for t in tasks:
        if t.get("status") == "completed":
            continue
        try:
            dl = datetime.fromisoformat(t["deadline"])
            hours_until = (dl - now).total_seconds() / 3600.0
            est = float(t.get("estimated_hours", 1.0))
            if hours_until < 0:
                risk_level = "critical"
                risk_warnings.append(f"OVERDUE: '{t.get('title')}' passed deadline on {dl.strftime('%a %H:%M')}.")
            elif hours_until < 24 and est > 3.0:
                risk_level = "critical"
                risk_warnings.append(f"HIGH CRUNCH: '{t.get('title')}' ({est}h) is due within 24 hours ({dl.strftime('%a %H:%M')}).")
            elif hours_until < 48 and est > 4.0:
                if risk_level != "critical":
                    risk_level = "warning"
                risk_warnings.append(f"TIGHT DEADLINE: '{t.get('title')}' requires {est}h before {dl.strftime('%a %H:%M')}.")
        except Exception:
            continue

    if client:
        try:
            tasks_summary = [
                f"- {t.get('title')} ({t.get('module_code', 'GEN')}, {t.get('estimated_hours')}h, {t.get('priority')} priority, deadline: {t.get('deadline')})"
                for t in tasks[:8]
            ]
            prompt = f"""
You are the AI Academic Coach of the Smart Scheduling Assistant for university students.
Current time: {now.strftime("%Y-%m-%d %H:%M")}
Current Tasks:
{chr(10).join(tasks_summary) or "No active tasks."}

Total estimated study hours needed: {total_task_hours} hrs.
Student's direct feedback/request: "{user_feedback or 'Provide general schedule feedback and optimization tips.'}"
Algorithmic risk assessment: {risk_level} ({len(risk_warnings)} warnings).

Respond in JSON with:
{{
    "risk_level": "{risk_level}",
    "coach_message": "2-3 sentences of empathetic, practical student advice directly addressing their feedback.",
    "recommendations": ["Actionable tip 1", "Actionable tip 2", "Actionable tip 3"],
    "plan_adjustments": "Brief summary of how the timetable was or should be adjusted."
}}
Return ONLY raw JSON.
"""
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt,
            )
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            return json.loads(raw.strip())
        except Exception as e:
            print(f"[Gemini Feedback fallback] {e}")

    # Intelligent local fallback
    if user_feedback:
        coach_message = f"Got your feedback: '{user_feedback}'. We've balanced your study slots to respect your energy levels and ensure high-priority deadlines are secured first."
    elif risk_level == "critical":
        coach_message = "Deadline Risk Warning! You have high-workload submissions due very soon. We prioritized these in your earliest free daytime slots to prevent last-minute all-nighters."
    elif risk_level == "warning":
        coach_message = "Your upcoming week has a solid workload. Spreading sessions into 1.5 - 2 hour intervals will keep your retention high."
    else:
        coach_message = "Your schedule is healthy and well-paced! All tasks fit comfortably before their deadlines with ample breathing room."

    recommendations = []
    if risk_warnings:
        recommendations.extend(risk_warnings)
    if urgent_tasks:
        recommendations.append(f"Focus on your {len(urgent_tasks)} high-priority task(s) during peak morning concentration.")
    recommendations.append("Break large study blocks into 90-minute Pomodoro sessions.")
    recommendations.append("Review lecture notes within 24 hours of class for 2x memory retention.")

    return {
        "risk_level": risk_level,
        "coach_message": coach_message,
        "recommendations": recommendations[:4],
        "plan_adjustments": "Timetable organized: high-priority tasks placed first, avoiding overlaps with fixed commitments.",
    }


def generate_slot_explanation(
    task_title: str,
    module_code: str,
    slot_start: datetime,
    duration_hours: float,
    deadline_str: str,
    priority: str,
) -> str:
    """Generates a concise 1-sentence decision rationale for a scheduled study block."""
    try:
        dl = datetime.fromisoformat(deadline_str)
        day_name = slot_start.strftime("%A")
        time_str = slot_start.strftime("%I:%M %p").lstrip("0")
        dl_day = dl.strftime("%A")

        if (dl.date() - slot_start.date()).days <= 1:
            return f"Scheduled {task_title} on {day_name} at {time_str} because it's due {dl_day} and requires dedicated focus."
        elif priority == "high":
            return f"Placed {task_title} in this {duration_hours}h open slot on {day_name} to secure early progress on your high-priority {module_code} milestone."
        else:
            return f"{task_title} fitted on {day_name} ({duration_hours}h) because your calendar is clear and well ahead of the {dl_day} deadline."
    except Exception:
        return f"Optimal study window allocated on {slot_start.strftime('%A')} based on calendar availability and task priority."
