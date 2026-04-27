# STRIDER — off-road terrain GO/NO-GO trafficability per vehicle
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""STRIDER — off-road terrain GO/NO-GO trafficability per vehicle.

Dataset frame: GOOSE — German Outdoor and Offroad Dataset (off-road semantic
segmentation, 50 GB free academic). https://goose-dataset.de

Hero AI play
------------
1. Vision call (multimodal): terrain image -> structured JSON
   {cover_type, slope_estimate_pct, water_present, water_depth_in_est,
    obstacles[], surface_firmness, confidence}
2. Reasoning call: cross-references the vehicle_specs.csv -> per-vehicle
   GO / GO-WITH-CAUTION / NO-GO recommendation with the binding constraint
   named in plain English.
3. Streaming narrator paragraph for the convoy commander.

All three calls route through the shared multi-provider client
(shared/kamiwaza_client.py) so swapping providers requires zero code changes.

Stack: Gradio dark theme (Kamiwaza brand kit). Pillow for image handling.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import sys
from pathlib import Path
from typing import Iterator

import gradio as gr
import pandas as pd
from PIL import Image

# Make `shared/` importable when run from anywhere
ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO))

from shared.kamiwaza_client import BRAND, chat, chat_json, get_client  # noqa: E402

DATA_DIR = ROOT / "data"
IMG_DIR = ROOT / "sample_images"
VEHICLES_CSV = DATA_DIR / "vehicle_specs.csv"

VISION_MODEL = "gpt-4o"        # hero call — explicit per spec
REASON_MODEL = None             # use shared client default chain (gpt-5.4-mini → ...)


# ---------------------------------------------------------------------------
# Vehicle specs
# ---------------------------------------------------------------------------
def load_vehicles() -> list[dict]:
    if not VEHICLES_CSV.exists():
        raise FileNotFoundError(
            f"{VEHICLES_CSV} not found. Run: python data/generate.py"
        )
    with VEHICLES_CSV.open() as f:
        return list(csv.DictReader(f))


VEHICLES = load_vehicles()


def vehicles_table() -> pd.DataFrame:
    df = pd.DataFrame(VEHICLES)
    return df[
        [
            "vehicle_id",
            "class",
            "ground_clearance_in",
            "fording_depth_in",
            "max_grade_pct",
            "max_side_slope_pct",
            "tire_or_track",
            "powertrain",
            "autonomy_level",
        ]
    ]


# ---------------------------------------------------------------------------
# Vision: terrain classification
# ---------------------------------------------------------------------------
TERRAIN_SCHEMA = {
    "cover_type": "one of [mud, soft_sand, gravel, packed_dirt, broken_rock, vegetation, water_crossing, snow, paved]",
    "slope_estimate_pct": "integer 0..60 — estimated grade",
    "side_slope_pct": "integer 0..40 — estimated cross-slope",
    "water_present": "bool",
    "water_depth_in_est": "integer inches if water_present else 0",
    "obstacles": "array of short strings, e.g. ['boulder field', 'fallen log', 'tire ruts']",
    "surface_firmness": "one of [firm, moderate, soft, very_soft]",
    "visibility_conditions": "short string — daylight/dust/fog/etc.",
    "confidence": "float 0..1",
    "summary": "one sentence terrain summary for an operator",
}

VISION_SYSTEM = (
    "You are STRIDER, an off-road terrain analyst supporting USMC autonomous "
    "logistics convoys (Force Design 2030). Inspect the supplied terrain image "
    "and return a structured JSON terrain report. Be conservative — when in "
    "doubt assume worse trafficability. Always respond with ONLY valid JSON "
    f"matching this schema: {json.dumps(TERRAIN_SCHEMA)}"
)


def _img_to_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def vision_classify(img: Image.Image) -> dict:
    """Hero vision call — terrain image → structured JSON."""
    client = get_client()
    data_url = _img_to_data_url(img)
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": VISION_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Classify this terrain. Respond JSON only."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"cover_type": "unknown", "summary": raw[:200], "confidence": 0.0}


# ---------------------------------------------------------------------------
# Reasoning: vehicle compatibility matrix
# ---------------------------------------------------------------------------
MATRIX_SCHEMA = {
    "matrix": "array of {vehicle_id, recommendation, color, reason} where recommendation is GO|CAUTION|NO-GO and color is green|amber|red",
    "convoy_call": "one of GO|MIXED|NO-GO",
    "narrator": "3–5 sentence radio-voice brief for the convoy commander",
}

MATRIX_SYSTEM = """You are STRIDER's tactical reasoner. You are given (a) a terrain JSON
report and (b) a fleet specification table for USMC ground vehicles. For each
vehicle row, decide GO / CAUTION / NO-GO using these rules:

- Water depth > fording_depth_in -> NO-GO
- Estimated grade > max_grade_pct -> NO-GO
- Side slope > max_side_slope_pct -> CAUTION (or NO-GO if exceeds by >25%)
- soft / very_soft surface + low ground_clearance (<10 in) -> NO-GO for that vehicle
- broken_rock + electric depot tractor -> NO-GO
- mud + tracked or 6x6 wheeled -> GO if grade and depth permit
- vegetation: CAUTION for low-clearance, GO for tactical wheeled
- Always call out the binding constraint in the reason field, max 18 words

Color mapping: GO=green, CAUTION=amber, NO-GO=red.
convoy_call is GO if all are GO, NO-GO if all are NO-GO, MIXED otherwise.
Respond ONLY with JSON matching the schema."""


def reason_matrix(terrain: dict) -> dict:
    fleet = [
        {
            "vehicle_id": v["vehicle_id"],
            "ground_clearance_in": float(v["ground_clearance_in"]),
            "fording_depth_in": float(v["fording_depth_in"]),
            "max_grade_pct": float(v["max_grade_pct"]),
            "max_side_slope_pct": float(v["max_side_slope_pct"]),
            "tire_or_track": v["tire_or_track"],
            "powertrain": v["powertrain"],
        }
        for v in VEHICLES
    ]
    user = (
        f"TERRAIN_REPORT = {json.dumps(terrain)}\n"
        f"FLEET = {json.dumps(fleet)}\n"
        f"Schema = {json.dumps(MATRIX_SCHEMA)}"
    )
    return chat_json(
        [
            {"role": "system", "content": MATRIX_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.25,
        schema_hint="matrix array, convoy_call string, narrator string",
    )


# ---------------------------------------------------------------------------
# Streaming narrator (separate, gives the demo a 'streaming' moment)
# ---------------------------------------------------------------------------
def stream_narrator(terrain: dict, matrix: dict) -> Iterator[str]:
    client = get_client()
    sys_msg = (
        "You are the STRIDER tactical voice. Deliver a calm, terse, radio-style "
        "convoy brief. Use the per-vehicle matrix verbatim ('ALPV: GO. JLTV: GO "
        "with caution.'). End with the binding constraint and a recommended "
        "alternate route hint. 5 sentences max."
    )
    msg = (
        f"Terrain: {json.dumps(terrain)}\n"
        f"Vehicle matrix: {json.dumps(matrix.get('matrix', []))}\n"
        f"Convoy call: {matrix.get('convoy_call')}"
    )
    chain = ["gpt-4o-mini", "gpt-4o"]
    for model in chain:
        try:
            stream = client.chat.completions.create(
                model=model,
                temperature=0.4,
                stream=True,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": msg},
                ],
            )
            buf = ""
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    buf += delta
                    yield buf
            return
        except Exception:
            continue
    yield matrix.get("narrator", "Narrator unavailable.")


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
COLOR_HEX = {"green": "#00BB7A", "amber": "#FFB400", "red": "#E5484D"}


def matrix_to_html(matrix: dict) -> str:
    rows = matrix.get("matrix", [])
    convoy_call = matrix.get("convoy_call", "—")
    convoy_color = (
        "#00BB7A" if convoy_call == "GO"
        else "#E5484D" if convoy_call == "NO-GO"
        else "#FFB400"
    )
    body = []
    for r in rows:
        c = COLOR_HEX.get(str(r.get("color", "")).lower(), "#7E7E7E")
        body.append(
            f"<tr style='background:#0E0E0E;'>"
            f"<td style='padding:10px 14px;color:#fff;font-weight:600;'>{r.get('vehicle_id','')}</td>"
            f"<td style='padding:10px 14px;'>"
            f"<span style='background:{c};color:#0A0A0A;padding:4px 10px;border-radius:6px;font-weight:700;font-size:13px;'>"
            f"{r.get('recommendation','?')}</span></td>"
            f"<td style='padding:10px 14px;color:#cfcfcf;font-size:14px;'>{r.get('reason','')}</td>"
            f"</tr>"
        )
    table = (
        "<table style='width:100%;border-collapse:collapse;border:1px solid #222;border-radius:8px;overflow:hidden;font-family:Helvetica,Arial,sans-serif;'>"
        "<thead><tr style='background:#111;color:#00FFA7;text-align:left;'>"
        "<th style='padding:10px 14px;'>Vehicle</th>"
        "<th style='padding:10px 14px;'>Call</th>"
        "<th style='padding:10px 14px;'>Binding constraint</th>"
        "</tr></thead><tbody>"
        + "".join(body) +
        "</tbody></table>"
    )
    header = (
        f"<div style='margin-bottom:12px;font-size:18px;color:#fff;'>"
        f"Convoy call: "
        f"<span style='background:{convoy_color};color:#0A0A0A;padding:4px 12px;border-radius:6px;font-weight:800;'>"
        f"{convoy_call}</span></div>"
    )
    return header + table


def terrain_to_html(t: dict) -> str:
    keys = [
        ("cover_type", "Cover"),
        ("surface_firmness", "Firmness"),
        ("slope_estimate_pct", "Grade %"),
        ("side_slope_pct", "Side slope %"),
        ("water_present", "Water"),
        ("water_depth_in_est", "Depth (in)"),
        ("visibility_conditions", "Visibility"),
        ("confidence", "Confidence"),
    ]
    rows = []
    for k, label in keys:
        v = t.get(k, "—")
        rows.append(
            f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1a1a;'>"
            f"<span style='color:#7E7E7E;'>{label}</span>"
            f"<span style='color:#00FFA7;font-weight:600;'>{v}</span></div>"
        )
    obs = t.get("obstacles", []) or []
    obs_html = ""
    if obs:
        chips = "".join(
            f"<span style='background:#222;color:#fff;padding:3px 8px;border-radius:12px;margin:2px;display:inline-block;font-size:12px;'>{o}</span>"
            for o in obs
        )
        obs_html = f"<div style='margin-top:10px;'><div style='color:#7E7E7E;margin-bottom:4px;'>Obstacles</div>{chips}</div>"
    summary = t.get("summary", "")
    return (
        "<div style='background:#0E0E0E;border:1px solid #222;border-radius:8px;padding:14px;font-family:Helvetica,Arial,sans-serif;'>"
        + "".join(rows)
        + obs_html
        + (f"<div style='margin-top:12px;color:#cfcfcf;font-style:italic;'>{summary}</div>" if summary else "")
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def analyze(image: Image.Image | None):
    if image is None:
        yield (
            "<div style='color:#E5484D;'>Upload or pick a sample terrain image.</div>",
            "<div></div>",
            "{}",
            "Awaiting image.",
        )
        return

    # Step 1 — vision
    yield (
        "<div style='color:#00FFA7;'>STRIDER vision call running on Kamiwaza-deployed multimodal ...</div>",
        "<div></div>",
        "{}",
        "Calling vision model...",
    )
    terrain = vision_classify(image)

    # Step 2 — matrix
    yield (
        terrain_to_html(terrain),
        "<div style='color:#00FFA7;'>Cross-referencing fleet specs ...</div>",
        json.dumps(terrain, indent=2),
        "Reasoning over fleet...",
    )
    matrix = reason_matrix(terrain)

    # Step 3 — initial render
    yield (
        terrain_to_html(terrain),
        matrix_to_html(matrix),
        json.dumps({"terrain": terrain, "matrix": matrix}, indent=2),
        "Streaming narrator brief...",
    )

    # Step 4 — stream the narrator
    last = ""
    for partial in stream_narrator(terrain, matrix):
        last = partial
        yield (
            terrain_to_html(terrain),
            matrix_to_html(matrix),
            json.dumps({"terrain": terrain, "matrix": matrix}, indent=2),
            last,
        )
    if not last:
        yield (
            terrain_to_html(terrain),
            matrix_to_html(matrix),
            json.dumps({"terrain": terrain, "matrix": matrix}, indent=2),
            matrix.get("narrator", ""),
        )


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------
THEME = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#E6FBF2", c100="#C9F5E0", c200="#9BEBC4", c300="#6BDFA6",
        c400="#3DD389", c500="#00BB7A", c600="#00A86C", c700="#008B59",
        c800="#066D45", c900="#054A30", c950="#022619",
    ),
    neutral_hue=gr.themes.Color(
        c50="#fafafa", c100="#f4f4f5", c200="#e4e4e7", c300="#d4d4d8",
        c400="#a1a1aa", c500="#7E7E7E", c600="#52525b", c700="#3f3f46",
        c800="#222222", c900="#111111", c950="#0A0A0A",
    ),
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "Helvetica"],
).set(
    body_background_fill=BRAND["bg"],
    body_background_fill_dark=BRAND["bg"],
    background_fill_primary=BRAND["surface"],
    background_fill_primary_dark=BRAND["surface"],
    background_fill_secondary=BRAND["surface_high"],
    background_fill_secondary_dark=BRAND["surface_high"],
    border_color_primary=BRAND["border"],
    border_color_primary_dark=BRAND["border"],
    button_primary_background_fill=BRAND["primary"],
    button_primary_background_fill_hover=BRAND["primary_hover"],
    button_primary_text_color="#0A0A0A",
    body_text_color="#EAEAEA",
    body_text_color_dark="#EAEAEA",
)

CSS = """
.gradio-container {background:#0A0A0A !important;color:#EAEAEA !important;}
footer {display:none !important;}
.strider-header {display:flex;align-items:center;justify-content:space-between;padding:12px 8px;border-bottom:1px solid #222;margin-bottom:12px;}
.strider-title {color:#00FFA7;font-size:24px;font-weight:800;letter-spacing:1px;}
.strider-tag {color:#7E7E7E;font-size:13px;}
.strider-footer {text-align:center;color:#7E7E7E;padding:14px 0 6px 0;border-top:1px solid #222;margin-top:14px;font-size:12px;letter-spacing:1px;}
.kamiwaza-pill {background:#00BB7A;color:#0A0A0A;padding:2px 8px;border-radius:6px;font-weight:700;}
"""

HEADER_HTML = """
<div class='strider-header'>
  <div>
    <div class='strider-title'>STRIDER #07</div>
    <div class='strider-tag'>Surface Terrain Recognition &amp; Intelligence for Deployed Expeditionary Routes</div>
  </div>
  <div style='text-align:right;'>
    <div style='color:#fff;font-size:14px;'>USMC LOGCOM &middot; MDM 2026</div>
    <div class='strider-tag'>Dataset: <span style='color:#00FFA7'>GOOSE</span> German Outdoor &amp; Offroad &middot; <span class='kamiwaza-pill'>On-prem ready</span></div>
  </div>
</div>
"""

MISSION_HTML = """
<div style='background:#0E0E0E;border:1px solid #222;border-radius:8px;padding:14px;color:#cfcfcf;font-size:14px;'>
  <span style='color:#00FFA7;font-weight:700;'>MISSION FRAME.</span>
  Force Design 2030 puts Marines in places maps don't reach. STRIDER tells autonomous
  logistics convoys (ALPV, autonomous tow tractors, UGV mules) what they're rolling onto —
  before they roll. Ground rover snaps a frame; the Kamiwaza-deployed vision model returns a structured terrain
  report, the reasoner cross-references fleet ground-clearance and fording depth, and
  every vehicle gets a green / amber / red call with the binding constraint named.
</div>
"""

FOOTER_HTML = """
<div class='strider-footer'>
  Powered by Kamiwaza &middot; KAMIWAZA_BASE_URL swap = 100% data containment &middot;
  IL5 / IL6 ready &middot; STIG-hardened &middot; vLLM behind /v1/chat/completions
</div>
"""


def sample_choices():
    return sorted(str(p) for p in IMG_DIR.glob("*.jpg"))


def load_sample(path: str | None) -> Image.Image | None:
    if not path:
        return None
    return Image.open(path)


with gr.Blocks(title="STRIDER #07 — USMC LOGCOM") as demo:
    gr.HTML(HEADER_HTML)
    gr.HTML(MISSION_HTML)

    with gr.Row():
        with gr.Column(scale=4):
            gr.Markdown("### Step 1 — drop a terrain frame")
            img_in = gr.Image(
                type="pil",
                label="Forward-rover / dashcam / ISR still",
                height=360,
            )
            sample_dd = gr.Dropdown(
                choices=sample_choices(),
                label="Or pick a synthetic sample (GOOSE-style swatches)",
                value=None,
                interactive=True,
            )
            run_btn = gr.Button("Run STRIDER analysis", variant="primary", size="lg")

            gr.Markdown("### Fleet specifications (synthetic but plausible)")
            gr.Dataframe(
                value=vehicles_table(),
                interactive=False,
                wrap=True,
                row_count=(len(VEHICLES), "fixed"),
            )

        with gr.Column(scale=6):
            gr.Markdown("### Step 2 — terrain report (vision)")
            terrain_html = gr.HTML(value="<div style='color:#7E7E7E;'>No image yet.</div>")
            gr.Markdown("### Step 3 — vehicle compatibility matrix")
            matrix_html = gr.HTML(value="<div style='color:#7E7E7E;'>Waiting for analysis.</div>")
            gr.Markdown("### Step 4 — convoy commander brief")
            narrator_box = gr.Textbox(
                label="STRIDER tactical voice",
                lines=5,
                interactive=False,
                value="Awaiting image.",
            )
            with gr.Accordion("Raw JSON (operator audit trail)", open=False):
                json_box = gr.Code(value="{}", language="json", lines=18)

    gr.HTML(FOOTER_HTML)

    sample_dd.change(fn=load_sample, inputs=sample_dd, outputs=img_in)
    run_btn.click(
        fn=analyze,
        inputs=img_in,
        outputs=[terrain_html, matrix_html, json_box, narrator_box],
    )


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=3007,
        inbrowser=False,
        theme=THEME,
        css=CSS,
    )
