"""GHOST — synthetic RF scan generator.

Real dataset reference (would plug in via data/load_real.py):
  IEEE Real-world Commercial WiFi and Bluetooth Dataset for RF Fingerprinting
  https://ieee-dataport.org/   (CSV: timestamp, MAC, RSSI, channel, signal_type)

Generates ~5,000 synthetic Wi-Fi probe + BT advertisement events captured
across a notional Camp Pendleton main-gate perimeter over a single 24h scan
window (centered on 2026-04-26). Patterns planted:

  - device_dwell  : ~60 nightly emitters at the gate guard shack (24h, low rate)
  - gathering     : ~120 phones/wearables at chow hall midday (1100-1300)
  - mobile_transit: phones along main road during morning/evening rush
  - fixed_infra   : Wi-Fi APs (Cisco, Ruckus) scattered across buildings
  - ephemeral     : random one-off transient probes

Outputs:
  rf_events.csv          (5,000 rows: ts, lat, lon, signal_type, mac, rssi, channel, oui, vendor)
  vendor_oui.csv         (30-row OUI -> vendor lookup)
  cached_briefs.json     (2 pre-computed hero briefs for cache-first demo)
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_DIR = Path(__file__).parent
SEED = 1776
N_EVENTS = 5000
SCAN_DATE = datetime(2026, 4, 26, 0, 0, 0, tzinfo=timezone.utc)

# Camp Pendleton main gate (San Onofre) approximate coordinates
GATE_LAT, GATE_LON = 33.2106, -117.3973

# Anchors within a ~2km perimeter around the main gate
ANCHORS = {
    "gate_shack":        (33.2106, -117.3973),  # the gate itself
    "chow_hall":         (33.2185, -117.3905),  # ~900m NE
    "main_road_n":       (33.2245, -117.3881),  # transit pattern north
    "main_road_s":       (33.2050, -117.3995),  # transit pattern south
    "bldg_22_offices":   (33.2152, -117.3940),  # office WiFi APs
    "bldg_44_motorpool": (33.2078, -117.4012),  # motor pool / IoT
    "vehicle_park":      (33.2128, -117.3962),  # vehicle staging
    "perimeter_fence_e": (33.2130, -117.3902),  # eastern fence
    "perimeter_fence_w": (33.2095, -117.4030),  # western fence
}

# Realistic OUI prefixes by vendor (first 3 octets of MAC).
# Source: IEEE OUI registry public listings.
VENDOR_OUI = [
    # phones / personal
    ("Apple",          "3C:22:FB"),
    ("Apple",          "A8:96:75"),
    ("Apple",          "F0:18:98"),
    ("Samsung",        "00:12:FB"),
    ("Samsung",        "78:25:AD"),
    ("Samsung",        "D0:17:6A"),
    ("Google",         "14:7D:DA"),
    ("Google",         "F4:F5:D8"),
    ("Xiaomi",         "F8:A4:5F"),
    ("OnePlus",        "94:65:2D"),
    ("Huawei",         "00:1E:10"),
    # wearables
    ("Fitbit",         "C0:91:34"),
    ("Garmin",         "00:0B:7D"),
    ("Polar",          "A0:9E:1A"),
    # Wi-Fi access points / infra
    ("Cisco",          "00:0C:14"),
    ("Cisco-Meraki",   "E0:CB:BC"),
    ("Ruckus",         "94:F6:65"),
    ("Aruba",          "94:B4:0F"),
    ("Ubiquiti",       "B4:FB:E4"),
    # BLE beacons / iot
    ("Estimote",       "F0:35:75"),
    ("Kontakt-io",     "F4:B8:5E"),
    ("BlueCharm",      "AC:23:3F"),
    # vehicles / motor pool sensors
    ("Continental",    "00:08:54"),
    ("Bosch",          "60:A4:23"),
    # contractor / unknown
    ("Espressif",      "AC:67:B2"),  # ESP32 IoT
    ("TexasInstr",     "00:17:E9"),
    ("Microsoft",      "F8:E4:FB"),  # Surface
    ("IntelCorp",      "DC:FB:48"),
    ("Unknown",        "02:00:00"),  # locally administered random
    ("Unknown",        "06:11:22"),
]


# Each pattern: (anchor, signal_type bias, vendor pool, RSSI range, hour profile, dwell minutes)
PATTERNS = [
    # gate shack — nightly device dwell, 60 emitters, persistent
    {
        "name": "device_dwell_gate",
        "anchor": "gate_shack",
        "signal_bias": ("WiFi", 0.55),  # mix WiFi probe + BT beacons
        "vendors": ["Apple", "Samsung", "Google", "Cisco-Meraki", "Estimote",
                    "Fitbit", "Espressif"],
        "rssi": (-78, -55),
        # hour profile (24 hours): heavy nightly (2200-0500), present all day
        "hour_weights": [4, 4, 4, 4, 4, 3, 2, 2, 2, 2, 2, 2,
                          2, 2, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4],
        "spread_m": 35,
        "share": 0.18,
    },
    # chow hall midday gathering — phones / wearables
    {
        "name": "gathering_chow_hall",
        "anchor": "chow_hall",
        "signal_bias": ("BT", 0.55),
        "vendors": ["Apple", "Samsung", "Google", "Xiaomi", "OnePlus",
                    "Fitbit", "Garmin", "Polar"],
        "rssi": (-82, -50),
        "hour_weights": [0, 0, 0, 0, 0, 0, 1, 2, 3, 3, 4, 9,
                          12, 11, 6, 3, 3, 3, 4, 3, 2, 1, 0, 0],
        "spread_m": 55,
        "share": 0.22,
    },
    # main road transit — mobile phones moving north/south
    {
        "name": "mobile_transit_road",
        "anchor": "main_road_n",
        "signal_bias": ("WiFi", 0.65),
        "vendors": ["Apple", "Samsung", "Google", "Xiaomi", "Huawei", "OnePlus"],
        "rssi": (-92, -65),
        "hour_weights": [0, 0, 0, 0, 0, 1, 4, 9, 8, 5, 3, 3,
                          3, 3, 3, 4, 6, 9, 8, 5, 3, 2, 1, 0],
        "spread_m": 200,  # along the road = wide spread
        "share": 0.20,
    },
    # building 22 office APs — fixed infra, business hours WiFi probe responses
    {
        "name": "fixed_infra_offices",
        "anchor": "bldg_22_offices",
        "signal_bias": ("WiFi", 0.95),
        "vendors": ["Cisco", "Cisco-Meraki", "Ruckus", "Aruba", "Ubiquiti",
                    "Microsoft", "IntelCorp"],
        "rssi": (-72, -45),
        "hour_weights": [1, 1, 1, 1, 1, 1, 2, 4, 7, 8, 8, 8,
                          7, 8, 8, 7, 6, 4, 2, 2, 1, 1, 1, 1],
        "spread_m": 60,
        "share": 0.13,
    },
    # motor pool IoT (sensors, vehicle telemetry)
    {
        "name": "fixed_infra_motorpool",
        "anchor": "bldg_44_motorpool",
        "signal_bias": ("BT", 0.70),
        "vendors": ["Continental", "Bosch", "Espressif", "TexasInstr",
                    "Kontakt-io", "BlueCharm"],
        "rssi": (-86, -60),
        "hour_weights": [1, 1, 1, 1, 1, 2, 4, 6, 6, 6, 5, 5,
                          5, 5, 5, 6, 6, 5, 3, 2, 2, 1, 1, 1],
        "spread_m": 70,
        "share": 0.10,
    },
    # vehicle park BT beacons (eastern fence area, mid + late shift)
    {
        "name": "device_dwell_vehiclepark",
        "anchor": "vehicle_park",
        "signal_bias": ("BT", 0.85),
        "vendors": ["Estimote", "BlueCharm", "Kontakt-io", "Garmin"],
        "rssi": (-80, -58),
        "hour_weights": [2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3,
                          3, 3, 3, 3, 4, 5, 5, 4, 3, 3, 2, 2],
        "spread_m": 45,
        "share": 0.07,
    },
    # ephemeral / unknown — random one-off probes from fence perimeter (suspicious)
    {
        "name": "ephemeral_perimeter",
        "anchor": "perimeter_fence_e",
        "signal_bias": ("WiFi", 0.45),
        "vendors": ["Unknown", "Espressif", "Huawei"],
        "rssi": (-94, -78),
        "hour_weights": [3, 3, 3, 4, 4, 3, 2, 1, 1, 1, 1, 1,
                          1, 1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4],
        "spread_m": 120,
        "share": 0.05,
    },
    # ephemeral western fence
    {
        "name": "ephemeral_perimeter_w",
        "anchor": "perimeter_fence_w",
        "signal_bias": ("BT", 0.50),
        "vendors": ["Unknown", "Espressif"],
        "rssi": (-95, -80),
        "hour_weights": [3, 3, 4, 4, 4, 3, 2, 1, 1, 1, 1, 1,
                          1, 1, 1, 1, 1, 2, 3, 3, 4, 4, 4, 4],
        "spread_m": 110,
        "share": 0.05,
    },
]


def meters_to_deg(meters: float, lat: float) -> tuple[float, float]:
    dlat = meters / 111_320.0
    dlon = meters / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    return dlat, dlon


def random_mac(rng: random.Random, vendor: str, oui_lookup: dict[str, list[str]]) -> tuple[str, str]:
    """Return (mac, oui_prefix). MAC has the vendor's OUI prefix + 3 random octets."""
    pool = oui_lookup.get(vendor) or oui_lookup["Unknown"]
    oui = rng.choice(pool)
    rest = ":".join(f"{rng.randint(0,255):02X}" for _ in range(3))
    return f"{oui}:{rest}", oui


def write_vendor_oui_csv() -> None:
    p = OUT_DIR / "vendor_oui.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vendor", "oui_prefix"])
        for vendor, oui in VENDOR_OUI:
            w.writerow([vendor, oui])


def main() -> Path:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_vendor_oui_csv()

    # Build vendor -> [oui prefixes] lookup
    oui_lookup: dict[str, list[str]] = {}
    for vendor, oui in VENDOR_OUI:
        oui_lookup.setdefault(vendor, []).append(oui)
    # Ensure "Unknown" key exists
    oui_lookup.setdefault("Unknown", ["02:00:00"])

    rows: list[dict] = []
    # Allocate counts per pattern by share (rounded), top up with ephemeral
    counts = []
    total_assigned = 0
    for pat in PATTERNS:
        n = int(round(N_EVENTS * pat["share"]))
        counts.append(n)
        total_assigned += n
    # top up / trim to N_EVENTS exactly via the largest pattern
    diff = N_EVENTS - total_assigned
    counts[0] += diff

    event_id = 0
    for pat, n in zip(PATTERNS, counts):
        anchor_lat, anchor_lon = ANCHORS[pat["anchor"]]
        sig_pref, sig_pref_p = pat["signal_bias"]
        spread_m = pat["spread_m"]
        dlat_unit, dlon_unit = meters_to_deg(spread_m, anchor_lat)
        weights = pat["hour_weights"]
        for _ in range(n):
            # Hour drawn from this pattern's hour profile
            hour = rng.choices(range(24), weights=weights, k=1)[0]
            minute = rng.randint(0, 59)
            second = rng.randint(0, 59)
            ts = SCAN_DATE.replace(hour=hour, minute=minute, second=second)
            # Position — gaussian around anchor; transit pattern stretched along axis
            if pat["name"] == "mobile_transit_road":
                # bias along a NS axis between main_road_n and main_road_s
                t = rng.random()
                lat = ANCHORS["main_road_n"][0] * t + ANCHORS["main_road_s"][0] * (1 - t)
                lon = ANCHORS["main_road_n"][1] * t + ANCHORS["main_road_s"][1] * (1 - t)
                lat += rng.gauss(0, dlat_unit / 4.0)
                lon += rng.gauss(0, dlon_unit / 6.0)
            else:
                lat = anchor_lat + rng.gauss(0, dlat_unit / 2.5)
                lon = anchor_lon + rng.gauss(0, dlon_unit / 2.5)
            # Signal type
            sig = sig_pref if rng.random() < sig_pref_p else ("BT" if sig_pref == "WiFi" else "WiFi")
            vendor = rng.choice(pat["vendors"])
            mac, oui = random_mac(rng, vendor, oui_lookup)
            rssi = rng.randint(pat["rssi"][0], pat["rssi"][1])
            if sig == "WiFi":
                channel = rng.choice([1, 6, 11, 36, 40, 44, 48, 149, 157])
            else:
                channel = rng.choice([37, 38, 39])  # BLE adv channels
            rows.append({
                "event_id": f"RF-{event_id:06d}",
                "timestamp": ts.isoformat(),
                "hour": hour,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "signal_type": sig,
                "mac": mac,
                "oui": oui,
                "vendor": vendor,
                "rssi": rssi,
                "channel": channel,
                "pattern": pat["name"],
            })
            event_id += 1

    # Shuffle so the CSV doesn't read pattern-by-pattern
    rng.shuffle(rows)

    csv_path = OUT_DIR / "rf_events.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Sample JSON for inspection
    json_path = OUT_DIR / "rf_events_sample.json"
    json_path.write_text(json.dumps(rows[:200], indent=2))

    print(f"Wrote {len(rows)} RF events to {csv_path}")
    from collections import Counter
    sig_c = Counter(r["signal_type"] for r in rows)
    pat_c = Counter(r["pattern"] for r in rows)
    ven_c = Counter(r["vendor"] for r in rows)
    print(f"  signal: {dict(sig_c)}")
    print(f"  patterns: {dict(pat_c)}")
    print(f"  top vendors: {ven_c.most_common(8)}")
    return csv_path


def _precompute_briefs() -> None:
    """Cache-first hero call. Pre-compute the RF Pattern of Life Survey for two
    canonical scenarios so the demo never sits on a spinner."""
    # late import — generate.py must be runnable without LLM creds
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
    try:
        from shared.kamiwaza_client import chat  # noqa: WPS433
    except Exception as e:  # noqa: BLE001
        print(f"[precompute] LLM client unavailable, skipping cache: {e}")
        return

    # Curated scenario inputs: stable, deterministic, demo-grade
    scenarios = {
        "full_24h_all_signals": {
            "label": "Full 24-hour scan · WiFi + BT · all vendors",
            "site": "Camp Pendleton main gate (San Onofre) perimeter",
            "window_utc": "2026-04-26 00:00Z to 2026-04-26 23:59Z",
            "totals": {
                "events": 5000,
                "wifi": 2700,
                "bluetooth": 2300,
                "unique_macs": 1180,
            },
            "clusters": [
                {"id": 1, "anchor": "gate_shack", "n": 880,
                 "type": "device_dwell", "device_class": "wifi_AP+phone+beacon",
                 "tod": "nightly persistent"},
                {"id": 2, "anchor": "chow_hall", "n": 1090,
                 "type": "gathering", "device_class": "phone+wearable",
                 "tod": "1100-1300 spike"},
                {"id": 3, "anchor": "main_road", "n": 980,
                 "type": "mobile_transit", "device_class": "phone",
                 "tod": "0700-0900 / 1700-1900 rush"},
                {"id": 4, "anchor": "bldg_22_offices", "n": 650,
                 "type": "fixed_infra", "device_class": "wifi_AP",
                 "tod": "office hours"},
                {"id": 5, "anchor": "bldg_44_motorpool", "n": 510,
                 "type": "fixed_infra", "device_class": "iot+sensor",
                 "tod": "office hours"},
                {"id": 6, "anchor": "perimeter_fence_e/w", "n": 490,
                 "type": "ephemeral", "device_class": "unknown OUI",
                 "tod": "sporadic, nightly bias"},
            ],
            "anomalies": [
                "Cluster 6 — 220 events from locally-administered MAC prefixes "
                "(02:00:00 / 06:11:22) along east + west perimeter fences, "
                "weighted toward 0200-0500 local. No vendor attribution.",
                "Three Espressif (ESP32) MACs observed on western fence at "
                "RSSI -82 to -94 with no daytime presence — consistent with "
                "battery-powered drop sensors.",
            ],
        },
        "bt_only_workhours": {
            "label": "Bluetooth only · 0900-1700 work hours · phones/wearables/beacons",
            "site": "Camp Pendleton main gate (San Onofre) perimeter",
            "window_utc": "2026-04-26 09:00Z to 2026-04-26 17:00Z",
            "totals": {"events": 1450, "wifi": 0, "bluetooth": 1450, "unique_macs": 510},
            "clusters": [
                {"id": 1, "anchor": "chow_hall", "n": 720,
                 "type": "gathering", "device_class": "phone+wearable",
                 "tod": "1100-1300 spike"},
                {"id": 2, "anchor": "bldg_44_motorpool", "n": 320,
                 "type": "fixed_infra", "device_class": "iot+sensor",
                 "tod": "office hours"},
                {"id": 3, "anchor": "vehicle_park", "n": 240,
                 "type": "device_dwell", "device_class": "beacon",
                 "tod": "afternoon shift"},
                {"id": 4, "anchor": "gate_shack", "n": 170,
                 "type": "device_dwell", "device_class": "phone+beacon",
                 "tod": "office hours subset"},
            ],
            "anomalies": [
                "Vehicle park cluster: 24 Estimote beacon MACs persist with "
                "no associated phone — verify these are inventory tags vs. "
                "covertly placed locators.",
            ],
        },
    }

    SYSTEM = (
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

    cached: dict[str, str] = {}
    for sid, payload in scenarios.items():
        user = (
            f"Scan site: {payload['site']}\n"
            f"Scan window (UTC): {payload['window_utc']}\n"
            f"Totals: {payload['totals']}\n"
            f"Clusters (DBSCAN over lat/lon/scaled_time):\n"
            + "\n".join(
                f"  - Cluster {c['id']} @ {c['anchor']} : n={c['n']}, "
                f"type={c['type']}, device_class={c['device_class']}, "
                f"time_of_day={c['tod']}"
                for c in payload["clusters"]
            )
            + "\n\nAnomalies flagged by classifier:\n"
            + "\n".join(f"  - {a}" for a in payload["anomalies"])
            + "\n\nWrite the RF Pattern of Life Survey now."
        )
        text = ""
        for hero_model in ("gpt-5.4", "gpt-5.4-mini", None):
            try:
                print(f"[precompute] generating brief: {sid} (model={hero_model or 'chain-default'}) ...")
                text = chat(
                    [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    model=hero_model,
                    temperature=0.4,
                )
                if text and text.strip():
                    break
            except Exception as e:  # noqa: BLE001
                print(f"[precompute] {hero_model} failed for {sid}: {e}")
                continue
        if not text:
            print(f"[precompute] all models failed for {sid}; using deterministic fallback")
            text = _fallback_brief(payload)
        cached[sid] = text

    out = OUT_DIR / "cached_briefs.json"
    out.write_text(json.dumps(cached, indent=2))
    print(f"[precompute] wrote {out}")


def _fallback_brief(payload: dict) -> str:
    """Deterministic brief used when no LLM is reachable. Same template the
    runtime watchdog uses on timeout."""
    site = payload["site"]
    window = payload["window_utc"]
    n = payload["totals"]["events"]
    macs = payload["totals"]["unique_macs"]
    cls = payload["clusters"]
    anom = payload["anomalies"]
    by_class: dict[str, int] = {}
    for c in cls:
        by_class[c["device_class"]] = by_class.get(c["device_class"], 0) + c["n"]
    cls_lines = "; ".join(f"{k}: {v}" for k, v in by_class.items())
    return (
        f"(U) BLUF\n"
        f"GHOST scan over {site} ({window}) ingested {n:,} RF events from "
        f"{macs:,} unique MACs. Six DBSCAN clusters identified; perimeter "
        f"ephemeral cluster carries the highest counter-intel concern.\n\n"
        f"(U) Target / Location Summary\n"
        f"Coverage spans the main gate, chow hall, motor pool, office "
        f"buildings, and the eastern + western fence lines. Activity is "
        f"dominated by a midday gathering at the chow hall and a persistent "
        f"nightly dwell at the gate shack.\n\n"
        f"(U) Device Counts by Class\n"
        f"{cls_lines}.\n\n"
        f"(U) Suspicious or Anomalous Signatures\n"
        + "\n".join(anom) + "\n\n"
        f"(U) Recommended ISR Follow-ups\n"
        f"1) Sweep the eastern + western fence corridors for emplaced "
        f"sensors at first light. 2) Vehicle-park beacon inventory "
        f"reconciliation against property records. 3) Trigger an OUI "
        f"watchlist on locally-administered MAC prefixes for the next 72h.\n\n"
        f"(U) Confidence\n"
        f"MED — clusters are statistically clean but vendor attribution on "
        f"perimeter cluster is limited by locally-administered MACs."
    )


if __name__ == "__main__":
    main()
    if os.getenv("SKIP_PRECOMPUTE") != "1":
        _precompute_briefs()
