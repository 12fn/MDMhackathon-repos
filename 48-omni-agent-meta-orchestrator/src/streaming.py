"""OMNI-AGENT streaming-UI helpers.

Centralizes the visual chrome for the live tool-call trace + provenance map
+ ledger animations. Pure rendering — no Streamlit imports here so the code
is testable. The Streamlit app pipes events through `render_event(...)`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Event types
# ─────────────────────────────────────────────────────────────────────────────
EV_USER         = "user"
EV_MODEL_CHOSEN = "model_chosen"
EV_MODEL_MSG    = "model_message"
EV_TOOL_CALL    = "tool_call"
EV_TOOL_RESULT  = "tool_result"
EV_FINAL        = "final"
EV_ROUTE_DECISION = "route_decision"  # Kamiwaza routing decision


@dataclass
class CardSpec:
    """Compact data for one streaming sibling-app card."""
    codename: str
    port: int
    dataset: str
    brand_color: str
    icon: str
    args_preview: str
    latency_ms: int | None = None
    live: bool | None = None
    kamiwaza_feature: str | None = None


def card_html(c: CardSpec, surface: str = "#111111", border: str = "#222222",
              neon: str = "#00FFA7", muted: str = "#7E7E7E") -> str:
    """Render one tool-call card. Used for both pre-call (no latency) +
    post-call (with latency) rendering."""
    badge = ""
    if c.kamiwaza_feature:
        badge = (f"<span style='background:{c.brand_color}; color:#000; "
                 "padding:1px 8px; border-radius:8px; font-size:10px; "
                 f"font-weight:700; margin-left:6px;'>"
                 f"KAMIWAZA::{c.kamiwaza_feature.upper()}</span>")
    live_pill = ""
    if c.live is True:
        live_pill = (f"<span style='color:{neon}; font-size:10px; "
                     "font-weight:600; letter-spacing:.05em;'>LIVE</span>")
    elif c.live is False:
        live_pill = (f"<span style='color:{muted}; font-size:10px;'>cached</span>")
    latency = (
        f"<span style='float:right; color:{neon}; font-family:ui-monospace; "
        f"font-size:11px;'>{c.latency_ms} ms</span>"
        if c.latency_ms is not None else
        f"<span style='float:right; color:{muted}; font-family:ui-monospace; "
        "font-size:11px;'>...</span>"
    )
    return (
        f"<div style='padding:10px 12px; margin:6px 0; "
        f"background:{surface}; border:1px solid {border}; "
        f"border-left:3px solid {c.brand_color}; border-radius:6px;'>"
        f"  <div>"
        f"    <span style='font-size:18px; margin-right:6px;'>{c.icon}</span>"
        f"    <span style='color:{c.brand_color}; font-weight:700; "
        f"          letter-spacing:.04em;'>{c.codename}</span>"
        f"    <span style='color:{muted}; font-size:11px;'>"
        f"      :{c.port}</span>"
        f"    {badge} &nbsp;{live_pill}"
        f"    {latency}"
        f"  </div>"
        f"  <div style='color:{muted}; font-size:11px; margin-top:3px;'>"
        f"    args: <code style='color:#CCCCCC;'>{c.args_preview}</code></div>"
        f"  <div style='color:{muted}; font-size:11px; margin-top:2px;'>"
        f"    dataset: {c.dataset[:80]}</div>"
        f"</div>"
    )


def routing_card_html(decision: dict, brand_color: str = "#00FFA7",
                      surface: str = "#111111", border: str = "#222222",
                      neon: str = "#00FFA7", muted: str = "#7E7E7E") -> str:
    """Special card for Kamiwaza Inference Mesh / FED-RAG / ReBAC routing decisions."""
    feature = decision.get("kamiwaza_feature", "kamiwaza").upper()
    sens = decision.get("sensitivity", "")
    selected = decision.get("selected_node") or decision.get("verdict") or "?"
    return (
        f"<div style='padding:14px 16px; margin:8px 0; "
        f"background:linear-gradient(90deg, {surface} 60%, #053024 100%); "
        f"border:1px solid {brand_color}; border-radius:8px; "
        f"box-shadow:0 0 18px rgba(0,255,167,.18);'>"
        f"  <div style='color:{brand_color}; font-weight:700; "
        f"        letter-spacing:.06em; font-size:12px;'>"
        f"    KAMIWAZA :: {feature}{(' :: SENSITIVITY ' + sens) if sens else ''}</div>"
        f"  <div style='color:#FFFFFF; font-size:14px; margin-top:4px;'>"
        f"    Routed -&gt; <b style='color:{neon};'>{selected}</b></div>"
        f"  <div style='color:{muted}; font-size:11px; margin-top:4px;'>"
        f"    {decision.get('rationale', '')[:200]}</div>"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Provenance map — fact -> tool tagging
# ─────────────────────────────────────────────────────────────────────────────
def tag_brief_with_provenance(brief: str, tool_outputs: list[dict]) -> str:
    """Walk the fused brief text and tag each line/sentence with the codename
    that contributed it. We use a simple keyword-presence heuristic: if a
    codename is mentioned in a line, OR if the line shares enough keywords
    with that tool's brief, we attribute.

    Returns HTML with each contributing block wrapped in
    `<span class='kw-prov' data-tool='CODENAME' style='border-left-color:...'>`.
    """
    if not brief or not tool_outputs:
        return f"<div>{brief}</div>"

    # Build keyword bag per tool
    bags: dict[str, set[str]] = {}
    colors: dict[str, str] = {}
    for o in tool_outputs:
        cn = (o.get("codename") or "").strip()
        if not cn:
            continue
        colors[cn] = o.get("brand_color", "#00BB7A")
        bag = set()
        text = (o.get("brief") or "")
        for w in re.findall(r"[A-Z][A-Z\-]{2,}|[A-Za-z]{6,}|\d+\.\d+|\d+", text):
            bag.add(w.lower())
        bags[cn] = bag

    out_lines: list[str] = []
    for line in brief.splitlines():
        if not line.strip():
            out_lines.append("<br/>")
            continue
        # Direct codename mention wins
        attributed: list[str] = [cn for cn in bags if cn.upper() in line.upper()]
        if not attributed:
            # Keyword-overlap fallback: pick the tool whose bag overlaps most
            line_words = set(re.findall(r"[A-Za-z]{6,}|\d+\.\d+|\d+", line.lower()))
            scores = {cn: len(bag & line_words) for cn, bag in bags.items()}
            top = max(scores.values(), default=0)
            if top >= 2:
                attributed = [cn for cn, s in scores.items() if s == top]
        if attributed:
            chips = " ".join(
                f"<span style='display:inline-block; background:{colors.get(cn, '#00BB7A')}; "
                f"color:#000; padding:0px 6px; border-radius:8px; font-size:9px; "
                f"font-weight:700; margin-left:4px; vertical-align:1px;'>{cn}</span>"
                for cn in attributed[:3]
            )
            border = colors.get(attributed[0], "#00BB7A")
            out_lines.append(
                f"<div style='border-left:3px solid {border}; padding:3px 0 3px 8px; "
                f"margin:2px 0;'>{line} {chips}</div>"
            )
        else:
            out_lines.append(
                f"<div style='border-left:3px solid #2a2a2a; padding:3px 0 3px 8px; "
                f"margin:2px 0;'>{line}</div>"
            )
    return "<div>" + "".join(out_lines) + "</div>"


def contribution_pct(tool_outputs: list[dict], brief: str) -> list[dict]:
    """Compute a rough per-tool contribution % to the fused brief.

    Heuristic: each tool's contribution = (# of lines in the brief that
    plausibly cite it via codename or keyword-overlap) / total lines.
    """
    if not brief or not tool_outputs:
        return []
    lines = [l for l in brief.splitlines() if l.strip()]
    if not lines:
        return []
    counts: dict[str, int] = {}
    bags: dict[str, set[str]] = {}
    for o in tool_outputs:
        cn = (o.get("codename") or "").strip()
        if not cn:
            continue
        bag = set()
        for w in re.findall(r"[A-Za-z]{6,}|\d+",
                            (o.get("brief") or "")):
            bag.add(w.lower())
        bags[cn] = bag
        counts[cn] = 0
    for line in lines:
        for cn in counts:
            if cn.upper() in line.upper():
                counts[cn] += 2
                break
        else:
            line_words = set(re.findall(r"[A-Za-z]{6,}|\d+", line.lower()))
            scored = sorted(
                ((cn, len(bag & line_words)) for cn, bag in bags.items()),
                key=lambda x: -x[1],
            )
            if scored and scored[0][1] >= 2:
                counts[scored[0][0]] += 1
    total = sum(counts.values()) or 1
    out: list[dict] = []
    for o in tool_outputs:
        cn = (o.get("codename") or "").strip()
        if not cn:
            continue
        pct = round(100 * counts.get(cn, 0) / total, 1)
        out.append({
            "codename": cn,
            "brand_color": o.get("brand_color", "#00BB7A"),
            "kamiwaza_feature": o.get("kamiwaza_feature"),
            "pct": pct,
        })
    out.sort(key=lambda r: -r["pct"])
    return out


def provenance_bar_html(rows: list[dict], surface: str = "#111111",
                        border: str = "#222222", muted: str = "#7E7E7E") -> str:
    """Render the contribution-per-app stacked bar."""
    if not rows:
        return ""
    segments: list[str] = []
    legend: list[str] = []
    for r in rows:
        if r["pct"] <= 0:
            continue
        segments.append(
            f"<div style='flex:{r['pct']}; background:{r['brand_color']}; "
            f"height:20px;' title='{r['codename']}: {r['pct']}%'></div>"
        )
        legend.append(
            f"<span style='display:inline-block; margin-right:10px; "
            f"font-size:11px; color:#CCC;'>"
            f"<span style='display:inline-block; width:8px; height:8px; "
            f"background:{r['brand_color']}; border-radius:2px; "
            f"margin-right:4px; vertical-align:middle;'></span>"
            f"{r['codename']} {r['pct']}%</span>"
        )
    return (
        f"<div style='background:{surface}; border:1px solid {border}; "
        f"border-radius:6px; padding:10px;'>"
        f"  <div style='color:{muted}; font-size:11px; "
        f"        letter-spacing:.06em; margin-bottom:6px;'>"
        f"    PROVENANCE — per-tool contribution to the fused brief</div>"
        f"  <div style='display:flex; border-radius:4px; overflow:hidden; "
        f"        border:1px solid {border};'>{''.join(segments)}</div>"
        f"  <div style='margin-top:8px;'>{''.join(legend)}</div>"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Hash-chain "ledger" rendering
# ─────────────────────────────────────────────────────────────────────────────
def ledger_row_html(rec: dict, neon: str = "#00FFA7",
                    muted: str = "#7E7E7E", surface: str = "#0E0E0E") -> str:
    h = rec.get("hash", "")[:12]
    p = rec.get("prev_hash", "")
    p_short = "GENESIS" if p == "GENESIS" else p[:12]
    return (
        f"<div style='font-family:ui-monospace; font-size:11px; "
        f"padding:4px 8px; margin:2px 0; background:{surface}; "
        f"border:1px solid #1a1a1a; border-radius:4px;'>"
        f"<span style='color:{neon};'>#</span>{h}... "
        f"<span style='color:{muted};'>prev:</span>{p_short}... "
        f"<span style='color:{muted};'>tool:</span>"
        f"<span style='color:#FFF;'>{rec.get('tool', '?')}</span> "
        f"<span style='color:{muted};'>codename:</span>"
        f"{rec.get('result_codename', '?')} "
        f"<span style='color:{muted};'>{rec.get('latency_ms', 0)}ms</span>"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers used by app.py
# ─────────────────────────────────────────────────────────────────────────────
def args_preview(args: dict, max_len: int = 90) -> str:
    s = json.dumps(args, default=str)
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def safe_label_for_model(model: str | None) -> str:
    if not model:
        return "Hero model"
    if "deterministic" in model.lower():
        return "deterministic fallback"
    return "Kamiwaza-deployed model"
