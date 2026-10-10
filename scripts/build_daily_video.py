#!/usr/bin/env python3
"""
End-to-end daily autopilot video builder (Imran's complete package, 2026-10-09).

Input:  one hadith_bank.json entry id, e.g.  python3 build_daily_video.py dhikr-004
Output: ~/workspace/your_files/autopilot-daily-NN.mp4  (full regular file)
        ~/workspace/your_files/seo-<entry_id>.json   (SEO package)

Pipeline per video:
  1. Voiceover — v3 MALE multilingual recipe (FINALIZED by Imran):
     full Arabic salam (ar-SA-HamedNeural, -8%, own unit) -> Urdu hook
     (ur-PK-AsadNeural) -> voweled Arabic matn (ar-SA-HamedNeural, -5%)
     -> Urdu tarjuma (ur-PK-AsadNeural) -> Urdu CTA (ur-PK-AsadNeural).
     Separate synthesis + ffmpeg concat (SSML voice-switching is a dead end).
  2. Visuals — 4 AI-generated Islamic backgrounds, slow Ken Burns zoom,
     ZERO animate beings/faces (all pre-verified).
  3. Text overlays — Arabic matn voweled in gold large centered + Urdu tarjuma
     + hadith reference, timed to voiceover. 9:16 (1080x1920).
  4. ffmpeg assembly with fades; 5. SEO package via seo_generator.py.

Guardrails (ISLAMIC_STYLE_GUIDE.md): no animate beings, Arabic never
mispronounced (ar-SA voice + whisper verification), references verified,
no instrumental music, no unsourced claims.
"""
import os
import sys
import json
import subprocess
import tempfile
import shutil
import logging

BASE = os.path.dirname(os.path.abspath(__file__))
FORK = os.path.dirname(BASE)
sys.path.insert(0, BASE)

from edge_tts_proxy_client import synthesize
from multilingual_voiceover import (
    VOICE_AR_MALE, VOICE_UR_MALE, FULL_SALAM_AR,
    mp3_to_wav, make_silence_wav, SAMPLE_RATE, PAUSE_MS,
)
from seo_generator import generate_seo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import arabic_reshaper
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"
W, H, FPS = 1080, 1920, 30
GOLD = (212, 175, 55)
WHITE = (255, 255, 255)
BATCH_DIR = os.path.join(FORK, os.environ.get("AUTOPILOT_BATCH", "batch01"))
YOUR_FILES = os.path.expanduser("~/workspace/your_files")


def _run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed: {r.stderr[-600:]}")
    return r


def probe(path):
    out = _run(["ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "csv=p=0", path], "ffprobe")
    return float(out.stdout.strip())


def clean_arabic(t):
    """Strip invisible control chars that confuse TTS/rendering."""
    return "".join(c for c in t if c not in ("\u200e", "\u200f", "\u202a",
                                            "\u202b", "\u202c", "\u202d", "\u202e"))


def wrap_urdu(text, max_chars=26):
    """Simple word-wrap for on-screen Urdu lines (no hyphen-minus anywhere)."""
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        if len(cur) + len(w_) + 1 <= max_chars:
            cur = (cur + " " + w_).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def render_text(lines, out_path):
    """lines: list of (text, size, color). Transparent PNG, auto-shrink to fit."""
    reshaped = [arabic_reshaper.reshape(t) for t, _, _ in lines]
    fonts = [ImageFont.truetype(FONT, s, layout_engine=ImageFont.Layout.RAQM)
             for _, s, _ in lines]
    while True:
        tmp = Image.new("RGBA", (10, 10))
        d = ImageDraw.Draw(tmp)
        widths = []
        for t, f in zip(reshaped, fonts):
            bb = d.textbbox((0, 0), t, font=f, stroke_width=2)
            widths.append(bb[2] - bb[0])
        if max(widths) <= 940 or min(f.size for f in fonts) < 30:
            break
        fonts = [ImageFont.truetype(FONT, int(f.size * 0.92),
                                    layout_engine=ImageFont.Layout.RAQM)
                 for f in fonts]
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    heights, total = [], 0
    for t, f in zip(reshaped, fonts):
        bb = d.textbbox((0, 0), t, font=f, stroke_width=2)
        heights.append(bb[3] - bb[1] + 36)
        total += heights[-1]
    img = Image.new("RGBA", (W, total), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 0
    for (t, _, col), f, hh in zip(lines, fonts, heights):
        bb = d.textbbox((0, 0), t, font=f, stroke_width=2)
        x = (W - (bb[2] - bb[0])) // 2 - bb[0]
        d.text((x, y - bb[1] + 10), t, font=f, fill=col + (255,),
               stroke_width=2, stroke_fill=(0, 0, 0, 200))
        y += hh
    img.save(out_path)
    return out_path


def build_scene(bg, text_png, dur, out_path):
    frames = int(dur * FPS)
    fc = (
        "[0:v]scale=1152:2048,"
        f"zoompan=z='min(1+0.0009*on\\,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={W}x{H}:fps={FPS}[bg];"
        "[1:v]format=rgba,"
        f"fade=t=in:st=0:d=0.6:alpha=1,fade=t=out:st={dur-0.6:.2f}:d=0.6:alpha=1[txt];"
        "[bg][txt]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    )
    _run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", bg,
          "-loop", "1", "-framerate", str(FPS), "-i", text_png,
          "-filter_complex", fc, "-map", "[v]", "-t", f"{dur:.2f}",
          "-c:v", "libx264", "-preset", "medium", "-crf", "20",
          out_path], f"scene {out_path}")
    logger.info(f"scene OK: {out_path} ({dur:.2f}s)")


def synth_segments(segments, workdir):
    """Synthesize each segment separately; return list of (mp3_path, duration).

    Reuse rule (2026-10-10, Edge-TTS Colab fallback): a valid existing
    seg_NN.mp3 is NOT re-synthesized — lets the VM resume a build whose
    voiceover was synthesized elsewhere (e.g. Google Colab) from identical
    segment text/voice/rate. Fresh tempdirs never hit this path.
    """
    out = []
    for i, seg in enumerate(segments):
        mp3_path = os.path.join(workdir, f"seg_{i:02d}.mp3")
        reused = False
        if os.path.isfile(mp3_path) and not os.path.islink(mp3_path):
            try:
                if probe(mp3_path) > 0:
                    logger.info(f"TTS {i+1}/{len(segments)} REUSED {mp3_path}")
                    out.append((mp3_path, probe(mp3_path)))
                    reused = True
            except Exception:
                pass
        if reused:
            continue
        logger.info(f"TTS {i+1}/{len(segments)} [{seg['voice']} @ {seg.get('rate', '+0%')}]: "
                    f"{seg['text'][:45]}...")
        synthesize(seg["text"], seg["voice"], mp3_path, rate=seg.get("rate", "+0%"))
        out.append((mp3_path, probe(mp3_path)))
    return out


def concat_voiceover(seg_files, out_mp3, pause_ms=PAUSE_MS):
    tmpdir = tempfile.mkdtemp(prefix="vo_concat_")
    try:
        wavs = []
        for i, (mp3_path, _d) in enumerate(seg_files):
            wp = os.path.join(tmpdir, f"s{i:02d}.wav")
            mp3_to_wav(mp3_path, wp)
            wavs.append(wp)
            if i < len(seg_files) - 1:
                sp = os.path.join(tmpdir, f"p{i:02d}.wav")
                make_silence_wav(pause_ms, sp)
                wavs.append(sp)
        lst = os.path.join(tmpdir, "c.txt")
        with open(lst, "w") as f:
            for w_ in wavs:
                f.write(f"file '{w_}'\n")
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
              "-i", lst, "-c:a", "libmp3lame", "-b:a", "48k", out_mp3],
             "voiceover concat")
        return out_mp3
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ----------------------------------------------------------------------------
# Per-entry video scripts. hook_voice/tarjuma_voice/cta_voice are SPOKEN
# (multilingual rule: Urdu in ur-PK voice). display_* are ON-SCREEN text.
# ----------------------------------------------------------------------------
ENTRY_SCRIPTS = {
    "dhikr-004": {
        "hook_voice": "کیا آپ جانتے ہیں؟ دو چھوٹے کلمے، جو میزان میں سب سے بھاری ہیں؟",
        "hook_text": [("کیا آپ جانتے ہیں؟", 76, WHITE),
                      ("دو چھوٹے کلمے،", 68, WHITE),
                      ("میزان میں سب سے بھاری؟", 68, GOLD)],
        "display_arabic": [("سُبْحَانَ اللَّهِ وَبِحَمْدِهِ", 96, GOLD),
                           ("سُبْحَانَ اللَّهِ الْعَظِيمِ", 88, GOLD)],
        # D treatment (2026-10-09, Imran-approved): matn synthesized as
        # ISOLATED units + 400ms pauses — fixes swallowed ح in وَبِحَمْدِهِ
        # ("وبعده" in connected speech). Correct Bukhari 6406 order.
        "matn_units": [
            "كَلِمَتَانِ خَفِيفَتَانِ عَلَى اللِّسَانِ، ثَقِيلَتَانِ فِي الْمِيزَانِ،",
            "حَبِيبَتَانِ إِلَى الرَّحْمَنِ،",
            "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ، سُبْحَانَ اللَّهِ الْعَظِيمِ",
        ],
        # TARJUMA SPLIT (2026-10-10): the tarjuma QUOTES the Arabic phrases.
        # They must be spoken by the ARABIC voice (full makharij), not the
        # Urdu voice — the Urdu voice was mispronouncing وَبِحَمْدِهِ, which
        # is exactly the "same mistake" Imran heard in the rebuilt video.
        # (Standing rule: har zuban apne ASAL talaffuz mein.)
        "tarjuma_voice_urdu": "دو کلمے زبان پر ہلکے، میزان میں بھاری، رحمٰن کو محبوب ہیں:",
        "tarjuma_voice_arabic": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ، سُبْحَانَ اللَّهِ الْعَظِيمِ",
        "cta_voice": ("آج ہی سے ان کلموں کو اپنا معمول بنائیے، اور اس ویڈیو کو "
                      "شیئر کر کے صدقۂ جاریہ میں حصہ لیجیے۔"),
        "cta_text": [("آج ہی سے معمول بنائیے", 68, WHITE),
                     ("شیئر کریں، صدقۂ جاریہ", 64, GOLD)],
        "bgs": ["daily01-bg1-mosque-sunrise", "daily01-bg2-geometric-teal",
                "daily01-bg3-crescent-desert", "daily01-bg4-mihrab-glow"],
    },
    "akhlaq-001": {
        "hook_voice": "کیا آپ جانتے ہیں؟ کامل مومن کون ہے؟",
        "hook_text": [("کیا آپ جانتے ہیں؟", 76, WHITE),
                      ("کامل مومن کون ہے؟", 72, GOLD)],
        "display_arabic": [("لَا يُؤْمِنُ أَحَدُكُمْ حَتَّى", 72, GOLD),
                           ("يُحِبَّ لِأَخِيهِ مَا يُحِبُّ لِنَفْسِهِ", 64, GOLD)],
        "cta_voice": ("آج ہی سے اس حدیث پر عمل کیجیے، اور اس ویڈیو کو شیئر کر کے "
                      "صدقۂ جاریہ میں حصہ لیجیے۔"),
        "cta_text": [("عمل کیجیے، اجر پائیے", 68, WHITE),
                     ("شیئر کریں، صدقۂ جاریہ", 64, GOLD)],
        "bgs": ["daily02-bg1-courtyard-dusk", "daily02-bg2-geometric-blue",
                "daily02-bg3-mountains-sunrise", "daily02-bg4-archway-light"],
    },
    "dua-001": {
        "hook_voice": "کیا آپ جانتے ہیں؟ دعا کی اصل حقیقت کیا ہے؟",
        "hook_text": [("کیا آپ جانتے ہیں؟", 76, WHITE),
                      ("دعا کی اصل حقیقت؟", 72, GOLD)],
        "display_arabic": [("الدُّعَاءُ هُوَ الْعِبَادَةُ", 96, GOLD)],
        "cta_voice": ("آج ہی سے دعا کو معمول بنائیے، اور اس ویڈیو کو شیئر کر کے "
                      "صدقۂ جاریہ میں حصہ لیجیے۔"),
        "cta_text": [("دعا مانگیے، قبولیت پائیے", 68, WHITE),
                     ("شیئر کریں، صدقۂ جاریہ", 64, GOLD)],
        "bgs": ["daily03-bg1-night-domes", "daily03-bg2-geometric-purple",
                "daily03-bg3-sea-dawn", "daily03-bg4-lantern"],
    },
    # --- batch02 (trial day 2, 2026-10-11) — added 2026-10-10 ---
    "dhikr-001": {
        "hook_voice": "کیا آپ جانتے ہیں؟ سو مرتبہ کا ایک ذکر، جو سمندر کی جھاگ جتنے گناہ مٹا دے؟",
        "hook_text": [("کیا آپ جانتے ہیں؟", 76, WHITE),
                      ("سو مرتبہ کا ایک ذکر،", 72, WHITE),
                      ("سمندر جتنے گناہ مٹا دے؟", 68, GOLD)],
        "display_arabic": [("مَنْ قَالَ سُبْحَانَ اللَّهِ وَبِحَمْدِهِ", 68, GOLD),
                           ("فِي يَوْمٍ مِائَةَ مَرَّةٍ حُطَّتْ خَطَايَاهُ", 56, GOLD),
                           ("وَإِنْ كَانَتْ مِثْلَ زَبَدِ الْبَحْرِ", 64, GOLD)],
        # D treatment: isolated units + 400ms pauses — وَبِحَمْدِهِ must not
        # be swallowed ("وبعده"). Correct Bukhari 6405 wording.
        "matn_units": [
            "مَنْ قَالَ سُبْحَانَ اللَّهِ وَبِحَمْدِهِ،",
            "فِي يَوْمٍ مِائَةَ مَرَّةٍ،",
            "حُطَّتْ خَطَايَاهُ،",
            "وَإِنْ كَانَتْ مِثْلَ زَبَدِ الْبَحْرِ",
        ],
        # TARJUMA SPLIT: tarjuma quotes the Arabic dhikr — Urdu part in Urdu
        # voice, the quote in the ARABIC voice (full makharij, never the
        # Urdu voice). Standing rule: har zuban apne ASAL talaffuz mein.
        "tarjuma_voice_urdu": ("جو شخص دن میں سو مرتبہ یہ ذکر کہے، اس کے گناہ "
                               "معاف کر دیے جاتے ہیں، چاہے سمندر کی جھاگ کے برابر ہوں:"),
        "tarjuma_voice_arabic": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ",
        "cta_voice": ("آج ہی سے اس ذکر کو اپنا معمول بنائیے، اور اس ویڈیو کو "
                      "شیئر کر کے صدقۂ جاریہ میں حصہ لیجیے۔"),
        "cta_text": [("آج ہی سے معمول بنائیے", 68, WHITE),
                     ("شیئر کریں، صدقۂ جاریہ", 64, GOLD)],
        "bgs": ["daily03-bg1-night-domes", "daily03-bg2-geometric-purple",
                "daily03-bg3-sea-dawn", "daily03-bg4-lantern"],
    },
    "akhlaq-002": {
        "hook_voice": "کیا آپ جانتے ہیں؟ کامل مومن کی تین نشانیاں کون سی ہیں؟",
        "hook_text": [("کیا آپ جانتے ہیں؟", 76, WHITE),
                      ("کامل مومن کی", 72, WHITE),
                      ("تین نشانیاں کون سی ہیں؟", 68, GOLD)],
        "display_arabic": [("مَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الْآخِرِ", 60, GOLD),
                           ("فَلَا يُؤْذِ جَارَهُ، فَلْيُكْرِمْ ضَيْفَهُ،", 56, GOLD),
                           ("فَلْيَقُلْ خَيْرًا أَوْ لِيَصْمُتْ", 64, GOLD)],
        # Isolated units + 400ms pauses; the repeated ل of اللہ keeps its
        # fatha in every occurrence (standing fix).
        "matn_units": [
            "مَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الْآخِرِ فَلَا يُؤْذِ جَارَهُ،",
            "وَمَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الْآخِرِ فَلْيُكْرِمْ ضَيْفَهُ،",
            "وَمَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الْآخِرِ فَلْيَقُلْ خَيْرًا أَوْ لِيَصْمُتْ",
        ],
        "cta_voice": ("آج ہی سے اس حدیث پر عمل کیجیے، اور اس ویڈیو کو شیئر کر کے "
                      "صدقۂ جاریہ میں حصہ لیجیے۔"),
        "cta_text": [("عمل کیجیے، اجر پائیے", 68, WHITE),
                     ("شیئر کریں، صدقۂ جاریہ", 64, GOLD)],
        "bgs": ["daily01-bg1-mosque-sunrise", "daily01-bg2-geometric-teal",
                "daily01-bg3-crescent-desert", "daily01-bg4-mihrab-glow"],
    },
    "dua-003": {
        "hook_voice": "کیا آپ جانتے ہیں؟ بھائی کے لیے دعا — فرشتہ کہتا ہے آمین!",
        "hook_text": [("کیا آپ جانتے ہیں؟", 76, WHITE),
                      ("بھائی کے لیے دعا،", 72, WHITE),
                      ("فرشتہ کہتا ہے: آمین!", 68, GOLD)],
        "display_arabic": [("دَعْوَةُ الْمَرْءِ الْمُسْلِمِ لِأَخِيهِ", 60, GOLD),
                           ("بِظَهْرِ الْغَيْبِ مُسْتَجَابَةٌ", 68, GOLD),
                           ("عِنْدَ رَأْسِهِ مَلَكٌ مُوَكَّلٌ", 60, GOLD),
                           ("قَالَ: آمِينَ، وَلَكَ بِمِثْلٍ", 64, GOLD)],
        # Isolated units + 400ms pauses (standing D treatment).
        "matn_units": [
            "دَعْوَةُ الْمَرْءِ الْمُسْلِمِ لِأَخِيهِ بِظَهْرِ الْغَيْبِ مُسْتَجَابَةٌ،",
            "عِنْدَ رَأْسِهِ مَلَكٌ مُوَكَّلٌ،",
            "كُلَّمَا دَعَا لِأَخِيهِ بِخَيْرٍ قَالَ الْمَلَكُ الْمُوَكَّلُ بِهِ: آمِينَ، وَلَكَ بِمِثْلٍ",
        ],
        "cta_voice": ("آج ہی سے اپنے بھائیوں کے لیے دعا کیجیے، اور اس ویڈیو کو "
                      "شیئر کر کے صدقۂ جاریہ میں حصہ لیجیے۔"),
        "cta_text": [("دعا کیجیے، قبولیت پائیے", 68, WHITE),
                     ("شیئر کریں، صدقۂ جاریہ", 64, GOLD)],
        "bgs": ["daily02-bg1-courtyard-dusk", "daily02-bg2-geometric-blue",
                "daily02-bg3-mountains-sunrise", "daily02-bg4-archway-light"],
    },
}


# ----------------------------------------------------------------------------
# Urdu-script tarjumas (the bank's urdu_tarjuma is ROMAN Urdu, which the
# Noto Naskh Arabic font cannot render (tofu boxes) and the ur-PK voice
# mispronounces — verified 2026-10-09 on autopilot-daily-01 frame 3).
# These overrides are used for BOTH voiceover and on-screen text.
# ----------------------------------------------------------------------------
TARJUMA_URDU = {
    "dhikr-004": ("دو کلمے زبان پر ہلکے، میزان میں بھاری، رحمٰن کو محبوب ہیں: "
                  "سبحان اللہ وبحمدہ، سبحان اللہ العظیم۔"),
    "akhlaq-001": ("تم میں سے کوئی مومن نہیں ہو سکتا جب تک اپنے بھائی کے لیے "
                   "وہی پسند نہ کرے جو اپنے لیے پسند کرتا ہے۔"),
    "dua-001": "دعا ہی عبادت ہے۔",
    # --- batch02 (trial day 2) — full, accurate Urdu-script tarjumas ---
    # (bank's urdu_tarjuma is Roman; akhlaq-002/dua-003 are also shortened)
    "dhikr-001": ("جو شخص دن میں سو مرتبہ سبحان اللہ وبحمدہ کہے، اس کے گناہ "
                  "معاف کر دیے جاتے ہیں، چاہے سمندر کی جھاگ کے برابر ہوں۔"),
    "akhlaq-002": ("جو اللہ اور قیامت کے دن پر ایمان رکھتا ہے، وہ اپنے پڑوسی کو "
                   "تکلیف نہ دے؛ جو اللہ اور قیامت کے دن پر ایمان رکھتا ہے، وہ "
                   "اپنے مہمان کی عزت کرے؛ اور جو اللہ اور قیامت کے دن پر ایمان "
                   "رکھتا ہے، وہ بھلائی کی بات کہے یا خاموش رہے۔"),
    "dua-003": ("مسلمان کی اپنے بھائی کے لیے پیٹھ پیچھے کی ہوئی دعا قبول ہوتی ہے؛ "
                "اس کے سر کے پاس ایک فرشتہ مقرر ہے — جب وہ اپنے بھائی کے لیے "
                "بھلائی کی دعا کرتا ہے، تو وہ فرشتہ کہتا ہے: آمین، اور تیرے لیے "
                "بھی اسی جیسا ہو۔"),
}


# --- Auto-generated entry scripts (2026-10-10, gen_entry_scripts.py) ---
# Covers all remaining bank entries so the pipeline runs token-free.
# Human-reviewed patterns; TARJUMA_AUTO via roman_urdu.py (all 679 bank
# words mapped). Merge after the hand-crafted entries above.
try:
    _auto_path = os.path.join(FORK, "entry_scripts_auto.py")
    _auto_ns = {"WHITE": WHITE, "GOLD": GOLD}
    with open(_auto_path, encoding="utf-8") as _f:
        exec(compile(_f.read(), _auto_path, "exec"), _auto_ns)
    ENTRY_SCRIPTS.update(_auto_ns["ENTRY_SCRIPTS_AUTO"])
    TARJUMA_URDU.update(_auto_ns["TARJUMA_AUTO"])
    logger.info(f"Loaded {len(_auto_ns['ENTRY_SCRIPTS_AUTO'])} auto entry scripts")
except Exception as _e:
    logger.warning(f"Could not load entry_scripts_auto.py: {_e}")


def is_urdu_script(t):
    """Heuristic: true if the text is mostly Arabic-script (not Roman)."""
    arabic = sum(1 for c in t if "\u0600" <= c <= "\u06ff")
    latin = sum(1 for c in t if c.isascii() and c.isalpha())
    return arabic >= latin


def load_entry(entry_id):
    with open(os.path.join(FORK, "hadith_bank.json"), encoding="utf-8") as f:
        bank = json.load(f)
    for e in bank["entries"]:
        if e["id"] == entry_id:
            return e
    raise ValueError(f"entry {entry_id} not found in hadith_bank.json")


def find_bg(stem):
    for f in os.listdir(BATCH_DIR):
        if f.startswith("media-generation-" + stem + "-") and f.endswith(".webp"):
            return os.path.join(BATCH_DIR, f)
    raise FileNotFoundError(f"background {stem} not found in {BATCH_DIR}")


def ref_line(entry):
    book = {"bukhari": "صحیح بخاری", "muslim": "صحیح مسلم",
            "tirmidhi": "سنن ترمذی", "abudawud": "سنن ابو داؤد"}.get(
                entry["book"], entry["book"])
    return f"{book} {entry['number']}"


def build_segments(entry_id):
    """Voiceover segment list for an entry (v3 MALE recipe, FINALIZED by Imran).

    Extracted 2026-10-10 (pure move — same logic as before) so the exact
    segment list can be dumped for off-VM synthesis (Colab fallback).
    Returns (segments, n_matn, n_tarjuma, tarjuma_display).
    """
    entry = load_entry(entry_id)
    cfg = ENTRY_SCRIPTS[entry_id]
    matn = clean_arabic(entry["arabic"])
    tarjuma = TARJUMA_URDU.get(entry_id)
    if tarjuma is None:
        tarjuma = entry["urdu_tarjuma"].strip()
        if not is_urdu_script(tarjuma):
            logger.warning(f"tarjuma for {entry_id} looks like Roman Urdu — "
                           f"add a Urdu-script override to TARJUMA_URDU!")

    # --- 1. Voiceover segments (v3 MALE recipe, finalized by Imran) ---
    segments = [
        {"text": FULL_SALAM_AR, "voice": VOICE_AR_MALE, "rate": "-8%"},
        {"text": cfg["hook_voice"], "voice": VOICE_UR_MALE, "rate": "+0%"},
    ]
    matn_units = cfg.get("matn_units")
    if matn_units:
        # D treatment: each Arabic unit synthesized in isolation
        # (prevents swallowed ح/ع in consonant clusters).
        for u in matn_units:
            segments.append({"text": clean_arabic(u), "voice": VOICE_AR_MALE,
                             "rate": "-5%"})
        n_matn = len(matn_units)
    else:
        segments.append({"text": matn, "voice": VOICE_AR_MALE, "rate": "-5%"})
        n_matn = 1
    segments += [
        {"text": cfg["cta_voice"], "voice": VOICE_UR_MALE, "rate": "+0%"},
    ]
    # Tarjuma split: entries whose tarjuma quotes Arabic get TWO segments —
    # Urdu part in the Urdu voice, Arabic quotes in the Arabic voice
    # (tarjuma_voice_arabic). Without it, tarjuma stays one Urdu segment.
    tarjuma_ar = cfg.get("tarjuma_voice_arabic")
    if tarjuma_ar:
        segments.insert(-1, {"text": cfg.get("tarjuma_voice_urdu", tarjuma),
                             "voice": VOICE_UR_MALE, "rate": "+0%"})
        segments.insert(-1, {"text": clean_arabic(tarjuma_ar),
                             "voice": VOICE_AR_MALE, "rate": "-5%"})
        n_tarjuma = 2
    else:
        segments.insert(-1, {"text": tarjuma, "voice": VOICE_UR_MALE,
                             "rate": "+0%"})
        n_tarjuma = 1
    return segments, n_matn, n_tarjuma, tarjuma


def build_video(entry_id, out_mp4, workdir=None):
    entry = load_entry(entry_id)
    cfg = ENTRY_SCRIPTS[entry_id]
    workdir = workdir or tempfile.mkdtemp(prefix=f"daily_{entry_id}_")
    os.makedirs(workdir, exist_ok=True)
    logger.info(f"Building video for {entry_id} ({entry['book']} {entry['number']})")

    segments, n_matn, n_tarjuma, tarjuma = build_segments(entry_id)
    seg_files = synth_segments(segments, workdir)
    durs = [d for _, d in seg_files]
    voiceover = os.path.join(workdir, "voiceover.mp3")
    concat_voiceover(seg_files, voiceover)
    total_vo = probe(voiceover)
    logger.info(f"voiceover {total_vo:.2f}s, segments {[f'{d:.2f}' for d in durs]}")

    # --- 2. Scene durations (pauses distributed so scenes sum = voiceover) ---
    # Timeline: seg0 |p| seg1 |p| seg2 ... |p| segN  (p = PAUSE_MS between segs)
    # Indices: 0=salam, 1=hook, 2..2+n_matn-1=matn units,
    # then tarjuma (1 or 2 segs), then cta.
    p = PAUSE_MS / 1000.0
    i_tarjuma = 2 + n_matn
    i_cta = 2 + n_matn + n_tarjuma
    if n_tarjuma == 2:
        tarjuma_dur = p + durs[i_tarjuma] + p + durs[i_tarjuma + 1]
    else:
        tarjuma_dur = p + durs[i_tarjuma]
    scene_durs = [
        durs[0] + p + durs[1],
        p + sum(durs[2:2 + n_matn]) + p * (n_matn - 1),
        tarjuma_dur,
        p + durs[i_cta],
    ]

    # --- 3. Text overlays ---
    ref = ref_line(entry)
    tarjuma_lines = wrap_urdu(tarjuma)
    texts = [
        cfg["hook_text"],
        cfg["display_arabic"] + [(ref, 56, GOLD)],
        [(l, 60 if len(tarjuma_lines) > 2 else 68, WHITE) for l in tarjuma_lines]
        + [(ref, 54, GOLD)],
        cfg["cta_text"],
    ]
    bgs = [find_bg(s) for s in cfg["bgs"]]
    scene_files = []
    for i, (bg, tl, dur) in enumerate(zip(bgs, texts, scene_durs)):
        tp = os.path.join(workdir, f"text{i}.png")
        render_text(tl, tp)
        sp = os.path.join(workdir, f"scene{i}.mp4")
        build_scene(bg, tp, dur, sp)
        scene_files.append(sp)

    # --- 4. Assemble ---
    lst = os.path.join(workdir, "scenes.txt")
    with open(lst, "w") as f:
        f.write("\n".join(f"file '{s}'" for s in scene_files))
    silent = os.path.join(workdir, "silent.mp4")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
          "-c", "copy", silent], "concat scenes")
    _run(["ffmpeg", "-y", "-i", silent, "-i", voiceover,
          "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
          "-t", f"{total_vo:.2f}", "-shortest", out_mp4], "mux final")
    logger.info(f"FINAL: {out_mp4} ({total_vo:.2f}s)")

    # --- 5. SEO package (YouTube + all platforms) ---
    seo = generate_seo(entry)
    seo_path = os.path.join(os.path.dirname(out_mp4), f"seo-{entry_id}.json")
    with open(seo_path, "w", encoding="utf-8") as f:
        json.dump({"entry_id": entry_id, "entry": entry, "seo": seo}, f,
                  ensure_ascii=False, indent=2)
    logger.info(f"SEO: {seo_path}")
    # --- 5b. Multi-platform SEO (Instagram / Facebook / TikTok) ---
    try:
        from multiplatform import generate_all
        mp = generate_all(entry, seo)
        mp_path = os.path.join(os.path.dirname(out_mp4), f"mp-{entry_id}.json")
        with open(mp_path, "w", encoding="utf-8") as f:
            json.dump({"entry_id": entry_id, "platforms": mp}, f,
                      ensure_ascii=False, indent=2)
        logger.info(f"Multi-platform SEO: {mp_path}")
    except Exception as e:
        logger.warning(f"multiplatform SEO failed: {e}")
    return out_mp4, seo_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: build_daily_video.py <entry_id> <out_mp4> [workdir]")
        sys.exit(1)
    entry_id, out_mp4 = sys.argv[1], sys.argv[2]
    wd = sys.argv[3] if len(sys.argv) > 3 else None
    mp4, seo = build_video(entry_id, out_mp4, wd)
    print(f"OK: {mp4}")
    print(f"OK: {seo}")
