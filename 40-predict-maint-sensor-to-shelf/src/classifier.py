"""RandomForest classifier on hand-crafted features + RUL estimator."""
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
    Xtr, Xte, ytr, yte = train_test_split(
        X, labels, test_size=0.25, stratify=labels, random_state=1776
    )
    clf = RandomForestClassifier(
        n_estimators=200, max_depth=None, min_samples_leaf=2,
        random_state=1776, n_jobs=-1,
    )
    clf.fit(Xtr, ytr)
    return clf, {
        "train_acc": float(clf.score(Xtr, ytr)),
        "test_acc": float(clf.score(Xte, yte)),
        "fs": fs,
        "classes": CLASSES,
    }


def predict_one(clf: RandomForestClassifier, sig: np.ndarray, fs: int) -> dict:
    feats = hand_crafted_features(sig, fs).reshape(1, -1)
    proba = clf.predict_proba(feats)[0]
    idx = int(np.argmax(proba))
    return {
        "class": CLASSES[idx],
        "confidence": float(proba[idx]),
        "probabilities": {CLASSES[i]: float(p) for i, p in enumerate(proba)},
    }


def estimate_rul(predicted_class: str, confidence: float, severity: float,
                 current_op_hours: int) -> dict:
    """NASA Pred Mx CMAPSS-flavoured RUL: severity-dominated slope per fault."""
    if predicted_class == "healthy":
        rul = int(np.clip(2000 - current_op_hours * 0.05, 800, 2500))
        recommendation = "safe_to_operate"
    else:
        slope = {"inner_race": 750, "outer_race": 600, "ball": 850}.get(
            predicted_class, 700
        )
        rul = int(np.clip(slope * (1.0 - severity), 24, 1500))
        if rul < 200 or (confidence > 0.85 and severity > 0.5):
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
    kurt = feats[5]
    crest = feats[2]
    bearing_band = feats[10] + feats[11] + feats[12]
    sev = (
        0.35 * np.tanh((kurt - 3.0) / 4.0)
        + 0.35 * np.tanh((crest - 4.0) / 3.0)
        + 0.30 * np.tanh(bearing_band / 0.6)
    )
    return float(np.clip((sev + 0.3), 0.0, 1.0))
