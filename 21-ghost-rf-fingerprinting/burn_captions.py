"""Caption burner that doesn't require libass/freetype-enabled ffmpeg.

Same pattern as apps/06-corsair/burn_captions.py: render one transparent
PNG per cue with PIL, then composite via ffmpeg overlay + enable=between(t,...).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

APP_DIR = Path(__file__).resolve().parent
SCRIPT = APP_DIR / "demo-script.json"
OUT = APP_DIR / "videos" / "ghost-demo.mp4"
CAP_DIR = APP_DIR / ".caption_pngs"

W, H = 1440, 900
FONT_SIZE = 30
LINE_WRAP = 80


def find_video() -> Path:
    # Look for the most recent webm under test-results/
    tr = APP_DIR / "test-results"
    if not tr.exists():
        raise SystemExit(f"no test-results dir at {tr}")
    candidates = sorted(tr.rglob("video.webm"), key=lambda p: p.stat().st_mtime,
                         reverse=True)
    if not candidates:
        raise SystemExit("no video.webm found under test-results/")
    return candidates[0]


def find_font() -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, FONT_SIZE)
            except Exception:
                continue
    return ImageFont.load_default()


def render_caption_png(text: str, path: Path, font: ImageFont.FreeTypeFont) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=LINE_WRAP) or [""])
    line_h = FONT_SIZE + 8
    total_h = line_h * len(lines) + 24
    y0 = H - total_h - 28
    draw.rectangle([(40, y0), (W - 40, y0 + total_h)], fill=(0, 0, 0, 200))
    # Kamiwaza neon accent bar
    draw.rectangle([(40, y0), (44, y0 + total_h)], fill=(0, 255, 167, 240))
    y = y0 + 12
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h
    img.save(path)


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not on PATH")
    if not SCRIPT.exists():
        raise SystemExit(f"missing {SCRIPT} (run Playwright first)")
    video = find_video()
    cues = json.loads(SCRIPT.read_text())
    CAP_DIR.mkdir(exist_ok=True)
    font = find_font()
    pngs: list[Path] = []
    for i, c in enumerate(cues):
        p = CAP_DIR / f"cue_{i:03d}.png"
        render_caption_png(c["text"], p, font)
        pngs.append(p)

    inputs = ["-i", str(video)]
    for p in pngs:
        inputs += ["-i", str(p)]
    fc_parts = []
    prev_label = "0:v"
    for i, c in enumerate(cues):
        out_label = f"v{i}"
        fc_parts.append(
            f"[{prev_label}][{i+1}:v]overlay=0:0:enable='between(t,{c['start']:.3f},{c['end']:.3f})'[{out_label}]"
        )
        prev_label = out_label
    filter_complex = ";".join(fc_parts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(OUT),
    ]
    print(f"compositing {len(cues)} caption overlays onto {video.name}…")
    subprocess.run(cmd, check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
