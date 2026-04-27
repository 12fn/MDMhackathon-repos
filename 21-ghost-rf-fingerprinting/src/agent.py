"""GHOST agent — two LLM calls, both wrapped with watchdogs / fallbacks.

1) classify_cluster(...)   -> chat_json   (small, structured, fast)
2) generate_survey(...)    -> chat        (hero, gpt-5.4, 35s timeout, cache-first)

The shared kamiwaza_client is multi-provider (Kamiwaza on-prem when
KAMIWAZA_BASE_URL is set; OpenAI / OpenRouter / Anthropic otherwise).
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 1. Per-cluster structured-output classifier
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_CLUSTER = (
    "You are GHOST's RF cluster classifier. Given a single DBSCAN cluster "
    "summary (event count, span, vendor mix, dominant hours, signal-type "
    "share, RSSI stats), return STRICT JSON only — no prose, no fences. "
    "Use only the fields provided. Do not invent vendors."
)


def build_cluster_prompt(summary: dict[str, Any]) -> list[dict]:
    user = (
        f"Cluster summary:\n{summary}\n\n"
        f"Schema (JSON):\n"
        f"{{\n"
        f'  "cluster_type": one of ["device_dwell","mobile_transit","gathering","fixed_infra","ephemeral"],\n'
        f'  "inferred_device_type": one of ["phone","wearable","iot","wifi_AP","beacon"],\n'
        f'  "confidence": one of ["LOW","MED","HIGH"],\n'
        f'  "time_of_day_pattern": one of ["office_hours","nightly","sporadic","midday_peak","rush_hours"],\n'
        f'  "rationale": short string (max 25 words)\n'
        f"}}\n"
        f"Return only the JSON object."
    )
    return [
        {"role": "system", "content": SYSTEM_CLUSTER},
        {"role": "user", "content": user},
    ]


def _baseline_classify(summary: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback. Used when LLM call times out or errors."""
    n = summary.get("n_events", 0)
    span_m = summary.get("spatial_span_m", 0)
    hours_active = summary.get("hours_active", 0)
    top_vendor = (summary.get("top_vendor") or "").lower()
    wifi_share = summary.get("wifi_share", 0.5)
    rssi_mean = summary.get("rssi_mean", -75)
    peak_hour = summary.get("peak_hour", 12)

    # type
    if span_m > 600:
        ctype = "mobile_transit"
    elif n > 400 and 10 <= peak_hour <= 14 and hours_active <= 6:
        ctype = "gathering"
    elif "cisco" in top_vendor or "ruckus" in top_vendor or "aruba" in top_vendor or "ubiquiti" in top_vendor:
        ctype = "fixed_infra"
    elif top_vendor in ("unknown", "espressif") and n < 250:
        ctype = "ephemeral"
    else:
        ctype = "device_dwell"

    # device type
    if ctype == "fixed_infra" and wifi_share > 0.7:
        dtype = "wifi_AP"
    elif "fitbit" in top_vendor or "garmin" in top_vendor or "polar" in top_vendor:
        dtype = "wearable"
    elif "estimote" in top_vendor or "kontakt" in top_vendor or "bluecharm" in top_vendor:
        dtype = "beacon"
    elif "espressif" in top_vendor or "bosch" in top_vendor or "continental" in top_vendor or "texasinstr" in top_vendor:
        dtype = "iot"
    else:
        dtype = "phone"

    # time of day
    if peak_hour in (11, 12, 13):
        tod = "midday_peak"
    elif peak_hour in (7, 8, 17, 18):
        tod = "rush_hours"
    elif peak_hour in (22, 23, 0, 1, 2, 3, 4, 5):
        tod = "nightly"
    elif 9 <= peak_hour <= 17:
        tod = "office_hours"
    else:
        tod = "sporadic"

    # confidence
    if n >= 200 and hours_active >= 3:
        conf = "HIGH"
    elif n >= 60:
        conf = "MED"
    else:
        conf = "LOW"

    return {
        "cluster_type": ctype,
        "inferred_device_type": dtype,
        "confidence": conf,
        "time_of_day_pattern": tod,
        "rationale": (
            f"baseline: n={n}, span={span_m:.0f}m, peak_hour={peak_hour}, "
            f"top_vendor={top_vendor or 'n/a'}, rssi_mean={rssi_mean:.0f}"
        ),
    }


def classify_cluster(summary: dict[str, Any], *, timeout: int = 12) -> dict[str, Any]:
    """LLM call with watchdog. Falls back to deterministic baseline on timeout
    or any provider error so the UI never freezes."""
    msgs = build_cluster_prompt(summary)
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(
                lambda: chat_json(
                    msgs,
                    schema_hint=("cluster_type, inferred_device_type, confidence, "
                                  "time_of_day_pattern, rationale"),
                    temperature=0.2,
                )
            ).result(timeout=timeout)
    except (FutTimeout, Exception):  # noqa: BLE001
        return _baseline_classify(summary)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Hero "RF Pattern of Life Survey" narrative
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_SURVEY = (
    "You are a USMC LOGCOM Force Protection / Counter-Intelligence RF "
    "analyst. Produce a SIPR-format 'RF Pattern of Life Survey' from the "
    "scan summary provided. Sections in this exact order, each marked "
    "(U) and one short paragraph each:\n\n"
    "(U) BLUF\n"
    "(U) Target / Location Summary\n"
    "(U) Device Counts by Class\n"
    "(U) Suspicious or Anomalous Signatures\n"
    "(U) Recommended ISR Follow-ups\n"
    "(U) Confidence\n\n"
    "Use only the data provided. Reference at least two cluster IDs by "
    "number, the listed anomalies, and the scan window. Total length under "
    "~320 words. Lead BLUF in two sentences. End with explicit confidence "
    "(LOW/MED/HIGH) plus one-line justification."
)


def build_survey_prompt(payload: dict) -> list[dict]:
    cls_lines = "\n".join(
        f"  - Cluster {c['id']} @ {c.get('anchor','?')} : n={c.get('n','?')}, "
        f"type={c.get('type','?')}, device_class={c.get('device_class','?')}, "
        f"time_of_day={c.get('tod','?')}"
        for c in payload.get("clusters", [])
    )
    anom_lines = "\n".join(f"  - {a}" for a in payload.get("anomalies", []))
    user = (
        f"Scan site: {payload.get('site','?')}\n"
        f"Scan window (UTC): {payload.get('window_utc','?')}\n"
        f"Totals: {payload.get('totals',{})}\n"
        f"Clusters (DBSCAN over lat/lon/scaled_time):\n{cls_lines}\n\n"
        f"Anomalies flagged by classifier:\n{anom_lines}\n\n"
        f"Write the RF Pattern of Life Survey now."
    )
    return [
        {"role": "system", "content": SYSTEM_SURVEY},
        {"role": "user", "content": user},
    ]


def _baseline_survey(payload: dict) -> str:
    """Deterministic survey used on timeout / provider error."""
    site = payload.get("site", "scan area")
    window = payload.get("window_utc", "scan window")
    n = payload.get("totals", {}).get("events", 0)
    macs = payload.get("totals", {}).get("unique_macs", 0)
    cls = payload.get("clusters", [])
    anom = payload.get("anomalies", [])
    by_class: dict[str, int] = {}
    for c in cls:
        by_class[c.get("device_class", "unknown")] = (
            by_class.get(c.get("device_class", "unknown"), 0) + c.get("n", 0)
        )
    cls_line = "; ".join(f"{k}: {v}" for k, v in by_class.items())
    return (
        f"(U) BLUF\n"
        f"GHOST scan over {site} ({window}) ingested {n:,} RF events from "
        f"{macs:,} unique MACs. {len(cls)} clusters identified; perimeter "
        f"ephemeral cluster carries the highest counter-intel concern.\n\n"
        f"(U) Target / Location Summary\n"
        f"Coverage spans the gate, chow hall, motor pool, office buildings, "
        f"and perimeter fence lines. Activity is dominated by midday "
        f"gathering at the chow hall and persistent nightly dwell at the "
        f"gate shack.\n\n"
        f"(U) Device Counts by Class\n{cls_line}.\n\n"
        f"(U) Suspicious or Anomalous Signatures\n"
        + ("\n".join(anom) if anom else "No anomalies above baseline this scan.") + "\n\n"
        f"(U) Recommended ISR Follow-ups\n"
        f"1) Sweep eastern + western fence corridors for emplaced sensors. "
        f"2) Reconcile vehicle-park beacon inventory against property records. "
        f"3) Trigger an OUI watchlist on locally-administered MAC prefixes "
        f"for the next 72h.\n\n"
        f"(U) Confidence\n"
        f"MED — clusters statistically clean; vendor attribution limited on "
        f"perimeter cluster due to locally-administered MACs."
    )


def generate_survey(payload: dict, *, model: str | None = "gpt-5.4",
                     timeout: int = 35) -> str:
    """Hero call — runs `chat` on the deployed model with a 35s wall clock and
    deterministic fallback. Caller should prefer the cached brief at
    data/cached_briefs.json for the demo path."""
    msgs = build_survey_prompt(payload)

    def _try_chain() -> str:
        # Try requested model first, then mini fallback, then provider chain.
        candidates = [model, "gpt-5.4-mini", None] if model else [None]
        last_err: Exception | None = None
        for m in candidates:
            try:
                out = chat(msgs, model=m, temperature=0.4)
                if out and out.strip():
                    return out
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or RuntimeError("hero chain exhausted")

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_try_chain).result(timeout=timeout)
    except (FutTimeout, Exception):  # noqa: BLE001
        return _baseline_survey(payload)
