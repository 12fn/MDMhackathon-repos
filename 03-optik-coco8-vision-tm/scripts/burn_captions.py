"""OPTIK fallback caption burner — works when brew-ffmpeg lacks libass.

Reads the source webm via OpenCV, draws Pillow text per cue at the bottom,
writes mp4. No subtitles/drawtext filter required.

Usage:
  python scripts/burn_captions.py \
    --video test-results/.../video.webm \
    --script demo-script.json \
    --out videos/optik-demo.mp4
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Avenir Next.ttc",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def cue_at(cues: list[dict], t: float) -> str | None:
    for c in cues:
        if c["start"] <= t <= c["end"]:
            return c["text"]
    return None


def draw_caption(frame_rgb: np.ndarray, text: str, *, font_size: int = 30) -> np.ndarray:
    h, w = frame_rgb.shape[:2]
    img = Image.fromarray(frame_rgb)
    d = ImageDraw.Draw(img, "RGBA")
    font = load_font(font_size)

    # Wrap text to ~70 char lines.
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        candidate = (cur + " " + word).strip()
        if d.textlength(candidate, font=font) > w * 0.85 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = candidate
    if cur:
        lines.append(cur)

    line_h = font_size + 8
    box_h = line_h * len(lines) + 16
    box_top = h - box_h - 30
    pad = 20
    # Compute widest line
    max_w = max(d.textlength(ln, font=font) for ln in lines)
    box_w = int(max_w + 2 * pad)
    box_left = (w - box_w) // 2
    d.rectangle(
        [box_left, box_top, box_left + box_w, box_top + box_h],
        fill=(0, 0, 0, 200),
        outline=(0, 187, 122, 255),
        width=2,
    )
    for i, ln in enumerate(lines):
        ln_w = d.textlength(ln, font=font)
        x = box_left + (box_w - ln_w) // 2
        y = box_top + 8 + i * line_h
        d.text((x, y), ln, fill=(255, 255, 255), font=font)
    return np.array(img)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--script", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--font-size", type=int, default=30)
    args = ap.parse_args()

    cues = json.loads(args.script.read_text())
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        sys.exit(f"Cannot open {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"input: {w}x{h} @ {fps:.2f} fps, {n_frames} frames")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp .mp4 with mp4v then re-mux to h264 via ffmpeg for compatibility.
    tmp = args.out.with_suffix(".tmp.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(tmp), fourcc, fps, (w, h))

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        cue = cue_at(cues, t)
        if cue:
            rgb = draw_caption(rgb, cue, font_size=args.font_size)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        vw.write(bgr)
        idx += 1
        if idx % 200 == 0:
            print(f"  frame {idx}/{n_frames}")
    cap.release()
    vw.release()
    print(f"  burned {idx} frames -> {tmp}")

    # Re-encode to h264/aac with faststart for broadest compatibility.
    cmd = [
        "ffmpeg", "-y", "-i", str(tmp),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(args.out),
    ]
    print("  re-encoding:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    tmp.unlink(missing_ok=True)
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
