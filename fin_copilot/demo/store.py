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
