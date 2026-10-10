# Zikr-e-Ilahi Autopilot — Zero-Token Autonomous Pipeline

**Ye asli automation hai: koi AI agent, koi token kharch nahi. Sirf code, jo roz khud chalta hai.**

## Kya karta hai (roz, automatic — 3 slots)

Har roz **07:00 / 13:00 / 20:00 PKT** par `Autopilot Slot` workflow chalta hai.
Har slot par:

1. **Video banata hai** — `scripts/build_daily_video.py`: 1 vertical reel (1080×1920)
   - Slot category: 07:00 → dhikr, 13:00 → akhlaq, 20:00 → dua
   - `hadith_bank.json` se rotation (113 entries — category cycle tak repeat nahi)
   - Voice: Arabic `ar-SA-HamedNeural`, Urdu `ur-PK-AsadNeural` (Imran-finalized)
   - D-treatment: isolated Arabic synthesis — talaffuz safe
   - Tarjuma split: Arabic quotes Arabic voice me, Urdu Urdu voice me
2. **SEO karta hai (HAR PLATFORM KE LIYE)** — `scripts/multiplatform.py`:
   - **YouTube**: hook-first title ≤100, keyword description, tags, hashtags
   - **Instagram**: keyword caption + 10 tier-balanced hashtags (L/M/N mix)
   - **Facebook**: caption + 3 hashtags + cross-links
   - **TikTok**: punchy caption + 4 hashtags (app approval pending — placeholder)
3. **Upload karta hai (HAR PLATFORM PAR, slot time par)**
   - **YouTube**: Data API, public immediately (slot time = publish time)
   - **Instagram**: Graph API reel (public release-asset URL se fetch)
   - **Facebook**: Graph API Page video
   - **TikTok**: developer app approval ke baad (`TIKTOK_SETUP.md`)

## Setup (ek dafa)

### 1. Repo — **PUBLIC** (zaroori: release assets IG/FB ke liye public URLs hote hain)
- `zikr-e-ilahi-autopilot` (public) — ye repo
- Content: `scripts/  hadith_bank.json  entry_scripts_auto.py  rotation_state.json  batch01/  assets/fonts/  .github/workflows/autopilot-slot.yml`

### 2. Secrets (Settings → Secrets and variables → Actions)
| Secret | Value |
|---|---|
| `YT_CLIENT_ID` | `~/.config/zikr-e-ilahi/youtube_oauth.json` → `client_id` |
| `YT_CLIENT_SECRET` | same file → `client_secret` |
| `YT_REFRESH_TOKEN` | same file → `refresh_token` |
| `IG_USER_ID` | Instagram Business account ID (Page se linked) |
| `IG_TOKEN` | Long-lived Graph API token |
| `FB_PAGE_ID` | Zikr-e-Ilahi Page ID |
| `FB_PAGE_TOKEN` | Long-lived Page token |

### 3. Workflow
- Actions tab → `Autopilot Slot` — schedule active: `0 2,8,15 * * *` (UTC)
- Test: Actions → Run workflow → optional slot override (dhikr/akhlaq/dua)

## Kaise kaam karta hai (technical)

```
GitHub Actions (3x daily, slot time) — ubuntu-latest, FREE
  │  1. rotation_state.json se slot category ki next entry
  │  2. build_daily_video.py → MP4 + seo-*.json + mp-*.json
  │  3. GitHub Release (public MP4 URL → IG/FB fetch)
  │  4. YouTube (resumable API, full SEO, public)
  │  5. Instagram (Graph API reel, optimized caption)
  │  6. Facebook (Graph API Page video)
  │  7. rotation_state.json commit back
  └──► Results workflow summary me (watch URLs, permalinks)
```

## Cost

- GitHub Actions: **free** (~15 min/day << 2000 min/month)
- YouTube Data API: **free** (3 uploads/day ≈ 4800/10000 quota units)
- Meta Graph API: **free**
- AI tokens: **zero**
