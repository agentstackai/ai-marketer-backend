import os
import requests

LI_BASE = "https://api.linkedin.com/v2"

def get_headers():
    return {
        "Authorization": f"Bearer {os.getenv('LINKEDIN_ACCESS_TOKEN')}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

def post_text(text: str) -> dict:
    """Post a text update to LinkedIn personal or company page."""
    person_urn = os.getenv("LINKEDIN_PERSON_URN")  # e.g. urn:li:person:ABC123

    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }

    resp = requests.post(f"{LI_BASE}/ugcPosts", json=payload, headers=get_headers(), timeout=15)
    resp.raise_for_status()
    post_id = resp.headers.get("x-restli-id", "")
    return {"ok": True, "post_id": post_id, "url": f"https://www.linkedin.com/feed/update/{post_id}"}


def test_connection() -> dict:
    try:
        resp = requests.get(f"{LI_BASE}/userinfo", headers=get_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "name": data.get("name"), "sub": data.get("sub")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
