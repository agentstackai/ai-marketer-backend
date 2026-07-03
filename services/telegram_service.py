import os
import requests

TG_BASE = "https://api.telegram.org"


def get_bot_token():
    return os.getenv("TELEGRAM_BOT_TOKEN")


def get_channel_id():
    return os.getenv("TELEGRAM_CHANNEL_ID")


def send_message(text: str, chat_id: str = None, parse_mode: str = "Markdown") -> dict:
    """Send a message to a Telegram channel or chat."""
    token = get_bot_token()
    target = chat_id or get_channel_id()

    resp = requests.post(
        f"{TG_BASE}/bot{token}/sendMessage",
        json={
            "chat_id": target,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    msg = data.get("result", {})
    return {
        "ok": True,
        "message_id": msg.get("message_id"),
        "chat": msg.get("chat", {}).get("title") or msg.get("chat", {}).get("username"),
    }


def send_campaign_messages(recipients: list, message_template: str, personalize_fn=None) -> dict:
    """Broadcast Telegram messages to individual chat IDs in the audience list."""
    results = {"sent": 0, "failed": 0, "errors": []}
    for recipient in recipients:
        chat_id = recipient.get("telegram_id", "").strip()
        if not chat_id:
            results["failed"] += 1
            results["errors"].append(f"{recipient.get('name')}: no telegram_id")
            continue
        try:
            body = personalize_fn(message_template, recipient) if personalize_fn else message_template
            send_message(body, chat_id=chat_id)
            results["sent"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{chat_id}: {str(e)}")
    return results


def test_connection() -> dict:
    try:
        token = get_bot_token()
        resp = requests.get(f"{TG_BASE}/bot{token}/getMe", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("result", {})
        return {
            "ok": True,
            "username": data.get("username"),
            "name": data.get("first_name"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
