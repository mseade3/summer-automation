import logging

from flask import Flask, request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse

from ai_handler import classify_incoming_intent
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
from database import (
    initialize_database,
    log_lead,
    log_transaction,
    add_conversation_message,
    check_existing_customer,
    get_customer_state,
    update_customer_state,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

try:
    initialize_database()
except RuntimeError as error:
    logger.exception("Application startup failed during database initialization.")
    raise

def get_twilio_client() -> Client:
    """Return a Twilio client after validating credentials."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise RuntimeError("Twilio credentials are missing. Check your .env settings.")
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_text_message(to_phone_number: str, body_text: str) -> None:
    """Send an outbound SMS using the Twilio REST API."""
    if not TWILIO_PHONE_NUMBER:
        raise RuntimeError("TWILIO_PHONE_NUMBER is missing. Check your .env settings.")

    twilio_client = get_twilio_client()
    try:
        twilio_client.messages.create(
            to=to_phone_number,
            from_=TWILIO_PHONE_NUMBER,
            body=body_text,
        )
    except Exception as error:
        logger.exception("Failed to send outbound SMS through Twilio.")
        raise RuntimeError(f"Twilio send failed: {error}") from error


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200


@app.route("/webhook/twilio", methods=["POST"])
def twilio_webhook():
    """
    Handle both incoming Twilio voice and SMS events from a single endpoint.
    - Voice trigger (missed call): logs lead and sends automated text-back.
    - SMS trigger: continues conversation with an AI-generated response.
    """
    form_data = request.form
    from_phone_number = form_data.get("From", "").strip()

    if not from_phone_number:
        logger.warning("Webhook called without a valid From number.")
        return jsonify({"error": "Missing From phone number"}), 400

    try:
        if "CallSid" in form_data:
            return handle_voice_trigger(form_data, from_phone_number)
        if "SmsSid" in form_data:
            return process_sms_pipeline_internal(form_data, from_phone_number)

        logger.warning("Unsupported Twilio trigger type received.")
        return jsonify({"error": "Unsupported Twilio trigger type"}), 400
    except RuntimeError as error:
        logger.exception("Runtime failure while processing Twilio webhook.")
        return jsonify({"error": str(error)}), 500
    except Exception as error:
        logger.exception("Unexpected failure while processing Twilio webhook.")
        return jsonify({"error": f"Unexpected server error: {error}"}), 500


def handle_voice_trigger(form_data, from_phone_number: str):
    """
    Handle missed-call events.
    This logs a lead, sends a text-back, and returns a short TwiML voice response.
    """
    call_status = form_data.get("CallStatus", "unknown")
    lead_note = f"voice_trigger status={call_status}"

    check_existing_customer(from_phone_number)
    log_lead(
        phone_number=from_phone_number,
        raw_text=lead_note,
        lead_status="MISSED_CALL_TEXT_BACK",
        intent_name="VOICE_MISSED_CALL",
        handling_note="automatic_text_back_sent",
    )
    update_customer_state(from_phone_number, "TEXT_BACK_SENT")

    text_back_message = (
        "Thanks for calling! We missed your call but can help by text right away. "
        "Tell us what you need and we will assist shortly."
    )
    send_text_message(from_phone_number, text_back_message)

    voice_response = VoiceResponse()
    voice_response.say(
        "Thanks for calling. We just sent you a text message and will assist you there.",
        voice="alice",
    )
    voice_response.hangup()

    logger.info("Processed voice trigger for %s", from_phone_number)
    return str(voice_response), 200, {"Content-Type": "application/xml"}


@app.route("/webhook/sms", methods=["POST"])
def process_sms_pipeline():
    """Dedicated SMS endpoint using strict interface-vs-operator flow."""
    sender_number = request.values.get("From", "").strip()
    if not sender_number:
        return jsonify({"error": "Missing From phone number"}), 400
    return process_sms_pipeline_internal(request.values, sender_number)


def process_sms_pipeline_internal(form_data, from_phone_number: str):
    """
    Main routing engine with deterministic control:
    1) load state context from DB
    2) classify intent via LLM
    3) execute hardcoded stateful actions
    """
    customer_message = form_data.get("Body", "").strip()
    if not customer_message:
        logger.warning("Received SMS trigger with empty body.")
        customer_message = "[empty_message]"

    customer_profile = check_existing_customer(from_phone_number)
    previous_state = get_customer_state(from_phone_number)
    add_conversation_message(from_phone_number, "user", customer_message)

    try:
        parsed_result = classify_incoming_intent(customer_message)
        detected_intent = parsed_result.get("intent", "UNKNOWN")
        detected_entities = parsed_result.get("entities", {})
    except RuntimeError as error:
        logger.error("Intent extraction failed: %s", error)
        detected_intent = "UNKNOWN"
        detected_entities = {}

    next_state = decide_next_state(
        current_state=previous_state,
        detected_intent=detected_intent,
    )
    update_customer_state(from_phone_number, next_state)
    log_transaction(from_phone_number, customer_message, current_state=next_state)

    reply_message, lead_status, handling_note = build_deterministic_response(
        detected_intent=detected_intent,
        customer_profile=customer_profile,
        detected_entities=detected_entities,
    )

    log_lead(
        phone_number=from_phone_number,
        raw_text=customer_message,
        lead_status=lead_status,
        intent_name=detected_intent,
        handling_note=handling_note,
    )

    add_conversation_message(from_phone_number, "assistant", reply_message)

    sms_response = MessagingResponse()
    sms_response.message(reply_message)

    logger.info(
        "Processed SMS trigger for %s intent=%s state=%s",
        from_phone_number,
        detected_intent,
        next_state,
    )
    return str(sms_response), 200, {"Content-Type": "application/xml"}


def decide_next_state(current_state: str, detected_intent: str) -> str:
    """
    Lightweight deterministic state machine.
    The LLM never decides next state; code does.
    """
    transition_map = {
        ("NEW_SESSION", "BOOKING"): "PRIORITY_BOOKING",
        ("NEW_SESSION", "LEAD_INQUIRY"): "NEW_LEAD",
        ("TEXT_BACK_SENT", "BOOKING"): "PRIORITY_BOOKING",
        ("TEXT_BACK_SENT", "LEAD_INQUIRY"): "NEW_LEAD",
        ("HUMAN_INTERVENTION_REQUIRED", "BOOKING"): "PRIORITY_BOOKING",
        ("HUMAN_INTERVENTION_REQUIRED", "LEAD_INQUIRY"): "NEW_LEAD",
        ("PRIORITY_BOOKING", "BOOKING"): "PRIORITY_BOOKING",
        ("PRIORITY_BOOKING", "LEAD_INQUIRY"): "NEW_LEAD",
        ("NEW_LEAD", "LEAD_INQUIRY"): "NEW_LEAD",
        ("NEW_LEAD", "BOOKING"): "PRIORITY_BOOKING",
    }
    return transition_map.get((current_state, detected_intent), "HUMAN_INTERVENTION_REQUIRED")


def build_deterministic_response(detected_intent, customer_profile, detected_entities):
    """
    Return hardcoded responses for each intent.
    This is the deterministic execution layer.
    """
    if detected_intent == "BOOKING":
        service_name = detected_entities.get("service")
        if service_name:
            message = (
                f"Acknowledged. We flagged your {service_name} booking request. "
                "A coordinator will verify times shortly."
            )
        else:
            message = (
                "Acknowledged. Our booking engine has flagged your request. "
                "A coordinator will verify times shortly."
            )
        return message, "PRIORITY_BOOKING", "booking_queue"

    if detected_intent == "LEAD_INQUIRY":
        return (
            "Inquiry captured. Your details have been routed to our operations dashboard.",
            "NEW_LEAD",
            "lead_queue",
        )

    return (
        "Message received. Forwarding this thread directly to our front desk team for immediate assistance.",
        "HUMAN_INTERVENTION_REQUIRED",
        "unknown_intent_fallback",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

