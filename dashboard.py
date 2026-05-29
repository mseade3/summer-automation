import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from streamlit_autorefresh import st_autorefresh

from db import get_engine
from database import initialize_database

try:
    from config import BUSINESS_NAME
except ImportError:
    BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Your Business")


# Plain-language meaning for every behind-the-scenes status.
# (label shown to owner, accent color, is this something to act on now?)
STATUS_MEANINGS = {
    "PRIORITY_BOOKING": ("Wants to Book", "#15803d", "#eafaf0", True),
    "HUMAN_INTERVENTION_REQUIRED": ("Needs Your Reply", "#b42318", "#fff1f1", True),
    "NEW_LEAD": ("New Inquiry", "#1554c0", "#eaf3ff", True),
    "TEXT_BACK_SENT": ("Auto-Replied", "#475467", "#f2f4f7", False),
    "RESOLVED": ("Handled", "#15803d", "#eafaf0", False),
}


def describe_status(raw_status: str):
    """Return owner-friendly (label, text_color, background, needs_action)."""
    if raw_status in STATUS_MEANINGS:
        return STATUS_MEANINGS[raw_status]
    friendly = raw_status.replace("_", " ").title()
    return (friendly, "#475467", "#f2f4f7", False)


def format_phone_number(raw_number: str) -> str:
    """Turn +12407580338 into +1 (240) 758-0338 for easy reading."""
    digits = "".join(character for character in raw_number if character.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"
    return raw_number


def describe_time_ago(raw_timestamp: str) -> str:
    """Convert a stored timestamp into 'just now', '5 minutes ago', etc."""
    try:
        parsed_time = datetime.fromisoformat(raw_timestamp)
    except (ValueError, TypeError):
        return raw_timestamp

    if parsed_time.tzinfo is None:
        parsed_time = parsed_time.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    seconds_elapsed = (now - parsed_time).total_seconds()

    if seconds_elapsed < 60:
        return "Just now"
    if seconds_elapsed < 3600:
        minutes = int(seconds_elapsed // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds_elapsed < 86400:
        hours = int(seconds_elapsed // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(seconds_elapsed // 86400)
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return parsed_time.strftime("%b %d, %Y")


def load_conversations() -> pd.DataFrame:
    """Load every customer conversation, newest first."""
    empty_frame = pd.DataFrame(
        columns=["id", "phone_number", "timestamp", "raw_input", "assigned_state"]
    )

    query_sql = """
        SELECT id, phone_number, timestamp, raw_input, assigned_state
        FROM interaction_logs
        ORDER BY timestamp DESC
    """
    try:
        with get_engine().connect() as connection:
            conversations = pd.read_sql_query(text(query_sql), connection)
    except SQLAlchemyError:
        conversations = empty_frame
    return conversations


def mark_lead_as_handled(record_id: int) -> None:
    """Mark a single conversation as handled so it leaves the action list."""
    update_sql = "UPDATE interaction_logs SET assigned_state = 'RESOLVED' WHERE id = :record_id"
    with get_engine().begin() as connection:
        connection.execute(text(update_sql), {"record_id": record_id})


def count_today(conversations: pd.DataFrame) -> int:
    """Count conversations that arrived today."""
    if conversations.empty:
        return 0
    today_string = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return int(conversations["timestamp"].astype(str).str.startswith(today_string).sum())


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; max-width: 1180px; }

        .hero {
            background: linear-gradient(120deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%);
            border-radius: 20px;
            padding: 30px 34px;
            color: #ffffff;
            margin-bottom: 26px;
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.25);
        }
        .hero_eyebrow {
            text-transform: uppercase;
            letter-spacing: 2px;
            font-size: 0.72rem;
            opacity: 0.8;
            margin-bottom: 6px;
        }
        .hero_title { font-size: 2.1rem; font-weight: 800; margin: 0; }
        .hero_subtitle { font-size: 1rem; opacity: 0.9; margin-top: 8px; }
        .live_badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 255, 255, 0.14);
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-top: 16px;
        }
        .live_pulse {
            width: 9px; height: 9px; border-radius: 50%;
            background: #4ade80;
            box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7);
            animation: pulse 1.8s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.6); }
            70% { box-shadow: 0 0 0 10px rgba(74, 222, 128, 0); }
            100% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0); }
        }

        .kpi {
            background: #ffffff;
            border: 1px solid #eaecf0;
            border-radius: 16px;
            padding: 20px 22px;
            min-height: 132px;
            box-shadow: 0 4px 14px rgba(16, 24, 40, 0.05);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .kpi:hover { transform: translateY(-3px); box-shadow: 0 12px 26px rgba(16, 24, 40, 0.1); }
        .kpi_label { font-size: 0.85rem; color: #667085; font-weight: 600; }
        .kpi_number { font-size: 2.4rem; font-weight: 800; color: #101828; line-height: 1.1; margin-top: 6px; }
        .kpi_note { font-size: 0.8rem; color: #98a2b3; margin-top: 6px; }
        .kpi_accent { height: 4px; border-radius: 999px; margin-top: 14px; }

        .lead_card {
            background: #ffffff;
            border: 1px solid #eaecf0;
            border-left: 6px solid #cbd5e1;
            border-radius: 14px;
            padding: 18px 20px;
            margin-bottom: 4px;
            box-shadow: 0 3px 10px rgba(16, 24, 40, 0.04);
        }
        .lead_top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .lead_chip {
            display: inline-block; padding: 4px 12px; border-radius: 999px;
            font-size: 0.74rem; font-weight: 700;
        }
        .lead_time { font-size: 0.8rem; color: #98a2b3; }
        .lead_message { font-size: 1.12rem; color: #101828; font-weight: 600; margin: 6px 0 10px 0; }
        .lead_phone { font-size: 0.92rem; color: #475467; font-weight: 600; }
        .contact_links a {
            text-decoration: none; font-weight: 600; font-size: 0.85rem;
            margin-right: 16px; color: #2563eb;
        }
        .empty_state {
            text-align: center; padding: 48px 20px; color: #667085;
            border: 1px dashed #d0d5dd; border-radius: 16px; background: #fafbfc;
        }
        .empty_state h3 { color: #101828; margin-bottom: 6px; }
        .section_heading { font-size: 1.3rem; font-weight: 700; color: #101828; margin: 8px 0 4px 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(conversations: pd.DataFrame) -> None:
    needs_action = 0
    if not conversations.empty:
        for raw_status in conversations["assigned_state"]:
            _, _, _, action = describe_status(str(raw_status))
            if action:
                needs_action += 1

    if needs_action > 0:
        subtitle = (
            f"You have {needs_action} customer"
            f"{'s' if needs_action != 1 else ''} waiting to hear back."
        )
    else:
        subtitle = "You're all caught up. Every customer has been taken care of."

    st.markdown(
        f"""
        <div class="hero">
            <div class="hero_eyebrow">{BUSINESS_NAME}</div>
            <div class="hero_title">Customer Response Center</div>
            <div class="hero_subtitle">{subtitle}</div>
            <div class="live_badge"><span class="live_pulse"></span> Answering calls &amp; texts automatically</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(conversations: pd.DataFrame) -> None:
    total_conversations = len(conversations)
    ready_to_book = int((conversations["assigned_state"] == "PRIORITY_BOOKING").sum()) if not conversations.empty else 0
    waiting_reply = int((conversations["assigned_state"] == "HUMAN_INTERVENTION_REQUIRED").sum()) if not conversations.empty else 0
    captured_today = count_today(conversations)

    cards = [
        ("New Today", captured_today, "Customers who reached out today", "#2563eb"),
        ("Ready to Book", ready_to_book, "Hot leads — call these first", "#15803d"),
        ("Waiting on You", waiting_reply, "Need a personal reply", "#b42318"),
        ("Total Captured", total_conversations, "Every customer we've answered", "#7c3aed"),
    ]

    columns = st.columns(4)
    for column, (label, number, note, accent) in zip(columns, cards):
        with column:
            st.markdown(
                f"""
                <div class="kpi">
                    <div class="kpi_label">{label}</div>
                    <div class="kpi_number">{number}</div>
                    <div class="kpi_note">{note}</div>
                    <div class="kpi_accent" style="background:{accent};"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_lead_card(row) -> None:
    record_id = int(row["id"])
    raw_status = str(row["assigned_state"])
    label, text_color, background, _ = describe_status(raw_status)
    pretty_phone = format_phone_number(str(row["phone_number"]))
    dial_digits = "".join(ch for ch in str(row["phone_number"]) if ch.isdigit() or ch == "+")
    time_ago = describe_time_ago(str(row["timestamp"]))
    message = str(row["raw_input"])

    card_column, action_column = st.columns([5, 1.4])

    with card_column:
        st.markdown(
            f"""
            <div class="lead_card" style="border-left-color:{text_color};">
                <div class="lead_top">
                    <span class="lead_chip" style="color:{text_color}; background:{background};">{label}</span>
                    <span class="lead_time">{time_ago}</span>
                </div>
                <div class="lead_message">&ldquo;{message}&rdquo;</div>
                <div class="lead_phone">{pretty_phone}</div>
                <div class="contact_links">
                    <a href="tel:{dial_digits}">Call customer</a>
                    <a href="sms:{dial_digits}">Send a text</a>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with action_column:
        st.write("")
        st.write("")
        if st.button("Mark as Handled", key=f"handle_{record_id}", use_container_width=True):
            mark_lead_as_handled(record_id)
            st.toast("Marked as handled. Nice work.")
            st.rerun()


def render_call_first(conversations: pd.DataFrame) -> None:
    st.markdown('<div class="section_heading">Call These First</div>', unsafe_allow_html=True)
    st.caption("Customers who want to book or need a personal reply — sorted by most recent.")

    if conversations.empty:
        render_empty_state("No customers in line right now", "New calls and texts will appear here automatically.")
        return

    action_mask = conversations["assigned_state"].apply(lambda value: describe_status(str(value))[3])
    priority_rows = conversations[action_mask]

    if priority_rows.empty:
        render_empty_state("You're all caught up", "Every customer has been taken care of. Great job.")
        return

    for _, row in priority_rows.iterrows():
        render_lead_card(row)


def render_all_conversations(conversations: pd.DataFrame) -> None:
    st.markdown('<div class="section_heading">All Conversations</div>', unsafe_allow_html=True)
    st.caption("A complete history of every customer who has reached out.")

    if conversations.empty:
        render_empty_state("No conversations yet", "As soon as a customer calls or texts, it will show up here.")
        return

    display_frame = pd.DataFrame()
    display_frame["When"] = conversations["timestamp"].apply(lambda value: describe_time_ago(str(value)))
    display_frame["Customer"] = conversations["phone_number"].apply(lambda value: format_phone_number(str(value)))
    display_frame["Their Message"] = conversations["raw_input"].astype(str)
    display_frame["Status"] = conversations["assigned_state"].apply(lambda value: describe_status(str(value))[0])

    st.dataframe(display_frame, use_container_width=True, hide_index=True)


def render_empty_state(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="empty_state">
            <h3>{title}</h3>
            <div>{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_dashboard() -> None:
    st.set_page_config(
        page_title="Customer Response Center",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_styles()

    with st.sidebar:
        st.subheader("Settings")
        live_updates = st.toggle("Update automatically", value=True)
        st.caption("Keeps the screen current as new customers come in.")
        if st.button("Refresh now", use_container_width=True):
            st.rerun()
        st.divider()
        st.caption(f"Last updated {datetime.now().strftime('%I:%M %p')}")

    if live_updates:
        st_autorefresh(interval=5000, key="seamless_refresh")

    # Make sure the tables exist even when the dashboard is deployed as its
    # own service and starts before the backend has run.
    try:
        initialize_database()
    except RuntimeError:
        pass

    try:
        conversations = load_conversations()
    except SQLAlchemyError:
        conversations = pd.DataFrame(
            columns=["id", "phone_number", "timestamp", "raw_input", "assigned_state"]
        )

    render_hero(conversations)
    render_kpis(conversations)
    st.write("")

    call_first_tab, history_tab = st.tabs(["Call These First", "All Conversations"])
    with call_first_tab:
        render_call_first(conversations)
    with history_tab:
        render_all_conversations(conversations)


if __name__ == "__main__":
    build_dashboard()
