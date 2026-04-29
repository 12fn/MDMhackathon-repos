"""OMNI Attribute-Based Access Control (ABAC) — role-aware data layer.

The ABAC checks happen INSIDE the data layer, not just in the UI: streams
the persona is not authorized for never make it to the renderer with
content; they are returned as `{stream, redacted: True, reason: ...}`.
The UI shows them as "REDACTED — INSUFFICIENT CLEARANCE" so the
information-presence is itself signal (the persona knows the stream
exists; they just can't see its contents).

Anomaly classes are inferred from the contributing_streams set, then
filtered against persona["allowed_anomaly_classes"]. CO has class "ALL".
"""
from __future__ import annotations

# Map streams → anomaly_class buckets (one stream can map to multiple).
STREAM_TO_CLASS = {
    "gate": ["personnel", "force_protection", "ops"],
    "utility": ["infrastructure", "supply"],
    "ems": ["safety", "ops", "personnel"],
    "massnotify": ["safety", "ops", "comms"],
    "weather": ["safety", "ops"],
    "maintenance": ["maintenance", "supply"],
    "rf": ["intel", "comms", "force_protection"],
    "drone_rf": ["intel", "force_protection"],
    "firms": ["intel", "safety", "force_protection"],
}


def classes_for_streams(streams: list[str]) -> set[str]:
    out: set[str] = set()
    for s in streams or []:
        out.update(STREAM_TO_CLASS.get(s, []))
    return out


def filter_streams_summary(summary: list[dict], persona: dict) -> list[dict]:
    """Annotate each stream-summary row with `redacted` + `reason` when the
    persona is not authorized to see it. Counts/anomaly-counts stay so the
    UI can show the bar exists and is denied."""
    allowed = set(persona.get("allowed_streams", []))
    out = []
    for s in summary:
        row = dict(s)
        if s["stream"] not in allowed:
            row["redacted"] = True
            row["reason"] = "INSUFFICIENT CLEARANCE FOR THIS STREAM"
        else:
            row["redacted"] = False
            row["reason"] = None
        out.append(row)
    return out


def filter_timeline(fused: list[dict], persona: dict) -> list[dict]:
    """Drop timeline rows the persona is not authorized to see. We DROP
    them rather than redact-in-place to keep the map / ticker clean. The
    'this stream exists' signal is preserved on the chip strip."""
    allowed = set(persona.get("allowed_streams", []))
    return [f for f in fused if f.get("stream") in allowed]


def filter_anomalies(correlation: dict, persona: dict) -> dict:
    """Filter the cross-domain anomaly list:
       - keep an anomaly only if AT LEAST ONE of its contributing streams
         is in the persona's allowed_streams set, AND its inferred
         anomaly-class set intersects allowed_anomaly_classes (or persona
         has 'ALL').
       - For visible anomalies, scrub contributing-stream names that the
         persona is not authorized for, and append a `_redacted_streams`
         list so the UI can show "(plus 2 streams REDACTED)".
    """
    allowed_streams = set(persona.get("allowed_streams", []))
    allowed_classes = set(persona.get("allowed_anomaly_classes", []))
    is_god = "ALL" in allowed_classes

    out_anoms = []
    for a in correlation.get("anomalies", []):
        contrib = list(a.get("contributing_streams", []))
        anom_classes = classes_for_streams(contrib)
        class_ok = is_god or bool(anom_classes & allowed_classes)
        any_visible = bool(set(contrib) & allowed_streams)
        if not class_ok or not any_visible:
            continue
        scrub = dict(a)
        visible_contrib = [s for s in contrib if s in allowed_streams]
        redacted_contrib = [s for s in contrib if s not in allowed_streams]
        scrub["contributing_streams"] = visible_contrib
        scrub["_redacted_streams"] = redacted_contrib
        out_anoms.append(scrub)
    return {**correlation, "anomalies": out_anoms}


def can_view_brief(persona: dict) -> bool:
    return bool(persona.get("view_brief", False))


def can_view_audit(persona: dict) -> bool:
    return bool(persona.get("view_audit", False))
