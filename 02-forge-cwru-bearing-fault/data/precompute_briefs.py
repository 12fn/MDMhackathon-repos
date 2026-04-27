"""Precompute commander briefs for all three demo vehicles and cache to disk.

Run once before the demo so the Streamlit UI can render the LLM hero output
instantly (no LLM round-trip during recording).

    python -m data.precompute_briefs

Writes data/cached_briefs.json keyed by vehicle_id.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(ROOT))

from src.signal_proc import hand_crafted_features  # noqa: E402
from src.classifier import (  # noqa: E402
    CLASSES,
    estimate_rul,
    predict_one,
    severity_from_features,
    train_classifier,
)
from src.agent import commander_recommendation, lookup_part_availability  # noqa: E402

DATA = ROOT / "data"
CORPUS = DATA / "vibration_corpus.npz"
LOG = DATA / "maintenance_log.json"
VEHICLES_FILE = DATA / "vehicles.json"
OUT = DATA / "cached_briefs.json"


def render_spectrogram_png(sig: np.ndarray, fs: int, vehicle_id: str) -> bytes:
    """Standalone (non-Streamlit) spectrogram PNG renderer matching app.py output."""
    import io
    import matplotlib.pyplot as plt
    from src.signal_proc import characteristic_freqs, spectrogram_image

    BG, SURFACE, NEON, BORDER = "#0A0A0A", "#0E0E0E", "#00FFA7", "#222222"
    f, t, Sxx = spectrogram_image(sig, fs)
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=140)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(SURFACE)
    ax.pcolormesh(t, f, Sxx, shading="gouraud", cmap="inferno")
    ax.set_ylim(0, 5500)
    ax.set_title(f"Drive-end accelerometer spectrogram - {vehicle_id}", color=NEON, pad=10)
    cf = characteristic_freqs()
    for label, freq, color in [
        ("BPFO", cf.bpfo, NEON),
        ("BPFI", cf.bpfi, "#62d4ff"),
        ("BSF", cf.bsf, "#ffb347"),
    ]:
        ax.axhline(freq, color=color, linewidth=0.7, linestyle="--", alpha=0.55)
    for spine in ax.spines.values():
        spine.set_color(BORDER)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def pick_signal_for_class(corpus: dict, target_class: str, severity_hint: float | None) -> tuple[np.ndarray, float]:
    cls_idx = CLASSES.index(target_class)
    mask = corpus["labels"] == cls_idx
    idxs = np.where(mask)[0]
    if severity_hint is not None and target_class != "healthy":
        sevs = corpus["severity"][idxs]
        closest = idxs[int(np.argmin(np.abs(sevs - severity_hint)))]
        return corpus["signals"][closest], float(corpus["severity"][closest])
    rng = np.random.default_rng(1776)
    pick = int(rng.choice(idxs))
    return corpus["signals"][pick], float(corpus["severity"][pick])


def main() -> None:
    print(f"Loading corpus from {CORPUS}...")
    z = np.load(CORPUS, allow_pickle=False)
    corpus = {
        "signals": z["signals"],
        "labels": z["labels"],
        "severity": z["severity"],
        "fs": int(z["fs"]),
    }
    fs = corpus["fs"]

    print("Training classifier (one-time)...")
    clf, clf_meta = train_classifier(CORPUS)
    print(f"  test acc: {clf_meta['test_acc']*100:.1f}%")

    vehicles = json.loads(VEHICLES_FILE.read_text())
    log = json.loads(LOG.read_text())

    cache: dict[str, dict] = {}
    for v in vehicles:
        vid = v["vehicle_id"]
        print(f"\n[{vid}] Generating brief...")
        sig, sev = pick_signal_for_class(
            corpus,
            v["current_class"],
            severity_hint=v["current_severity"] if v["current_class"] != "healthy" else None,
        )
        spec_png = render_spectrogram_png(sig, fs, vid)
        pred = predict_one(clf, sig, fs)
        feats = hand_crafted_features(sig, fs)
        sev_est = severity_from_features(feats)
        rul = estimate_rul(pred["class"], pred["confidence"], sev_est, v["operating_hours"])
        wo = log.get(vid, [])

        try:
            result = commander_recommendation(
                spectrogram_png=spec_png,
                classifier_result=pred,
                rul_result=rul,
                vehicle=v,
                maintenance_log=wo,
                use_hero_model=False,  # mini is fast and reliable
            )
            print(f"  -> recommendation: {result.get('recommendation')} ({result.get('urgency')})")
        except Exception as e:
            print(f"  ! LLM failed ({e}); writing rule-based fallback to cache.")
            parts = lookup_part_availability(v["nsn"])
            result = {
                "recommendation": rul.get("recommendation", "monitor_closely"),
                "urgency": "amber" if rul.get("recommendation") != "induct_now" else "red",
                "rationale_bullets": [
                    f"Classifier: {pred['class'].replace('_',' ')} @ {pred['confidence']*100:.0f}% confidence.",
                    f"Severity index {sev_est:.2f}; RUL {rul['rul_hours']} operating hours.",
                    f"Maintenance log shows {len(wo)} prior events; trend evaluated.",
                ],
                "commander_brief": (
                    f"{vid} drive-end vibration shows {pred['class'].replace('_',' ')} signature at "
                    f"{pred['confidence']*100:.0f}% confidence with ~{rul['rul_hours']} operating hours of remaining life. "
                    f"Recommend {rul['recommendation'].replace('_',' ')}. Replacement bearing NSN {v['nsn']} is "
                    f"{'in stock at MCLB Albany' if parts.get('in_stock_at_mclb_albany') else 'short at Albany; check Barstow / Blount Island'}."
                ),
                "parts_action": (
                    f"NSN {v['nsn']} - {parts.get('qty_albany', 0)} ea at MCLB Albany; "
                    f"{parts.get('alt_depots', {}).get('MCLB_Barstow', 0)} ea at Barstow."
                ),
                "predicted_failure_mode": f"Probable {pred['class'].replace('_',' ')} progression to hub seizure within ~30 days of operation.",
                "_tool_call_log": [{"tool": "lookup_part_availability", "args": {"nsn": v["nsn"]}, "result": parts}],
                "_model": "rule-based-fallback",
            }

        # Also cache the derived numeric outputs so the UI can skip recomputing if it wants
        cache[vid] = {
            "agent_result": result,
            "classifier_result": pred,
            "rul_result": rul,
            "severity_est": sev_est,
        }

    OUT.write_text(json.dumps(cache, indent=2, default=str))
    print(f"\nWrote {OUT} ({OUT.stat().st_size:,} bytes) for {len(cache)} vehicles.")


if __name__ == "__main__":
    main()
