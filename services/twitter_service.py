import os
import requests
from requests_oauthlib import OAuth1

TWITTER_BASE = "https://api.twitter.com/2"


def get_auth():
    return OAuth1(
        os.getenv("TWITTER_API_KEY"),
        os.getenv("TWITTER_API_SECRET"),
        os.getenv("TWITTER_ACCESS_TOKEN"),
        os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
    )


def post_tweet(text: str) -> dict:
    """Post a tweet via Twitter API v2."""
    resp = requests.post(
        f"{TWITTER_BASE}/tweets",
        json={"text": text},
        auth=get_auth(),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    tweet_id = data.get("id", "")
    return {
        "ok": True,
        "tweet_id": tweet_id,
        "url": f"https://x.com/i/web/status/{tweet_id}",
    }


def post_thread(tweets: list[str]) -> dict:
    """Post a thread of tweets. Each item is a tweet text (max 280 chars)."""
    auth = get_auth()
    results = []
    reply_to_id = None

    for text in tweets:
        payload: dict = {"text": text}
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        resp = requests.post(f"{TWITTER_BASE}/tweets", json=payload, auth=auth, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        tweet_id = data.get("id", "")
        reply_to_id = tweet_id
        results.append({"tweet_id": tweet_id, "text": text})

    return {"ok": True, "thread": results, "count": len(results)}


def test_connection() -> dict:
    try:
        resp = requests.get(
            f"{TWITTER_BASE}/users/me",
            auth=get_auth(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {"ok": True, "username": data.get("username"), "name": data.get("name")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
