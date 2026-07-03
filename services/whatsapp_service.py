import os
import requests

GRAPH_BASE = "https://graph.facebook.com/v19.0"


def get_headers():
    return {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_ACCESS_TOKEN')}",
        "Content-Type": "application/json",
    }


def send_text_message(to_number: str, message: str) -> dict:
    """
    Send a free-form text message to a WhatsApp number.
    to_number: E.164 format, e.g. "919876543210"
    """
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    resp = requests.post(
        f"{GRAPH_BASE}/{phone_id}/messages",
        json=payload,
        headers=get_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    msg_id = data.get("messages", [{}])[0].get("id", "")
    return {"ok": True, "message_id": msg_id, "to": to_number}


def send_campaign_messages(recipients: list, message_template: str, personalize_fn=None) -> dict:
    """
    Broadcast a WhatsApp message to a list of recipients.
    recipients: [{"name": str, "phone": str, ...}]
    phone field must be in E.164 format (e.g. "919876543210").
    """
    results = {"sent": 0, "failed": 0, "errors": []}
    for recipient in recipients:
        phone = recipient.get("phone", "").strip().lstrip("+")
        if not phone:
            results["failed"] += 1
            results["errors"].append(f"{recipient.get('name')}: no phone number")
            continue
        try:
            body = personalize_fn(message_template, recipient) if personalize_fn else message_template
            send_text_message(phone, body)
            results["sent"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{phone}: {str(e)}")
    return results


def test_connection() -> dict:
    try:
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        resp = requests.get(
            f"{GRAPH_BASE}/{phone_id}",
            params={"fields": "display_phone_number,verified_name"},
            headers=get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "phone": data.get("display_phone_number"),
            "name": data.get("verified_name"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
