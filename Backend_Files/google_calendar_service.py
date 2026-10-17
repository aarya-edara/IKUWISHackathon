import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from Backend_Files.Database_Functions.UserDatabaseFunctions import (
    delete_google_token,
    get_commitments,
    get_google_token,
    get_schedule_blocks,
    save_google_token,
    save_schedule_blocks,
    update_block_google_event_id,
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"

# In-memory undo snapshot store for displaced blocks
_last_displacement_undo: Optional[Dict[str, Any]] = None


def get_oauth_config() -> Optional[Dict[str, Any]]:
    """Checks for credentials.json or environment variables for Google OAuth."""
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Google OAuth] Error reading credentials.json: {e}")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    return None


def get_authorization_url(redirect_uri: str) -> Tuple[Optional[str], Optional[str]]:
    """Generates Google OAuth authorization URL."""
    config = get_oauth_config()
    if not config:
        return None, "Google Cloud OAuth credentials not configured. Place credentials.json in project root or set GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET in .env."

    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url, None
    except Exception as e:
        return None, str(e)


def handle_oauth_callback(code: str, redirect_uri: str) -> Tuple[bool, str]:
    """Exchanges authorization code for credentials and saves to database."""
    config = get_oauth_config()
    if not config:
        return False, "Google Cloud OAuth configuration missing."

    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials

        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        }

        # Retrieve user email
        email = "student@gmail.com"
        try:
            from googleapiclient.discovery import build
            oauth2 = build("oauth2", "v2", credentials=creds)
            user_info = oauth2.userinfo().get().execute()
            email = user_info.get("email", email)
        except Exception:
            pass

        save_google_token(json.dumps(token_data), email=email)
        return True, email
    except Exception as e:
        return False, str(e)


def get_calendar_client():
    """Returns an authorized Google Calendar API service instance or None."""
    token_row = get_google_token()
    if not token_row:
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_info = json.loads(token_row["token_json"])
        creds = Credentials(
            token=token_info.get("token"),
            refresh_token=token_info.get("refresh_token"),
            token_uri=token_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_info.get("client_id"),
            client_secret=token_info.get("client_secret"),
            scopes=token_info.get("scopes", SCOPES),
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update token in DB
            token_info["token"] = creds.token
            save_google_token(json.dumps(token_info), email=token_row.get("email", ""))

        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"[Google Calendar Service] Auth error: {e}")
        return None


def get_connection_status() -> Dict[str, Any]:
    """Returns current Google Calendar connection status."""
    token_row = get_google_token()
    config_available = get_oauth_config() is not None

    if token_row:
        return {
            "connected": True,
            "mode": "live",
            "email": token_row.get("email", "student@uni.edu"),
            "config_available": config_available,
        }
    return {
        "connected": False,
        "mode": "simulated",
        "email": None,
        "config_available": config_available,
    }


def disconnect_google_calendar() -> bool:
    """Disconnects Google account by removing stored tokens."""
    return delete_google_token()


def fetch_google_freebusy(time_min: datetime, time_max: datetime) -> List[Dict[str, str]]:
    """Fetches busy intervals using Google Calendar's privacy-preserving freebusy endpoint.

    Returns a list of dicts: [{'start': '2026-10-18T10:00:00Z', 'end': '...'}]
    Falls back to local commitments if Google account is not connected.
    """
    client = get_calendar_client()
    if client:
        try:
            body = {
                "timeMin": time_min.isoformat() + "Z",
                "timeMax": time_max.isoformat() + "Z",
                "items": [{"id": "primary"}],
            }
            res = client.freebusy().query(body=body).execute()
            busy = res.get("calendars", {}).get("primary", {}).get("busy", [])
            return busy
        except Exception as e:
            print(f"[Google Freebusy Error] {e}")

    # Fallback to local commitments
    commitments = get_commitments()
    busy_list = []
    for c in commitments:
        busy_list.append({"start": c["start_time"], "end": c["end_time"]})
    return busy_list


def write_blocks_to_google_calendar() -> Dict[str, Any]:
    """Writes confirmed AI study blocks to the user's primary Google Calendar."""
    client = get_calendar_client()
    blocks = get_schedule_blocks()

    if not client:
        # Simulated push if not connected
        return {
            "success": True,
            "mode": "simulated",
            "written_count": len(blocks),
            "message": f"Successfully synced {len(blocks)} study blocks to your calendar (Simulated Google Sync). To push to a live Google account, connect in settings.",
        }

    written = 0
    errors = 0

    for b in blocks:
        try:
            mod = b.get("module_code", "GEN")
            event_body = {
                "summary": f"[{mod}] {b['title']}",
                "description": (
                    f"Module: {mod}\n"
                    f"AI Decision Rationale: {b.get('reason', 'Optimal study slot allocated by AI Scheduler')}\n"
                    f"Status: {'Locked by Student' if b.get('is_locked') else 'AI Scheduled'}\n\n"
                    "Smart Student Scheduler: Code does the maths, AI does the judgment."
                ),
                "start": {
                    "dateTime": b["start_time"] if "T" in b["start_time"] else b["start_time"] + "T00:00:00",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": b["end_time"] if "T" in b["end_time"] else b["end_time"] + "T00:00:00",
                    "timeZone": "UTC",
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 15}],
                },
                "extendedProperties": {
                    "private": {
                        "ai_scheduler": "true",
                        "block_id": str(b["id"]),
                    }
                },
            }

            created_event = client.events().insert(calendarId="primary", body=event_body).execute()
            if created_event.get("id"):
                update_block_google_event_id(b["id"], created_event["id"])
                written += 1
        except Exception as e:
            print(f"[Write Block Error] {e}")
            errors += 1

    return {
        "success": True,
        "mode": "live",
        "written_count": written,
        "errors": errors,
        "message": f"Successfully created {written} study events directly on your Google Calendar!",
    }


def sync_and_detect_conflicts(simulated_clash_event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Incremental sync: Compares current study blocks against Google Calendar busy intervals.

    If a clash occurs, re-places ONLY the displaced block and leaves the rest of the plan stable.
    """
    global _last_displacement_undo
    now = datetime.now()
    week_end = now + timedelta(days=7)

    # 1. Fetch busy intervals (real Google Calendar or local)
    busy_times = fetch_google_freebusy(now, week_end)

    # If simulation requested, inject a clash event
    if simulated_clash_event:
        busy_times.append({
            "start": simulated_clash_event["start_time"],
            "end": simulated_clash_event["end_time"],
            "title": simulated_clash_event.get("title", "New Google Calendar Event"),
        })

    blocks = get_schedule_blocks()
    if not blocks:
        return {"has_conflicts": False, "displaced_tasks": [], "message": "No scheduled study blocks to check."}

    # 2. Check for overlaps between non-locked study blocks and busy intervals
    displaced_info: List[Dict[str, Any]] = []
    updated_blocks = [dict(b) for b in blocks]

    for b_idx, b in enumerate(updated_blocks):
        if b.get("is_locked"):
            continue  # Locked blocks are never overridden by AI

        try:
            b_start = datetime.fromisoformat(b["start_time"].replace("Z", ""))
            b_end = datetime.fromisoformat(b["end_time"].replace("Z", ""))
        except Exception:
            continue

        for busy in busy_times:
            try:
                busy_start = datetime.fromisoformat(busy["start"].replace("Z", ""))
                busy_end = datetime.fromisoformat(busy["end"].replace("Z", ""))
            except Exception:
                continue

            # Overlap condition: max(start1, start2) < min(end1, end2)
            if max(b_start, busy_start) < min(b_end, busy_end):
                # Save snapshot for undo
                _last_displacement_undo = {
                    "blocks_snapshot": [dict(x) for x in blocks],
                    "timestamp": datetime.now().isoformat(),
                }

                # Found clash! Calculate new slot for ONLY this task
                duration_hours = (b_end - b_start).total_seconds() / 3600.0
                new_start, new_end = _find_next_stable_free_slot(
                    b_start, duration_hours, busy_times, [x for i, x in enumerate(updated_blocks) if i != b_idx]
                )

                old_slot_str = f"{b_start.strftime('%a %H:%M')} - {b_end.strftime('%H:%M')}"
                new_slot_str = f"{new_start.strftime('%a %H:%M')} - {new_end.strftime('%H:%M')}"

                new_reason = (
                    f"Moved {b['title']} to {new_start.strftime('%A')} ({new_start.strftime('%I:%M %p')}) "
                    f"due to a conflict with a new event on your Google Calendar. Other plan blocks preserved."
                )

                # Update the displaced block
                b["start_time"] = new_start.strftime("%Y-%m-%dT%H:%M:%S")
                b["end_time"] = new_end.strftime("%Y-%m-%dT%H:%M:%S")
                b["reason"] = new_reason

                displaced_info.append({
                    "task_id": b.get("task_id"),
                    "title": b["title"],
                    "old_slot": old_slot_str,
                    "new_slot": new_slot_str,
                    "reason": new_reason,
                })
                break

    if displaced_info:
        # Save updated blocks back to DB
        save_schedule_blocks(updated_blocks)
        return {
            "has_conflicts": True,
            "displaced_count": len(displaced_info),
            "displaced_tasks": displaced_info,
            "message": f"Conflict detected! Re-scheduled {len(displaced_info)} task(s) while keeping the rest of your week stable.",
        }

    return {
        "has_conflicts": False,
        "displaced_tasks": [],
        "message": "All study blocks are conflict-free with your Google Calendar.",
    }


def undo_last_displacement() -> bool:
    """Restores the timetable state before the last conflict re-planning."""
    global _last_displacement_undo
    if not _last_displacement_undo or not _last_displacement_undo.get("blocks_snapshot"):
        return False

    save_schedule_blocks(_last_displacement_undo["blocks_snapshot"])
    _last_displacement_undo = None
    return True


def _find_next_stable_free_slot(
    earliest_time: datetime,
    duration_hours: float,
    busy_intervals: List[Dict[str, Any]],
    other_blocks: List[Dict[str, Any]],
) -> Tuple[datetime, datetime]:
    """Finds the next free daytime slot for a single displaced task without moving other blocks."""
    slot_minutes = duration_hours * 60.0
    cursor = earliest_time + timedelta(hours=1)

    # Collect all other busy periods
    all_busy: List[Tuple[datetime, datetime]] = []
    for b in busy_intervals:
        try:
            st = datetime.fromisoformat(b["start"].replace("Z", ""))
            et = datetime.fromisoformat(b["end"].replace("Z", ""))
            all_busy.append((st, et))
        except Exception:
            continue

    for ob in other_blocks:
        try:
            st = datetime.fromisoformat(ob["start_time"].replace("Z", ""))
            et = datetime.fromisoformat(ob["end_time"].replace("Z", ""))
            all_busy.append((st, et))
        except Exception:
            continue

    all_busy.sort(key=lambda x: x[0])

    # Scan 5 days ahead
    for day_offset in range(6):
        target_day = cursor.date() + timedelta(days=day_offset)
        day_start = datetime(target_day.year, target_day.month, target_day.day, 9, 0)
        day_end = datetime(target_day.year, target_day.month, target_day.day, 21, 0)

        check_time = max(cursor if day_offset == 0 else day_start, day_start)
        while check_time + timedelta(minutes=slot_minutes) <= day_end:
            candidate_end = check_time + timedelta(minutes=slot_minutes)
            clash = False
            for b_st, b_et in all_busy:
                if max(check_time, b_st) < min(candidate_end, b_et):
                    clash = True
                    check_time = b_et  # Jump past the clash
                    break
            if not clash:
                return check_time, candidate_end
            check_time += timedelta(minutes=15)

    # Fallback to tomorrow 10am
    fb_start = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0)
    return fb_start, fb_start + timedelta(hours=duration_hours)
