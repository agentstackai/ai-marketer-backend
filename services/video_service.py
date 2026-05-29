import os
import time
import requests

DID_BASE = "https://api.d-id.com"
DID_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
}

def get_headers():
    return {**DID_HEADERS, "authorization": f"Basic {os.getenv('DID_API_KEY')}"}


def create_video(script: str, presenter_id: str = None) -> dict:
    """
    Submit a D-ID talk creation request.
    Returns the talk ID and initial status.
    """
    pid = presenter_id or os.getenv("DID_PRESENTER_ID", "amy-jcwCkr1j2")

    payload = {
        "script": {
            "type": "text",
            "input": script,
            "provider": {
                "type": "microsoft",
                "voice_id": "en-US-JennyNeural"
            }
        },
        "presenter_id": pid,
        "driver_id": "uM00QM8E5e",
        "config": {"fluent": True, "pad_audio": 0}
    }

    resp = requests.post(f"{DID_BASE}/talks", json=payload, headers=get_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {"talk_id": data.get("id"), "status": data.get("status", "created")}


def get_video_status(talk_id: str) -> dict:
    """Poll D-ID for video status. Returns status and result_url when done."""
    resp = requests.get(f"{DID_BASE}/talks/{talk_id}", headers=get_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {
        "talk_id": talk_id,
        "status": data.get("status"),
        "result_url": data.get("result_url"),
        "error": data.get("error")
    }


def wait_for_video(talk_id: str, max_wait: int = 180) -> dict:
    """Poll until video is done or timeout. Returns final status dict."""
    start = time.time()
    while time.time() - start < max_wait:
        status = get_video_status(talk_id)
        if status["status"] in ("done", "error"):
            return status
        time.sleep(5)
    return {"talk_id": talk_id, "status": "timeout", "result_url": None}


def list_presenters() -> list:
    resp = requests.get(f"{DID_BASE}/presenters", headers=get_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json().get("presenters", [])


def test_connection() -> dict:
    try:
        resp = requests.get(f"{DID_BASE}/credits", headers=get_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "remaining": data.get("remaining"), "total": data.get("total")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
