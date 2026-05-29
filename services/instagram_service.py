import os
import requests

GRAPH_BASE = "https://graph.facebook.com/v19.0"

def get_account_id():
    return os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")

def get_token():
    return os.getenv("INSTAGRAM_ACCESS_TOKEN")


def post_image(image_url: str, caption: str) -> dict:
    """
    Post an image to Instagram Business account.
    image_url must be a publicly accessible URL.
    """
    account_id = get_account_id()
    token = get_token()

    # Step 1: Create media container
    container_resp = requests.post(
        f"{GRAPH_BASE}/{account_id}/media",
        params={
            "image_url": image_url,
            "caption": caption,
            "access_token": token
        },
        timeout=15
    )
    container_resp.raise_for_status()
    container_id = container_resp.json().get("id")

    # Step 2: Publish the container
    publish_resp = requests.post(
        f"{GRAPH_BASE}/{account_id}/media_publish",
        params={"creation_id": container_id, "access_token": token},
        timeout=15
    )
    publish_resp.raise_for_status()
    media_id = publish_resp.json().get("id")

    return {"ok": True, "media_id": media_id, "container_id": container_id}


def post_reel(video_url: str, caption: str) -> dict:
    """Post a video reel to Instagram."""
    account_id = get_account_id()
    token = get_token()

    container_resp = requests.post(
        f"{GRAPH_BASE}/{account_id}/media",
        params={
            "video_url": video_url,
            "caption": caption,
            "media_type": "REELS",
            "share_to_feed": "true",
            "access_token": token
        },
        timeout=30
    )
    container_resp.raise_for_status()
    container_id = container_resp.json().get("id")

    publish_resp = requests.post(
        f"{GRAPH_BASE}/{account_id}/media_publish",
        params={"creation_id": container_id, "access_token": token},
        timeout=15
    )
    publish_resp.raise_for_status()
    return {"ok": True, "media_id": publish_resp.json().get("id")}


def test_connection() -> dict:
    try:
        account_id = get_account_id()
        token = get_token()
        resp = requests.get(
            f"{GRAPH_BASE}/{account_id}",
            params={"fields": "name,username,followers_count", "access_token": token},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "username": data.get("username"), "followers": data.get("followers_count")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
