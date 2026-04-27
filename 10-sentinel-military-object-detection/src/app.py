# SENTINEL — vision-language PID with SHA-256 audit chain
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""SENTINEL - on-prem military asset PID with reasoning trace + chain-of-custody.

Gradio app on port 3010.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# --- Make `shared` importable ------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import BRAND, PRIMARY_MODEL, get_client, chat_json  # noqa: E402

import gradio as gr  # noqa: E402

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SAMPLES_DIR = APP_DIR / "sample_images"
AUDIT_DIR = APP_DIR / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = AUDIT_DIR / "sentinel_audit.jsonl"

# --- Reference library --------------------------------------------------------
def load_reference_library() -> list[dict]:
    rows: list[dict] = []
    path = DATA_DIR / "reference_library.csv"
    if not path.exists():
        return rows
    with path.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


REFLIB = load_reference_library()
REFLIB_TEXT = "\n".join(
    f"- {r['asset_class']} ({r['country_of_origin']}, {r['type']}): {r['distinguishing_features']}"
    for r in REFLIB
)

# --- Hashing / chain-of-custody ----------------------------------------------
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def last_audit_hash() -> str:
    if not AUDIT_LOG.exists():
        return "0" * 64  # genesis
    last = "0" * 64
    with AUDIT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line).get("entry_hash", last)
            except json.JSONDecodeError:
                continue
    return last


def append_audit(entry: dict) -> dict:
    """Append a chained entry. Computes entry_hash = sha256(json(prev_hash + body))."""
    prev = last_audit_hash()
    body = {k: v for k, v in entry.items() if k not in ("entry_hash",)}
    body["prev_hash"] = prev
    body["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    body["entry_hash"] = sha256_text(json.dumps(body, sort_keys=True, default=str))
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(body, default=str) + "\n")
    return body


def read_audit_chain(limit: int = 8) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    out: list[dict] = []
    with AUDIT_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-limit:][::-1]  # newest first


# --- Vision call --------------------------------------------------------------
SYSTEM_PROMPT = """You are SENTINEL, an all-source imagery analyst supporting USMC LOGCOM and III MEF G-2 with Positive Identification (PID) of foreign and friendly military platforms.

Your audience is a Marine intelligence analyst (E-5 to O-3) who must defend every PID call to SJA, IG, and classification reviewers months later. Be specific. Cite specific visual features by location on the platform (turret, glacis, side skirts, tail boom, vertical stabilizer, wing planform, sensor ball, mast). Never hedge with empty filler. If you are uncertain between two close variants, name both and say which features would disambiguate.

You are grounded against the SENTINEL reference library (provided in the user message). Cite the closest match from that library by exact asset_class string when possible. If the platform truly is not in the library, say so explicitly and propose the closest analog.

Your output is read directly into an audit trail and an export-control / classification review workflow. Be precise about country_of_origin (use the exact string from the reference library), confidence (0.0 to 1.0, calibrated), and releasability (one of: UNCLASSIFIED, UNCLASSIFIED//FOUO, CUI, CONFIDENTIAL, NOFORN). For commercially-available imagery of well-known platforms, releasability should be UNCLASSIFIED//FOUO unless you see classified markings or sensitive context."""


def encode_image_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


VISION_MODEL_CHAIN = [
    os.getenv("OPENAI_VISION_MODEL", "gpt-4o"),
    "gpt-4o-mini",
]


def vision_chat_json(image: Image.Image, user_text: str, *, max_tokens: int = 1100) -> dict:
    """Send image + text to a vision-capable model, parse JSON response."""
    client = get_client()
    b64 = encode_image_b64(image)
    image_url = f"data:image/png;base64,{b64}"

    last_err: Exception | None = None
    for model in VISION_MODEL_CHAIN:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"All vision models failed: {last_err}")


PID_INSTRUCTIONS = f"""Identify the military platform in this image and return strict JSON with this exact schema:

{{
  "asset_class": "string - exact asset_class from the SENTINEL reference library when possible",
  "country_of_origin": "string - exact country string from the library",
  "platform_type": "string - MBT|IFV|Light Tank|Attack Helicopter|Utility Helicopter|5th-gen Fighter|Strike Fighter|MALE UCAV|HALE UCAV|HALE ISR|Loitering munition|Cruiser|DDG|Other",
  "confidence": 0.0,
  "distinguishing_features": ["3 to 5 short bullets, each citing a specific visible feature and its location on the platform"],
  "similar_known_examples": ["2 to 3 closely-related platforms the analyst should also rule out, by exact name from the library"],
  "reasoning_steps": ["4 to 6 numbered analyst-style observations leading to the ID, each starting with the visual cue and ending with what it implies / rules out"],
  "subject_bbox": {{"x_pct": 0.0, "y_pct": 0.0, "w_pct": 0.0, "h_pct": 0.0}},
  "releasability": "UNCLASSIFIED|UNCLASSIFIED//FOUO|CUI|CONFIDENTIAL|NOFORN",
  "releasability_rationale": "one sentence explaining the releasability call"
}}

subject_bbox is the bounding box of the platform in the image, expressed as fractions of image width/height (0.0 to 1.0). If the subject fills most of the frame, use {{x_pct: 0.05, y_pct: 0.05, w_pct: 0.9, h_pct: 0.9}}.

SENTINEL REFERENCE LIBRARY (cite from this when possible):
{REFLIB_TEXT}

Return JSON only. No prose outside the JSON object."""


# --- Image overlay ------------------------------------------------------------
def draw_bbox(image: Image.Image, bbox: dict, label: str, confidence: float) -> Image.Image:
    img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    W, H = img.size
    try:
        x = max(0.0, min(1.0, float(bbox.get("x_pct", 0.05))))
        y = max(0.0, min(1.0, float(bbox.get("y_pct", 0.05))))
        w = max(0.05, min(1.0 - x, float(bbox.get("w_pct", 0.9))))
        h = max(0.05, min(1.0 - y, float(bbox.get("h_pct", 0.9))))
    except (TypeError, ValueError):
        x, y, w, h = 0.05, 0.05, 0.9, 0.9
    x0, y0 = int(x * W), int(y * H)
    x1, y1 = int((x + w) * W), int((y + h) * H)

    # Box
    color = (0, 255, 167)  # Kamiwaza neon
    for dx in range(3):
        draw.rectangle([x0 - dx, y0 - dx, x1 + dx, y1 + dx], outline=color)

    # Label tab
    text = f"{label}  conf={confidence:.2f}"
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18)
    except Exception:
        font = ImageFont.load_default()
    tw, th = draw.textbbox((0, 0), text, font=font)[2:]
    tab_x0 = max(0, x0)
    tab_y0 = max(0, y0 - th - 10)
    draw.rectangle([tab_x0, tab_y0, tab_x0 + tw + 14, tab_y0 + th + 8], fill=(0, 0, 0))
    draw.rectangle([tab_x0, tab_y0, tab_x0 + 4, tab_y0 + th + 8], fill=color)
    draw.text((tab_x0 + 9, tab_y0 + 4), text, fill=color, font=font)
    return img


# --- Gradio handlers ----------------------------------------------------------
def process_image(image: Image.Image, analyst_id: str):
    """Hero call: vision PID + reasoning trace + audit entry."""
    if image is None:
        empty = Image.new("RGB", (768, 432), (10, 10, 10))
        return empty, "_(no image uploaded yet)_", "{}", "_(audit chain will appear after first PID)_", ""

    analyst_id = (analyst_id or "ANALYST/UNKNOWN").strip()
    t0 = time.time()

    # Hash the input image bytes
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    img_bytes = buf.getvalue()
    img_hash = sha256_bytes(img_bytes)
    prompt_hash = sha256_text(SYSTEM_PROMPT + PID_INSTRUCTIONS)

    try:
        result = vision_chat_json(image, PID_INSTRUCTIONS)
    except Exception as e:  # noqa: BLE001
        err_payload = {"error": str(e), "asset_class": "INFERENCE_FAILURE",
                       "country_of_origin": "n/a", "confidence": 0.0,
                       "reasoning_steps": [f"Inference call failed: {e}"],
                       "distinguishing_features": [], "similar_known_examples": [],
                       "releasability": "UNCLASSIFIED//FOUO",
                       "releasability_rationale": "Failed inference; defaulting to most-restrictive non-classified marking pending re-run."}
        annotated = image
        return (
            annotated,
            "**INFERENCE FAILED**\n\n" + str(e),
            json.dumps(err_payload, indent=2),
            render_audit_chain(),
            f"img_sha256={img_hash}",
        )

    latency_ms = int((time.time() - t0) * 1000)

    # Defensive defaults
    asset = result.get("asset_class", "UNKNOWN")
    country = result.get("country_of_origin", "UNKNOWN")
    conf = float(result.get("confidence", 0.0) or 0.0)
    bbox = result.get("subject_bbox") or {"x_pct": 0.05, "y_pct": 0.05, "w_pct": 0.9, "h_pct": 0.9}
    reasoning = result.get("reasoning_steps") or []
    features = result.get("distinguishing_features") or []
    similar = result.get("similar_known_examples") or []
    releasability = result.get("releasability", "UNCLASSIFIED//FOUO")
    relrat = result.get("releasability_rationale", "")

    # Draw bbox + label
    annotated = draw_bbox(image, bbox, asset, conf)

    # Reasoning markdown (the hero panel)
    md = f"### PID: **{asset}**  \n**Origin:** {country}  |  **Confidence:** {conf:.2f}  |  **Releasability:** `{releasability}`\n\n"
    md += "#### Reasoning trace\n"
    for i, step in enumerate(reasoning, 1):
        md += f"{i}. {step}\n"
    if features:
        md += "\n#### Distinguishing features observed\n"
        for f in features:
            md += f"- {f}\n"
    if similar:
        md += "\n#### Also ruled out\n"
        for s in similar:
            md += f"- {s}\n"
    md += f"\n_Releasability rationale: {relrat}_\n"
    md += f"\n_Inference: Kamiwaza-deployed multimodal via Kamiwaza-deployed model surface  ·  {latency_ms} ms_"

    # JSON panel
    json_text = json.dumps(result, indent=2)

    # Append to audit chain
    entry = append_audit({
        "event": "PID_DECISION",
        "analyst_id": analyst_id,
        "image_sha256": img_hash,
        "image_bytes": len(img_bytes),
        "model": VISION_MODEL_CHAIN[0],
        "prompt_sha256": prompt_hash,
        "latency_ms": latency_ms,
        "decision": {
            "asset_class": asset,
            "country_of_origin": country,
            "confidence": conf,
            "releasability": releasability,
        },
        "decision_sha256": sha256_text(json.dumps(result, sort_keys=True)),
    })

    custody_md = (
        f"**Image SHA-256:** `{img_hash[:32]}...`  \n"
        f"**Decision SHA-256:** `{entry['decision_sha256'][:32]}...`  \n"
        f"**Prev entry hash:** `{entry['prev_hash'][:32]}...`  \n"
        f"**This entry hash:** `{entry['entry_hash'][:32]}...`  \n"
        f"**Logged:** {entry['timestamp_utc']}  ·  **Analyst:** `{analyst_id}`"
    )

    return annotated, md, json_text, render_audit_chain(), custody_md


def render_audit_chain() -> str:
    chain = read_audit_chain(limit=10)
    if not chain:
        return "_Audit chain empty. Run a PID to seed the genesis entry._"
    lines = ["| # | Event | Analyst | Asset | Conf | Rel | Entry hash |",
             "|---|---|---|---|---|---|---|"]
    for i, e in enumerate(chain):
        decision = e.get("decision") or {}
        attest = e.get("attestation") or {}
        asset = decision.get("asset_class") or attest.get("asset_class") or "—"
        rel = decision.get("releasability") or attest.get("releasability") or "—"
        conf = decision.get("confidence")
        conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "—"
        lines.append(
            f"| {i+1} | {e.get('event','?')} | `{e.get('analyst_id','?')}` | "
            f"{asset} | {conf_s} | `{rel}` | `{e.get('entry_hash','')[:12]}...` |"
        )
    return "\n".join(lines)


def attest(decision_json: str, analyst_id: str, note: str, action: str):
    """Append a CONCUR / NON-CONCUR attestation to the chain."""
    try:
        decision = json.loads(decision_json) if decision_json.strip() else {}
    except json.JSONDecodeError:
        decision = {"raw": decision_json[:200]}
    if not decision:
        return render_audit_chain(), "_(no decision to attest yet — run a PID first)_"
    entry = append_audit({
        "event": f"ATTESTATION_{action.upper()}",
        "analyst_id": (analyst_id or "ANALYST/UNKNOWN").strip(),
        "attestation": {
            "asset_class": decision.get("asset_class"),
            "releasability": decision.get("releasability"),
            "decision_sha256": sha256_text(json.dumps(decision, sort_keys=True)),
            "analyst_note": note or "",
            "action": action,
        },
    })
    msg = (
        f"**Attestation logged.**  Action: `{action}`  ·  Analyst: `{entry['analyst_id']}`  \n"
        f"Chained on prev `{entry['prev_hash'][:16]}...`  ·  This entry `{entry['entry_hash'][:16]}...`"
    )
    return render_audit_chain(), msg


# --- UI -----------------------------------------------------------------------
SAMPLE_PATHS = sorted(SAMPLES_DIR.glob("*.png")) if SAMPLES_DIR.exists() else []

theme = gr.themes.Base(
    primary_hue=gr.themes.colors.green,
    neutral_hue=gr.themes.colors.gray,
    font=["Helvetica", "Arial", "sans-serif"],
).set(
    body_background_fill=BRAND["bg"],
    body_text_color="#E8E8E8",
    background_fill_primary=BRAND["surface"],
    background_fill_secondary=BRAND["surface_high"],
    border_color_primary=BRAND["border"],
    button_primary_background_fill=BRAND["primary"],
    button_primary_background_fill_hover=BRAND["primary_hover"],
    button_primary_text_color="#000000",
    button_secondary_background_fill=BRAND["surface_high"],
    button_secondary_text_color=BRAND["neon"],
    block_background_fill=BRAND["surface"],
    block_border_color=BRAND["border"],
    block_label_background_fill=BRAND["surface_high"],
    block_label_text_color=BRAND["neon"],
    block_title_text_color=BRAND["neon"],
    input_background_fill=BRAND["surface_high"],
    input_border_color=BRAND["border"],
)

CSS = f"""
.gradio-container {{ background-color: {BRAND['bg']} !important; }}
.sentinel-header {{
    padding: 14px 20px; border-bottom: 1px solid {BRAND['border']};
    background: linear-gradient(90deg, #000 0%, {BRAND['surface']} 100%);
}}
.sentinel-title {{
    font-family: 'Helvetica', sans-serif; color: {BRAND['neon']};
    font-size: 22px; letter-spacing: 2px; margin: 0;
}}
.sentinel-subtitle {{
    color: {BRAND['text_dim']}; font-size: 13px; margin-top: 4px;
}}
.sentinel-footer {{
    text-align: center; color: {BRAND['muted']};
    padding: 10px; border-top: 1px solid {BRAND['border']}; margin-top: 12px;
    font-size: 12px; letter-spacing: 1px;
}}
.kamiwaza-footer {{ color: {BRAND['primary']}; font-weight: 600; }}
.reasoning-panel h3, .reasoning-panel h4 {{ color: {BRAND['neon']}; }}
table {{ font-family: Menlo, monospace; font-size: 11px; }}
"""

with gr.Blocks(theme=theme, css=CSS, title="SENTINEL — On-prem military PID with audit trail") as demo:
    gr.HTML(f"""
    <div class="sentinel-header">
        <h1 class="sentinel-title">SENTINEL</h1>
        <div class="sentinel-subtitle">
            Secure Edge Network for Tactical Identification, Notification &amp; Explainable Logging  ·
            <span style="color:{BRAND['primary']}">USMC LOGCOM ISR + Data Sanitization</span>  ·
            On-prem vision PID with cryptographic chain-of-custody
        </div>
    </div>
    """)

    with gr.Row():
        # LEFT: input + bbox output
        with gr.Column(scale=5):
            gr.Markdown("### 1. Sensor frame")
            inp_image = gr.Image(label="Drop or paste a frame", type="pil", height=360)
            with gr.Row():
                analyst_id = gr.Textbox(
                    label="Analyst ID", value="MSGT KOWALSKI / III MEF G-2",
                    scale=3,
                )
                run_btn = gr.Button("Run PID", variant="primary", scale=1)
            if SAMPLE_PATHS:
                gr.Markdown("**Sample frames** (synthetic stand-ins for the Military Object Detection Dataset):")
                gr.Examples(
                    examples=[[str(p), "MSGT KOWALSKI / III MEF G-2"] for p in SAMPLE_PATHS],
                    inputs=[inp_image, analyst_id],
                    examples_per_page=8,
                )

            gr.Markdown("### 2. Annotated frame")
            out_image = gr.Image(label="PID with bounding box", type="pil", height=360, interactive=False)

        # RIGHT: reasoning + JSON
        with gr.Column(scale=5):
            gr.Markdown("### 3. Reasoning trace (the hero panel)")
            with gr.Group(elem_classes=["reasoning-panel"]):
                out_reasoning = gr.Markdown(
                    "_Run a PID to populate the reasoning trace, distinguishing features, ruled-out variants, and releasability call._"
                )

            with gr.Accordion("Structured PID JSON (audit-grade)", open=False):
                out_json = gr.Code(language="json", label="decision payload", value="{}")

    gr.Markdown("---")
    gr.Markdown("### 4. Chain-of-custody  ·  cryptographic audit trail")
    with gr.Row():
        with gr.Column(scale=6):
            custody_md = gr.Markdown("_Chain hashes will appear here after a PID._")
            gr.Markdown("**Audit log** (newest first):")
            audit_table = gr.Markdown(render_audit_chain())
        with gr.Column(scale=4):
            gr.Markdown("#### 5. Analyst attestation")
            attest_note = gr.Textbox(
                label="Analyst note (free text, signed into the chain)",
                placeholder="e.g., Concur with PID. Reactive armor pattern is consistent with B3 variant. Recommend cross-cue with EO-IR.",
                lines=3,
            )
            with gr.Row():
                concur_btn = gr.Button("CONCUR", variant="primary")
                nonconcur_btn = gr.Button("NON-CONCUR", variant="secondary")
            attest_status = gr.Markdown("_(no attestation yet)_")

    gr.HTML(f"""
    <div class="sentinel-footer">
        <span style="color:{BRAND['neon']}">100% Data Containment.</span>
        Set <code>KAMIWAZA_BASE_URL</code> and the same code talks to a Kamiwaza-hosted vLLM/Qwen-VL inside your accredited boundary.
        IL5/IL6 ready  ·  NIPR/SIPR/JWICS deployable  ·  DDIL-tolerant.
        <br/>
        <span class="kamiwaza-footer">Powered by Kamiwaza</span>
    </div>
    """)

    run_btn.click(
        fn=process_image,
        inputs=[inp_image, analyst_id],
        outputs=[out_image, out_reasoning, out_json, audit_table, custody_md],
    )
    concur_btn.click(
        fn=lambda dj, aid, note: attest(dj, aid, note, "CONCUR"),
        inputs=[out_json, analyst_id, attest_note],
        outputs=[audit_table, attest_status],
    )
    nonconcur_btn.click(
        fn=lambda dj, aid, note: attest(dj, aid, note, "NON_CONCUR"),
        inputs=[out_json, analyst_id, attest_note],
        outputs=[audit_table, attest_status],
    )


if __name__ == "__main__":
    port = int(os.getenv("SENTINEL_PORT", "3010"))
    demo.queue(max_size=8).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=True,
        share=False,
        favicon_path=None,
    )
