#!/usr/bin/env python3
"""Assemble a 16:9 history video: title card + Ken Burns backgrounds + end card.

Usage: build_history_video.py <voiceover_mp3> <meta_json> <out_mp4>

- Reads topic meta (title_urdu, backgrounds) from <meta_json>.
- Title card (8s): PIL-rendered Urdu title on geometric background.
- Main: 6 backgrounds cycle with slow zoompan, total duration = voiceover len.
- End card (12s): branding + subscribe CTA.
- Audio: voiceover (starts at 8s) + subtle ambient bed looped underneath.
- Output: 1920x1080, 24fps, H.264 + AAC.

Fonts: assets/fonts/NotoNaskhArabic-Bold.ttf (installed to system fonts in CI).
Bed: assets/audio/morning-birds-dawn-chorus.mp3 (CC BY-SA 4.0, attributed in desc).
"""
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1920, 1080
FPS = 24
TITLE_DUR = 8
END_DUR = 12
FONT_PATH = os.path.join(BASE, "assets", "fonts", "NotoNaskhArabic-Bold.ttf")
BED = os.path.join(BASE, "assets", "audio", "morning-birds-dawn-chorus.mp3")


def _run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed: {r.stderr[-800:]}")


def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def urdu_text(draw, xy, text, font, fill):
    # VM Pillow has raqm: reshape() ONLY, no bidi get_display (else reversed).
    # layout_engine is set at ImageFont.truetype() time, not here.
    reshaped = arabic_reshaper.reshape(text)
    draw.text(xy, reshaped, font=font, fill=fill, anchor="mm")


def make_card(bg_path, lines, out_path, fontsize=90):
    """Render centered Urdu lines on a 1920x1080 card."""
    img = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
    # darken for text legibility
    overlay = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.blend(img, overlay, 0.45)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, fontsize,
                              layout_engine=ImageFont.Layout.RAQM)
    small = ImageFont.truetype(FONT_PATH, 54,
                               layout_engine=ImageFont.Layout.RAQM)
    y = H // 2 - (len(lines) - 1) * 70
    for i, (txt, is_title) in enumerate(lines):
        f = font if is_title else small
        col = (255, 215, 130) if is_title else (240, 240, 240)
        urdu_text(d, (W // 2, y + i * 140), txt, f, col)
    # brand footer
    urdu_text(d, (W // 2, H - 90), "ذکر الٰہی", small, (255, 215, 130))
    img.save(out_path)


def seg_mp4(img_path, dur, out_path, zoom_in=True):
    """One Ken Burns segment."""
    z0, z1 = (1.0, 1.12) if zoom_in else (1.12, 1.0)
    frames = int(dur * FPS)
    # zoompan animates with 'on' = output frame number
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1",
          "-framerate", str(FPS), "-i", img_path,
          "-vf", f"scale=1920:1080,"
                  f"zoompan=z='min({z0}+({z1}-{z0})*on/{frames},{z1})':"
                  f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                  f"d=1:s=1920x1080:fps={FPS}",
          "-t", f"{dur}", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "20", "-pix_fmt", "yuv420p", out_path],
         f"segment {img_path}")


def still_mp4(img_path, dur, out_path):
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1",
          "-framerate", str(FPS), "-i", img_path,
          "-t", f"{dur}", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "20", "-pix_fmt", "yuv420p",
          "-vf", "scale=1920:1080", out_path],
         f"still {img_path}")


def main():
    voice_mp3, meta_json, out_mp4 = sys.argv[1], sys.argv[2], sys.argv[3]
    meta = json.load(open(meta_json, encoding="utf-8"))
    voice_dur = probe_duration(voice_mp3)
    print(f"voiceover={voice_dur:.1f}s", flush=True)

    tmpdir = tempfile.mkdtemp(prefix="hist_vid_")
    try:
        # --- title card ---
        title_bg = os.path.join(BASE, "assets", "history",
                                "hist-bg-geometric-gold.jpg")
        title_png = os.path.join(tmpdir, "title.png")
        make_card(title_bg,
                  [(meta["title_urdu"], True), (meta["era"], False)],
                  title_png)
        title_mp4 = os.path.join(tmpdir, "title.mp4")
        still_mp4(title_png, TITLE_DUR, title_mp4)

        # --- main segments ---
        bgs = meta["backgrounds"]
        seg_dur = voice_dur / len(bgs)
        seg_files = []
        for i, bg in enumerate(bgs):
            bg_path = os.path.join(BASE, "assets", "history", bg)
            seg = os.path.join(tmpdir, f"seg{i}.mp4")
            print(f"segment {i+1}/{len(bgs)}: {bg} ({seg_dur:.1f}s)",
                  flush=True)
            seg_mp4(bg_path, seg_dur, seg, zoom_in=(i % 2 == 0))
            seg_files.append(seg)

        # --- end card ---
        end_png = os.path.join(tmpdir, "end.png")
        make_card(title_bg,
                  [("جزاک اللہ خیرا", True),
                   ("ویڈیو پسند آئی تو شیئر کریں", False)],
                  end_png, fontsize=80)
        end_mp4 = os.path.join(tmpdir, "end.mp4")
        still_mp4(end_png, END_DUR, end_mp4)

        # --- concat video ---
        lst = os.path.join(tmpdir, "vlist.txt")
        with open(lst, "w") as f:
            f.write(f"file '{title_mp4}'\n")
            for s in seg_files:
                f.write(f"file '{s}'\n")
            f.write(f"file '{end_mp4}'\n")
        vcat = os.path.join(tmpdir, "video.mp4")
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
              "-i", lst, "-c", "copy", vcat], "concat video")
        total_dur = TITLE_DUR + voice_dur + END_DUR
        print(f"total video={total_dur:.1f}s", flush=True)

        # --- audio: voiceover delayed 8s + bed underneath ---
        # bed: loop to total_dur, low volume
        _run(["ffmpeg", "-y", "-v", "error",
              "-i", voice_mp3,
              "-stream_loop", "-1", "-i", BED,
              "-filter_complex",
              f"[0:a]adelay={TITLE_DUR*1000}|{TITLE_DUR*1000},apad[v];"
              f"[1:a]volume=0.05,aloop=loop=-1:size=2e9,atrim=0:{total_dur}[b];"
              f"[v][b]amix=inputs=2:duration=first:dropout_transition=0,"
              f"aformat=sample_fmts=fltp:channel_layouts=stereo[a]",
              "-map", "[a]", "-t", f"{total_dur}",
              "-c:a", "aac", "-b:a", "128k",
              os.path.join(tmpdir, "audio.m4a")], "mix audio")

        # --- mux ---
        _run(["ffmpeg", "-y", "-v", "error",
              "-i", vcat, "-i", os.path.join(tmpdir, "audio.m4a"),
              "-c:v", "copy", "-c:a", "copy", "-shortest",
              "-movflags", "+faststart", out_mp4], "mux")
        print(f"OK: {out_mp4}")
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
