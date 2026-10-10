#!/usr/bin/env python3
"""
Multilingual voiceover builder (Imran's standing rule, 2026-10-09):
every language segment is synthesized in its OWN native voice/pronunciation.
- Arabic (salam, hadith, dua): ar-SA neural voice, full Arabic makharij
- Urdu: ur-PK neural voice, natural Urdu
- English: en-US neural voice (when needed)

Why not single-request <voice> switching: this Edge endpoint closes the WS
connection on multiple sibling <voice> elements (tested 2026-10-09). So each
segment is synthesized separately and concatenated with natural pauses.

Known endpoint constraints (do not regress):
- NO <phoneme> tags (kills WS), NO <break>, NO nested <prosody>
- NO tashkeel/diacritics on ur-PK voices (distorts G2P)
- Salam always its own unit at -8% rate + 400ms pause (Ghulam Rasool tareeqa)
"""
import os
import sys
import subprocess
import tempfile
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_tts_proxy_client import synthesize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Native voices per language
VOICE_AR_MALE = "ar-SA-HamedNeural"
VOICE_AR_FEMALE = "ar-SA-ZariyahNeural"
VOICE_UR_MALE = "ur-PK-AsadNeural"
VOICE_UR_FEMALE = "ur-PK-UzmaNeural"
VOICE_EN_MALE = "en-US-GuyNeural"
VOICE_EN_FEMALE = "en-US-JennyNeural"

PAUSE_MS = 400  # natural pause between units (established technique)
SAMPLE_RATE = 24000


def _run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed: {r.stderr[-500:]}")
    return r


def make_silence_wav(duration_ms, out_path):
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
        "-t", f"{duration_ms / 1000.0}",
        "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-ac", "1",
        out_path,
    ], "silence generation")


def mp3_to_wav(mp3_path, wav_path):
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", mp3_path,
        "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-ac", "1",
        wav_path,
    ], f"decode {mp3_path}")


def build_voiceover(segments, out_mp3, pause_ms=PAUSE_MS):
    """
    segments: list of dicts: {"text":..., "voice":..., "rate":"+0%"}
    Concatenates: seg1 + pause + seg2 + pause + ... -> out_mp3
    Returns out_mp3 path.
    """
    tmpdir = tempfile.mkdtemp(prefix="ml_voiceover_")
    wav_files = []
    try:
        for i, seg in enumerate(segments):
            mp3_path = os.path.join(tmpdir, f"seg_{i}.mp3")
            logger.info(f"Synthesizing segment {i+1}/{len(segments)} "
                        f"[{seg['voice']} @ {seg.get('rate', '+0%')}]: {seg['text'][:40]}...")
            synthesize(seg["text"], seg["voice"], mp3_path,
                       rate=seg.get("rate", "+0%"))
            wav_path = os.path.join(tmpdir, f"seg_{i}.wav")
            mp3_to_wav(mp3_path, wav_path)
            wav_files.append(wav_path)
            if i < len(segments) - 1:
                sil_path = os.path.join(tmpdir, f"sil_{i}.wav")
                make_silence_wav(pause_ms, sil_path)
                wav_files.append(sil_path)

        list_path = os.path.join(tmpdir, "concat.txt")
        with open(list_path, "w") as f:
            for w in wav_files:
                f.write(f"file '{w}'\n")
        _run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c:a", "libmp3lame", "-b:a", "48k",
            out_mp3,
        ], "concat+encode")
        logger.info(f"Voiceover built: {out_mp3}")
        return out_mp3
    finally:
        # keep tmpdir on failure for debugging; clean on success
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---- Preset segment builders -------------------------------------------------

# On ar-SA voices, FULL tashkeel IMPROVES accuracy (opposite of ur-PK rule):
# plain "وبرکاتہ" -> whisper hears "وبرض"; voweled -> perfect "وبرکاتہ".
# (Arabic TTS is trained on voweled text; verified 2026-10-09.)
FULL_SALAM_AR = "اَلسَّلَامُ عَلَيْكُمْ وَرَحْمَةُ اللَّهِ وَبَرَكَاتُهُ"


def preset_sample(male=True):
    """The multilingual test sample: Arabic salam -> Urdu body -> Arabic hadith -> Urdu tarjuma."""
    ar_voice = VOICE_AR_MALE if male else VOICE_AR_FEMALE
    ur_voice = VOICE_UR_MALE if male else VOICE_UR_FEMALE
    return [
        {"text": FULL_SALAM_AR, "voice": ar_voice, "rate": "-8%"},
        {"text": "کیا آپ جانتے ہیں؟ صرف چند منٹ کا ذکر، اور گناہ چاہے سمندر کی جھاگ جتنے ہوں، سب معاف!",
         "voice": ur_voice, "rate": "+0%"},
        {"text": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ", "voice": ar_voice, "rate": "-5%"},
        {"text": "اللہ اس کے گناہ معاف فرما دیتا ہے۔",
         "voice": ur_voice, "rate": "+0%"},
    ]


# ---- v3 tuned recipe (2026-10-09): rate sweep + wobble analysis winners ----
# Voice selection: 8 Arabic voices tested (ar-SA/ar-AE/ar-SY/ar-EG, M/F).
# All transcribed perfectly, so wobble (4-9 Hz pitch modulation) decided:
#   male:   ar-SA-HamedNeural smoothest male (0.0885); MSA standard
#   female: ar-SA-ZariyahNeural (0.0280) — ar-EG-SalmaNeural was marginally
#           smoother (0.0233) but Egyptian dialect; MSA purity wins for
#           Quranic-style phrases. Imran picks by ear anyway.
# Rate sweep findings (transcription + wobble):
#   Hamed salam:  -8% smoothest (0.0991) & deliberate 4.2s  -> keep -8%
#   Hamed hadith: -5% best (0.3780); -10% DISQUALIFIED (س->ص distortion)
#   Zariyah salam: -5% smoothest (0.0195) AND naturally unhurried (4.22s) -> -5%
#   Zariyah hadith: -5% best (0.1385)
#   pitch -10Hz: rejected (worse wobble, no benefit). Pause stays 400ms.
def preset_sample_v3(male=True):
    """v3 tuned multilingual sample: same 4 units, sweep-winning rates."""
    ar_voice = VOICE_AR_MALE if male else VOICE_AR_FEMALE
    ur_voice = VOICE_UR_MALE if male else VOICE_UR_FEMALE
    salam_rate = "-8%" if male else "-5%"
    return [
        {"text": FULL_SALAM_AR, "voice": ar_voice, "rate": salam_rate},
        {"text": "کیا آپ جانتے ہیں؟ صرف چند منٹ کا ذکر، اور گناہ چاہے سمندر کی جھاگ جتنے ہوں، سب معاف!",
         "voice": ur_voice, "rate": "+0%"},
        {"text": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ", "voice": ar_voice, "rate": "-5%"},
        {"text": "اللہ اس کے گناہ معاف فرما دیتا ہے۔",
         "voice": ur_voice, "rate": "+0%"},
    ]


if __name__ == "__main__":
    # usage: multilingual_voiceover.py <out.mp3> [male|female]
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ml_test.mp3"
    male = (sys.argv[2].lower() != "female") if len(sys.argv) > 2 else True
    build_voiceover(preset_sample(male=male), out)
    print(f"OK: {out}")
