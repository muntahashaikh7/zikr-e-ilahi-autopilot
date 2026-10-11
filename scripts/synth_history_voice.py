#!/usr/bin/env python3
"""Synthesize long-form Urdu voiceover for history videos.

Usage: synth_history_voice.py <script_txt> <out_mp3>

- Parses <ar>...</ar> tags: Arabic -> ar-SA-HamedNeural @ -5% (full tashkeel OK).
- Urdu text -> ur-PK-AsadNeural @ -8% (slow, deliberate; NO tashkeel in source).
- Chunks long text at paragraph boundaries (~3000 chars per TTS request).
- Concatenates with 700ms pauses between chunks -> single MP3.
- Uses scripts/edge_tts_proxy_client.synthesize (auto-routes: direct edge_tts
  on GitHub Actions, proxy tunnel on the sandbox VM).

Zero AI tokens at runtime: pure TTS.
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_tts_proxy_client import synthesize

VOICE_UR = "ur-PK-AsadNeural"
VOICE_AR = "ar-SA-HamedNeural"
RATE_UR = "-8%"
RATE_AR = "-5%"
CHUNK_CHARS = 3000
PAUSE_MS = 700
SR = 24000


def _run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed: {r.stderr[-600:]}")


def split_units(text):
    """Split script into (lang, text) units on <ar> tags."""
    units = []
    pos = 0
    for m in re.finditer(r"<ar>(.*?)</ar>", text, re.S):
        pre = text[pos:m.start()].strip()
        if pre:
            units.append(("ur", pre))
        units.append(("ar", m.group(1).strip()))
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        units.append(("ur", tail))
    return units


def chunk_paragraphs(text, limit=CHUNK_CHARS):
    """Split text into <=limit char chunks at paragraph boundaries."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= limit:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            # single huge paragraph: split at sentence boundaries
            while len(p) > limit:
                cut = p.rfind("۔", 0, limit)
                cut = cut + 1 if cut > limit // 2 else limit
                chunks.append(p[:cut].strip())
                p = p[cut:].strip()
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def main():
    script_txt, out_mp3 = sys.argv[1], sys.argv[2]
    text = open(script_txt, encoding="utf-8").read().strip()
    units = split_units(text)

    # flatten into synth jobs
    jobs = []  # (voice, rate, text)
    for lang, utext in units:
        if lang == "ar":
            jobs.append((VOICE_AR, RATE_AR, utext))
        else:
            for ch in chunk_paragraphs(utext):
                jobs.append((VOICE_UR, RATE_UR, ch))

    print(f"units={len(units)} synth_jobs={len(jobs)}", flush=True)
    tmpdir = tempfile.mkdtemp(prefix="hist_voice_")
    wavs = []
    try:
        for i, (voice, rate, jtext) in enumerate(jobs):
            mp3 = os.path.join(tmpdir, f"j{i:03d}.mp3")
            print(f"[{i+1}/{len(jobs)}] {voice} {rate} ({len(jtext)} chars)",
                  flush=True)
            synthesize(jtext, voice, mp3, rate=rate, timeout=120)
            wav = os.path.join(tmpdir, f"j{i:03d}.wav")
            _run(["ffmpeg", "-y", "-v", "error", "-i", mp3,
                  "-c:a", "pcm_s16le", "-ar", str(SR), "-ac", "1", wav],
                 f"decode job {i}")
            wavs.append(wav)
            if i < len(jobs) - 1:
                sil = os.path.join(tmpdir, f"sil{i:03d}.wav")
                _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                      "-i", f"anullsrc=r={SR}:cl=mono",
                      "-t", f"{PAUSE_MS/1000.0}",
                      "-c:a", "pcm_s16le", "-ar", str(SR), "-ac", "1", sil],
                     "silence")
                wavs.append(sil)

        lst = os.path.join(tmpdir, "concat.txt")
        with open(lst, "w") as f:
            for w in wavs:
                f.write(f"file '{w}'\n")
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
              "-i", lst, "-c:a", "libmp3lame", "-b:a", "96k", out_mp3],
             "concat voiceover")
        print(f"OK: {out_mp3}")
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
