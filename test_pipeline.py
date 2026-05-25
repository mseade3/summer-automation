import sqlite3
import os
import requests

from config import DATABASE_FILE


SERVER_URL = os.getenv("TEST_SERVER_URL", "http://127.0.0.1:5000/webhook/sms")


def send_mock_sms(from_number: str, message_body: str) -> None:
    """Simulate a Twilio webhook payload hitting the Flask app."""
    print(f"\n--- Outgoing Simulation from {from_number} ---")
    print(f'Message: "{message_body}"')

    payload = {
        "From": from_number,
        "Body": message_body,
    }

    try:
        response = requests.post(SERVER_URL, data=payload, timeout=15)
        print(f"Server Status Code: {response.status_code}")
        print(f"TwiML XML Output:\n{response.text}")
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to the server. Is app.py running?")
    except requests.exceptions.RequestException as error:
        print(f"HTTP request failed: {error}")


def inspect_database_state() -> None:
    """Read recent deterministic execution logs from SQLite."""
    print(f"\n--- Inspecting Database State (interaction_logs in {DATABASE_FILE}) ---")
    connection = None
    try:
        connection = sqlite3.connect(DATABASE_FILE)
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, phone_number, assigned_state, raw_input
            FROM interaction_logs
            ORDER BY id DESC
            LIMIT 5
            """
        )
        records = cursor.fetchall()

        if not records:
            print("Database is currently empty.")
            return

        for row in records:
            print(f"Log ID: {row[0]} | Phone: {row[1]} | State: {row[2]} | Input: {row[3]}")
    except Exception as error:
        print(f"Database Read Error: {error}")
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    send_mock_sms("+13015550199", "I need to book a slot for tomorrow at 3 PM if possible.")
    send_mock_sms("+13015550199", "Hey can you tell me more about your pricing and services?")
    send_mock_sms("+12025550144", "Where is my missing package from last Tuesday?")
    inspect_database_state()

