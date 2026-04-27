"""Synthetic CWRU-shape vibration corpus generator.

Models the Case Western Reserve University Bearing Data Center 12 kHz drive-end
fixture so FORGE has plausible vibration to demo against without requiring the
real CWRU dataset at install time. We emulate four classes (Healthy / Inner
Race / Outer Race / Ball) by superposing:
    - shaft rotation harmonics (motor + gear mesh)
    - characteristic bearing fault frequencies (BPFO / BPFI / BSF / FTF)
    - amplitude modulation (sidebands at shaft rate for inner-race; cage rate for ball)
    - broadband Gaussian + impulsive noise

Bearing geometry: SKF 6205-2RS JEM (CWRU canonical drive-end), n=9 balls,
d=0.3126", D=1.537", contact angle 0deg. Shaft 1772 rpm (29.53 Hz) under load.

Output:
    data/vibration_corpus.npz   ← signals, labels, metadata
    data/vehicles.json          ← three test assets (MTVR / JLTV / LAV)
    data/maintenance_log.json   ← 6-month work-order history per vehicle
    data/parts_inventory.json   ← MCLB Albany NSN inventory for the agent's tool

Swapping in real CWRU vibration data (or any 12 kHz accelerometer trace) is a
Bucket B change — see ../DATA_INGESTION.md for the loader hook. Drop single-
column 12 kHz vibration CSVs in data/signals/<asset_id>.csv and point the
loader at that folder; the classifier, envelope spectrum, RUL estimator, and
agent all run unchanged.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
SEED = 1776
FS = 12_000          # Hz, drive-end accelerometer sample rate (CWRU canonical)
WIN_SEC = 1.0
N = int(FS * WIN_SEC)

# CWRU 6205-2RS JEM drive-end bearing geometry
N_BALLS = 9
BALL_DIA_IN = 0.3126
PITCH_DIA_IN = 1.537
CONTACT_ANGLE_DEG = 0.0

# Operating shaft frequency (1772 rpm @ ~1 hp load)
F_SHAFT = 1772.0 / 60.0   # ≈ 29.53 Hz

CLASSES = ["healthy", "inner_race", "outer_race", "ball"]
SAMPLES_PER_CLASS = 50

VEHICLES = [
    {
        "vehicle_id": "MTVR-2491",
        "type": "M1083 MTVR",
        "unit": "1st MLG, CLB-1",
        "hub_position": "Right rear (axle 3)",
        "operating_hours": 4127,
        "since_last_overhaul_hr": 612,
        "current_class": "outer_race",
        "current_severity": 0.78,
        "rul_hours_estimate": 118,
        "nsn": "3110-01-433-0978",
        "part_name": "Bearing, Wheel Hub, Tapered Roller, MTVR Drive Axle",
    },
    {
        "vehicle_id": "JLTV-1107",
        "type": "JLTV M1278A1 Heavy Gun Carrier",
        "unit": "2d MarDiv, 2/2",
        "hub_position": "Front left",
        "operating_hours": 1842,
        "since_last_overhaul_hr": 421,
        "current_class": "healthy",
        "current_severity": 0.04,
        "rul_hours_estimate": 1500,
        "nsn": "3110-01-660-2271",
        "part_name": "Bearing, Wheel Hub, Front, JLTV",
    },
    {
        "vehicle_id": "LAV-25-0892",
        "type": "LAV-25A2",
        "unit": "1st LAR Bn",
        "hub_position": "Mid right (axle 2)",
        "operating_hours": 6810,
        "since_last_overhaul_hr": 980,
        "current_class": "inner_race",
        "current_severity": 0.41,
        "rul_hours_estimate": 312,
        "nsn": "3110-01-204-5587",
        "part_name": "Bearing, Wheel Hub, LAV-25 Drive Train",
    },
]

PARTS_INVENTORY = {
    # NSN -> qty available at MCLB Albany / nearest depot
    "3110-01-433-0978": {
        "name": "Bearing, Wheel Hub, Tapered Roller, MTVR Drive Axle",
        "qty_albany": 14,
        "qty_barstow": 8,
        "qty_blount_island": 22,
        "lead_time_days_if_short": 11,
        "unit_cost_usd": 387.42,
    },
    "3110-01-660-2271": {
        "name": "Bearing, Wheel Hub, Front, JLTV",
        "qty_albany": 41,
        "qty_barstow": 27,
        "qty_blount_island": 19,
        "lead_time_days_if_short": 6,
        "unit_cost_usd": 512.10,
    },
    "3110-01-204-5587": {
        "name": "Bearing, Wheel Hub, LAV-25 Drive Train",
        "qty_albany": 0,
        "qty_barstow": 3,
        "qty_blount_island": 5,
        "lead_time_days_if_short": 21,
        "unit_cost_usd": 622.85,
    },
}


@dataclass
class CharFreqs:
    bpfo: float
    bpfi: float
    bsf: float
    ftf: float


def char_freqs(f_shaft: float = F_SHAFT) -> CharFreqs:
    """Compute characteristic bearing frequencies from geometry.

    Standard formulas for ball bearings, contact angle ~0:
      FTF  = (f/2) * (1 - d/D)
      BPFO = (n/2) * f * (1 - d/D)
      BPFI = (n/2) * f * (1 + d/D)
      BSF  = (D / (2d)) * f * (1 - (d/D)**2)
    """
    ratio = BALL_DIA_IN / PITCH_DIA_IN
    ftf = (f_shaft / 2.0) * (1 - ratio)
    bpfo = (N_BALLS / 2.0) * f_shaft * (1 - ratio)
    bpfi = (N_BALLS / 2.0) * f_shaft * (1 + ratio)
    bsf = (PITCH_DIA_IN / (2 * BALL_DIA_IN)) * f_shaft * (1 - ratio ** 2)
    return CharFreqs(bpfo=bpfo, bpfi=bpfi, bsf=bsf, ftf=ftf)


def synth_signal(
    cls: str,
    *,
    rng: np.random.Generator,
    severity: float | None = None,
    fs: int = FS,
    n: int = N,
) -> np.ndarray:
    """Generate one 1-second drive-end vibration window for a given class.

    severity: 0.0 (incipient) to 1.0 (catastrophic). Default: random per call.
    """
    cf = char_freqs()
    t = np.arange(n) / fs
    if severity is None:
        severity = float(rng.uniform(0.25, 0.95))

    # Baseline: shaft + gear-mesh harmonics + noise floor
    sig = (
        0.10 * np.sin(2 * np.pi * F_SHAFT * t)
        + 0.06 * np.sin(2 * np.pi * 2 * F_SHAFT * t + rng.uniform(0, 2 * np.pi))
        + 0.04 * np.sin(2 * np.pi * 3 * F_SHAFT * t + rng.uniform(0, 2 * np.pi))
        + 0.05 * np.sin(2 * np.pi * 178.0 * t + rng.uniform(0, 2 * np.pi))   # gear mesh
    )
    # Broadband noise (sensor + structural)
    sig += rng.normal(0.0, 0.06, size=n)

    # Random small impulsive contamination (always present in real machinery)
    n_imp = rng.integers(0, 4)
    for _ in range(n_imp):
        idx = int(rng.integers(0, n))
        sig[idx] += rng.normal(0.0, 0.15)

    if cls == "healthy":
        return sig.astype(np.float32)

    # Pick fault impulse train freq + amplitude-modulation envelope
    if cls == "outer_race":
        f_fault = cf.bpfo
        am_env = 1.0  # outer race: fault is stationary in load zone, no AM
        amp = 0.6 * severity
        impulse_decay = 320.0 * (0.6 + 0.4 * severity)  # higher Q = sharper impulses
        carrier = rng.uniform(2800, 3600)
    elif cls == "inner_race":
        f_fault = cf.bpfi
        # Inner race: amplitude-modulated by shaft rotation (passes through load zone)
        am_env = 1.0 + 0.7 * np.cos(2 * np.pi * F_SHAFT * t)
        amp = 0.55 * severity
        impulse_decay = 280.0 * (0.6 + 0.4 * severity)
        carrier = rng.uniform(2600, 3400)
    elif cls == "ball":
        f_fault = cf.bsf
        # Ball fault: AM by cage frequency (FTF), and the impulses appear at 2x BSF too
        am_env = 1.0 + 0.6 * np.cos(2 * np.pi * cf.ftf * t)
        amp = 0.45 * severity
        impulse_decay = 240.0 * (0.6 + 0.4 * severity)
        carrier = rng.uniform(2200, 3000)
    else:
        raise ValueError(f"Unknown class {cls}")

    # Build impulse train at f_fault, each impulse is a damped exponential burst
    # convolved with a high-frequency carrier — classical bearing-fault signature.
    period_samples = max(2, int(fs / f_fault))
    impulse_train = np.zeros(n)
    # Add a small jitter (slip) — real bearings slip 1-2%
    jitter = rng.normal(0, 0.015, size=n // period_samples + 2)
    pos = 0
    k = 0
    while pos < n and k < len(jitter):
        slip_pos = int(pos * (1.0 + jitter[k]))
        if 0 <= slip_pos < n:
            impulse_train[slip_pos] = 1.0
        pos += period_samples
        k += 1

    # Convolve with damped resonance burst (high-freq ringdown)
    burst_len = int(fs * 0.01)  # 10 ms ringdown
    bt = np.arange(burst_len) / fs
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


def gen_maintenance_log(seed: int = SEED) -> dict:
    rng = random.Random(seed)
    log: dict[str, list[dict]] = {}

    def wo(date: str, kind: str, narrative: str, hours: int) -> dict:
        return {
            "date": date,
            "type": kind,
            "narrative": narrative,
            "operating_hours_at_event": hours,
        }

    log["MTVR-2491"] = [
        wo("2025-10-12", "PMCS-Q", "Quarterly PMCS. Hub temp slightly elevated rear right; greased; within tolerance.", 3702),
        wo("2025-12-04", "Operator Report", "Driver complains of intermittent rumble at 25-40 mph from rear right corner. No vibration at low speed.", 3854),
        wo("2026-01-19", "PMCS-Q", "Quarterly PMCS. Vibration noted on rear right hub. Mechanic recommended monitor; no maintenance action taken — mission tempo prevented teardown.", 3961),
        wo("2026-02-22", "Mission Log", "VTC convoy SAN MATEO->BLOUNT ISLAND. 412 mi. No mid-mission faults but driver re-reported rumble.", 4034),
        wo("2026-03-30", "Operator Report", "Rumble now constant >15 mph. Tactical movement to MCB CamPen. Vehicle returned for evaluation.", 4087),
        wo("2026-04-18", "Sensor Trigger", "Vibration sensor on hub passed amber threshold during yard test. Telemetry forwarded to FORGE.", 4127),
    ]
    log["JLTV-1107"] = [
        wo("2025-11-08", "PMCS-S", "Semi-annual. All hubs nominal. New vehicle, low hours.", 1422),
        wo("2026-01-15", "Operator Report", "Cold start moan front left, dissipates within 1 mile. Likely brake; no further investigation.", 1611),
        wo("2026-03-02", "PMCS-Q", "Quarterly PMCS. All hubs within spec. Greased per LO.", 1759),
    ]
    log["LAV-25-0892"] = [
        wo("2025-09-22", "Depot Overhaul", "Returned from 50-level overhaul at MDMC Barstow. New axle 1, axle 2 hub bearings refurbished (not replaced).", 5830),
        wo("2025-11-30", "Operator Report", "High-pitched whine axle 2 right at sustained road speed >35 mph.", 6042),
        wo("2026-01-08", "PMCS-Q", "Quarterly PMCS. Mechanic noted whine still present, recommended hub inspection at next 1000 hr mark.", 6201),
        wo("2026-02-26", "Field Repair", "Mid-mission grease pumped to axle 2 right hub. Whine reduced but did not eliminate.", 6488),
        wo("2026-04-05", "Sensor Trigger", "Vibration sensor crossed yellow threshold. Crew re-tasked to FORGE evaluation queue.", 6810),
    ]
    return log


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    corpus = gen_corpus(rng)
    np.savez_compressed(HERE / "vibration_corpus.npz", **corpus)
    print(f"  wrote {HERE/'vibration_corpus.npz'}: {corpus['signals'].shape} signals, {len(CLASSES)} classes")

    log = gen_maintenance_log()
    (HERE / "maintenance_log.json").write_text(json.dumps(log, indent=2))
    print(f"  wrote {HERE/'maintenance_log.json'}: {sum(len(v) for v in log.values())} work orders across {len(log)} vehicles")

    (HERE / "parts_inventory.json").write_text(json.dumps(PARTS_INVENTORY, indent=2))
    print(f"  wrote {HERE/'parts_inventory.json'}: {len(PARTS_INVENTORY)} NSNs in stock dataset")

    (HERE / "vehicles.json").write_text(json.dumps(VEHICLES, indent=2))
    print(f"  wrote {HERE/'vehicles.json'}: {len(VEHICLES)} test assets")

    cf = char_freqs()
    print(f"  bearing characteristic freqs (Hz): BPFO={cf.bpfo:.2f}  BPFI={cf.bpfi:.2f}  BSF={cf.bsf:.2f}  FTF={cf.ftf:.2f}")


if __name__ == "__main__":
    main()
