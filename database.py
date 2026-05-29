import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db import get_engine, is_postgres


logger = logging.getLogger(__name__)


def _auto_increment_id_column() -> str:
    """Return the right primary-key definition for the active database."""
    if is_postgres():
        return "id BIGSERIAL PRIMARY KEY"
    return "id INTEGER PRIMARY KEY AUTOINCREMENT"


def initialize_database() -> None:
    """Create tables if they do not already exist (works on SQLite and Postgres)."""
    id_column = _auto_increment_id_column()

    create_leads_table_sql = f"""
        CREATE TABLE IF NOT EXISTS leads (
            {id_column},
            phone_number TEXT NOT NULL,
            received_at TEXT NOT NULL,
            raw_text TEXT,
            lead_status TEXT NOT NULL,
            intent_name TEXT NOT NULL,
            handling_note TEXT
        );
    """
    create_conversation_table_sql = f"""
        CREATE TABLE IF NOT EXISTS conversation_history (
            {id_column},
            phone_number TEXT NOT NULL,
            role TEXT NOT NULL,
            message_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """
    create_customer_profile_table_sql = """
        CREATE TABLE IF NOT EXISTS customer_profiles (
            phone_number TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            customer_state TEXT NOT NULL,
            total_messages INTEGER NOT NULL DEFAULT 0
        );
    """
    create_interaction_logs_table_sql = f"""
        CREATE TABLE IF NOT EXISTS interaction_logs (
            {id_column},
            phone_number TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            raw_input TEXT,
            assigned_state TEXT NOT NULL
        );
    """

    try:
        with get_engine().begin() as connection:
            connection.execute(text(create_leads_table_sql))
            connection.execute(text(create_conversation_table_sql))
            connection.execute(text(create_customer_profile_table_sql))
            connection.execute(text(create_interaction_logs_table_sql))
            _migrate_legacy_leads_table(connection)
    except SQLAlchemyError as error:
        logger.exception("Failed to initialize database tables.")
        raise RuntimeError(f"Database initialization failed: {error}") from error


def _migrate_legacy_leads_table(connection) -> None:
    """Add newer columns to an older SQLite leads table when upgrading."""
    # Fresh Postgres tables already include every column, so this only
    # matters for older local SQLite files.
    if is_postgres():
        return

    existing = connection.execute(text("PRAGMA table_info(leads);")).fetchall()
    existing_columns = {row[1] for row in existing}

    migration_statements = []
    if "lead_status" not in existing_columns:
        migration_statements.append(
            "ALTER TABLE leads ADD COLUMN lead_status TEXT NOT NULL DEFAULT 'NEW_INBOUND';"
        )
    if "intent_name" not in existing_columns:
        migration_statements.append(
            "ALTER TABLE leads ADD COLUMN intent_name TEXT NOT NULL DEFAULT 'UNKNOWN';"
        )
    if "handling_note" not in existing_columns:
        migration_statements.append("ALTER TABLE leads ADD COLUMN handling_note TEXT;")

    for statement in migration_statements:
        connection.execute(text(statement))


def ensure_customer_profile(phone_number: str) -> None:
    """Ensure a customer profile exists for deterministic routing context."""
    now_timestamp = datetime.now(timezone.utc).isoformat()
    upsert_sql = """
        INSERT INTO customer_profiles
            (phone_number, first_seen_at, last_seen_at, customer_state, total_messages)
        VALUES (:phone_number, :first_seen, :last_seen, :state, :total)
        ON CONFLICT (phone_number) DO UPDATE SET
            last_seen_at = excluded.last_seen_at
    """
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(upsert_sql),
                {
                    "phone_number": phone_number,
                    "first_seen": now_timestamp,
                    "last_seen": now_timestamp,
                    "state": "NEW",
                    "total": 0,
                },
            )
    except SQLAlchemyError as error:
        logger.exception("Failed to ensure customer profile.")
        raise RuntimeError(f"Customer profile upsert failed: {error}") from error


def check_existing_customer(phone_number: str) -> Dict[str, Any]:
    """
    Deterministic baseline:
    Fetch profile data before intent execution.
    """
    ensure_customer_profile(phone_number)
    query_sql = """
        SELECT phone_number, first_seen_at, last_seen_at, customer_state, total_messages
        FROM customer_profiles
        WHERE phone_number = :phone_number
    """
    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(query_sql), {"phone_number": phone_number}
            ).mappings().first()
        if row is None:
            raise RuntimeError("Customer profile not found after creation.")
        return {
            "phone_number": row["phone_number"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "customer_state": row["customer_state"],
            "total_messages": int(row["total_messages"]),
        }
    except SQLAlchemyError as error:
        logger.exception("Failed to fetch customer profile.")
        raise RuntimeError(f"Customer profile read failed: {error}") from error


def get_customer_state(phone_number: str) -> str:
    """
    Return the latest deterministic state from interaction_logs.
    Falls back to NEW_SESSION when no record exists.
    """
    ensure_customer_profile(phone_number)
    query_sql = """
        SELECT assigned_state
        FROM interaction_logs
        WHERE phone_number = :phone_number
        ORDER BY id DESC
        LIMIT 1
    """
    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(query_sql), {"phone_number": phone_number}
            ).mappings().first()
        if row is None:
            return "NEW_SESSION"
        return str(row["assigned_state"])
    except SQLAlchemyError as error:
        logger.exception("Failed to fetch customer state.")
        raise RuntimeError(f"Customer state read failed: {error}") from error


def update_customer_state(phone_number: str, next_state: str) -> None:
    """Update deterministic state-machine value and message counter."""
    update_sql = """
        UPDATE customer_profiles
        SET customer_state = :state,
            last_seen_at = :last_seen,
            total_messages = total_messages + 1
        WHERE phone_number = :phone_number
    """
    now_timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with get_engine().begin() as connection:
            result = connection.execute(
                text(update_sql),
                {
                    "state": next_state,
                    "last_seen": now_timestamp,
                    "phone_number": phone_number,
                },
            )
            if result.rowcount == 0:
                raise RuntimeError("No customer profile found to update.")
    except SQLAlchemyError as error:
        logger.exception("Failed to update customer state.")
        raise RuntimeError(f"Customer state update failed: {error}") from error


def log_lead(
    phone_number: str,
    raw_text: str,
    lead_status: str,
    intent_name: str = "UNKNOWN",
    handling_note: Optional[str] = None,
) -> None:
    """Store a lead entry with deterministic routing metadata."""
    insert_sql = """
        INSERT INTO leads
            (phone_number, received_at, raw_text, lead_status, intent_name, handling_note)
        VALUES (:phone_number, :received_at, :raw_text, :lead_status, :intent_name, :handling_note)
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(insert_sql),
                {
                    "phone_number": phone_number,
                    "received_at": timestamp,
                    "raw_text": raw_text,
                    "lead_status": lead_status,
                    "intent_name": intent_name,
                    "handling_note": handling_note,
                },
            )
    except SQLAlchemyError as error:
        logger.exception("Failed to log lead.")
        raise RuntimeError(f"Lead logging failed: {error}") from error


def log_transaction(phone_number: str, raw_input: str, current_state: str) -> None:
    """Write an auditable state-transition record for tracing."""
    ensure_customer_profile(phone_number)
    insert_sql = """
        INSERT INTO interaction_logs (phone_number, timestamp, raw_input, assigned_state)
        VALUES (:phone_number, :timestamp, :raw_input, :assigned_state)
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(insert_sql),
                {
                    "phone_number": phone_number,
                    "timestamp": timestamp,
                    "raw_input": raw_input,
                    "assigned_state": current_state,
                },
            )
    except SQLAlchemyError as error:
        logger.exception("Failed to log interaction transaction.")
        raise RuntimeError(f"Transaction logging failed: {error}") from error


def add_conversation_message(phone_number: str, role: str, message_text: str) -> None:
    """Store one message in conversation history."""
    insert_sql = """
        INSERT INTO conversation_history (phone_number, role, message_text, created_at)
        VALUES (:phone_number, :role, :message_text, :created_at)
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(insert_sql),
                {
                    "phone_number": phone_number,
                    "role": role,
                    "message_text": message_text,
                    "created_at": timestamp,
                },
            )
    except SQLAlchemyError as error:
        logger.exception("Failed to add conversation message.")
        raise RuntimeError(f"Conversation write failed: {error}") from error


def log_incoming_lead(phone_number: str, raw_text: str) -> None:
    """
    Backward-compatible helper for earlier app calls.
    New code should prefer log_lead().
    """
    log_lead(
        phone_number=phone_number,
        raw_text=raw_text,
        lead_status="NEW_INBOUND",
        intent_name="UNKNOWN",
        handling_note="legacy_log_call",
    )


def get_conversation_history(phone_number: str, limit: int = 10) -> List[Dict[str, str]]:
    """Fetch recent conversation history for a phone number."""
    query_sql = """
        SELECT role, message_text
        FROM conversation_history
        WHERE phone_number = :phone_number
        ORDER BY id DESC
        LIMIT :limit
    """
    try:
        with get_engine().connect() as connection:
            rows = connection.execute(
                text(query_sql), {"phone_number": phone_number, "limit": limit}
            ).mappings().all()
        rows_in_order = list(reversed(rows))
        return [{"role": row["role"], "content": row["message_text"]} for row in rows_in_order]
    except SQLAlchemyError as error:
        logger.exception("Failed to fetch conversation history.")
        raise RuntimeError(f"Conversation read failed: {error}") from error
