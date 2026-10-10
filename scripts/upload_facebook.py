#!/usr/bin/env python3
"""Upload a video to the Zikr-e-Ilahi Facebook Page via Graph API.

Prefers file_url (Facebook fetches the MP4 from a public URL itself);
falls back to chunked direct upload when no public URL is available.
Needs env: FB_PAGE_ID, FB_PAGE_TOKEN (long-lived Page token).

Usage:
  python3 upload_facebook.py --file-url <public_mp4_url> --title T --description D
  python3 upload_facebook.py --file-path <local.mp4> --title T --description D
Prints the Facebook video/post ID.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://graph.facebook.com/v21.0"
CHUNK = 32 * 1024 * 1024


def api_post(path, params, timeout=120):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()[:500]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file-url")
    ap.add_argument("--file-path")
    ap.add_argument("--title", default="")
    ap.add_argument("--description", default="")
    a = ap.parse_args()
    page_id = os.environ["FB_PAGE_ID"]
    token = os.environ["FB_PAGE_TOKEN"]

    if a.file_url:
        print("Trying file_url upload (FB fetches from URL)...", flush=True)
        r = api_post(f"/{page_id}/videos", {
            "access_token": token, "file_url": a.file_url,
            "title": a.title, "description": a.description})
        if r.get("id") and not r.get("_http_error"):
            print("PUBLISHED:", r["id"])
            return
        print("file_url failed:", json.dumps(r)[:400], "— falling back to chunked")

    # chunked direct upload
    size = os.path.getsize(a.file_path)
    print(f"Chunked upload: {size} bytes", flush=True)
    # start session
    r = api_post(f"/{page_id}/videos", {
        "access_token": token, "upload_phase": "start",
        "file_size": str(size)})
    session = r.get("upload_session_id") or r.get("id")
    if not session or r.get("_http_error"):
        print("START FAILED:", json.dumps(r)[:500]); sys.exit(1)
    # transfer chunks
    start = 0
    with open(a.file_path, "rb") as f:
        while start < size:
            chunk = f.read(CHUNK)
            end = start + len(chunk)
            boundary = "----fbchunk"
            body = b""
            for k, v in {"access_token": token, "upload_phase": "transfer",
                         "upload_session_id": session,
                         "start_offset": str(start)}.items():
                body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                         f"name=\"{k}\"\r\n\r\n{v}\r\n").encode()
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"video_file\"; "
                     f"filename=\"chunk.mp4\"\r\nContent-Type: video/mp4\r\n\r\n").encode()
            body += chunk + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                API + f"/{page_id}/videos", data=body, method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            try:
                with urllib.request.urlopen(req, timeout=600) as resp:
                    rr = json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                print("CHUNK FAILED:", e.code, e.read().decode()[:300]); sys.exit(1)
            start = int(rr.get("start_offset", end))
            print(f"  {start}/{size}", flush=True)
    # finish
    r = api_post(f"/{page_id}/videos", {
        "access_token": token, "upload_phase": "finish",
        "upload_session_id": session, "title": a.title,
        "description": a.description})
    vid = r.get("id") or r.get("video_id")
    print("PUBLISHED:", vid, json.dumps(r)[:200])


if __name__ == "__main__":
    main()
