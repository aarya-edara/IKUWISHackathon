import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_DIR = Path(__file__).resolve().parent.parent / "Data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_SQLITE_PATH = DB_DIR / "scheduler.db"


class BaseDatabaseAdapter(ABC):
    """Abstract Database Adapter to allow switching between SQLite and TigerData/Cloud DB."""

    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def get_modules(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def add_module(self, code: str, name: str, color: str = "#3b82f6", weekly_target_hours: float = 4.0) -> int:
        pass

    @abstractmethod
    def delete_module(self, module_id: int) -> bool:
        pass

    @abstractmethod
    def get_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def add_task(
        self,
        title: str,
        module_id: Optional[int],
        priority: str,
        deadline: str,
        estimated_hours: float,
        notes: str = "",
    ) -> int:
        pass

    @abstractmethod
    def update_task(self, task_id: int, **fields) -> bool:
        pass

    @abstractmethod
    def delete_task(self, task_id: int) -> bool:
        pass

    @abstractmethod
    def get_commitments(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def add_commitment(self, title: str, start_time: str, end_time: str, recurrence: str = "none") -> int:
        pass

    @abstractmethod
    def delete_commitment(self, commitment_id: int) -> bool:
        pass

    @abstractmethod
    def save_schedule_blocks(self, blocks: List[Dict[str, Any]]) -> None:
        pass

    @abstractmethod
    def get_schedule_blocks(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def clear_unlocked_blocks(self) -> None:
        pass

    @abstractmethod
    def save_recommendation(self, user_feedback: str, ai_advice: str, risk_level: str = "normal") -> int:
        pass

    @abstractmethod
    def get_latest_recommendation(self) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def save_google_token(self, token_json: str, email: str = "") -> None:
        pass

    @abstractmethod
    def get_google_token(self) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete_google_token(self) -> bool:
        pass

    @abstractmethod
    def update_block_google_event_id(self, block_id: int, google_event_id: str) -> bool:
        pass


class SQLiteDatabaseAdapter(BaseDatabaseAdapter):
    """SQLite implementation for rapid local development and testing."""

    def __init__(self, db_path: Path = DEFAULT_SQLITE_PATH):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Modules table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS modules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    color TEXT NOT NULL DEFAULT '#3b82f6',
                    weekly_target_hours REAL NOT NULL DEFAULT 4.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Tasks table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    module_id INTEGER,
                    priority TEXT NOT NULL CHECK(priority IN ('low', 'medium', 'high')),
                    deadline TEXT NOT NULL,
                    estimated_hours REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'scheduled', 'completed')),
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE SET NULL
                )
                """
            )

            # Commitments table (Fixed classes, shifts, meetings)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS commitments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    recurrence TEXT DEFAULT 'none',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Schedule Blocks table (Generated study slots with AI rationale)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    title TEXT NOT NULL,
                    module_code TEXT DEFAULT '',
                    color TEXT NOT NULL DEFAULT '#6366f1',
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    is_locked INTEGER NOT NULL DEFAULT 0,
                    google_event_id TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
                """
            )

            # Auto-migrate schedule_blocks if google_event_id column is missing
            try:
                cursor.execute("ALTER TABLE schedule_blocks ADD COLUMN google_event_id TEXT DEFAULT NULL")
            except sqlite3.OperationalError:
                pass

            # Google OAuth Tokens table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS google_tokens (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    token_json TEXT NOT NULL,
                    email TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # AI Recommendations & Feedback table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_feedback TEXT DEFAULT '',
                    ai_advice TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'normal',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Seed default modules if empty
            cursor.execute("SELECT COUNT(*) FROM modules")
            if cursor.fetchone()[0] == 0:
                default_modules = [
                    ("CS101", "Introduction to Computer Systems", "#3b82f6", 5.0),
                    ("MATH201", "Linear Algebra & Calculus", "#10b981", 4.0),
                    ("AI305", "Machine Learning & Reasoning", "#8b5cf6", 6.0),
                    ("ENG105", "Academic Writing & Research", "#f59e0b", 3.0),
                ]
                cursor.executemany(
                    "INSERT INTO modules (code, name, color, weekly_target_hours) VALUES (?, ?, ?, ?)",
                    default_modules,
                )

            # Seed sample commitments if empty
            cursor.execute("SELECT COUNT(*) FROM commitments")
            if cursor.fetchone()[0] == 0:
                now = datetime.now()
                # Find current week Monday
                monday = (now - timedelta(days=now.weekday())).replace(hour=10, minute=0, second=0, microsecond=0)
                tuesday = monday + timedelta(days=1)
                wednesday = monday + timedelta(days=2)
                thursday = monday + timedelta(days=3)

                sample_commitments = [
                    ("CS101 Lecture", (monday).strftime("%Y-%m-%dT10:00:00"), (monday).strftime("%Y-%m-%dT12:00:00")),
                    ("MATH201 Seminar", (tuesday.replace(hour=14)).strftime("%Y-%m-%dT14:00:00"), (tuesday.replace(hour=16)).strftime("%Y-%m-%dT16:00:00")),
                    ("AI305 Lab", (wednesday.replace(hour=11)).strftime("%Y-%m-%dT11:00:00"), (wednesday.replace(hour=13)).strftime("%Y-%m-%dT13:00:00")),
                    ("Gym Session", (thursday.replace(hour=17)).strftime("%Y-%m-%dT17:00:00"), (thursday.replace(hour=18, minute=30)).strftime("%Y-%m-%dT18:30:00")),
                ]
                cursor.executemany(
                    "INSERT INTO commitments (title, start_time, end_time) VALUES (?, ?, ?)",
                    sample_commitments,
                )

            conn.commit()

    def get_modules(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM modules ORDER BY code ASC")
            return [dict(row) for row in cursor.fetchall()]

    def add_module(self, code: str, name: str, color: str = "#3b82f6", weekly_target_hours: float = 4.0) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO modules (code, name, color, weekly_target_hours)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET name=excluded.name, color=excluded.color, weekly_target_hours=excluded.weekly_target_hours
                """,
                (code.strip().upper(), name.strip(), color, float(weekly_target_hours)),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def delete_module(self, module_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM modules WHERE id = ?", (module_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT t.*, m.code AS module_code, m.name AS module_name, m.color AS module_color
                FROM tasks t
                LEFT JOIN modules m ON t.module_id = m.id
            """
            params: List[Any] = []
            if status:
                query += " WHERE t.status = ?"
                params.append(status)
            query += " ORDER BY t.deadline ASC, CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def add_task(
        self,
        title: str,
        module_id: Optional[int],
        priority: str,
        deadline: str,
        estimated_hours: float,
        notes: str = "",
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (title, module_id, priority, deadline, estimated_hours, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title.strip(), module_id, priority.lower(), deadline, float(estimated_hours), notes.strip()),
            )
            conn.commit()
            return cursor.lastrowid

    def update_task(self, task_id: int, **fields) -> bool:
        if not fields:
            return False
        allowed = {"title", "module_id", "priority", "deadline", "estimated_hours", "status", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        params = list(updates.values()) + [task_id]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_commitments(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM commitments ORDER BY start_time ASC")
            return [dict(row) for row in cursor.fetchall()]

    def add_commitment(self, title: str, start_time: str, end_time: str, recurrence: str = "none") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO commitments (title, start_time, end_time, recurrence)
                VALUES (?, ?, ?, ?)
                """,
                (title.strip(), start_time, end_time, recurrence),
            )
            conn.commit()
            return cursor.lastrowid

    def delete_commitment(self, commitment_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM commitments WHERE id = ?", (commitment_id,))
            conn.commit()
            return cursor.rowcount > 0

    def save_schedule_blocks(self, blocks: List[Dict[str, Any]]) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Retain locked blocks, delete unlocked
            cursor.execute("DELETE FROM schedule_blocks WHERE is_locked = 0")
            for b in blocks:
                cursor.execute(
                    """
                    INSERT INTO schedule_blocks (task_id, title, module_code, color, start_time, end_time, reason, is_locked, google_event_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        b.get("task_id"),
                        b.get("title", "Study Session"),
                        b.get("module_code", ""),
                        b.get("color", "#6366f1"),
                        b.get("start_time"),
                        b.get("end_time"),
                        b.get("reason", "Allocated optimal study slot"),
                        b.get("is_locked", 0),
                        b.get("google_event_id"),
                    ),
                )
            conn.commit()

    def get_schedule_blocks(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedule_blocks ORDER BY start_time ASC")
            return [dict(row) for row in cursor.fetchall()]

    def clear_unlocked_blocks(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM schedule_blocks WHERE is_locked = 0")
            conn.commit()

    def save_recommendation(self, user_feedback: str, ai_advice: str, risk_level: str = "normal") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO recommendations (user_feedback, ai_advice, risk_level)
                VALUES (?, ?, ?)
                """,
                (user_feedback.strip(), ai_advice.strip(), risk_level),
            )
            conn.commit()
            return cursor.lastrowid

    def get_latest_recommendation(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recommendations ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_google_token(self, token_json: str, email: str = "") -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO google_tokens (id, token_json, email, updated_at)
                VALUES (1, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET token_json=excluded.token_json, email=excluded.email, updated_at=CURRENT_TIMESTAMP
                """,
                (token_json, email),
            )
            conn.commit()

    def get_google_token(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM google_tokens WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_google_token(self) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM google_tokens WHERE id = 1")
            conn.commit()
            return cursor.rowcount > 0

    def update_block_google_event_id(self, block_id: int, google_event_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE schedule_blocks SET google_event_id = ? WHERE id = ?", (google_event_id, block_id))
            conn.commit()
            return cursor.rowcount > 0


class TigerDatabaseAdapter(BaseDatabaseAdapter):
    """Placeholder adapter for TigerData / cloud-hosted SQL databases.

    When deploying to production with TigerData, configure TIGERDATA_DATABASE_URL
    or host/credentials in your environment to seamlessly redirect queries.
    """

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.getenv("TIGERDATA_DATABASE_URL")
        # In future deployment, connect using pg8000/psycopg2/mysql-connector or TigerData REST client
        # Fall back to SQLite adapter for local execution if URL not set
        self._fallback = SQLiteDatabaseAdapter()

    def initialize(self) -> None:
        self._fallback.initialize()

    def get_modules(self) -> List[Dict[str, Any]]:
        return self._fallback.get_modules()

    def add_module(self, code: str, name: str, color: str = "#3b82f6", weekly_target_hours: float = 4.0) -> int:
        return self._fallback.add_module(code, name, color, weekly_target_hours)

    def delete_module(self, module_id: int) -> bool:
        return self._fallback.delete_module(module_id)

    def get_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._fallback.get_tasks(status)

    def add_task(self, title: str, module_id: Optional[int], priority: str, deadline: str, estimated_hours: float, notes: str = "") -> int:
        return self._fallback.add_task(title, module_id, priority, deadline, estimated_hours, notes)

    def update_task(self, task_id: int, **fields) -> bool:
        return self._fallback.update_task(task_id, **fields)

    def delete_task(self, task_id: int) -> bool:
        return self._fallback.delete_task(task_id)

    def get_commitments(self) -> List[Dict[str, Any]]:
        return self._fallback.get_commitments()

    def add_commitment(self, title: str, start_time: str, end_time: str, recurrence: str = "none") -> int:
        return self._fallback.add_commitment(title, start_time, end_time, recurrence)

    def delete_commitment(self, commitment_id: int) -> bool:
        return self._fallback.delete_commitment(commitment_id)

    def save_schedule_blocks(self, blocks: List[Dict[str, Any]]) -> None:
        return self._fallback.save_schedule_blocks(blocks)

    def get_schedule_blocks(self) -> List[Dict[str, Any]]:
        return self._fallback.get_schedule_blocks()

    def clear_unlocked_blocks(self) -> None:
        return self._fallback.clear_unlocked_blocks()

    def save_recommendation(self, user_feedback: str, ai_advice: str, risk_level: str = "normal") -> int:
        return self._fallback.save_recommendation(user_feedback, ai_advice, risk_level)

    def get_latest_recommendation(self) -> Optional[Dict[str, Any]]:
        return self._fallback.get_latest_recommendation()

    def save_google_token(self, token_json: str, email: str = "") -> None:
        return self._fallback.save_google_token(token_json, email)

    def get_google_token(self) -> Optional[Dict[str, Any]]:
        return self._fallback.get_google_token()

    def delete_google_token(self) -> bool:
        return self._fallback.delete_google_token()

    def update_block_google_event_id(self, block_id: int, google_event_id: str) -> bool:
        return self._fallback.update_block_google_event_id(block_id, google_event_id)


# Factory function to get active adapter
_db_instance: Optional[BaseDatabaseAdapter] = None


def get_db() -> BaseDatabaseAdapter:
    global _db_instance
    if _db_instance is None:
        if os.getenv("USE_TIGERDATA", "false").lower() in ("true", "1") or os.getenv("TIGERDATA_DATABASE_URL"):
            _db_instance = TigerDatabaseAdapter()
        else:
            _db_instance = SQLiteDatabaseAdapter()
        _db_instance.initialize()
    return _db_instance


def init_db() -> None:
    get_db().initialize()


# Export helper functions for direct use across modules
def get_modules() -> List[Dict[str, Any]]:
    return get_db().get_modules()


def add_module(code: str, name: str, color: str = "#3b82f6", weekly_target_hours: float = 4.0) -> int:
    return get_db().add_module(code, name, color, weekly_target_hours)


def delete_module(module_id: int) -> bool:
    return get_db().delete_module(module_id)


def get_tasks(status: Optional[str] = None) -> List[Dict[str, Any]]:
    return get_db().get_tasks(status)


def add_task(title: str, module_id: Optional[int], priority: str, deadline: str, estimated_hours: float, notes: str = "") -> int:
    return get_db().add_task(title, module_id, priority, deadline, estimated_hours, notes)


def update_task(task_id: int, **fields) -> bool:
    return get_db().update_task(task_id, **fields)


def delete_task(task_id: int) -> bool:
    return get_db().delete_task(task_id)


def get_commitments() -> List[Dict[str, Any]]:
    return get_db().get_commitments()


def add_commitment(title: str, start_time: str, end_time: str, recurrence: str = "none") -> int:
    return get_db().add_commitment(title, start_time, end_time, recurrence)


def delete_commitment(commitment_id: int) -> bool:
    return get_db().delete_commitment(commitment_id)


def save_schedule_blocks(blocks: List[Dict[str, Any]]) -> None:
    get_db().save_schedule_blocks(blocks)


def get_schedule_blocks() -> List[Dict[str, Any]]:
    return get_db().get_schedule_blocks()


def clear_unlocked_blocks() -> None:
    get_db().clear_unlocked_blocks()


def save_recommendation(user_feedback: str, ai_advice: str, risk_level: str = "normal") -> int:
    return get_db().save_recommendation(user_feedback, ai_advice, risk_level)


def get_latest_recommendation() -> Optional[Dict[str, Any]]:
    return get_db().get_latest_recommendation()


def save_google_token(token_json: str, email: str = "") -> None:
    get_db().save_google_token(token_json, email)


def get_google_token() -> Optional[Dict[str, Any]]:
    return get_db().get_google_token()


def delete_google_token() -> bool:
    return get_db().delete_google_token()


def update_block_google_event_id(block_id: int, google_event_id: str) -> bool:
    return get_db().update_block_google_event_id(block_id, google_event_id)
