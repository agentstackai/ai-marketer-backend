import os
import requests

GRAPH_BASE = "https://graph.facebook.com/v19.0"


def get_page_id():
    return os.getenv("FACEBOOK_PAGE_ID")


def get_token():
    return os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")


def post_text(message: str, link: str = None) -> dict:
    """Post a text update (with optional link) to a Facebook Page."""
    page_id = get_page_id()
    params = {
        "message": message,
        "access_token": get_token(),
    }
    if link:
        params["link"] = link

    resp = requests.post(
        f"{GRAPH_BASE}/{page_id}/feed",
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    post_id = resp.json().get("id", "")
    return {
        "ok": True,
        "post_id": post_id,
        "url": f"https://www.facebook.com/{post_id.replace('_', '/posts/')}",
    }


def post_image(image_url: str, caption: str) -> dict:
    """Post an image with caption to a Facebook Page."""
    page_id = get_page_id()
    resp = requests.post(
        f"{GRAPH_BASE}/{page_id}/photos",
        params={
            "url": image_url,
            "caption": caption,
            "access_token": get_token(),
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    post_id = data.get("post_id") or data.get("id", "")
    return {"ok": True, "post_id": post_id}


def test_connection() -> dict:
    try:
        page_id = get_page_id()
        resp = requests.get(
            f"{GRAPH_BASE}/{page_id}",
            params={
                "fields": "name,fan_count,followers_count",
                "access_token": get_token(),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "page": data.get("name"),
            "fans": data.get("fan_count"),
            "followers": data.get("followers_count"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
