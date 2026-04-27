# WEATHERVANE — mission-window environmental brief
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""LLM fusion agent for WEATHERVANE.

Two LLM calls per brief:
  1. chat_json — typed H-hour recommendation (start/end window, go/no-go grade, risk tags)
  2. chat     — narrative environmental brief, planner-grade prose

Both consume the same compact summary of the timeseries window so the JSON
recommendation and prose stay coherent.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Allow `from shared.kamiwaza_client import ...` when running via streamlit
ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402


MISSION_PROFILES = {
    "Amphibious landing": {
        "max_hs_m": 1.25,
        "max_wind_kn": 18,
        "max_precip_mmhr": 2.0,
        "min_visibility_proxy_cloud_pct": 85,  # cloud > 85% degrades CAS / observation
        "notes": "LCAC operations require Hs<=1.25m. Wind onshore >18kn unsafe for craft recovery.",
    },
    "Drone ISR sortie": {
        "max_hs_m": 99,
        "max_wind_kn": 22,
        "max_precip_mmhr": 0.5,
        "min_visibility_proxy_cloud_pct": 70,
        "notes": "Group-3 UAS sensitive to precip + dense cloud (degrades EO/IR collection).",
    },
    "Fast-rope insert (helo)": {
        "max_hs_m": 99,
        "max_wind_kn": 25,
        "max_precip_mmhr": 1.5,
        "min_visibility_proxy_cloud_pct": 60,
        "notes": "Rotorwash + downdrafts: sustained wind >25kn or low ceilings are no-go.",
    },
    "Surface resupply (LCU/LCAC)": {
        "max_hs_m": 1.5,
        "max_wind_kn": 20,
        "max_precip_mmhr": 3.0,
        "min_visibility_proxy_cloud_pct": 90,
        "notes": "Sustained Hs>1.5m halts beach throughput.",
    },
}


def slice_window(df: pd.DataFrame, start_iso: str, end_iso: str) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    start = pd.to_datetime(start_iso, utc=True)
    end = pd.to_datetime(end_iso, utc=True)
    return df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].reset_index(drop=True)


def summarize_window(df: pd.DataFrame) -> dict[str, Any]:
    """Compact stats the LLM can reason over without seeing 168+ rows."""
    if df.empty:
        return {}
    out = {
        "rows": int(len(df)),
        "start": df["timestamp"].iloc[0].isoformat(),
        "end": df["timestamp"].iloc[-1].isoformat(),
    }
    for col, label in [("hs_m", "Hs (m)"), ("wind_kn", "Wind (kn)"),
                       ("precip_mmhr", "Precip (mm/hr)"), ("sst_c", "SST (C)"),
                       ("cloud_pct", "Cloud (%)")]:
        s = df[col]
        out[col] = {
            "min": round(float(s.min()), 2),
            "mean": round(float(s.mean()), 2),
            "max": round(float(s.max()), 2),
            "p90": round(float(s.quantile(0.9)), 2),
            "label": label,
        }
    # Find a candidate calmest 4-hour window using rolling penalty score
    score = (df["hs_m"] / 1.5) + (df["wind_kn"] / 20) + (df["precip_mmhr"] / 3) + (df["cloud_pct"] / 100)
    rolling = score.rolling(4, min_periods=4).mean()
    if rolling.notna().any():
        idx = int(rolling.idxmin())
        win_start = df["timestamp"].iloc[max(0, idx - 3)]
        win_end = df["timestamp"].iloc[idx]
        out["calmest_4h_candidate"] = {
            "start": win_start.isoformat(),
            "end": win_end.isoformat(),
            "score": round(float(rolling.iloc[idx]), 3),
        }
    return out


def recommend_window(summary: dict, location_name: str, mission: str) -> dict:
    """LLM JSON-mode call returning typed H-hour recommendation."""
    profile = MISSION_PROFILES.get(mission, MISSION_PROFILES["Amphibious landing"])
    schema_hint = (
        '{"grade": "GO" | "CAUTION" | "NO-GO", '
        '"recommended_window": {"start": "ISO8601", "end": "ISO8601"}, '
        '"alt_window": {"start": "ISO8601", "end": "ISO8601"} | null, '
        '"confidence_pct": integer 0-100, '
        '"top_risks": ["short label", ...] (1-4 items, each <=5 words), '
        '"one_liner": "single-sentence call to the planner"}'
    )
    sys_prompt = (
        "You are a USMC operational meteorologist embedded with a MARFORPAC planning cell. "
        "You read fused NASA Earth-observation data (MERRA-2 winds, GPM IMERG precip, GHRSST SST, "
        "MODIS cloud, WAVEWATCH III Hs) and produce typed mission recommendations.\n\n"
        "OUTPUT: a single JSON object with EXACTLY these top-level keys: "
        "grade, recommended_window, alt_window, confidence_pct, top_risks, one_liner. "
        "No extra keys. No prose outside JSON."
    )
    user_prompt = (
        f"Location: {location_name}\n"
        f"Mission profile: {mission}\n"
        f"Mission constraints: {json.dumps(profile)}\n"
        f"Window summary stats from fused NASA timeseries:\n{json.dumps(summary, indent=2)}\n\n"
        f"Required JSON schema:\n{schema_hint}\n\n"
        "Rules:\n"
        "- recommended_window must lie WITHIN summary.start..summary.end and be ~4 hours long.\n"
        "- Prefer the calmest_4h_candidate if it satisfies constraints; otherwise shift to the "
        "closest 4-hour block that does.\n"
        "- If NO 4h block satisfies, set grade=\"NO-GO\" and return the least-bad 4h block.\n"
        "- grade=\"GO\" requires all constraints satisfied; \"CAUTION\" if borderline; \"NO-GO\" if exceeded.\n"
        "- top_risks are short tags like \"surf > 1.5 m\", \"wind gusts 25 kn\", \"cloud > 90%\".\n"
        "- Use ISO8601 with timezone offset. Be concise."
    )
    return chat_json(
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema_hint=schema_hint,
        temperature=0.2,
    )


def write_brief(summary: dict, recommendation: dict, location_name: str, mission: str,
                *, hero_model: str | None = None) -> str:
    """LLM narrative brief — planner-grade prose."""
    sys_prompt = (
        "You are a USMC operational meteorologist. Write a tight environmental brief for a Marine "
        "planner. Format: 5 short sections separated by blank lines: "
        "BLUF, Sea State, Atmospherics, Risk Callouts, Recommendation. "
        "Reference specific numbers with units. Cite the source ('per fused NASA MERRA-2 / GPM / "
        "MODIS / GHRSST / WAVEWATCH III'). No markdown headers, just SECTION NAME: text. "
        "Maximum 220 words total. End with the recommended H-hour window in HHMM-HHMM Zulu format."
    )
    user_prompt = (
        f"Location: {location_name}\n"
        f"Mission profile: {mission}\n"
        f"Window stats:\n{json.dumps(summary, indent=2)}\n"
        f"Typed recommendation produced upstream (you must remain consistent):\n"
        f"{json.dumps(recommendation, indent=2)}\n"
    )
    return chat(
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=hero_model,
        temperature=0.35,
        max_tokens=600,
    )


def _normalize_recommendation(rec: dict, summary: dict) -> dict:
    """Coerce loose LLM output to the UI's expected shape."""
    out = dict(rec) if isinstance(rec, dict) else {}
    # Map alternate key names the LLM sometimes invents
    if "decision" in out and "grade" not in out:
        out["grade"] = out["decision"]
    if "go_no_go" in out and "grade" not in out:
        out["grade"] = out["go_no_go"]
    out.setdefault("grade", "CAUTION")
    out["grade"] = str(out["grade"]).upper().replace(" ", "-")

    out.setdefault("confidence_pct", 70)
    try:
        out["confidence_pct"] = int(round(float(out["confidence_pct"])))
    except Exception:
        out["confidence_pct"] = 70

    out.setdefault("top_risks", [])
    if not isinstance(out["top_risks"], list):
        out["top_risks"] = [str(out["top_risks"])]

    if not out.get("one_liner"):
        if "summary" in out and isinstance(out["summary"], str):
            out["one_liner"] = out["summary"]
        elif "assessment" in out and isinstance(out["assessment"], dict):
            out["one_liner"] = str(out["assessment"].get("overall", ""))
        else:
            out["one_liner"] = f"{out['grade']} for the proposed window."

    # Ensure recommended_window has a sane default if missing
    if not isinstance(out.get("recommended_window"), dict):
        cand = summary.get("calmest_4h_candidate") or {}
        out["recommended_window"] = {
            "start": cand.get("start", summary.get("start")),
            "end": cand.get("end", summary.get("end")),
        }
    return out


def fuse(df: pd.DataFrame, *, location_name: str, start_iso: str, end_iso: str,
         mission: str, hero: bool = False) -> dict:
    """Top-level entry: window the data, summarize, call LLM twice, return everything."""
    window = slice_window(df, start_iso, end_iso)
    summary = summarize_window(window)
    if not summary:
        return {"error": "Empty window. Widen the date range."}

    raw_rec = recommend_window(summary, location_name, mission)
    recommendation = _normalize_recommendation(raw_rec, summary)
    brief = write_brief(
        summary, recommendation, location_name, mission,
        hero_model="gpt-5.4" if hero else None,
    )
    return {
        "summary": summary,
        "recommendation": recommendation,
        "brief": brief,
        "window_df": window,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
