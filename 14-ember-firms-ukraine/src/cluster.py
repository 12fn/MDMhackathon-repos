# EMBER — combat-fire signature analytics + ASIB brief
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""DBSCAN-based space+time clustering for FIRMS fire pixels.

We treat each fire pixel as a point in (scaled lat, scaled lon, scaled time)
and cluster with DBSCAN. The resulting clusters are then summarized into a
feature vector that the LLM classifier consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN


# Scale factors so 1 unit ~= meaningful proximity in each axis
LAT_SCALE = 1.0      # ~111 km / deg
LON_SCALE = 1.0      # ~80 km / deg at Ukraine latitude
TIME_HOURS_SCALE = 6.0  # 6h ~ 1 unit; clusters bridge same-day events


def _to_hours(iso: str, t0: datetime) -> float:
    dt = datetime.fromisoformat(iso.rstrip("Z"))
    return (dt - t0).total_seconds() / 3600.0


@dataclass
class ClusterSummary:
    cluster_id: int
    n_pixels: int
    centroid_lat: float
    centroid_lon: float
    bbox_km: float
    spread_km: float
    duration_hours: float
    start_iso: str
    end_iso: str
    mean_brightness_k: float
    max_brightness_k: float
    mean_frp_mw: float
    max_frp_mw: float
    sum_frp_mw: float
    high_conf_frac: float
    night_frac: float
    point_score: float       # 1 = pure point, 0 = sprawling line
    burst_score: float       # 1 = brief intense burst, 0 = sustained
    oblasts: list[str]
    dominant_oblast: str
    truth_majority: str      # majority truth_class label among member pixels
    sample_pixel_idx: list[int]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def cluster_pixels(
    pixels: list[dict],
    *,
    eps: float = 0.18,        # DBSCAN epsilon in scaled space
    min_samples: int = 4,
) -> tuple[np.ndarray, list[ClusterSummary]]:
    """Run DBSCAN on (lat, lon, scaled_time). Returns (labels, summaries[])."""
    if not pixels:
        return np.array([], dtype=int), []

    t0 = datetime.fromisoformat(min(p["acq_datetime"] for p in pixels).rstrip("Z"))
    X = np.array([
        [
            p["lat"] * LAT_SCALE,
            p["lon"] * LON_SCALE,
            _to_hours(p["acq_datetime"], t0) / TIME_HOURS_SCALE / 24.0,  # days-ish
        ]
        for p in pixels
    ])

    db = DBSCAN(eps=eps, min_samples=min_samples).fit(X)
    labels = db.labels_

    summaries: list[ClusterSummary] = []
    unique = sorted(set(labels.tolist()) - {-1})
    for cid in unique:
        idx = np.where(labels == cid)[0]
        members = [pixels[i] for i in idx]
        lats = np.array([m["lat"] for m in members])
        lons = np.array([m["lon"] for m in members])
        brights = np.array([m["brightness_k"] for m in members])
        frps = np.array([m["frp_mw"] for m in members])
        confs = [m["confidence"] for m in members]
        nights = sum(1 for m in members if m.get("daynight") == "N")
        oblasts = [m.get("oblast", "Unknown") for m in members]
        truths = [m.get("truth_class", "unknown") for m in members]

        cent_lat, cent_lon = float(lats.mean()), float(lons.mean())
        # bbox diagonal in km
        bbox_km = float(_haversine_km(lats.min(), lons.min(), lats.max(), lons.max()))
        # spread = mean distance to centroid
        spread_km = float(np.mean(_haversine_km(lats, lons, cent_lat, cent_lon)))

        times = sorted(datetime.fromisoformat(m["acq_datetime"].rstrip("Z")) for m in members)
        duration_h = float((times[-1] - times[0]).total_seconds() / 3600.0)

        # point_score: tighter spread => higher
        point_score = float(np.exp(-spread_km / 2.0))   # 0 km -> 1.0, 4 km -> 0.13
        # burst_score: shorter duration + high mean brightness => higher
        burst_score = float(
            np.exp(-duration_h / 12.0) * np.clip((brights.mean() - 300) / 100, 0, 1)
        )

        oblast_counts: dict[str, int] = {}
        for o in oblasts:
            oblast_counts[o] = oblast_counts.get(o, 0) + 1
        dominant_oblast = max(oblast_counts, key=oblast_counts.get)

        truth_counts: dict[str, int] = {}
        for t in truths:
            truth_counts[t] = truth_counts.get(t, 0) + 1
        truth_majority = max(truth_counts, key=truth_counts.get)

        summaries.append(ClusterSummary(
            cluster_id=int(cid),
            n_pixels=int(len(members)),
            centroid_lat=round(cent_lat, 4),
            centroid_lon=round(cent_lon, 4),
            bbox_km=round(bbox_km, 2),
            spread_km=round(spread_km, 2),
            duration_hours=round(duration_h, 2),
            start_iso=times[0].isoformat() + "Z",
            end_iso=times[-1].isoformat() + "Z",
            mean_brightness_k=round(float(brights.mean()), 1),
            max_brightness_k=round(float(brights.max()), 1),
            mean_frp_mw=round(float(frps.mean()), 2),
            max_frp_mw=round(float(frps.max()), 2),
            sum_frp_mw=round(float(frps.sum()), 2),
            high_conf_frac=round(sum(1 for c in confs if c == "high") / len(confs), 2),
            night_frac=round(nights / len(members), 2),
            point_score=round(point_score, 3),
            burst_score=round(burst_score, 3),
            oblasts=sorted(oblast_counts.keys()),
            dominant_oblast=dominant_oblast,
            truth_majority=truth_majority,
            sample_pixel_idx=[int(i) for i in idx[:25]],
        ))

    summaries.sort(key=lambda s: -s.sum_frp_mw)
    return labels, summaries


def heuristic_classify(s: ClusterSummary) -> tuple[str, float, str]:
    """Cheap, deterministic backup classifier -- used if LLM unavailable.

    Returns (label, confidence_0_1, rationale).
    """
    # Industrial: very high FRP and tight footprint, regardless of duration
    if s.max_frp_mw > 80 and s.spread_km < 3:
        return ("industrial", 0.80,
                f"Very high FRP ({s.max_frp_mw:.0f} MW) at a tight fixed footprint "
                f"({s.spread_km:.1f} km spread) -- refinery / depot / steel-plant signature.")
    # Wildfire: large sprawl, cooler temperature
    if s.bbox_km > 10 and s.mean_brightness_k < 335:
        return ("wildfire", 0.76,
                f"Sprawling footprint ({s.bbox_km:.1f} km), cooler mean brightness "
                f"({s.mean_brightness_k:.0f} K) -- agricultural / vegetation fire.")
    # Artillery-style: very hot peak + fairly tight + small cluster
    if s.max_brightness_k > 370 and s.spread_km < 4 and s.n_pixels <= 12:
        return ("combat_artillery", 0.80,
                f"Hot peak ({s.max_brightness_k:.0f} K) at tight footprint "
                f"({s.spread_km:.1f} km), small pixel count ({s.n_pixels}) -- "
                f"consistent with kinetic impact bursts in {s.dominant_oblast}.")
    # Armor / repeated combat: medium-hot, medium spread
    if s.max_brightness_k > 345 and 1.0 < s.spread_km < 8.0:
        return ("combat_armor", 0.66,
                f"Mid-intensity ({s.max_brightness_k:.0f} K peak), spread "
                f"{s.spread_km:.1f} km in {s.dominant_oblast} -- vehicle / armor "
                f"engagement signature along front-line salient.")
    # Structure: short, hot, single-area
    if s.n_pixels <= 6 and s.max_brightness_k > 335 and s.spread_km < 5:
        return ("structure", 0.55,
                f"Small isolated detection ({s.n_pixels} pixels) in {s.dominant_oblast} -- "
                f"likely structure fire.")
    return ("ambiguous", 0.45,
            f"Mixed signature: brightness {s.mean_brightness_k:.0f} K, "
            f"spread {s.spread_km:.1f} km, duration {s.duration_hours:.1f} h.")


def llm_classify(s: ClusterSummary) -> dict[str, Any]:
    """LLM-based JSON classification; falls back to heuristic on failure."""
    try:
        from shared.kamiwaza_client import chat_json  # type: ignore
    except Exception:
        try:
            import sys
            # Repo root is two levels up from this file.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from shared.kamiwaza_client import chat_json  # type: ignore
        except Exception:
            label, conf, why = heuristic_classify(s)
            return {"label": label, "confidence": conf, "rationale": why,
                    "source": "heuristic"}

    feature_payload = asdict(s)
    feature_payload.pop("sample_pixel_idx", None)
    feature_payload.pop("truth_majority", None)  # don't leak truth to LLM

    sys_prompt = (
        "You are a USMC LOGCOM all-source intelligence analyst. You classify "
        "NASA FIRMS satellite fire detections into combat-attributable vs "
        "non-combat origins to help cue ISR for Stand-In Forces operating in "
        "contested logistics environments. Use Marine-style brevity. "
        "Respond ONLY as JSON."
    )
    user_prompt = (
        "Classify this FIRMS spatiotemporal cluster. Choose label from: "
        "combat_artillery, combat_armor, industrial, wildfire, structure, ambiguous. "
        "Return JSON: "
        "{\"label\": str, \"confidence\": float 0..1, "
        "\"rationale\": str (<= 60 words, cite features), "
        "\"recommend\": str (one ISR/intel collection recommendation, <= 25 words)}.\n\n"
        f"FEATURES:\n{feature_payload}"
    )
    try:
        out = chat_json(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": user_prompt}],
            schema_hint="label, confidence, rationale, recommend",
            temperature=0.2,
        )
        # Normalize
        label = str(out.get("label", "ambiguous")).lower().replace(" ", "_")
        conf = float(out.get("confidence", 0.5))
        rationale = str(out.get("rationale", "")).strip()
        recommend = str(out.get("recommend", "")).strip()
        return {"label": label, "confidence": round(conf, 2),
                "rationale": rationale, "recommend": recommend, "source": "llm"}
    except Exception as e:  # noqa: BLE001
        label, conf, why = heuristic_classify(s)
        return {"label": label, "confidence": conf, "rationale": why,
                "recommend": "Cross-cue with SIGINT/UAS for confirmation.",
                "source": f"heuristic (LLM failed: {type(e).__name__})"}


CLASS_COLORS = {
    "combat_artillery": "#FF3B30",   # red
    "combat_armor":     "#FF9500",   # orange
    "industrial":       "#AF52DE",   # purple
    "wildfire":         "#FFD60A",   # yellow
    "structure":        "#5AC8FA",   # cyan
    "ambiguous":        "#8E8E93",   # gray
}
