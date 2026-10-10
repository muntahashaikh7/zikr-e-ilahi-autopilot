#!/usr/bin/env python3
"""TikTok upload — STATUS: needs TikTok developer app approval (phase 2).

TikTok's Content Posting API requires:
  1. A TikTok developer account + registered app (developers.tiktok.com)
  2. App audit approval for the "Video Upload" / content.posting scope
  3. User authorization (Imran connects the @officialzikreilahi account once)

Until the app is approved, TikTok uploads stay manual (app share sheet)
or via the existing browser route.

When approved, the flow is:
  POST https://open.tiktokapis.com/v2/post/publish/video/init/
    -> upload video bytes to the returned URL
    -> POST .../publish/status/fetch/ until published
  Captions come from multiplatform.py ("tiktok" package).

This file documents the integration point; the workflow will call it
once TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / TIKTOK_ACCESS_TOKEN
are configured as repo secrets.
"""
import sys

print("TikTok direct upload not yet configured: needs TikTok developer app "
      "approval (see docstring). Skipping.", flush=True)
sys.exit(0)
