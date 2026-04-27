"""WATCHTOWER cross-stream correlator + Commander's I-COP Brief generator.

Hero AI move: a `chat_json` cross-stream correlator analyzes the last 24h of
fused events and emits structured anomalies. Then a `chat` ("gpt-5.4", 35s
timeout) writes a Commander's I-COP Brief.

Both calls are wrapped in concurrent.futures with a wall-clock timeout and
fall back to deterministic functions on any failure, so the demo never
sits frozen on a spinner.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

HERO_MODEL = "gpt-5.4"
MINI_TIMEOUT = 18
HERO_TIMEOUT = 35


SYSTEM_CORRELATOR = (
    "You are a USMC LOGCOM Installation Common Operating Picture (I-COP) "
    "cross-stream correlator. You consume fused multi-source events from "
    "gate access (DBIDS), utility readings (DPW SCADA), fire/EMS dispatches "
    "(CAD), mass-notification (AtHoc / Giant Voice), weather (NASA Earthdata), "
    "and GCSS-MC maintenance status. You output strict JSON identifying "
    "anomalies that are corroborated ACROSS MULTIPLE STREAMS in the same "
    "time window. Each anomaly must list every stream that contributes "
    "evidence and propose a single concrete recommended action a watch "
    "officer can task in under 60 seconds."
)


SYSTEM_BRIEF = (
    "You are the senior watch officer's AI battle-buddy in the MCB Camp "
    "Pendleton Installation EOC. Draft a Commander's I-COP Brief in plain "
    "text. Use Marine register: BLUF, then the top 3 cross-stream anomalies, "
    "then predictive risk for the next 12 hours, then recommended "
    "pre-positioning actions. End with '//SIGNED// I-COP Aggregator "
    "(WATCHTOWER)'. Do not exceed 320 words."
)


def _correlator_user_prompt(installation_name: str, as_of_iso: str,
                            anomaly_window: list[dict]) -> str:
    return (
        f"Installation: {installation_name}\n"
        f"As of: {as_of_iso}\n\n"
        f"Anomalous fused events (last 24h):\n"
        f"{json.dumps(anomaly_window, indent=2)}\n\n"
        "Return JSON: {\"anomalies\": [{\"anomaly_id\": str, "
        "\"severity\": \"LOW|MEDIUM|HIGH\", "
        "\"contributing_streams\": [str], "
        "\"hypothesis\": str, "
        "\"recommended_action\": str}]} -- 2 to 4 anomalies, sorted by severity desc."
    )


def _brief_user_prompt(installation_name: str, as_of_iso: str,
                       correlation: dict) -> str:
    return (
        f"INSTALLATION: {installation_name}\n"
        f"AS OF: {as_of_iso}\n\n"
        f"CORRELATION JSON:\n{json.dumps(correlation, indent=2)}\n\n"
        "Draft the Commander's I-COP Brief now."
    )


def baseline_correlation(fused: list[dict]) -> dict:
    """Deterministic fallback. Identical to data/generate.py's _baseline_correlation,
    duplicated here so the runtime module is self-contained."""
    anomalies = [f for f in fused if f.get("is_anomaly")]
    streams_present = sorted(set(a["stream"] for a in anomalies))
    out = {
        "anomalies": [
            {
                "anomaly_id": "COP-001",
                "severity": "HIGH",
                "contributing_streams": [s for s in ["ems", "massnotify", "utility", "gate"] if s in streams_present],
                "hypothesis": (
                    "Cross-stream correlation indicates an active structure-fire incident "
                    "vicinity Las Pulgas Magazine 14: P1 multi-unit dispatch coincides with "
                    "a water-pressure dip at the Mainside Water Tower (consistent with "
                    "hydrant draw), a load surge at the 22-Area Substation, an EMERGENCY "
                    "AtHoc broadcast, and a POV ingress spike at Las Pulgas Gate."
                ),
                "recommended_action": (
                    "Activate Installation EOC at COG; pre-position MEDIC-5 to 43-Area as "
                    "backfill; verify Magazine 14 cooling-spray loop pressure; reaffirm "
                    "shelter-in-place via AtHoc; coordinate with CDF for collapse contingency."
                ),
            },
            {
                "anomaly_id": "COP-002",
                "severity": "MEDIUM",
                "contributing_streams": [s for s in ["weather", "ems"] if s in streams_present],
                "hypothesis": (
                    "Santa Ana wind shift to ~14 m/s easterly is concurrent with the "
                    "magazine structure fire; wind alignment is pushing smoke and embers "
                    "toward San Onofre family housing."
                ),
                "recommended_action": (
                    "Pre-stage Engine Co 1 reserves at San Onofre; coordinate with PWD for "
                    "downwind air-quality monitoring; place housing on voluntary evacuation."
                ),
            },
            {
                "anomaly_id": "COP-003",
                "severity": "MEDIUM",
                "contributing_streams": ["maintenance"],
                "hypothesis": (
                    "Three critical assets are NMC during the incident window. The MCFD "
                    "GENSET-MCFD-AUX-3 NMC reduces backup power resilience for Mainside "
                    "Fire Sta 1 exactly when an incident is consuming primary capacity."
                ),
                "recommended_action": (
                    "Direct CLB-1 to expedite voltage-regulator swap on GENSET-MCFD-AUX-3; "
                    "stage HMMWV-44119 / 44123 as Recon backfill; confirm AAV-09921 depot "
                    "induct date does not slip into the next exercise window."
                ),
            },
        ],
        "_source": "deterministic_baseline",
    }
    return out


def baseline_brief(installation_name: str, as_of_iso: str, correlation: dict) -> str:
    bullets = "\n".join(
        f"  - [{a['severity']}] {a['anomaly_id']}: {a['hypothesis']}"
        for a in correlation.get("anomalies", [])[:3]
    )
    actions = "\n".join(
        f"  - {a['recommended_action']}"
        for a in correlation.get("anomalies", [])[:3]
    )
    return (
        f"COMMANDER'S I-COP BRIEF — {installation_name}\n"
        f"AS OF: {as_of_iso}\n\n"
        f"BLUF: Active structure-fire incident at Las Pulgas Magazine 14 with "
        f"cross-stream corroboration across EMS, mass-notification, utility, and "
        f"gate streams. EOC activation recommended. Three critical assets NMC "
        f"during the incident window degrades resilience.\n\n"
        f"TOP 3 CROSS-STREAM ANOMALIES:\n{bullets}\n\n"
        f"PREDICTIVE RISK — NEXT 12H:\n"
        f"  - Santa Ana wind shift (~14 m/s easterly) sustains 6-8h; ember risk "
        f"to San Onofre family housing is the dominant hazard until winds abate.\n"
        f"  - Mainside water pressure expected to recover to baseline (62-78 psi) "
        f"within 90 min of incident-fire suppression.\n"
        f"  - Gate ingress at Las Pulgas should normalize within 60 min of the "
        f"AtHoc UPDATE; if it does not, escalate to PMO traffic-control plan.\n\n"
        f"RECOMMENDED PRE-POSITIONING:\n{actions}\n\n"
        f"//SIGNED// I-COP Aggregator (WATCHTOWER)"
    )


def correlate_streams(installation_name: str, as_of_iso: str,
                      fused: list[dict]) -> dict[str, Any]:
    """Live correlator with watchdog + deterministic fallback."""
    anomaly_window = [f for f in fused if f.get("is_anomaly")]
    messages = [
        {"role": "system", "content": SYSTEM_CORRELATOR},
        {"role": "user", "content": _correlator_user_prompt(
            installation_name, as_of_iso, anomaly_window)},
    ]
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(
                lambda: chat_json(
                    messages,
                    schema_hint=("anomalies[] with anomaly_id, severity, "
                                 "contributing_streams, hypothesis, recommended_action"),
                    temperature=0.25,
                    max_tokens=900,
                )
            )
            result = future.result(timeout=MINI_TIMEOUT)
        if isinstance(result, dict) and "anomalies" in result:
            result["_source"] = "live"
            return result
    except (FutTimeout, Exception):  # noqa: BLE001
        pass
    return baseline_correlation(fused)


def _hero_call(messages: list[dict]) -> str:
    """Direct hero-model call. gpt-5.4 wants max_completion_tokens; older
    chat models want max_tokens. We try the hero param shape first and
    fall back through the shared client's regular fallback chain on error."""
    try:
        from shared.kamiwaza_client import get_client  # noqa: WPS433
        client = get_client()
        resp = client.chat.completions.create(
            model=HERO_MODEL,
            messages=messages,
            max_completion_tokens=900,
        )
        return resp.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        # Fall back to the shared chat() with default model chain.
        return chat(messages, temperature=0.35, max_tokens=900)


def commander_brief(installation_name: str, as_of_iso: str,
                    correlation: dict) -> str:
    """Hero brief writer with watchdog + deterministic fallback."""
    messages = [
        {"role": "system", "content": SYSTEM_BRIEF},
        {"role": "user", "content": _brief_user_prompt(
            installation_name, as_of_iso, correlation)},
    ]
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(lambda: _hero_call(messages))
            text = future.result(timeout=HERO_TIMEOUT)
        if text and text.strip():
            return text
    except (FutTimeout, Exception):  # noqa: BLE001
        pass
    return baseline_brief(installation_name, as_of_iso, correlation)
