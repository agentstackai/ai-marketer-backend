import os
import requests

YT_BASE = "https://www.googleapis.com/youtube/v3"
YT_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_access_token = None

def get_access_token() -> str:
    """Get a fresh access token using the stored refresh token."""
    global _access_token
    resp = requests.post(TOKEN_URL, data={
        "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
        "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN"),
        "grant_type": "refresh_token"
    }, timeout=10)
    resp.raise_for_status()
    _access_token = resp.json().get("access_token")
    return _access_token


def upload_video(video_path: str, title: str, description: str, tags: list, category_id: str = "22") -> dict:
    """
    Upload a video file to YouTube.
    category_id 22 = People & Blogs, 28 = Science & Technology
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": {"privacyStatus": "public"}
    }

    params = {"part": "snippet,status", "uploadType": "multipart"}

    with open(video_path, "rb") as f:
        from requests_toolbelt.multipart.encoder import MultipartEncoder
        mp = MultipartEncoder(fields={
            "metadata": ("metadata.json", str(metadata), "application/json"),
            "file": (os.path.basename(video_path), f, "video/mp4")
        })
        upload_headers = {**headers, "Content-Type": mp.content_type}
        resp = requests.post(YT_UPLOAD, params=params, data=mp, headers=upload_headers, timeout=300)

    resp.raise_for_status()
    data = resp.json()
    video_id = data.get("id")
    return {"ok": True, "video_id": video_id, "url": f"https://youtu.be/{video_id}"}


def upload_video_from_url(video_url: str, title: str, description: str, tags: list) -> dict:
    """Download video from URL then upload to YouTube."""
    import tempfile
    import urllib.request

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        urllib.request.urlretrieve(video_url, tmp.name)
        return upload_video(tmp.name, title, description, tags)


def test_connection() -> dict:
    try:
        token = get_access_token()
        resp = requests.get(
            f"{YT_BASE}/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            return {"ok": True, "channel": items[0]["snippet"]["title"]}
        return {"ok": True, "channel": "unknown"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
