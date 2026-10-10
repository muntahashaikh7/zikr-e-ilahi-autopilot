# TikTok Auto-Upload — Phase 2 Setup Guide

## Kyun phase 2?
TikTok ka Content Posting API sirf **approved developer apps** ko milta hai.
Approval me 3-7 din lag sakte hain. Jab tak approval nahi milta, TikTok par
manual post hoga (ya browser route).

## Steps (Imran ke liye)

### 1. TikTok Developer account
- https://developers.tiktok.com par jao → Sign up (TikTok account se)
- **Create an app** → App name: `Zikr-e-Ilahi Autopilot`

### 2. Scopes add karo
App dashboard → **Add products** → **Content Posting API** select karo.
Required scopes:
- `video.upload`
- `video.publish`

### 3. App audit ke liye submit karo
- **App info**: description me likho — "Daily Islamic reminder videos
  (hadith with Urdu translation) auto-published to @officialzikreilahi"
- **Demo video / test**: 1-2 sample reels ka link do
- **Privacy policy URL**: zaroori hai (simple page: "we post our own videos")
- Submit → approval ka wait (3-7 din)

### 4. Approval ke baad — tokens
- App dashboard se **Client Key** + **Client Secret** lo
- OAuth flow se **Access Token** + **Refresh Token** generate karo
  (scope: video.upload + video.publish, user: @officialzikreilahi)
- GitHub repo secrets me add karo:
  - `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`
  - `TIKTOK_ACCESS_TOKEN`, `TIKTOK_REFRESH_TOKEN`

### 5. Workflow me enable karo
- `scripts/upload_tiktok.py` ko real implementation se replace karo
  (template tayyar hai — sirf tokens lagane hain)
- Workflow ke TikTok step me `exit 0` hatao

## Technical reference (jab implement karo)
```
POST https://open.tiktokapis.com/v2/post/publish/video/init/
  { "post_info": { "title": "<caption>", "privacy_level": "PUBLIC" },
    "source_info": { "source": "FILE_UPLOAD", "video_size": N, "chunk_size": N } }
→ upload bytes to upload_url
POST https://open.tiktokapis.com/v2/post/publish/status/fetch/
  { "publish_id": "..." }  → poll until SUCCESS
```
Caption: `multiplatform.py` ka "tiktok" package (already optimized).
