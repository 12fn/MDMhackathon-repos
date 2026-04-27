# WILDFIRE — installation wildfire predictor + auto-MASCAL comms
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""WILDFIRE multi-recipient comms package generator.

Hero AI move: ONE structured-output call to the LLM produces a 4-channel
MASCAL communications package, each with the appropriate military
register and length budget for its channel.

Channels:
  marforres_email     — formal HQMC notification, BLUF/EEFI/CCIR
  base_intranet_banner — short, action-prompted banner
  commander_sms       — <= 160 chars, terse
  evacuation_brief    — bullet list of routes + assembly + critical assets

The schema is strict so the UI can render each channel into its own tab.
"""
from __future__ import annotations

import json
from typing import Any

# Hero call may use the larger model; default falls back to chain.
HERO_MODEL = "gpt-5.4"

SYSTEM_PROMPT = """You are the watch officer's AI battle-buddy in a Marine Corps installation Emergency Operations Center (EOC).

Your job: when a wildfire trips a WARNING-level threat against the installation, draft a four-channel MASCAL comms package the watch officer can review and send in under 60 seconds.

Tone: Marine Corps direct. Use BLUF (Bottom Line Up Front), CCIR (Commander's Critical Information Requirements), EEFI (Essential Elements of Friendly Information). Cite specific lat/lon, distance in miles, FRP in MW, wind speed/direction, and the wind-projected risk if a fire is blowing toward the base.

You MUST output strict JSON conforming exactly to the schema. Every key listed in the schema is required. Do NOT inline keys; nest them as objects per the schema. Do NOT emit prose outside the JSON object.

Channel guidance:
  - marforres_email.body: 250-400 words. Includes BLUF, situation, recommended action, EEI follow-ups, signature block placeholder. The body is ONE STRING — do not split it into separate fields. Recipient is HQMC MARFORRES Operations Center (marforres.ops@usmc.mil). From: wildfire-eoc@<base>.usmc.mil.
  - base_intranet_banner.text: 1-2 sentences, 30-50 words max, imperative voice. Color is one of RED|AMBER|YELLOW.
  - commander_sms.text: <= 160 characters. Include lat/lon + nearest road.
  - evacuation_brief.bullets: 6-10 bullets, each begins with a verb. Cover routes, assembly areas, critical assets, EOC reachback.

Always populate incident_id with WX-YYYYMMDD-HHMM-<base-shortname>."""

JSON_SCHEMA_HINT = (
    'Return JSON with this EXACT shape and nesting (every key required, no extras): '
    '{'
    '  "incident_id": "WX-YYYYMMDD-HHMM-<base>", '
    '  "alert_band": "WATCH" | "ALERT" | "WARNING", '
    '  "marforres_email": {"subject": "...", "to": "marforres.ops@usmc.mil", "from": "wildfire-eoc@<base>.usmc.mil", "body": "BLUF... SITUATION... ACTIONS... EEIs... //SIGNED//"}, '
    '  "base_intranet_banner": {"color": "RED" | "AMBER" | "YELLOW", "text": "..."}, '
    '  "commander_sms": {"recipients": ["S3 Watch", "PMO Watch"], "text": "<=160 chars"}, '
    '  "evacuation_brief": {"title": "...", "bullets": ["Verb...", "Verb..."], "eoc_phone": "760-XXX-XXXX"}'
    '}'
)


def _normalize_pkg(pkg: dict, installation: dict, threat_block: dict) -> dict:
    """Coerce loose model output into the strict 4-channel schema.

    Models occasionally inline strings or sub-fields; this rescues the
    output so the UI always renders cleanly without re-prompting.
    """
    out = dict(pkg)
    band = threat_block.get("alert_band", "WARNING")
    nm = installation.get("name", "INSTALLATION")
    inst_id = installation.get("id", "base")
    out.setdefault("incident_id", pkg.get("incident_number") or f"WX-AUTO-{inst_id}")
    out.setdefault("alert_band", band)

    # marforres_email
    em = out.get("marforres_email") or {}
    if isinstance(em, str):
        em = {"subject": f"[{band}] WILDFIRE — {nm}", "body": em}
    if "body" not in em:
        # Stitch any common alt fields into a single body string
        parts = []
        for k in ("bluf", "situation", "recommended_action"):
            v = em.get(k)
            if v:
                parts.append(f"{k.upper()}: {v}")
        ee = em.get("eei_follow_ups") or em.get("eei") or []
        if ee:
            parts.append("EEIs:\n" + "\n".join(f"- {e}" for e in ee))
        sig = em.get("signature_block") or em.get("signature") or "//SIGNED// WILDFIRE EOC"
        parts.append(sig)
        em["body"] = "\n\n".join(parts) if parts else f"BLUF: {band} declared at {nm}."
    em.setdefault("subject", f"[{band}] WILDFIRE — {nm}")
    em.setdefault("to", "marforres.ops@usmc.mil")
    em.setdefault("from", f"wildfire-eoc@{inst_id}.usmc.mil")
    out["marforres_email"] = em

    # base_intranet_banner
    bn = out.get("base_intranet_banner") or {}
    if isinstance(bn, str):
        bn = {"color": "RED" if band == "WARNING" else "AMBER", "text": bn}
    bn.setdefault("color", "RED" if band == "WARNING" else "AMBER")
    bn.setdefault("text", f"{band}: wildfire threat to {nm} — stand by for direction.")
    out["base_intranet_banner"] = bn

    # commander_sms
    sm = out.get("commander_sms") or {}
    if isinstance(sm, str):
        sm = {"recipients": ["S3 Watch", "PMO Watch", "Range Control"], "text": sm}
    sm.setdefault("recipients", ["S3 Watch", "PMO Watch", "Range Control"])
    if "text" not in sm:
        sm["text"] = f"{band}: fire near {nm}. EOC stand-up."
    if len(sm["text"]) > 320:
        sm["text"] = sm["text"][:317] + "..."
    out["commander_sms"] = sm

    # evacuation_brief
    ev = out.get("evacuation_brief") or {}
    if isinstance(ev, list):
        ev = {"title": f"{nm} Evacuation Brief", "bullets": ev, "eoc_phone": "760-XXX-XXXX"}
    if "bullets" not in ev:
        # if body is a string list-shaped, split lines
        lines = (ev.get("text") or "").split("\n")
        ev["bullets"] = [ln.strip("-* ").strip() for ln in lines if ln.strip()]
    if not ev.get("bullets"):
        ev["bullets"] = ["Activate EOC.", "Recall first responders.",
                         "Verify accountability.", "Prep evacuation routes."]
    ev.setdefault("title", f"{nm} Evacuation Brief")
    ev.setdefault("eoc_phone", "760-XXX-XXXX")
    out["evacuation_brief"] = ev
    return out


def build_user_prompt(installation: dict, threat_block: dict, wind_summary: str) -> str:
    """Assemble the data payload the model uses to ground every channel."""
    return f"""SITUATION DATA — derived from NASA FIRMS thermal anomaly pixels and wind forecast.

INSTALLATION:
{json.dumps(installation, indent=2)}

THREAT BLOCK (from WILDFIRE risk engine):
{json.dumps(threat_block, indent=2)}

WIND SUMMARY:
{wind_summary}

TASK:
Draft the 4-channel MASCAL communications package per the schema. Use the installation's evacuation_routes and assembly_areas in the evacuation_brief. Cite at least one specific fire pixel by lat/lon and distance in the email and brief. If alignment > 0.5 anywhere, explicitly call out that the wind is pushing the fire toward the installation."""


def generate_comms_package(
    chat_json_fn,
    installation: dict,
    threat_block: dict,
    wind_summary: str = "",
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Make the hero call. chat_json_fn is shared.kamiwaza_client.chat_json.

    Returns the parsed JSON. On failure, returns a graceful fallback so the
    UI never crashes mid-demo.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(installation, threat_block, wind_summary)},
    ]
    try:
        kw = {"schema_hint": JSON_SCHEMA_HINT, "temperature": 0.35, "max_tokens": 1400}
        if model:
            kw["model"] = model
        raw = chat_json_fn(messages, **kw)
        return _normalize_pkg(raw, installation, threat_block)
    except Exception as e:  # noqa: BLE001
        # Fallback so the demo still has something to render.
        nm = installation.get("name", "INSTALLATION")
        band = threat_block.get("alert_band", "WARNING")
        nearest = (threat_block.get("top_threats") or [{}])[0]
        d = nearest.get("distance_mi", "?")
        lat = nearest.get("lat", "?")
        lon = nearest.get("lon", "?")
        return {
            "incident_id": f"WX-FALLBACK-{installation.get('id','x')}",
            "alert_band": band,
            "marforres_email": {
                "subject": f"[{band}] WILDFIRE — {nm} — fire pixel {d} mi out",
                "to": "marforres.ops@usmc.mil",
                "from": "wildfire-eoc@usmc.mil",
                "body": (f"BLUF: {band} declared at {nm}. Nearest FIRMS pixel "
                         f"({lat}, {lon}) is {d} mi from base centroid. "
                         f"LLM JSON-mode failed: {e}. Manual draft required."),
            },
            "base_intranet_banner": {
                "color": "RED" if band == "WARNING" else "AMBER",
                "text": f"{band} — wildfire {d} mi from {nm}. Stand by for guidance.",
            },
            "commander_sms": {
                "recipients": ["S3 Watch", "PMO Watch", "Range Control"],
                "text": f"{band}: fire {d} mi from base @ {lat},{lon}. EOC stand-up.",
            },
            "evacuation_brief": {
                "title": f"{nm} — {band} evacuation outline",
                "bullets": [
                    f"Confirm fire location {lat}, {lon} ({d} mi from base centroid).",
                    "Pre-stage evacuation buses at family-housing assembly areas.",
                    "Notify ammo storage detachment to verify cooling capacity.",
                    "EOC reachback (placeholder): 760-XXX-XXXX.",
                ],
                "eoc_phone": "760-XXX-XXXX",
            },
        }


def quick_wind_summary(threat_block: dict) -> str:
    """Compact wind context string for the prompt."""
    aligned = threat_block.get("wind_aligned_threats") or []
    if not aligned:
        return "No fires currently wind-aligned toward the installation."
    parts = []
    for a in aligned[:2]:
        parts.append(
            f"Fire {a['fire_id']} at ({a['lat']}, {a['lon']}) — "
            f"{a['distance_mi']} mi out, wind alignment {a['alignment']:+.2f}, "
            f"wind speed {a['wind_speed_mps']} m/s, fire->base bearing "
            f"{a['fire_to_base_bearing']} deg, wind blowing toward "
            f"{a['wind_to_dir_bearing']} deg."
        )
    return " ".join(parts)
