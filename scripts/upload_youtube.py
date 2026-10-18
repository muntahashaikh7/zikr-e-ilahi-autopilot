#!/usr/bin/env python3
"""Upload a reel to YouTube with full SEO, published immediately (public).

The slot workflow runs AT the publish slot (07:00/13:00/20:00 PKT), so no
publishAt scheduling is needed — the video goes public on upload.

Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Usage: upload_youtube.py <mp4_path> <seo_json_path>
Prints: https://www.youtube.com/watch?v=<id>
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error


def refresh_token(cid, sec, ref):
    body = urllib.parse.urlencode({
        "client_id": cid, "client_secret": sec,
        "refresh_token": ref, "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        # fail loud with Google's real error body (invalid_grant / invalid_client / ...)
        print("TOKEN_REFRESH_FAILED:", e.code, e.read().decode()[:500], file=sys.stderr)
        raise


def resumable_upload(token, mp4_path, seo):
    meta = {
        "snippet": {
            "title": seo["title"][:100],
            "description": seo["description"],
            "tags": seo.get("tags", [])[:15],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    body = json.dumps(meta).encode()
    size = os.path.getsize(mp4_path)
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status",
        data=body, method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            session = r.headers["Location"]
    except urllib.error.HTTPError as e:
        print("UPLOAD_SESSION_FAILED:", e.code, e.read().decode()[:500], file=sys.stderr)
        raise
    req = urllib.request.Request(
        session, method="PUT",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Length": str(size),
            "Content-Type": "video/mp4",
        })
    with open(mp4_path, "rb") as f:
        req.data = f.read()
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["id"]


def main():
    mp4_path, seo_path = sys.argv[1], sys.argv[2]
    cid = os.environ["YT_CLIENT_ID"]
    sec = os.environ["YT_CLIENT_SECRET"]
    ref = os.environ["YT_REFRESH_TOKEN"]
    seo = json.load(open(seo_path, encoding="utf-8"))["seo"]
    token = refresh_token(cid, sec, ref)
    vid = resumable_upload(token, mp4_path, seo)
    print(f"https://www.youtube.com/watch?v={vid}")


if __name__ == "__main__":
    main()
