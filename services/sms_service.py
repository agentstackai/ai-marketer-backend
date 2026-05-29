import os
from twilio.rest import Client

_client = None

def get_client():
    global _client
    if _client is None:
        _client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    return _client

def send_campaign_sms(recipients: list, message_template: str, personalize_fn=None) -> dict:
    """
    Send SMS to a list of recipients.
    recipients: [{"name": str, "phone": str, ...}]
    """
    client = get_client()
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    results = {"sent": 0, "failed": 0, "errors": []}

    for recipient in recipients:
        phone = recipient.get("phone", "").strip()
        if not phone:
            results["failed"] += 1
            results["errors"].append(f"{recipient.get('name')}: no phone number")
            continue
        try:
            body = personalize_fn(message_template, recipient) if personalize_fn else message_template
            msg = client.messages.create(body=body, from_=from_number, to=phone)
            if msg.status in ("queued", "sent", "delivered"):
                results["sent"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"{phone}: {msg.status}")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{phone}: {str(e)}")

    return results


def test_connection() -> dict:
    try:
        client = get_client()
        account = client.api.accounts(os.getenv("TWILIO_ACCOUNT_SID")).fetch()
        return {"ok": True, "account_name": account.friendly_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}
