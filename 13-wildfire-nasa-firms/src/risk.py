"""WILDFIRE risk scoring — distance-to-installation alert ladder + wind-projected priority.

Three core functions used by the FastAPI backend:

  haversine_mi(lat1, lon1, lat2, lon2) -> float
      Great-circle distance in statute miles.

  bearing_deg(lat1, lon1, lat2, lon2) -> float
      Initial compass bearing (0-360) FROM point 1 TO point 2.

  alert_band(distance_mi) -> str
      One of CLEAR | WATCH | ALERT | WARNING per the LADDER thresholds.

  installation_threats(installations, fires, wind) -> list[dict]
      For each installation, finds nearest fire, computes alert band, AND
      computes a wind-aligned priority score:
          score = (1 / max(d, 1)) * (1 + 2 * max(0, cos(theta_wind_to_base)))
      where theta is the angle between the wind vector and the
      fire-to-base bearing. A fire being blown straight at the base
      gets up to a 3x boost.
"""
from __future__ import annotations

import math
from typing import Iterable

# Alert ladder thresholds in statute miles.
LADDER = [
    ("WARNING", 10.0),
    ("ALERT", 25.0),
    ("WATCH", 50.0),
]


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_MI = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_MI * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing FROM 1 TO 2, degrees clockwise from North (0..360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = math.degrees(math.atan2(x, y))
    return (brg + 360.0) % 360.0


def alert_band(distance_mi: float) -> str:
    for label, thresh in LADDER:
        if distance_mi <= thresh:
            return label
    return "CLEAR"


def nearest_wind(wind: list[dict], lat: float, lon: float) -> dict | None:
    if not wind:
        return None
    best = None
    best_d = float("inf")
    for w in wind:
        d = haversine_mi(lat, lon, w["latitude"], w["longitude"])
        if d < best_d:
            best_d = d
            best = w
    return best


def wind_alignment(fire: dict, install_centroid: list[float], wind: list[dict]) -> dict:
    """How well-aligned is the wind at the fire with the fire->base bearing?

    Returns {alignment: -1..1, wind_speed_mps, fire_to_base_bearing,
             wind_to_dir_bearing}.
    +1 means wind is blowing the fire straight at the base.
    -1 means wind is blowing it directly away.
    """
    w = nearest_wind(wind, fire["latitude"], fire["longitude"])
    if not w:
        return {"alignment": 0.0, "wind_speed_mps": 0.0,
                "fire_to_base_bearing": 0.0, "wind_to_dir_bearing": 0.0}
    bearing_fb = bearing_deg(fire["latitude"], fire["longitude"],
                             install_centroid[0], install_centroid[1])
    # Wind "to" direction is opposite of "from": atan2(u, v) == compass dir wind blows TOWARD.
    u, v = w["u_mps"], w["v_mps"]
    wind_to = (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
    diff = abs(((bearing_fb - wind_to + 540.0) % 360.0) - 180.0)
    # diff: 0 means perfectly aligned (wind blowing toward base), 180 means opposite.
    alignment = math.cos(math.radians(diff))
    return {
        "alignment": round(alignment, 3),
        "wind_speed_mps": w["speed_mps"],
        "fire_to_base_bearing": round(bearing_fb, 1),
        "wind_to_dir_bearing": round(wind_to, 1),
    }


def installation_threats(
    installations: list[dict],
    fires: Iterable[dict],
    wind: list[dict],
    *,
    visible_ids: set[str] | None = None,
) -> list[dict]:
    """Compute threat block per installation. Optionally filter fires by visible IDs."""
    fires = [f for f in fires if visible_ids is None or f["id"] in visible_ids]
    out = []
    for inst in installations:
        clat, clon = inst["centroid"]
        ranked = []
        for f in fires:
            d = haversine_mi(clat, clon, f["latitude"], f["longitude"])
            if d > 80:  # don't bother
                continue
            wa = wind_alignment(f, inst["centroid"], wind)
            # Priority score: closer + wind-blown-toward-base = higher.
            score = (1.0 / max(d, 1.0)) * (1.0 + 2.0 * max(0.0, wa["alignment"]))
            ranked.append({
                "fire_id": f["id"],
                "lat": f["latitude"],
                "lon": f["longitude"],
                "distance_mi": round(d, 2),
                "frp": f.get("frp"),
                "brightness": f.get("brightness"),
                "satellite": f.get("satellite"),
                "acq_datetime": f.get("acq_datetime"),
                "alignment": wa["alignment"],
                "wind_speed_mps": wa["wind_speed_mps"],
                "fire_to_base_bearing": wa["fire_to_base_bearing"],
                "wind_to_dir_bearing": wa["wind_to_dir_bearing"],
                "priority_score": round(score, 4),
            })
        ranked.sort(key=lambda r: r["priority_score"], reverse=True)
        nearest = min(ranked, key=lambda r: r["distance_mi"]) if ranked else None
        band = alert_band(nearest["distance_mi"]) if nearest else "CLEAR"
        out.append({
            "installation_id": inst["id"],
            "installation_name": inst["name"],
            "centroid": inst["centroid"],
            "alert_band": band,
            "nearest_distance_mi": nearest["distance_mi"] if nearest else None,
            "n_fires_within_50mi": len(ranked),
            "top_threats": ranked[:5],
            "wind_aligned_threats": [r for r in ranked if r["alignment"] > 0.5][:3],
        })
    return out
