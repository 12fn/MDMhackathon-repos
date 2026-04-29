"""PREDICT-MAINT synthetic data generator.

Five-dataset stand-in (synthetic but plausible) covering the LOGCOM PdM-flavored
hackathon use cases:

  1. CWRU Bearing Fault             -> data/vibration_corpus.npz
  2. NASA Predictive Mx (CMAPSS)    -> embedded into RUL slope curves
  3. Microsoft Azure Predictive Mx  -> consumption history pattern in maintenance_history.csv
  4. GCSS-MC Supply & Maintenance   -> data/nsn_catalog.json + depot_capacity.json
  5. Inventory Control Management   -> data/inventory.csv

Plus:
  - data/maintenance_history.csv  (90 days of work orders)
  - data/depot_capacity.json      (3 depots * bays * shifts)
  - data/cached_briefs.json       (3 scenarios: nominal, surge, parts-constrained)

Seeded with random.Random(1776) for reproducibility.

NSN catalog policy: every entry uses a Federal Supply Class (FSC, the first 4
digits of the NSN) coherent with the part name. Bearing geometry uses the SKF
6205-2RS JEM (CWRU canonical drive-end), n=9 balls, d=0.3126", D=1.537".
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SEED = 1776

# ---------------------------------------------------------------------------
# CWRU vibration corpus
# ---------------------------------------------------------------------------
FS = 12_000
WIN_SEC = 1.0
N = int(FS * WIN_SEC)

# CWRU 6205-2RS JEM drive-end bearing geometry
N_BALLS = 9
BALL_DIA_IN = 0.3126
PITCH_DIA_IN = 1.537
F_SHAFT = 1772.0 / 60.0   # ≈ 29.53 Hz at 1772 rpm

CLASSES = ["healthy", "inner_race", "outer_race", "ball"]
SAMPLES_PER_CLASS = 50  # 200 windows total, 4 classes


@dataclass
class CharFreqs:
    bpfo: float
    bpfi: float
    bsf: float
    ftf: float


def char_freqs(f_shaft: float = F_SHAFT) -> CharFreqs:
    ratio = BALL_DIA_IN / PITCH_DIA_IN
    return CharFreqs(
        bpfo=(N_BALLS / 2.0) * f_shaft * (1 - ratio),
        bpfi=(N_BALLS / 2.0) * f_shaft * (1 + ratio),
        bsf=(PITCH_DIA_IN / (2 * BALL_DIA_IN)) * f_shaft * (1 - ratio ** 2),
        ftf=(f_shaft / 2.0) * (1 - ratio),
    )


def synth_signal(cls: str, *, rng: np.random.Generator,
                 severity: float | None = None) -> np.ndarray:
    cf = char_freqs()
    t = np.arange(N) / FS
    if severity is None:
        severity = float(rng.uniform(0.25, 0.95))

    sig = (
        0.10 * np.sin(2 * np.pi * F_SHAFT * t)
        + 0.06 * np.sin(2 * np.pi * 2 * F_SHAFT * t + rng.uniform(0, 2 * np.pi))
        + 0.04 * np.sin(2 * np.pi * 3 * F_SHAFT * t + rng.uniform(0, 2 * np.pi))
        + 0.05 * np.sin(2 * np.pi * 178.0 * t + rng.uniform(0, 2 * np.pi))
    )
    sig += rng.normal(0.0, 0.06, size=N)

    n_imp = rng.integers(0, 4)
    for _ in range(n_imp):
        idx = int(rng.integers(0, N))
        sig[idx] += rng.normal(0.0, 0.15)

    if cls == "healthy":
        return sig.astype(np.float32)

    if cls == "outer_race":
        f_fault = cf.bpfo
        am_env = 1.0
        amp = 0.6 * severity
        impulse_decay = 320.0 * (0.6 + 0.4 * severity)
        carrier = rng.uniform(2800, 3600)
    elif cls == "inner_race":
        f_fault = cf.bpfi
        am_env = 1.0 + 0.7 * np.cos(2 * np.pi * F_SHAFT * t)
        amp = 0.55 * severity
        impulse_decay = 280.0 * (0.6 + 0.4 * severity)
        carrier = rng.uniform(2600, 3400)
    elif cls == "ball":
        f_fault = cf.bsf
        am_env = 1.0 + 0.6 * np.cos(2 * np.pi * cf.ftf * t)
        amp = 0.45 * severity
        impulse_decay = 240.0 * (0.6 + 0.4 * severity)
        carrier = rng.uniform(2200, 3000)
    else:
        raise ValueError(f"Unknown class {cls}")

    period_samples = max(2, int(FS / f_fault))
    impulse_train = np.zeros(N)
    jitter = rng.normal(0, 0.015, size=N // period_samples + 2)
    pos = 0
    k = 0
    while pos < N and k < len(jitter):
        slip_pos = int(pos * (1.0 + jitter[k]))
        if 0 <= slip_pos < N:
            impulse_train[slip_pos] = 1.0
        pos += period_samples
        k += 1

    burst_len = int(FS * 0.01)
    bt = np.arange(burst_len) / FS
    burst = np.exp(-impulse_decay * bt) * np.sin(2 * np.pi * carrier * bt)
    fault_sig = np.convolve(impulse_train, burst, mode="same")

    fault_sig *= am_env
    fault_sig *= amp
    sig = sig + fault_sig
    return sig.astype(np.float32)


def gen_corpus(rng: np.random.Generator) -> dict:
    X, y, sev = [], [], []
    for ci, cls in enumerate(CLASSES):
        for _ in range(SAMPLES_PER_CLASS):
            s = float(rng.uniform(0.3, 0.95)) if cls != "healthy" else 0.0
            sig = synth_signal(cls, rng=rng, severity=s)
            X.append(sig)
            y.append(ci)
            sev.append(s)
    X = np.stack(X).astype(np.float32)
    y = np.array(y, dtype=np.int32)
    sev = np.array(sev, dtype=np.float32)
    return {
        "signals": X,
        "labels": y,
        "severity": sev,
        "classes": np.array(CLASSES),
        "fs": np.int32(FS),
    }


# ---------------------------------------------------------------------------
# Test asset roster (real platforms / real PMCS codes / real depots)
# ---------------------------------------------------------------------------
ASSETS = [
    {
        "asset_id": "MTVR-2491",
        "type": "M1083 MTVR (Medium Tactical Vehicle Replacement)",
        "unit": "1st MLG, CLB-1",
        "hub_position": "Right rear (axle 3)",
        "operating_hours": 4127,
        "since_last_overhaul_hr": 612,
        "current_class": "outer_race",
        "current_severity": 0.78,
        "nsn": "3110-01-561-1929",
        "part_name": "Bearing, Tapered Roller, Wheel Hub (MTVR drive axle)",
        "depot": "ALB",
        "rebuild_not_buy": True,
    },
    {
        "asset_id": "JLTV-1107",
        "type": "JLTV M1278A1 Heavy Gun Carrier",
        "unit": "2d MarDiv, 2/2",
        "hub_position": "Front left",
        "operating_hours": 1842,
        "since_last_overhaul_hr": 421,
        "current_class": "healthy",
        "current_severity": 0.04,
        "nsn": "3110-01-660-2271",
        "part_name": "Bearing, Wheel Hub Front (JLTV)",
        "depot": "BAR",
        "rebuild_not_buy": False,
    },
    {
        "asset_id": "LAV-25-0892",
        "type": "LAV-25A2",
        "unit": "1st LAR Bn",
        "hub_position": "Mid right (axle 2)",
        "operating_hours": 6810,
        "since_last_overhaul_hr": 980,
        "current_class": "inner_race",
        "current_severity": 0.52,
        "nsn": "3110-01-204-5587",
        "part_name": "Bearing, Wheel Hub (LAV-25 Drive Train)",
        "depot": "BAR",
        "rebuild_not_buy": True,
    },
    {
        "asset_id": "AAV-7A1-3318",
        "type": "AAV-7A1 RAM/RS",
        "unit": "3d AABn",
        "hub_position": "Final drive, port side",
        "operating_hours": 3204,
        "since_last_overhaul_hr": 540,
        "current_class": "ball",
        "current_severity": 0.61,
        "nsn": "3110-01-413-2691",
        "part_name": "Bearing, Final Drive Pinion (AAV-7A1)",
        "depot": "BAR",
        "rebuild_not_buy": True,
    },
    {
        "asset_id": "MV-22B-167902",
        "type": "MV-22B Osprey",
        "unit": "VMM-263",
        "hub_position": "Prop rotor hub, starboard",
        "operating_hours": 2210,
        "since_last_overhaul_hr": 310,
        "current_class": "outer_race",
        "current_severity": 0.41,
        "nsn": "3110-01-617-8013",
        "part_name": "Bearing, Prop Rotor Hub (MV-22)",
        "depot": "BIC",
        "rebuild_not_buy": True,
    },
]

# ---------------------------------------------------------------------------
# NSN Catalog (Class IX, FSC-coherent, real prices)
# ---------------------------------------------------------------------------
NSN_CATALOG = [
    # 3110 Bearings, Antifriction (the hero NSNs for the asset roster)
    {"nsn": "3110-01-561-1929", "part_name": "Bearing, Tapered Roller, Wheel Hub (MTVR drive axle)",
     "primary_platform": "MTVR", "subsystem": "wheels",
     "base_daily_per_vehicle": 0.0024, "unit_price_usd": 387,
     "rebuild_not_buy": True, "long_pole": False},
    {"nsn": "3110-01-660-2271", "part_name": "Bearing, Wheel Hub Front (JLTV)",
     "primary_platform": "JLTV", "subsystem": "wheels",
     "base_daily_per_vehicle": 0.0019, "unit_price_usd": 512,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "3110-01-204-5587", "part_name": "Bearing, Wheel Hub (LAV-25 Drive Train)",
     "primary_platform": "LAV", "subsystem": "wheels",
     "base_daily_per_vehicle": 0.0021, "unit_price_usd": 622,
     "rebuild_not_buy": True, "long_pole": True},
    {"nsn": "3110-01-413-2691", "part_name": "Bearing, Final Drive Pinion (AAV-7A1)",
     "primary_platform": "AAV-7A1", "subsystem": "tracks",
     "base_daily_per_vehicle": 0.0011, "unit_price_usd": 745,
     "rebuild_not_buy": True, "long_pole": True},
    {"nsn": "3110-01-617-8013", "part_name": "Bearing, Prop Rotor Hub (MV-22)",
     "primary_platform": "MV-22B", "subsystem": "rotor",
     "base_daily_per_vehicle": 0.0006, "unit_price_usd": 4_280,
     "rebuild_not_buy": True, "long_pole": True},

    # 2530 Vehicular Brake/Steering/Axle/Wheel
    {"nsn": "2530-01-621-3107", "part_name": "Brake rotor (MTVR)",
     "primary_platform": "MTVR", "subsystem": "brakes",
     "base_daily_per_vehicle": 0.0019, "unit_price_usd": 215,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "2530-01-487-5511", "part_name": "Hydraulic brake caliper (JLTV)",
     "primary_platform": "JLTV", "subsystem": "brakes",
     "base_daily_per_vehicle": 0.0014, "unit_price_usd": 320,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "2530-01-356-7711", "part_name": "Power steering pump (MTVR)",
     "primary_platform": "MTVR", "subsystem": "steering",
     "base_daily_per_vehicle": 0.0009, "unit_price_usd": 1180,
     "rebuild_not_buy": True, "long_pole": False},

    # 2520 Power Transmission
    {"nsn": "2520-01-365-7104", "part_name": "Drive shaft U-joint (MTVR)",
     "primary_platform": "MTVR", "subsystem": "transmission",
     "base_daily_per_vehicle": 0.0033, "unit_price_usd": 175,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "2520-01-528-3166", "part_name": "Torque converter (JLTV)",
     "primary_platform": "JLTV", "subsystem": "transmission",
     "base_daily_per_vehicle": 0.00055, "unit_price_usd": 2900,
     "rebuild_not_buy": True, "long_pole": True},
    {"nsn": "2520-01-562-9981", "part_name": "Transfer case, ratio 1.85 (MTVR)",
     "primary_platform": "MTVR", "subsystem": "transmission",
     "base_daily_per_vehicle": 0.0008, "unit_price_usd": 3450,
     "rebuild_not_buy": True, "long_pole": True},

    # 2920 Engine Electrical Equipment
    {"nsn": "2920-01-446-5219", "part_name": "Alternator 200A 28V (MTVR)",
     "primary_platform": "MTVR", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.0017, "unit_price_usd": 410,
     "rebuild_not_buy": True, "long_pole": False},
    {"nsn": "2920-01-396-9234", "part_name": "Starter motor 24V (HMMWV/MTVR)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0013, "unit_price_usd": 605,
     "rebuild_not_buy": True, "long_pole": False},

    # 2940 Engine Air & Oil Filters
    {"nsn": "2940-01-389-2196", "part_name": "Primary fuel/oil filter element (MTVR)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0095, "unit_price_usd": 24,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "2940-01-413-1984", "part_name": "Engine air filter element (HMMWV)",
     "primary_platform": "HMMWV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0082, "unit_price_usd": 58,
     "rebuild_not_buy": False, "long_pole": False},

    # 2930 Engine Fuel System
    {"nsn": "2930-01-477-0631", "part_name": "Fuel filter / water separator (MTVR)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0070, "unit_price_usd": 47,
     "rebuild_not_buy": False, "long_pole": False},

    # 4720 Hose, Pipe, Tube
    {"nsn": "4720-01-471-9951", "part_name": "High-pressure hydraulic hose 1/2 in. (M88A2)",
     "primary_platform": "M88A2", "subsystem": "hydraulics",
     "base_daily_per_vehicle": 0.0061, "unit_price_usd": 95,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "4720-01-329-4512", "part_name": "Coolant hose (MTVR engine)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0044, "unit_price_usd": 38,
     "rebuild_not_buy": False, "long_pole": False},

    # 1730 Aircraft Ground Servicing Equip / 1680 (MV-22 specific)
    {"nsn": "1680-01-651-2244", "part_name": "Prop rotor blade, MV-22 (composite)",
     "primary_platform": "MV-22B", "subsystem": "rotor",
     "base_daily_per_vehicle": 0.0004, "unit_price_usd": 28_500,
     "rebuild_not_buy": True, "long_pole": True},
    {"nsn": "2935-01-510-9923", "part_name": "Fuel control, MV-22 engine",
     "primary_platform": "MV-22B", "subsystem": "engine",
     "base_daily_per_vehicle": 0.0007, "unit_price_usd": 12_400,
     "rebuild_not_buy": True, "long_pole": True},

    # 4730 Hydraulic seal kits
    {"nsn": "4730-01-441-2298", "part_name": "Hydraulic seal kit, lift assy",
     "primary_platform": "AAV-7A1", "subsystem": "hydraulics",
     "base_daily_per_vehicle": 0.0033, "unit_price_usd": 240,
     "rebuild_not_buy": False, "long_pole": True},

    # 5305 Fasteners
    {"nsn": "5305-01-188-1057", "part_name": "Machine screw, hex-head 3/8-16 (general)",
     "primary_platform": "MTVR", "subsystem": "fasteners",
     "base_daily_per_vehicle": 0.022, "unit_price_usd": 2,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "5306-01-204-9033", "part_name": "Structural bolt 1/2-13 grade-8 (general)",
     "primary_platform": "JLTV", "subsystem": "fasteners",
     "base_daily_per_vehicle": 0.018, "unit_price_usd": 3,
     "rebuild_not_buy": False, "long_pole": False},

    # 6140 Batteries
    {"nsn": "6140-01-446-9512", "part_name": "Vehicle battery 6TL 12V (HMMWV/MTVR)",
     "primary_platform": "MTVR", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.0024, "unit_price_usd": 138,
     "rebuild_not_buy": False, "long_pole": False},

    # 5995 Cable
    {"nsn": "5995-01-538-7726", "part_name": "RF coaxial cable assembly, vehicle SINCGARS",
     "primary_platform": "LAV", "subsystem": "comms",
     "base_daily_per_vehicle": 0.0036, "unit_price_usd": 84,
     "rebuild_not_buy": False, "long_pole": False},

    # 2610 Tires
    {"nsn": "2610-01-561-7748", "part_name": "Radial tire 395/85R20 (MTVR)",
     "primary_platform": "MTVR", "subsystem": "tires",
     "base_daily_per_vehicle": 0.0028, "unit_price_usd": 690,
     "rebuild_not_buy": False, "long_pole": False},
    {"nsn": "2610-01-647-5106", "part_name": "Run-flat radial tire 37x12.5R17 (JLTV)",
     "primary_platform": "JLTV", "subsystem": "tires",
     "base_daily_per_vehicle": 0.0026, "unit_price_usd": 540,
     "rebuild_not_buy": False, "long_pole": False},

    # 2540 Vehicular Furniture/Accessories
    {"nsn": "2540-01-565-2210", "part_name": "Ballistic glass window panel (JLTV)",
     "primary_platform": "JLTV", "subsystem": "armor",
     "base_daily_per_vehicle": 0.00060, "unit_price_usd": 2400,
     "rebuild_not_buy": False, "long_pole": True},

    # 1240 Optics
    {"nsn": "1240-01-602-7715", "part_name": "Optical sight assembly, M1A1",
     "primary_platform": "M1A1", "subsystem": "weapons",
     "base_daily_per_vehicle": 0.00020, "unit_price_usd": 18_500,
     "rebuild_not_buy": True, "long_pole": True},

    # 2895 Misc Vehicular
    {"nsn": "2895-01-462-3318", "part_name": "Winch cable assembly 200ft (M88A2)",
     "primary_platform": "M88A2", "subsystem": "winch",
     "base_daily_per_vehicle": 0.0029, "unit_price_usd": 410,
     "rebuild_not_buy": False, "long_pole": False},

    # 2815 Engine
    {"nsn": "2815-01-377-2184", "part_name": "Cylinder head gasket (HMMWV 6.5L)",
     "primary_platform": "HMMWV", "subsystem": "engine",
     "base_daily_per_vehicle": 0.00072, "unit_price_usd": 220,
     "rebuild_not_buy": False, "long_pole": False},

    # 5965 Headsets
    {"nsn": "5965-01-411-7783", "part_name": "Intercom headset H-250/U",
     "primary_platform": "LAV", "subsystem": "comms",
     "base_daily_per_vehicle": 0.0058, "unit_price_usd": 165,
     "rebuild_not_buy": False, "long_pole": False},

    # 6135 Batteries non-rechargeable
    {"nsn": "6135-01-301-8776", "part_name": "BA-5590 lithium primary battery (radio)",
     "primary_platform": "JLTV", "subsystem": "comms",
     "base_daily_per_vehicle": 0.012, "unit_price_usd": 26,
     "rebuild_not_buy": False, "long_pole": False},

    # 2810 Diesel engine assy (rebuild)
    {"nsn": "2810-01-501-9928", "part_name": "Caterpillar C-12 engine assembly (MTVR rebuild)",
     "primary_platform": "MTVR", "subsystem": "engine",
     "base_daily_per_vehicle": 0.00012, "unit_price_usd": 47_800,
     "rebuild_not_buy": True, "long_pole": True},

    # 3040 Misc Power Transmission
    {"nsn": "3040-01-489-1071", "part_name": "Final drive housing, port (AAV-7A1)",
     "primary_platform": "AAV-7A1", "subsystem": "tracks",
     "base_daily_per_vehicle": 0.00038, "unit_price_usd": 8_900,
     "rebuild_not_buy": True, "long_pole": True},

    # 5340 Brackets
    {"nsn": "5340-01-122-4419", "part_name": "Bracket, armor liner",
     "primary_platform": "LAV", "subsystem": "armor",
     "base_daily_per_vehicle": 0.0018, "unit_price_usd": 95,
     "rebuild_not_buy": False, "long_pole": False},

    # 1730 hydraulic actuator
    {"nsn": "1730-01-498-7102", "part_name": "Hydraulic actuator, ramp assy (AAV)",
     "primary_platform": "AAV-7A1", "subsystem": "hydraulics",
     "base_daily_per_vehicle": 0.0008, "unit_price_usd": 1_180,
     "rebuild_not_buy": True, "long_pole": True},

    # 2540 seat
    {"nsn": "2540-01-572-3041", "part_name": "Seat, armored crew (driver)",
     "primary_platform": "LAV", "subsystem": "interior",
     "base_daily_per_vehicle": 0.00060, "unit_price_usd": 2_240,
     "rebuild_not_buy": False, "long_pole": False},

    # 6130 Power dist
    {"nsn": "6130-01-651-1182", "part_name": "Power distribution unit, vehicle",
     "primary_platform": "MTVR", "subsystem": "electrical",
     "base_daily_per_vehicle": 0.00080, "unit_price_usd": 1_410,
     "rebuild_not_buy": True, "long_pole": False},
]


# ---------------------------------------------------------------------------
# Depots (real LOGCOM industrial base)
# ---------------------------------------------------------------------------
DEPOTS = [
    {
        "id": "ALB",
        "name": "MCLB Albany",
        "location": "Albany, GA",
        "bays": 14,
        "shifts_per_day": 2,
        "skills": {
            "hydraulics": 18, "powertrain": 22, "armor": 14,
            "avionics": 6, "weapons": 10, "wheels": 16,
        },
        "specialty": ["MTVR", "LAV", "M1A1"],
    },
    {
        "id": "BAR",
        "name": "MCLB Barstow",
        "location": "Barstow, CA",
        "bays": 12,
        "shifts_per_day": 2,
        "skills": {
            "hydraulics": 14, "powertrain": 18, "armor": 16,
            "avionics": 4, "weapons": 12, "wheels": 14,
        },
        "specialty": ["AAV-7A1", "LAV", "JLTV"],
    },
    {
        "id": "BIC",
        "name": "Blount Island Command",
        "location": "Jacksonville, FL",
        "bays": 10,
        "shifts_per_day": 3,
        "skills": {
            "hydraulics": 12, "powertrain": 14, "armor": 8,
            "avionics": 16, "weapons": 6, "wheels": 8,
        },
        "specialty": ["MV-22B", "AAV-7A1"],
    },
]


# ---------------------------------------------------------------------------
# Fleets / OPTEMPO scaling for synthetic 90-day work-order history
# ---------------------------------------------------------------------------
FLEET = {
    "MTVR": 320, "LAV": 90, "JLTV": 410, "AAV-7A1": 60,
    "MV-22B": 22, "M88A2": 16, "HMMWV": 380, "M1A1": 14,
}


def gen_maintenance_history(catalog: list[dict], rng: random.Random,
                            days: int = 90) -> list[dict]:
    by_plat: dict[str, list[dict]] = {}
    for c in catalog:
        by_plat.setdefault(c["primary_platform"], []).append(c)

    base_date = datetime(2026, 1, 27)
    records: list[dict] = []
    seq = 0
    for d in range(days):
        day = base_date + timedelta(days=d)
        dow = day.weekday()
        ripple = 1.25 if dow in (0, 1) else (0.85 if dow in (5, 6) else 1.0)
        for plat_id, fleet_size in FLEET.items():
            for part in by_plat.get(plat_id, []):
                lam = part["base_daily_per_vehicle"] * fleet_size * ripple
                noisy = max(0.0, lam + rng.gauss(0, max(0.4, lam ** 0.5)))
                qty = int(round(noisy))
                if qty <= 0:
                    continue
                seq += 1
                # PMCS code rotates (real Marine codes — no fake "SLEP")
                pmcs = ["B", "D", "A", "W", "M", "Q", "S", "AN"][seq % 8]
                records.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "work_order_id": f"WO-{day.strftime('%y%m%d')}-{seq:05d}",
                    "platform": plat_id,
                    "vehicle_id": f"{plat_id}-{rng.randint(1, fleet_size):04d}",
                    "pmcs_code": pmcs,
                    "nsn": part["nsn"],
                    "part_name": part["part_name"],
                    "qty_consumed": qty,
                    "subsystem": part["subsystem"],
                })
    return records


# ---------------------------------------------------------------------------
# Inventory ledger (5,000 items) — ICM workbook stand-in
# ---------------------------------------------------------------------------
def gen_inventory(catalog: list[dict], rng: random.Random,
                  n_items: int = 5_000) -> list[dict]:
    today = datetime(2026, 4, 27)
    locations = [
        "WHSE-A1-ALB", "WHSE-A2-ALB", "WHSE-B1-ALB", "WHSE-C1-ALB",
        "WHSE-A1-BAR", "WHSE-B2-BAR", "VBAY-01-BAR",
        "BIC-WHSE-1", "BIC-WHSE-2", "BIC-CAGE-A",
    ]
    marines = [
        "SSgt Reyes, J.", "SSgt Whitfield, T.", "Sgt Alvarado, M.",
        "Sgt Carrillo, R.", "Sgt Pham, D.", "Cpl Boudreau, A.",
        "Cpl Diallo, S.", "Cpl Henderson, B.", "Cpl Iwamoto, K.",
        "GySgt Underwood, R.", "MSgt Quinones, V.",
    ]
    cond_codes = ["A", "A", "A", "A", "B", "B", "C", "F", "H"]

    rows = []
    for i in range(n_items):
        part = catalog[i % len(catalog)]
        base_qty = 14 if part["long_pole"] else 60
        qty_on_hand = max(0, int(rng.gauss(base_qty, base_qty * 0.4)))
        qty_required = max(qty_on_hand // 2, int(rng.gauss(base_qty * 0.7, base_qty * 0.2)))
        last_inv_days = rng.randint(2, 80)
        rows.append({
            "item_id": f"ITM-{1_000_000 + i:07d}",
            "nsn": part["nsn"],
            "nomenclature": part["part_name"],
            "fsc": part["nsn"][:4],
            "qty_on_hand": qty_on_hand,
            "qty_required": qty_required,
            "shortage": max(0, qty_required - qty_on_hand),
            "condition_code": rng.choice(cond_codes),
            "location_id": rng.choice(locations),
            "responsible_marine": rng.choice(marines),
            "last_inventoried_date": (today - timedelta(days=last_inv_days)).strftime("%Y-%m-%d"),
            "days_since_inventory": last_inv_days,
            "unit_price_usd": part["unit_price_usd"],
        })
    return rows


# ---------------------------------------------------------------------------
# SHA-256 chained ledger seed
# ---------------------------------------------------------------------------
def sha256_chain(prev_hash: str, payload: dict) -> str:
    body = (prev_hash + json.dumps(payload, sort_keys=True)).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def seed_ledger() -> list[dict]:
    """Seed the audit ledger with three founding entries; each row carries the
    hash of the previous row, so any tampering is immediately visible."""
    entries = []
    prev = "0" * 64
    seeds = [
        {"ts": "2026-04-27T07:00:00Z", "kind": "GENESIS",
         "actor": "system", "note": "Predict-Maint append-only ledger initialised."},
        {"ts": "2026-04-27T07:00:01Z", "kind": "INVENTORY_SYNC",
         "actor": "GCSS-MC bridge", "note": "5,000-item sync from ICM workbook."},
        {"ts": "2026-04-27T07:00:02Z", "kind": "TELEMETRY_SYNC",
         "actor": "CWRU-bridge", "note": "Vibration corpus indexed (200 windows, 4 fault classes)."},
    ]
    for s in seeds:
        h = sha256_chain(prev, s)
        entries.append({**s, "prev_hash": prev, "hash": h})
        prev = h
    return entries


# ---------------------------------------------------------------------------
# Cached briefs (3 scenarios)
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "nominal",
        "label": "Nominal — single asset triage",
        "asset_id": "MTVR-2491",
        "frame": "Sensor crossed amber threshold during yard test. Demand spike under control. Stock available CONUS.",
    },
    {
        "id": "surge",
        "label": "Surge — INDOPAC MEB push",
        "asset_id": "AAV-7A1-3318",
        "frame": "MARFORPAC stand-in force inducting 3 AAV-7A1 hulls; final-drive bearings projected to spike 4x baseline.",
    },
    {
        "id": "parts_constrained",
        "label": "Parts-constrained — long-pole NSN slip",
        "asset_id": "MV-22B-167902",
        "frame": "Prop rotor hub bearing trending toward induct-now. NSN 3110-01-617-8013 under stress with 0 on hand at MCLB Albany.",
    },
]


def _deterministic_brief(scenario: dict, asset: dict, chain_summary: dict) -> str:
    """Cache-first deterministic brief used as fallback for the LLM call."""
    ass = asset
    ch = chain_summary
    return (
        f"**BLUF.** {ass['asset_id']} ({ass['type']}) shows a "
        f"**{ass['current_class'].replace('_', ' ').upper()}** signature at the "
        f"{ass['hub_position'].lower()} hub with severity {ass['current_severity']:.2f}. "
        f"The 5-stage closed loop has fired: sensor -> classifier -> 30-day forecast spike "
        f"({ch['projected_30d']:.0f} ea proj. vs {ch['actual_30d']:.0f} historical) -> "
        f"GCSS-MC stock check ({ch['on_hand']} ea at {ch['source_depot']}) -> "
        f"depot induction reslot ({ch['induction_depot']}, "
        f"{ch['induction_window']}) -> ledger entry hash "
        f"`{ch['ledger_hash'][:16]}...`. Recommended commander action: "
        f"**{ch['action'].upper()}** by {ch['action_due_by']}.\n\n"
        f"## SENSOR-TO-SHELF CHAIN\n"
        f"1. **Sensor** — CWRU drive-end accelerometer trace (12 kHz, 1 s window). "
        f"Hand-crafted features fed into RandomForest; predicted **{ass['current_class']}** at "
        f"high confidence. RUL estimate: {ch['rul_hours']} operating hours.\n"
        f"2. **Forecast** — Holt-Winters projection on NSN {ass['nsn']} jumps from "
        f"{ch['actual_30d']:.0f} ea (trailing 30 d) to {ch['projected_30d']:.0f} ea "
        f"(next 30 d). Spike attributable to RUL-triggered induction wave across "
        f"the {ass['type'].split()[0]} fleet.\n"
        f"3. **Auto-reorder** — Validation against GCSS-MC stock + ICM ledger: "
        f"{ch['on_hand']} ea on hand at {ch['source_depot']}, shortfall "
        f"{ch['shortfall']} ea. Recommended reorder qty: **{ch['recommended_qty']} ea**, "
        f"action due by **{ch['action_due_by']}**.\n"
        f"4. **Depot induction** — `{ass['asset_id']}` reslotted into "
        f"**{ch['induction_depot']}** Gantt at **{ch['induction_window']}** "
        f"(rebuild-not-buy: {'YES' if ass['rebuild_not_buy'] else 'NO'}).\n"
        f"5. **Ledger** — Append-only audit row written. SHA-256 hash chain "
        f"intact ({ch['ledger_hash'][:32]}...). Commander brief signed by hash.\n\n"
        f"## NAMED BOTTLENECK\n"
        f"NSN {ass['nsn']} ({ass['part_name']}) — {ch['on_hand']} ea on hand at "
        f"{ch['source_depot']}; lead time {ch['lead_time_days']} days from DLA Land. "
        f"This is the rate-limiter on closing the loop within the 30-day window.\n\n"
        f"## RECOMMENDED COMMANDER ACTION\n"
        f"{ch['action_long']}\n\n"
        f"## CLASSIFICATION\n"
        f"UNCLASSIFIED // FOR OFFICIAL USE ONLY."
    )


def _scenario_chain_summary(scenario: dict, asset: dict, catalog: list[dict],
                            depots: list[dict]) -> dict:
    """Synthesize a scenario-aligned chain summary (fed into both deterministic
    + LLM briefs so they share the same numbers)."""
    part = next((c for c in catalog if c["nsn"] == asset["nsn"]), catalog[0])
    today = datetime(2026, 4, 27)

    base_30d = part["base_daily_per_vehicle"] * FLEET.get(part["primary_platform"], 200) * 30
    if scenario["id"] == "surge":
        spike_mult = 4.0
    elif scenario["id"] == "parts_constrained":
        spike_mult = 2.6
    else:
        spike_mult = 1.7
    actual_30d = base_30d
    projected_30d = base_30d * spike_mult

    on_hand_map = {
        "nominal": 14,
        "surge": 6,
        "parts_constrained": 0,
    }
    on_hand = on_hand_map[scenario["id"]]
    source_depot = "MCLB Albany"
    lead_time_days_map = {"nominal": 11, "surge": 18, "parts_constrained": 31}
    lead_time = lead_time_days_map[scenario["id"]]
    shortfall = max(0, int(round(projected_30d - on_hand)))
    recommended_qty = int(round(shortfall * 1.25))
    action_due = (today + timedelta(days=max(2, 14 - lead_time // 4))).strftime("%Y-%m-%d")

    induction_depot_id = asset["depot"]
    induction_depot = next(d for d in depots if d["id"] == induction_depot_id)["name"]
    induction_start = today + timedelta(days=3 if scenario["id"] != "parts_constrained" else 9)
    induction_end = induction_start + timedelta(days=11)
    induction_window = (
        f"{induction_start.strftime('%d-%b')} -> {induction_end.strftime('%d-%b')}"
    )

    rul_map = {"nominal": 312, "surge": 184, "parts_constrained": 96}
    rul = rul_map[scenario["id"]]

    if scenario["id"] == "parts_constrained":
        action = "expedite_lateral_transfer"
        action_long = (
            f"Expedite lateral transfer of {recommended_qty} ea NSN {asset['nsn']} from "
            f"Blount Island Command to {source_depot} via overnight blue-stripe; "
            f"defer 2 lower-priority MV-22B inductions at BIC by 7 days; release held-parts "
            f"pool. Net result: closes the 30-day shortfall and unblocks 1 priority hull."
        )
    elif scenario["id"] == "surge":
        action = "induct_now_pull_forward"
        action_long = (
            f"Induct {asset['asset_id']} immediately at {induction_depot}; pull forward "
            f"{recommended_qty} ea NSN {asset['nsn']} from Barstow on the next ALB resupply "
            f"sortie; surge a second-shift wheels-skill crew at ALB. +12% projected "
            f"throughput across the 30-day window."
        )
    else:
        action = "induct_now"
        action_long = (
            f"Induct {asset['asset_id']} at {induction_depot} during the "
            f"{induction_window} window. Pull {recommended_qty} ea NSN {asset['nsn']} "
            f"from MCLB Albany on the next milk-run; resume normal posture once the "
            f"asset clears."
        )

    payload = {
        "scenario": scenario["id"],
        "asset_id": asset["asset_id"],
        "nsn": asset["nsn"],
        "actual_30d": float(actual_30d),
        "projected_30d": float(projected_30d),
        "on_hand": int(on_hand),
        "source_depot": source_depot,
        "shortfall": int(shortfall),
        "recommended_qty": int(recommended_qty),
        "lead_time_days": int(lead_time),
        "action_due_by": action_due,
        "induction_depot": induction_depot,
        "induction_window": induction_window,
        "induction_start": induction_start.strftime("%Y-%m-%d"),
        "induction_end": induction_end.strftime("%Y-%m-%d"),
        "rul_hours": int(rul),
        "action": action,
        "action_long": action_long,
    }
    # Deterministic ledger hash for the scenario payload
    payload["ledger_hash"] = sha256_chain("0" * 64, payload)
    return payload


def precompute_briefs(catalog: list[dict], depots: list[dict]) -> dict:
    try:
        from shared.kamiwaza_client import chat
        have_llm = True
    except Exception:
        have_llm = False

    out = {}
    for scenario in SCENARIOS:
        asset = next((a for a in ASSETS if a["asset_id"] == scenario["asset_id"]), ASSETS[0])
        chain = _scenario_chain_summary(scenario, asset, catalog, depots)
        text = None
        if have_llm:
            try:
                import concurrent.futures
                system = (
                    "You are PREDICT-MAINT, a USMC Marine Corps Logistics Command "
                    "(MARCORLOGCOM) closed-loop predictive-maintenance analyst. "
                    "You write a *Closed-Loop Maintenance Action Brief* for an O-3 "
                    "commander and an E-5 maintenance chief. Required structure "
                    "(markdown):\n\n"
                    "Open with **BLUF** (one bold paragraph, 2-3 sentences) naming the "
                    "asset, the failure mode, the named bottleneck NSN, and the "
                    "recommended commander action with action-due date.\n\n"
                    "Then EXACTLY these sections, in order:\n"
                    "  ## SENSOR-TO-SHELF CHAIN  (5 numbered stages)\n"
                    "  ## NAMED BOTTLENECK\n"
                    "  ## RECOMMENDED COMMANDER ACTION\n"
                    "  ## CLASSIFICATION\n\n"
                    "In SENSOR-TO-SHELF CHAIN: number 1-5 corresponding to "
                    "Sensor / Forecast / Auto-reorder / Depot induction / Ledger. "
                    "Cite specific NSN, depot codes (ALB / BAR / BIC), real "
                    "platforms (MTVR/JLTV/LAV/AAV-7A1/MV-22B), and the SHA-256 "
                    "ledger hash prefix. Use real PMCS codes (B/D/A/W/M/Q/S/AN) "
                    "if you cite a check; do NOT invent codes like 'SLEP'.\n"
                    "Close CLASSIFICATION with: UNCLASSIFIED // FOR OFFICIAL USE ONLY.\n\n"
                    "Keep total output under ~480 words. Be specific and quantified."
                )
                user = (
                    f"SCENARIO: {scenario['label']}\n"
                    f"FRAME: {scenario['frame']}\n\n"
                    f"ASSET: {asset['asset_id']} ({asset['type']}) — {asset['unit']}\n"
                    f"  hub: {asset['hub_position']}; op_hours: {asset['operating_hours']}\n"
                    f"  classifier: {asset['current_class']} @ severity {asset['current_severity']:.2f}\n"
                    f"  RUL est: {chain['rul_hours']} hr\n\n"
                    f"DEMAND FORECAST (30-day, NSN {asset['nsn']}):\n"
                    f"  trailing actual: {chain['actual_30d']:.0f} ea\n"
                    f"  projected: {chain['projected_30d']:.0f} ea\n\n"
                    f"GCSS-MC STOCK + ICM LEDGER:\n"
                    f"  on hand at {chain['source_depot']}: {chain['on_hand']} ea\n"
                    f"  shortfall: {chain['shortfall']} ea\n"
                    f"  recommended reorder: {chain['recommended_qty']} ea\n"
                    f"  lead time if short: {chain['lead_time_days']} days\n"
                    f"  action due by: {chain['action_due_by']}\n\n"
                    f"DEPOT INDUCTION (greedy reslot):\n"
                    f"  asset reslotted at {chain['induction_depot']}\n"
                    f"  window: {chain['induction_window']}\n"
                    f"  rebuild_not_buy: {asset['rebuild_not_buy']}\n\n"
                    f"LEDGER:\n"
                    f"  SHA-256 chain hash: {chain['ledger_hash']}\n\n"
                    f"Compose the Closed-Loop Maintenance Action Brief now."
                )
                msgs = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    text = ex.submit(
                        lambda: chat(msgs, model="gpt-5.4", temperature=0.4)
                    ).result(timeout=35.0)
                if not text or "BLUF" not in text:
                    text = None
            except Exception:
                text = None
        if not text:
            text = _deterministic_brief(scenario, asset, chain)
        out[scenario["id"]] = {
            "label": scenario["label"],
            "frame": scenario["frame"],
            "asset_id": asset["asset_id"],
            "chain_summary": chain,
            "brief": text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "hero" if (text and "BLUF" in text and have_llm) else "deterministic",
        }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(*, do_briefs: bool = True) -> None:
    rng_np = np.random.default_rng(SEED)
    rng = random.Random(SEED)

    # Vibration corpus (CWRU stand-in)
    corpus = gen_corpus(rng_np)
    np.savez_compressed(ROOT / "vibration_corpus.npz", **corpus)
    print(f"  wrote vibration_corpus.npz: {corpus['signals'].shape} signals")

    # NSN catalog
    (ROOT / "nsn_catalog.json").write_text(json.dumps(NSN_CATALOG, indent=2))
    print(f"  wrote nsn_catalog.json: {len(NSN_CATALOG)} NSNs (FSC-coherent)")

    # Asset roster
    (ROOT / "assets.json").write_text(json.dumps(ASSETS, indent=2))
    print(f"  wrote assets.json: {len(ASSETS)} test assets")

    # Depot capacity
    (ROOT / "depot_capacity.json").write_text(json.dumps(DEPOTS, indent=2))
    print(f"  wrote depot_capacity.json: {len(DEPOTS)} depots")

    # Maintenance history
    history = gen_maintenance_history(NSN_CATALOG, rng, days=90)
    hist_path = ROOT / "maintenance_history.csv"
    with hist_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        w.writeheader()
        w.writerows(history)
    print(f"  wrote maintenance_history.csv: {len(history)} work orders")

    # Inventory ledger
    inventory = gen_inventory(NSN_CATALOG, rng, n_items=5_000)
    inv_path = ROOT / "inventory.csv"
    with inv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(inventory[0].keys()))
        w.writeheader()
        w.writerows(inventory)
    print(f"  wrote inventory.csv: {len(inventory)} items")

    # Audit ledger seed (SHA-256 chained)
    ledger = seed_ledger()
    with (ROOT / "ledger.jsonl").open("w") as f:
        for entry in ledger:
            f.write(json.dumps(entry) + "\n")
    print(f"  wrote ledger.jsonl: {len(ledger)} seed entries")

    # Bearing characteristic frequencies (for the README sanity check)
    cf = char_freqs()
    print(f"  bearing freqs (Hz): BPFO={cf.bpfo:.2f} BPFI={cf.bpfi:.2f} BSF={cf.bsf:.2f} FTF={cf.ftf:.2f}")

    # Scenarios
    (ROOT / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2))

    # Cached briefs
    if do_briefs:
        briefs = precompute_briefs(NSN_CATALOG, DEPOTS)
        (ROOT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
        print(f"  wrote cached_briefs.json: {len(briefs)} scenarios")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--no-briefs", action="store_true",
                   help="Skip pre-computing cached briefs (LLM-free).")
    args = p.parse_args()
    main(do_briefs=not args.no_briefs)
