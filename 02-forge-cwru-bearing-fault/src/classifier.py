"""RandomForest classifier on hand-crafted features + simple severity-driven RUL model."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from .signal_proc import hand_crafted_features

CLASSES = ["healthy", "inner_race", "outer_race", "ball"]


def featurize(signals: np.ndarray, fs: int) -> np.ndarray:
    return np.stack([hand_crafted_features(s, fs) for s in signals])


def train_classifier(corpus_path: Path) -> tuple[RandomForestClassifier, dict]:
    z = np.load(corpus_path, allow_pickle=False)
    signals = z["signals"]
    labels = z["labels"]
    fs = int(z["fs"])

    X = featurize(signals, fs)
    Xtr, Xte, ytr, yte = train_test_split(X, labels, test_size=0.25, stratify=labels, random_state=1776)

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_leaf=2,
        random_state=1776,
        n_jobs=-1,
    )
    clf.fit(Xtr, ytr)
    train_acc = clf.score(Xtr, ytr)
    test_acc = clf.score(Xte, yte)
    return clf, {"train_acc": float(train_acc), "test_acc": float(test_acc), "fs": fs, "classes": CLASSES}


def predict_one(clf: RandomForestClassifier, sig: np.ndarray, fs: int) -> dict:
    feats = hand_crafted_features(sig, fs).reshape(1, -1)
    proba = clf.predict_proba(feats)[0]
    idx = int(np.argmax(proba))
    return {
        "class": CLASSES[idx],
        "confidence": float(proba[idx]),
        "probabilities": {CLASSES[i]: float(p) for i, p in enumerate(proba)},
    }


def estimate_rul(predicted_class: str, confidence: float, severity: float, current_op_hours: int) -> dict:
    """Simple physics-flavored RUL: severity dominates remaining hours, class sets the slope."""
    if predicted_class == "healthy":
        rul = int(np.clip(2000 - current_op_hours * 0.05, 800, 2500))
        recommendation = "safe_to_operate"
    else:
        # Slope per fault class (hours of life lost per unit severity)
        slope = {"inner_race": 750, "outer_race": 600, "ball": 850}.get(predicted_class, 700)
        rul = int(np.clip(slope * (1.0 - severity), 24, 1500))
        # Confidence-weighted band
        if rul < 200 or confidence > 0.85 and severity > 0.5:
            recommendation = "induct_now"
        elif rul < 500:
            recommendation = "monitor_closely"
        else:
            recommendation = "monitor_routine"
    return {
        "rul_hours": rul,
        "recommendation": recommendation,
        "model_severity": float(severity),
    }


def severity_from_features(feats: np.ndarray) -> float:
    """Heuristic severity proxy from kurtosis + crest + characteristic-band energies.

    Calibrated so that healthy ~ 0.05 and clear faults ~ 0.5–0.95.
    """
    kurt = feats[5]
    crest = feats[2]
    bearing_band = feats[10] + feats[11] + feats[12]   # BPFO+BPFI+BSF in envelope spectrum
    # Normalize: healthy kurt ~ 3 (gaussian); fault kurt > 5
    sev = (
        0.35 * np.tanh((kurt - 3.0) / 4.0)
        + 0.35 * np.tanh((crest - 4.0) / 3.0)
        + 0.30 * np.tanh(bearing_band / 0.6)
    )
    return float(np.clip((sev + 0.3), 0.0, 1.0))
