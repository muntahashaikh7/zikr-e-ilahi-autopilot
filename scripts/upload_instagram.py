#!/usr/bin/env python3
"""Upload a reel to Instagram via Graph API (no browser, no tokens burned).

Flow: create media container (REELS) -> wait for processing -> publish.
Needs: IG_USER_ID + long-lived access token (env: IG_USER_ID, IG_TOKEN).
The video_url must be PUBLIC (GitHub release asset on a public repo works).

Usage: python3 upload_instagram.py <public_video_url> <caption>
Prints the published media ID / permalink.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://graph.facebook.com/v21.0"


def api_post(path, params, timeout=120):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API + path, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def api_get(path, params, timeout=60):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(API + path + "?" + q, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    video_url, caption = sys.argv[1], sys.argv[2]
    ig_id, token = os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]

    # 1. create container
    print("Creating IG media container...", flush=True)
    r = api_post(f"/{ig_id}/media", {
        "access_token": token,
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
    })
    creation_id = r.get("id")
    if not creation_id:
        print("CONTAINER FAILED:", json.dumps(r)[:500])
        sys.exit(1)
    print("container:", creation_id)

    # 2. wait until ready
    for _ in range(30):
        s = api_get(f"/{creation_id}", {
            "access_token": token, "fields": "status_code"})
        code = s.get("status_code")
        print("status:", code, flush=True)
        if code == "FINISHED":
            break
        if code == "ERROR":
            print("PROCESSING ERROR:", json.dumps(s)[:500])
            sys.exit(1)
        time.sleep(10)
    else:
        print("TIMEOUT waiting for processing")
        sys.exit(1)

    # 3. publish
    r = api_post(f"/{ig_id}/media_publish", {
        "access_token": token, "creation_id": creation_id})
    media_id = r.get("id")
    print("PUBLISHED:", media_id)
    if media_id:
        p = api_get(f"/{media_id}", {
            "access_token": token, "fields": "permalink"})
        print("PERMALINK:", p.get("permalink"))


if __name__ == "__main__":
    main()
