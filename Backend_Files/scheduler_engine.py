from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from Backend_Files.Database_Functions.UserDatabaseFunctions import (
    get_commitments,
    get_modules,
    get_schedule_blocks,
    get_tasks,
    save_schedule_blocks,
)
from Backend_Files.gemini_service import generate_slot_explanation


class SchedulerEngine:
    """Computes free calendar slots, validates constraints, and places study blocks."""

    STUDY_START_HOUR = 8
    STUDY_START_MINUTE = 30
    STUDY_END_HOUR = 21
    STUDY_END_MINUTE = 30
    MIN_SLOT_MINUTES = 30
    MAX_SESSION_HOURS = 2.0

    def __init__(self, days_ahead: int = 7, external_busy_intervals: Optional[List[Dict[str, Any]]] = None):
        self.days_ahead = days_ahead
        self.external_busy_intervals = external_busy_intervals or []
        self.now = datetime.now()

    def run(self) -> Dict[str, Any]:
        modules = {m["id"]: m for m in get_modules()}
        modules_by_code = {m["code"]: m for m in modules.values()}
        tasks = get_tasks(status="pending")
        commitments = get_commitments()
        existing_blocks = get_schedule_blocks()

        # Preserve locked blocks
        locked_blocks = [b for b in existing_blocks if b.get("is_locked")]

        # Determine start of planning horizon (today at study start, or now)
        start_date = self.now.date()
        planning_days = [start_date + timedelta(days=i) for i in range(self.days_ahead)]

        # Collect all busy intervals (commitments + Google Calendar freebusy + locked blocks)
        busy_intervals = self._collect_busy_intervals(commitments, locked_blocks, self.external_busy_intervals)

        # Compute free slots across the planning days
        free_slots = self._compute_free_slots(planning_days, busy_intervals)

        # Sort tasks by urgency & priority
        sorted_tasks = self._prioritize_tasks(tasks)

        # Place tasks into free slots
        scheduled_blocks, deadline_risks, unscheduled = self._place_tasks(
            sorted_tasks, free_slots, modules, locked_blocks
        )

        # Combine locked blocks with newly scheduled blocks
        all_blocks = locked_blocks + scheduled_blocks

        # Save to database
        save_schedule_blocks(all_blocks)

        return {
            "success": True,
            "scheduled_count": len(scheduled_blocks),
            "total_blocks": len(all_blocks),
            "deadline_risks": deadline_risks,
            "unscheduled_tasks": unscheduled,
            "blocks": all_blocks,
        }

    def _collect_busy_intervals(
        self,
        commitments: List[Dict[str, Any]],
        locked_blocks: List[Dict[str, Any]],
        external_busy: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Tuple[datetime, datetime]]:
        busy: List[Tuple[datetime, datetime]] = []

        for c in commitments:
            try:
                st = datetime.fromisoformat(c["start_time"].replace("Z", ""))
                et = datetime.fromisoformat(c["end_time"].replace("Z", ""))
                busy.append((st, et))
            except Exception:
                continue

        for ext in (external_busy or []):
            try:
                st = datetime.fromisoformat(ext["start"].replace("Z", ""))
                et = datetime.fromisoformat(ext["end"].replace("Z", ""))
                busy.append((st, et))
            except Exception:
                continue

        for b in locked_blocks:
            try:
                st = datetime.fromisoformat(b["start_time"].replace("Z", ""))
                et = datetime.fromisoformat(b["end_time"].replace("Z", ""))
                busy.append((st, et))
            except Exception:
                continue

        # Sort and merge overlapping busy intervals
        if not busy:
            return []

        busy.sort(key=lambda x: x[0])
        merged = [busy[0]]
        for curr in busy[1:]:
            prev_start, prev_end = merged[-1]
            if curr[0] <= prev_end:
                merged[-1] = (prev_start, max(prev_end, curr[1]))
            else:
                merged.append(curr)

        return merged

    def _compute_free_slots(
        self, days: List[datetime.date], busy_intervals: List[Tuple[datetime, datetime]]
    ) -> List[Dict[str, datetime]]:
        free_slots: List[Dict[str, datetime]] = []

        for d in days:
            day_start = datetime(d.year, d.month, d.day, self.STUDY_START_HOUR, self.STUDY_START_MINUTE)
            day_end = datetime(d.year, d.month, d.day, self.STUDY_END_HOUR, self.STUDY_END_MINUTE)

            # If today, don't schedule in the past
            if d == self.now.date() and self.now > day_start:
                # Next nearest 15-minute mark
                minutes = (self.now.minute // 15 + 1) * 15
                day_start = self.now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)

            if day_start >= day_end:
                continue

            # Intersect day boundary with busy intervals
            cursor = day_start
            for b_start, b_end in busy_intervals:
                if b_end <= cursor:
                    continue
                if b_start >= day_end:
                    break

                if b_start > cursor:
                    free_dur = (min(b_start, day_end) - cursor).total_seconds() / 60.0
                    if free_dur >= self.MIN_SLOT_MINUTES:
                        free_slots.append({"start": cursor, "end": min(b_start, day_end)})

                cursor = max(cursor, b_end)
                if cursor >= day_end:
                    break

            if cursor < day_end:
                free_dur = (day_end - cursor).total_seconds() / 60.0
                if free_dur >= self.MIN_SLOT_MINUTES:
                    free_slots.append({"start": cursor, "end": day_end})

        return free_slots

    def _prioritize_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        priority_weights = {"high": 1, "medium": 2, "low": 3}

        def sort_key(t):
            p_val = priority_weights.get(t.get("priority", "medium"), 2)
            try:
                dl = datetime.fromisoformat(t["deadline"])
            except Exception:
                dl = datetime.max
            return (dl, p_val)

        return sorted(tasks, key=sort_key)

    def _place_tasks(
        self,
        tasks: List[Dict[str, Any]],
        free_slots: List[Dict[str, datetime]],
        modules: Dict[int, Dict[str, Any]],
        locked_blocks: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
        scheduled: List[Dict[str, Any]] = []
        deadline_risks: List[str] = []
        unscheduled: List[Dict[str, Any]] = []

        # Available time per task tracking
        for task in tasks:
            total_needed = float(task.get("estimated_hours", 2.0))
            hours_left = total_needed
            try:
                deadline = datetime.fromisoformat(task["deadline"])
            except Exception:
                deadline = self.now + timedelta(days=7)

            mod_id = task.get("module_id")
            module = modules.get(mod_id, {})
            module_code = module.get("code") or task.get("module_code") or "GEN"
            color = module.get("color") or task.get("module_color") or "#6366f1"

            while hours_left > 0.01:
                chunk_duration = min(hours_left, self.MAX_SESSION_HOURS)
                chunk_minutes = chunk_duration * 60.0

                placed = False
                for i, slot in enumerate(free_slots):
                    slot_start = slot["start"]
                    slot_end = slot["end"]

                    # Check if slot is before deadline
                    if slot_start >= deadline:
                        continue

                    slot_capacity_min = (slot_end - slot_start).total_seconds() / 60.0
                    if slot_capacity_min < self.MIN_SLOT_MINUTES:
                        continue

                    # How much of chunk can fit
                    usable_min = min(chunk_minutes, slot_capacity_min)
                    # Don't exceed deadline
                    if slot_start + timedelta(minutes=usable_min) > deadline:
                        usable_min = (deadline - slot_start).total_seconds() / 60.0
                        if usable_min < self.MIN_SLOT_MINUTES:
                            continue

                    block_start = slot_start
                    block_end = block_start + timedelta(minutes=usable_min)
                    actual_hours = round(usable_min / 60.0, 2)

                    # Generate Gemini transparent explanation
                    reason = generate_slot_explanation(
                        task_title=task["title"],
                        module_code=module_code,
                        slot_start=block_start,
                        duration_hours=actual_hours,
                        deadline_str=task["deadline"],
                        priority=task.get("priority", "medium"),
                    )

                    scheduled.append({
                        "task_id": task["id"],
                        "title": f"Study: {task['title']}",
                        "module_code": module_code,
                        "color": color,
                        "start_time": block_start.strftime("%Y-%m-%dT%H:%M:%S"),
                        "end_time": block_end.strftime("%Y-%m-%dT%H:%M:%S"),
                        "reason": reason,
                        "is_locked": 0,
                    })

                    hours_left -= actual_hours
                    placed = True

                    # Update or shrink current slot
                    if block_end >= slot_end:
                        free_slots.pop(i)
                    else:
                        slot["start"] = block_end

                    break

                if not placed:
                    # Could not place remaining time before deadline
                    deadline_risks.append(
                        f"CRITICAL RISK: '{task['title']}' has {round(hours_left, 1)}h unscheduled before deadline ({deadline.strftime('%a %d %b %H:%M')})!"
                    )
                    unscheduled.append({
                        "task_id": task["id"],
                        "title": task["title"],
                        "missing_hours": round(hours_left, 1),
                        "deadline": task["deadline"],
                    })
                    break

        return scheduled, deadline_risks, unscheduled


def run_scheduler(days_ahead: int = 7, external_busy_intervals: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    engine = SchedulerEngine(days_ahead=days_ahead, external_busy_intervals=external_busy_intervals)
    return engine.run()
