"""SQLite-backed demo data store.

The demo store keeps mutable showcase data out of the hard-coded mock module
while preserving the same customer-centric shape expected by existing tools.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fin_copilot.config import get_settings


class DemoStoreError(RuntimeError):
    """Raised when the demo store cannot serve a requested operation."""


@dataclass(frozen=True)
class ResourceMeta:
    label: str
    source_name: str
    kind: str
    id_field: str
    prefix: str


RESOURCE_META: dict[str, ResourceMeta] = {
    "customers": ResourceMeta("客户人设", "CUSTOMERS", "single", "customer_id", "C"),
    "bills": ResourceMeta("账单还款", "BILLS", "single", "customer_id", "BILL"),
    "loans": ResourceMeta("贷款服务", "LOANS", "single", "customer_id", "LOAN"),
    "memberships": ResourceMeta("会员/优享卡", "MEMBERSHIPS", "single", "customer_id", "MEM"),
    "quotas": ResourceMeta("额度", "QUOTAS", "single", "customer_id", "QUOTA"),
    "tickets": ResourceMeta("工单", "TICKETS", "list", "ticket_id", "TK"),
    "call_history": ResourceMeta("通话记录", "CALL_HISTORY", "list", "call_id", "CALL"),
    "sms_history": ResourceMeta("短信记录", "SMS_HISTORY", "list", "sms_id", "SMS"),
    "stop_collection_history": ResourceMeta("停催记录", "STOP_COLLECTION_HISTORY", "list", "request_id", "STOP"),
    "refund_history": ResourceMeta("退款记录", "REFUND_HISTORY", "list", "refund_id", "RF"),
}

LIST_RESOURCES = frozenset(
    name for name, meta in RESOURCE_META.items() if meta.kind == "list"
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DemoStore:
    """Small SQLite repository for demo records and chat sessions."""

    def __init__(self, db_path: str | Path | None = None, project_root: str | Path | None = None) -> None:
        settings = get_settings()
        self.project_root = Path(project_root or settings.PROJECT_ROOT)
        configured_path = Path(db_path or settings.DEMO_DB_PATH)
        self.db_path = (
            configured_path
            if configured_path.is_absolute()
            else self.project_root / configured_path
        )
        self._lock = threading.RLock()
        self.initialize()

    def initialize(self) -> None:
        with self._lock:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                self._create_schema(conn)
                record_count = conn.execute("SELECT COUNT(*) FROM demo_records").fetchone()[0]
                if record_count == 0:
                    self._seed_records(conn)
                else:
                    self._apply_seed_protection(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS demo_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS demo_records (
                resource TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                record_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                immutable INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (resource, record_id)
            );

            CREATE INDEX IF NOT EXISTS idx_demo_records_resource_owner
                ON demo_records(resource, owner_id);

            CREATE TABLE IF NOT EXISTS demo_sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                customer_id TEXT NOT NULL DEFAULT '',
                llm_profile_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS demo_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                response_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES demo_sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS eval_txt_files (
                txt_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                messages_json TEXT NOT NULL,
                dropped_lines_json TEXT NOT NULL DEFAULT '[]',
                parse_summary_json TEXT NOT NULL DEFAULT '{}',
                badcase INTEGER NOT NULL DEFAULT 0,
                badcase_note TEXT NOT NULL DEFAULT '',
                imported_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS eval_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                llm_profile_id TEXT NOT NULL,
                total_turns INTEGER NOT NULL DEFAULT 0,
                completed_turns INTEGER NOT NULL DEFAULT 0,
                success_turns INTEGER NOT NULL DEFAULT 0,
                failed_turns INTEGER NOT NULL DEFAULT 0,
                cancelled INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS eval_runs (
                run_id TEXT PRIMARY KEY,
                txt_id TEXT NOT NULL,
                llm_profile_id TEXT NOT NULL,
                status TEXT NOT NULL,
                main_skill_id TEXT NOT NULL DEFAULT '',
                main_intent_l1 TEXT NOT NULL DEFAULT '',
                main_intent_l2 TEXT NOT NULL DEFAULT '',
                main_intent_label TEXT NOT NULL DEFAULT '',
                intent_error INTEGER NOT NULL DEFAULT 0,
                corrected_intent_l1 TEXT NOT NULL DEFAULT '',
                corrected_intent_l2 TEXT NOT NULL DEFAULT '',
                corrected_intent_label TEXT NOT NULL DEFAULT '',
                intent_error_note TEXT NOT NULL DEFAULT '',
                total_turns INTEGER NOT NULL DEFAULT 0,
                generated_turns INTEGER NOT NULL DEFAULT 0,
                failed_turns INTEGER NOT NULL DEFAULT 0,
                accepted_turns INTEGER NOT NULL DEFAULT 0,
                rejected_turns INTEGER NOT NULL DEFAULT 0,
                badcase_count INTEGER NOT NULL DEFAULT 0,
                avg_latency_ms REAL NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                job_id TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(txt_id, llm_profile_id),
                FOREIGN KEY (txt_id) REFERENCES eval_txt_files(txt_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS eval_turn_results (
                turn_result_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                txt_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                user_query TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '[]',
                model_answer TEXT NOT NULL DEFAULT '',
                route TEXT NOT NULL DEFAULT '',
                matched_skill_id TEXT NOT NULL DEFAULT '',
                matched_skill_name TEXT NOT NULL DEFAULT '',
                mapped_intent_json TEXT NOT NULL DEFAULT '{}',
                tools_called_json TEXT NOT NULL DEFAULT '[]',
                trace_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                latency_ms REAL NOT NULL DEFAULT 0,
                response_json TEXT NOT NULL DEFAULT '{}',
                annotation_json TEXT NOT NULL DEFAULT '{}',
                badcase INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES eval_runs(run_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (txt_id) REFERENCES eval_txt_files(txt_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_eval_runs_txt_profile
                ON eval_runs(txt_id, llm_profile_id);
            CREATE INDEX IF NOT EXISTS idx_eval_turn_results_run
                ON eval_turn_results(run_id, message_index);
            """
        )
        try:
            conn.execute("ALTER TABLE demo_records ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise
        try:
            conn.execute("ALTER TABLE demo_sessions ADD COLUMN llm_profile_id TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise
        try:
            conn.execute("ALTER TABLE eval_txt_files ADD COLUMN badcase INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise
        try:
            conn.execute("ALTER TABLE eval_txt_files ADD COLUMN badcase_note TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise
        for ddl in (
            "ALTER TABLE eval_runs ADD COLUMN intent_error INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE eval_runs ADD COLUMN corrected_intent_l1 TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE eval_runs ADD COLUMN corrected_intent_l2 TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE eval_runs ADD COLUMN corrected_intent_label TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE eval_runs ADD COLUMN intent_error_note TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc):
                    raise

    def _seed_records(self, conn: sqlite3.Connection) -> None:
        mock_data = self._load_mock_data_module()
        now = utc_now()
        for resource, meta in RESOURCE_META.items():
            source = copy.deepcopy(getattr(mock_data, meta.source_name))
            if meta.kind == "single":
                for customer_id, payload in source.items():
                    payload.setdefault("customer_id", customer_id)
                    payload = self._normalise_payload(resource, payload)
                    self._insert_record(conn, resource, customer_id, customer_id, payload, now, immutable=True)
                continue
            for customer_id, records in source.items():
                for index, payload in enumerate(records, start=1):
                    record_id = str(payload.get(meta.id_field) or f"{meta.prefix}{customer_id}{index:03d}")
                    payload.setdefault(meta.id_field, record_id)
                    payload = self._normalise_payload(resource, payload)
                    self._insert_record(conn, resource, customer_id, record_id, payload, now, immutable=True)
        self._set_meta(conn, "ticket_counter", str(getattr(mock_data, "_ticket_counter", 0)))
        self._set_meta(conn, "immutable_seed_applied", "1")

    def _load_mock_data_module(self):
        mock_path = self.project_root / "tools" / "mock_data.py"
        spec = importlib.util.spec_from_file_location("_demo_seed_mock_data", mock_path)
        if spec is None or spec.loader is None:
            raise DemoStoreError(f"cannot load mock data from {mock_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _apply_seed_protection(self, conn: sqlite3.Connection) -> None:
        applied = conn.execute(
            "SELECT value FROM demo_meta WHERE key = 'immutable_seed_applied'"
        ).fetchone()
        if applied and applied["value"] == "1":
            return
        mock_data = self._load_mock_data_module()
        now = utc_now()
        for resource, meta in RESOURCE_META.items():
            source = copy.deepcopy(getattr(mock_data, meta.source_name))
            if meta.kind == "single":
                for customer_id, payload in source.items():
                    payload.setdefault("customer_id", customer_id)
                    payload = self._normalise_payload(resource, payload)
                    self._lock_seed_record(conn, resource, customer_id, customer_id, payload, now)
                continue
            for customer_id, records in source.items():
                for index, payload in enumerate(records, start=1):
                    record_id = str(payload.get(meta.id_field) or f"{meta.prefix}{customer_id}{index:03d}")
                    payload.setdefault(meta.id_field, record_id)
                    payload = self._normalise_payload(resource, payload)
                    self._lock_seed_record(conn, resource, customer_id, record_id, payload, now)
        self._set_meta(conn, "immutable_seed_applied", "1")

    def _lock_seed_record(
        self,
        conn: sqlite3.Connection,
        resource: str,
        owner_id: str,
        record_id: str,
        payload: dict[str, Any],
        now: str,
    ) -> None:
        row = conn.execute(
            "SELECT record_id FROM demo_records WHERE resource = ? AND record_id = ?",
            (resource, record_id),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE demo_records
                SET owner_id = ?, payload = ?, immutable = 1, updated_at = ?
                WHERE resource = ? AND record_id = ?
                """,
                (
                    owner_id,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    resource,
                    record_id,
                ),
            )
            return
        self._insert_record(conn, resource, owner_id, record_id, payload, now, immutable=True)

    @staticmethod
    def _normalise_payload(resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        if resource == "customers":
            phone = payload.get("phone")
            if phone:
                payload["phone_masked"] = phone
        return payload

    @staticmethod
    def _insert_record(
        conn: sqlite3.Connection,
        resource: str,
        owner_id: str,
        record_id: str,
        payload: dict[str, Any],
        now: str,
        immutable: bool = False,
    ) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO demo_records
                (resource, owner_id, record_id, payload, immutable, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource,
                owner_id,
                record_id,
                json.dumps(payload, ensure_ascii=False),
                1 if immutable else 0,
                now,
                now,
            ),
        )

    @staticmethod
    def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO demo_meta(key, value) VALUES (?, ?)",
            (key, value),
        )

    @staticmethod
    def _decode_payload(row: sqlite3.Row) -> dict[str, Any]:
        return json.loads(row["payload"])

    @staticmethod
    def _record_response(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "resource": row["resource"],
            "owner_id": row["owner_id"],
            "record_id": row["record_id"],
            "payload": json.loads(row["payload"]),
            "immutable": bool(row["immutable"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def reset_records(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM demo_records")
            conn.execute("DELETE FROM demo_meta")
            self._seed_records(conn)
        return self.resource_summary()

    def resource_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT resource, COUNT(*) AS count FROM demo_records GROUP BY resource"
            ).fetchall()
        counts = {row["resource"]: row["count"] for row in rows}
        db_path = (
            str(self.db_path.relative_to(self.project_root))
            if self.db_path.is_relative_to(self.project_root)
            else self.db_path.name
        )
        return {
            "db_path": db_path,
            "resources": [
                {
                    "name": name,
                    "label": meta.label,
                    "kind": meta.kind,
                    "id_field": meta.id_field,
                    "count": counts.get(name, 0),
                }
                for name, meta in RESOURCE_META.items()
            ],
        }

    def list_records(self, resource: str, owner_id: str | None = None) -> list[dict[str, Any]]:
        self._ensure_resource(resource)
        sql = "SELECT * FROM demo_records WHERE resource = ?"
        params: list[Any] = [resource]
        if owner_id:
            sql += " AND owner_id = ?"
            params.append(owner_id)
        sql += " ORDER BY owner_id, record_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._record_response(row) for row in rows]

    def get_record(self, resource: str, record_id: str) -> dict[str, Any] | None:
        self._ensure_resource(resource)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM demo_records WHERE resource = ? AND record_id = ?",
                (resource, record_id),
            ).fetchone()
        return self._record_response(row) if row else None

    def get_customer_payload(self, resource: str, customer_id: str) -> dict[str, Any] | None:
        self._ensure_resource(resource)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM demo_records WHERE resource = ? AND owner_id = ? LIMIT 1",
                (resource, customer_id),
            ).fetchone()
        return self._decode_payload(row) if row else None

    def list_customer_payloads(self, resource: str, customer_id: str) -> list[dict[str, Any]]:
        self._ensure_resource(resource)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM demo_records
                WHERE resource = ? AND owner_id = ?
                ORDER BY record_id
                """,
                (resource, customer_id),
            ).fetchall()
        return [self._decode_payload(row) for row in rows]

    def upsert_record(
        self,
        resource: str,
        owner_id: str,
        payload: dict[str, Any],
        record_id: str | None = None,
    ) -> dict[str, Any]:
        meta = self._ensure_resource(resource)
        if not owner_id:
            raise DemoStoreError("owner_id is required")
        payload = copy.deepcopy(payload)
        if meta.kind == "single":
            record_id = owner_id
            payload.setdefault(meta.id_field, owner_id)
        else:
            record_id = str(record_id or payload.get(meta.id_field) or self._new_record_id(meta.prefix))
            payload.setdefault(meta.id_field, record_id)
        payload = self._normalise_payload(resource, payload)

        now = utc_now()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at, immutable FROM demo_records WHERE resource = ? AND record_id = ?",
                (resource, record_id),
            ).fetchone()
            if existing and existing["immutable"]:
                raise DemoStoreError(
                    f"seeded demo record cannot be modified: {resource}/{record_id}"
                )
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO demo_records
                    (resource, owner_id, record_id, payload, immutable, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    resource,
                    owner_id,
                    record_id,
                    json.dumps(payload, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )
        saved = self.get_record(resource, record_id)
        if saved is None:
            raise DemoStoreError(f"failed to save {resource}/{record_id}")
        return saved

    def delete_record(self, resource: str, record_id: str) -> bool:
        self._ensure_resource(resource)
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT immutable FROM demo_records WHERE resource = ? AND record_id = ?",
                (resource, record_id),
            ).fetchone()
            if existing and existing["immutable"]:
                raise DemoStoreError(
                    f"seeded demo record cannot be deleted: {resource}/{record_id}"
                )
            cur = conn.execute(
                "DELETE FROM demo_records WHERE resource = ? AND record_id = ?",
                (resource, record_id),
            )
        return cur.rowcount > 0

    def next_ticket_id(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        with self._lock, self._connect() as conn:
            raw = conn.execute(
                "SELECT value FROM demo_meta WHERE key = 'ticket_counter'"
            ).fetchone()
            current = int(raw["value"]) if raw else 0
            current += 1
            self._set_meta(conn, "ticket_counter", str(current))
        return f"TK{today}{current:03d}"

    def create_session(
        self,
        title: str | None = None,
        session_id: str | None = None,
        llm_profile_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = session_id or f"demo-{uuid.uuid4().hex[:12]}"
        now = utc_now()
        title = title or "新对话"
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO demo_sessions(session_id, title, customer_id, llm_profile_id, created_at, updated_at)
                VALUES (?, ?, '', ?, ?, ?)
                """,
                (session_id, title, llm_profile_id or "", now, now),
            )
        return self.get_session(session_id) or {}

    def ensure_session(self, session_id: str, title: str | None = None) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session:
            return session
        return self.create_session(title=title or "新对话", session_id=session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM demo_messages m WHERE m.session_id = s.session_id) AS message_count,
                       (
                           SELECT COUNT(*) FROM demo_messages m
                           WHERE m.session_id = s.session_id AND m.role = 'customer'
                       ) AS customer_message_count
                FROM demo_sessions s
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM demo_messages m WHERE m.session_id = s.session_id) AS message_count,
                       (
                           SELECT COUNT(*) FROM demo_messages m
                           WHERE m.session_id = s.session_id AND m.role = 'customer'
                       ) AS customer_message_count
                FROM demo_sessions s
                WHERE s.session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def has_customer_messages(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM demo_messages
                WHERE session_id = ? AND role = 'customer'
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return row is not None

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        customer_id: str | None = None,
        llm_profile_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_session(session_id)
        current = self.get_session(session_id) or {}
        next_title = title if title is not None else current.get("title", "新对话")
        next_customer_id = (
            customer_id if customer_id is not None else current.get("customer_id", "")
        )
        next_llm_profile_id = (
            llm_profile_id if llm_profile_id is not None else current.get("llm_profile_id", "")
        )
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE demo_sessions
                SET title = ?, customer_id = ?, llm_profile_id = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (next_title, next_customer_id, next_llm_profile_id, now, session_id),
            )
        return self.get_session(session_id) or {}

    def delete_session(self, session_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM demo_sessions WHERE session_id = ?", (session_id,))
        return cur.rowcount > 0

    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        response: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_session(session_id)
        now = utc_now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO demo_messages
                    (session_id, role, text, response_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    text,
                    json.dumps(response or {}, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            conn.execute(
                "UPDATE demo_sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            message_id = cur.lastrowid
        return self.get_message(int(message_id)) or {}

    def get_message(self, message_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM demo_messages WHERE id = ?",
                (message_id,),
            ).fetchone()
        return self._message_response(row) if row else None

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM demo_messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [self._message_response(row) for row in rows]

    # ------------------------------------------------------------------
    # Batch evaluation workspace
    # ------------------------------------------------------------------

    def create_eval_txt_file(
        self,
        *,
        filename: str,
        raw_text: str,
        messages: list[dict[str, Any]],
        dropped_lines: list[dict[str, Any]],
        parse_summary: dict[str, Any],
    ) -> dict[str, Any]:
        txt_id = f"txt-{uuid.uuid4().hex[:12]}"
        now = utc_now()
        with self._lock, self._connect() as conn:
            filename = self._unique_eval_filename(conn, filename)
            conn.execute(
                """
                INSERT INTO eval_txt_files
                    (txt_id, filename, raw_text, messages_json, dropped_lines_json,
                     parse_summary_json, imported_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    txt_id,
                    filename,
                    raw_text,
                    json.dumps(messages, ensure_ascii=False),
                    json.dumps(dropped_lines, ensure_ascii=False),
                    json.dumps(parse_summary, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_eval_txt_file(txt_id) or {}

    @staticmethod
    def _unique_eval_filename(conn: sqlite3.Connection, filename: str) -> str:
        clean = (filename or "未命名.txt").strip() or "未命名.txt"
        existing = {
            str(row["filename"])
            for row in conn.execute("SELECT filename FROM eval_txt_files").fetchall()
        }
        if clean not in existing:
            return clean

        path = Path(clean)
        stem = path.stem or clean
        suffix = path.suffix if path.suffix else ""
        counter = 2
        while True:
            candidate = f"{stem} ({counter}){suffix}"
            if candidate not in existing:
                return candidate
            counter += 1

    def list_eval_txt_files(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.*,
                       COUNT(DISTINCT r.llm_profile_id) AS model_count
                FROM eval_txt_files f
                LEFT JOIN eval_runs r ON r.txt_id = f.txt_id
                GROUP BY f.txt_id
                ORDER BY f.imported_at DESC
                """
            ).fetchall()
        return [self._eval_file_response(row) for row in rows]

    def get_eval_txt_file(self, txt_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT *, 0 AS model_count FROM eval_txt_files WHERE txt_id = ?",
                (txt_id,),
            ).fetchone()
        return self._eval_file_response(row) if row else None

    def delete_eval_txt_files(self, txt_ids: list[str]) -> int:
        if not txt_ids:
            return 0
        placeholders = ",".join("?" for _ in txt_ids)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"DELETE FROM eval_txt_files WHERE txt_id IN ({placeholders})",
                txt_ids,
            )
        return cur.rowcount

    def update_eval_txt_badcase(self, txt_id: str, *, badcase: bool, note: str = "") -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE eval_txt_files
                SET badcase = ?, badcase_note = ?, updated_at = ?
                WHERE txt_id = ?
                """,
                (1 if badcase else 0, note, now, txt_id),
            )
            if cur.rowcount == 0:
                raise DemoStoreError(f"unknown eval txt file: {txt_id}")
        file = self.get_eval_txt_file(txt_id)
        if file is None:
            raise DemoStoreError(f"unknown eval txt file: {txt_id}")
        return file

    def list_eval_runs(self, txt_id: str | None = None, llm_profile_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM eval_runs WHERE 1=1"
        params: list[Any] = []
        if txt_id:
            sql += " AND txt_id = ?"
            params.append(txt_id)
        if llm_profile_id:
            sql += " AND llm_profile_id = ?"
            params.append(llm_profile_id)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._eval_run_response(row) for row in rows]

    def get_eval_run(self, txt_id: str, llm_profile_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM eval_runs WHERE txt_id = ? AND llm_profile_id = ?",
                (txt_id, llm_profile_id),
            ).fetchone()
        return self._eval_run_response(row) if row else None

    def get_eval_run_by_id(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._eval_run_response(row) if row else None

    def start_eval_run(
        self,
        *,
        txt_id: str,
        llm_profile_id: str,
        total_turns: int,
        job_id: str,
        retry_failed_only: bool = False,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT run_id FROM eval_runs WHERE txt_id = ? AND llm_profile_id = ?",
                (txt_id, llm_profile_id),
            ).fetchone()
            if existing:
                run_id = existing["run_id"]
                if not retry_failed_only:
                    conn.execute("DELETE FROM eval_turn_results WHERE run_id = ?", (run_id,))
                conn.execute(
                    """
                    UPDATE eval_runs
                    SET status = 'running',
                        total_turns = ?,
                        generated_turns = CASE WHEN ? THEN generated_turns ELSE 0 END,
                        failed_turns = CASE WHEN ? THEN failed_turns ELSE 0 END,
                        accepted_turns = CASE WHEN ? THEN accepted_turns ELSE 0 END,
                        rejected_turns = CASE WHEN ? THEN rejected_turns ELSE 0 END,
                        badcase_count = CASE WHEN ? THEN badcase_count ELSE 0 END,
                        avg_latency_ms = CASE WHEN ? THEN avg_latency_ms ELSE 0 END,
                        intent_error = CASE WHEN ? THEN intent_error ELSE 0 END,
                        corrected_intent_l1 = CASE WHEN ? THEN corrected_intent_l1 ELSE '' END,
                        corrected_intent_l2 = CASE WHEN ? THEN corrected_intent_l2 ELSE '' END,
                        corrected_intent_label = CASE WHEN ? THEN corrected_intent_label ELSE '' END,
                        intent_error_note = CASE WHEN ? THEN intent_error_note ELSE '' END,
                        error = '',
                        job_id = ?,
                        started_at = ?,
                        finished_at = '',
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (
                        total_turns,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        1 if retry_failed_only else 0,
                        job_id,
                        now,
                        now,
                        run_id,
                    ),
                )
            else:
                run_id = f"run-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO eval_runs
                        (run_id, txt_id, llm_profile_id, status, total_turns,
                         generated_turns, failed_turns, accepted_turns, rejected_turns,
                         badcase_count, avg_latency_ms, error, job_id, started_at,
                         finished_at, updated_at)
                    VALUES (?, ?, ?, 'running', ?, 0, 0, 0, 0, 0, 0, '', ?, ?, '', ?)
                    """,
                    (
                        run_id,
                        txt_id,
                        llm_profile_id,
                        total_turns,
                        job_id,
                        now,
                        now,
                    ),
                )
        run = self.get_eval_run(txt_id, llm_profile_id)
        if run is None:
            raise DemoStoreError(f"failed to start eval run for {txt_id}/{llm_profile_id}")
        return run

    def update_eval_run_intent_review(
        self,
        run_id: str,
        *,
        intent_error: bool,
        corrected_intent: dict[str, Any] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        corrected_intent = corrected_intent or {}
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE eval_runs
                SET intent_error = ?,
                    corrected_intent_l1 = ?,
                    corrected_intent_l2 = ?,
                    corrected_intent_label = ?,
                    intent_error_note = ?,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    1 if intent_error else 0,
                    str(corrected_intent.get("l1") or "") if intent_error else "",
                    str(corrected_intent.get("l2") or "") if intent_error else "",
                    str(corrected_intent.get("label") or "") if intent_error else "",
                    note if intent_error else "",
                    now,
                    run_id,
                ),
            )
            if cur.rowcount == 0:
                raise DemoStoreError(f"unknown eval run: {run_id}")
        run = self.get_eval_run_by_id(run_id)
        if run is None:
            raise DemoStoreError(f"unknown eval run: {run_id}")
        return run

    def upsert_eval_turn_result(
        self,
        *,
        run_id: str,
        txt_id: str,
        message_index: int,
        user_query: str,
        context_messages: list[dict[str, Any]],
        status: str,
        model_answer: str = "",
        route: str = "",
        matched_skill_id: str = "",
        matched_skill_name: str = "",
        mapped_intent: dict[str, Any] | None = None,
        tools_called: list[str] | None = None,
        trace_id: str = "",
        error: str = "",
        latency_ms: float = 0,
        response: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        turn_result_id = f"{run_id}-m{message_index:04d}"
        now = utc_now()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT annotation_json, badcase, created_at FROM eval_turn_results WHERE turn_result_id = ?",
                (turn_result_id,),
            ).fetchone()
            annotation_json = existing["annotation_json"] if existing else "{}"
            badcase = int(existing["badcase"]) if existing else 0
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_turn_results
                    (turn_result_id, run_id, txt_id, message_index, user_query,
                     context_json, model_answer, route, matched_skill_id,
                     matched_skill_name, mapped_intent_json, tools_called_json,
                     trace_id, status, error, latency_ms, response_json,
                     annotation_json, badcase, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_result_id,
                    run_id,
                    txt_id,
                    message_index,
                    user_query,
                    json.dumps(context_messages, ensure_ascii=False),
                    model_answer,
                    route,
                    matched_skill_id,
                    matched_skill_name,
                    json.dumps(mapped_intent or {}, ensure_ascii=False),
                    json.dumps(tools_called or [], ensure_ascii=False),
                    trace_id,
                    status,
                    error,
                    latency_ms,
                    json.dumps(response or {}, ensure_ascii=False),
                    annotation_json,
                    badcase,
                    created_at,
                    now,
                ),
            )
        row = self.get_eval_turn_result(turn_result_id)
        if row is None:
            raise DemoStoreError(f"failed to save eval turn {turn_result_id}")
        return row

    def list_eval_turn_results(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM eval_turn_results WHERE run_id = ? ORDER BY message_index",
                (run_id,),
            ).fetchall()
        return [self._eval_turn_response(row) for row in rows]

    def get_eval_turn_result(self, turn_result_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM eval_turn_results WHERE turn_result_id = ?",
                (turn_result_id,),
            ).fetchone()
        return self._eval_turn_response(row) if row else None

    def annotate_eval_turn_result(
        self,
        turn_result_id: str,
        *,
        accepted: bool | None,
        reject_reasons: list[str],
        note: str,
        badcase: bool,
    ) -> dict[str, Any]:
        now = utc_now()
        annotation = {
            "accepted": accepted,
            "reject_reasons": reject_reasons,
            "note": note,
            "updated_at": now,
        }
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT run_id FROM eval_turn_results WHERE turn_result_id = ?",
                (turn_result_id,),
            ).fetchone()
            if row is None:
                raise DemoStoreError(f"unknown eval turn result: {turn_result_id}")
            # TXT-level Badcase is the only Badcase concept in the eval UI.
            # The legacy turn column is kept for DB compatibility, but single-turn
            # rejection is tracked through annotation/rejected_turns instead.
            conn.execute(
                """
                UPDATE eval_turn_results
                SET annotation_json = ?, badcase = ?, updated_at = ?
                WHERE turn_result_id = ?
                """,
                (
                    json.dumps(annotation, ensure_ascii=False),
                    0,
                    now,
                    turn_result_id,
                ),
            )
            run_id = row["run_id"]
        self.refresh_eval_run_summary(run_id)
        updated = self.get_eval_turn_result(turn_result_id)
        if updated is None:
            raise DemoStoreError(f"failed to annotate eval turn {turn_result_id}")
        return updated

    def finish_eval_run(
        self,
        run_id: str,
        *,
        status: str,
        main_skill_id: str = "",
        main_intent: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        main_intent = main_intent or {}
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE eval_runs
                SET status = ?, main_skill_id = ?, main_intent_l1 = ?,
                    main_intent_l2 = ?, main_intent_label = ?, error = ?,
                    finished_at = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    main_skill_id,
                    str(main_intent.get("l1") or ""),
                    str(main_intent.get("l2") or ""),
                    str(main_intent.get("label") or ""),
                    error,
                    now,
                    now,
                    run_id,
                ),
            )
        return self.refresh_eval_run_summary(run_id)

    def refresh_eval_run_summary(self, run_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT status, latency_ms, annotation_json, badcase FROM eval_turn_results WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            generated = sum(1 for row in rows if row["status"] == "success")
            failed = sum(1 for row in rows if row["status"] == "error")
            latencies = [float(row["latency_ms"] or 0) for row in rows if row["latency_ms"]]
            accepted = 0
            rejected = 0
            for row in rows:
                annotation = json.loads(row["annotation_json"] or "{}")
                if annotation.get("accepted") is True:
                    accepted += 1
                elif annotation.get("accepted") is False:
                    rejected += 1
            avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0
            conn.execute(
                """
                UPDATE eval_runs
                SET generated_turns = ?, failed_turns = ?, accepted_turns = ?,
                    rejected_turns = ?, badcase_count = ?, avg_latency_ms = ?,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    generated,
                    failed,
                    accepted,
                    rejected,
                    0,
                    avg_latency,
                    utc_now(),
                    run_id,
                ),
            )
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise DemoStoreError(f"unknown eval run: {run_id}")
        return self._eval_run_response(row)

    def create_eval_job(self, llm_profile_id: str, total_turns: int, config: dict[str, Any]) -> dict[str, Any]:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO eval_jobs
                    (job_id, status, llm_profile_id, total_turns, config_json, created_at, updated_at)
                VALUES (?, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    llm_profile_id,
                    total_turns,
                    json.dumps(config, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_eval_job(job_id) or {}

    def update_eval_job(self, job_id: str, **updates: Any) -> dict[str, Any]:
        allowed = {
            "status", "completed_turns", "success_turns", "failed_turns",
            "cancelled", "error",
        }
        pairs = [(key, value) for key, value in updates.items() if key in allowed]
        if not pairs:
            return self.get_eval_job(job_id) or {}
        pairs.append(("updated_at", utc_now()))
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE eval_jobs SET "
                + ", ".join(f"{key} = ?" for key, _ in pairs)
                + " WHERE job_id = ?",
                [value for _, value in pairs] + [job_id],
            )
        return self.get_eval_job(job_id) or {}

    def increment_eval_job(self, job_id: str, *, success: bool) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE eval_jobs
                SET completed_turns = completed_turns + 1,
                    success_turns = success_turns + ?,
                    failed_turns = failed_turns + ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (1 if success else 0, 0 if success else 1, utc_now(), job_id),
            )
        return self.get_eval_job(job_id) or {}

    def get_eval_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._eval_job_response(row) if row else None

    def list_eval_jobs(self, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 30), 100))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM eval_jobs ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [self._eval_job_response(row) for row in rows]

    @staticmethod
    def _eval_file_response(row: sqlite3.Row) -> dict[str, Any]:
        messages = json.loads(row["messages_json"] or "[]")
        return {
            "txt_id": row["txt_id"],
            "filename": row["filename"],
            "raw_text": row["raw_text"],
            "messages": messages,
            "dropped_lines": json.loads(row["dropped_lines_json"] or "[]"),
            "parse_summary": json.loads(row["parse_summary_json"] or "{}"),
            "user_turn_count": sum(1 for item in messages if item.get("role") == "user"),
            "model_count": int(row["model_count"] or 0) if "model_count" in row.keys() else 0,
            "badcase": bool(row["badcase"]),
            "badcase_note": row["badcase_note"],
            "imported_at": row["imported_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _eval_run_response(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "txt_id": row["txt_id"],
            "llm_profile_id": row["llm_profile_id"],
            "status": row["status"],
            "main_skill_id": row["main_skill_id"],
            "main_intent": {
                "l1": row["main_intent_l1"],
                "l2": row["main_intent_l2"],
                "label": row["main_intent_label"],
            },
            "intent_error": bool(row["intent_error"]),
            "corrected_intent": {
                "l1": row["corrected_intent_l1"],
                "l2": row["corrected_intent_l2"],
                "label": row["corrected_intent_label"],
            },
            "effective_intent": {
                "l1": row["corrected_intent_l1"] if row["intent_error"] and row["corrected_intent_l1"] else row["main_intent_l1"],
                "l2": row["corrected_intent_l2"] if row["intent_error"] and row["corrected_intent_l2"] else row["main_intent_l2"],
                "label": row["corrected_intent_label"] if row["intent_error"] and row["corrected_intent_label"] else row["main_intent_label"],
            },
            "intent_error_note": row["intent_error_note"],
            "total_turns": row["total_turns"],
            "generated_turns": row["generated_turns"],
            "failed_turns": row["failed_turns"],
            "accepted_turns": row["accepted_turns"],
            "rejected_turns": row["rejected_turns"],
            "issue_count": int(row["rejected_turns"] or 0) + int(row["failed_turns"] or 0),
            "badcase_count": row["badcase_count"],
            "avg_latency_ms": row["avg_latency_ms"],
            "error": row["error"],
            "job_id": row["job_id"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _eval_turn_response(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "turn_result_id": row["turn_result_id"],
            "run_id": row["run_id"],
            "txt_id": row["txt_id"],
            "message_index": row["message_index"],
            "user_query": row["user_query"],
            "context_messages": json.loads(row["context_json"] or "[]"),
            "model_answer": row["model_answer"],
            "route": row["route"],
            "matched_skill_id": row["matched_skill_id"],
            "matched_skill_name": row["matched_skill_name"],
            "mapped_intent": json.loads(row["mapped_intent_json"] or "{}"),
            "tools_called": json.loads(row["tools_called_json"] or "[]"),
            "trace_id": row["trace_id"],
            "status": row["status"],
            "error": row["error"],
            "latency_ms": row["latency_ms"],
            "response": json.loads(row["response_json"] or "{}"),
            "annotation": json.loads(row["annotation_json"] or "{}"),
            "badcase": bool(row["badcase"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _eval_job_response(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "llm_profile_id": row["llm_profile_id"],
            "total_turns": row["total_turns"],
            "completed_turns": row["completed_turns"],
            "success_turns": row["success_turns"],
            "failed_turns": row["failed_turns"],
            "cancelled": bool(row["cancelled"]),
            "error": row["error"],
            "config": json.loads(row["config_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _message_response(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "text": row["text"],
            "response": json.loads(row["response_json"] or "{}"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def verification_db(self) -> dict[str, dict[str, str]]:
        records = self.list_records("customers")
        out: dict[str, dict[str, str]] = {}
        for record in records:
            customer_id = record["record_id"]
            payload = record["payload"]
            id_last4 = str(payload.get("id_last4") or "")[-4:]
            if not id_last4 and payload.get("id_number"):
                id_last4 = str(payload["id_number"])[-4:].upper()
            out[customer_id] = {
                "real_name": str(payload.get("customer_name") or ""),
                "phone": str(payload.get("phone") or ""),
                "id_last4": id_last4,
            }
        return out

    def _ensure_resource(self, resource: str) -> ResourceMeta:
        if resource not in RESOURCE_META:
            raise DemoStoreError(f"unknown demo resource: {resource}")
        return RESOURCE_META[resource]

    @staticmethod
    def _new_record_id(prefix: str) -> str:
        return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]}"


_default_store: DemoStore | None = None
_default_lock = threading.Lock()


def get_demo_store() -> DemoStore:
    global _default_store
    if _default_store is None:
        with _default_lock:
            if _default_store is None:
                _default_store = DemoStore()
    return _default_store


def reset_default_store_for_tests() -> None:
    global _default_store
    with _default_lock:
        _default_store = None
