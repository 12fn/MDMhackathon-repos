# OPTIK — vision RAG over TM library
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Cosine-similarity RAG over the synthetic TM snippet corpus.

Lightweight: pure NumPy + the shared embed() call. No Milvus / no FAISS.
Maps cleanly to Kamiwaza DDE/Inference Mesh: swap embed() to a Kamiwaza-served
embedding model with one env-var change.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import embed  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class TMIndex:
    def __init__(self, snippets: list[dict], vecs: np.ndarray):
        self.snippets = snippets
        self.vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)

    @classmethod
    def load_or_build(cls, *, force_rebuild: bool = False) -> "TMIndex":
        snip_path = DATA_DIR / "tm_snippets.json"
        idx_path  = DATA_DIR / "tm_index.npz"
        if not snip_path.exists():
            raise FileNotFoundError(
                f"{snip_path} missing. Run: python data/generate.py"
            )
        snippets = json.loads(snip_path.read_text())

        if idx_path.exists() and not force_rebuild:
            data = np.load(idx_path, allow_pickle=True)
            vecs = data["vecs"]
            return cls(snippets, vecs)

        # Build on-the-fly (one Kamiwaza embed call, ~1 s for 30 snippets).
        texts = [
            f"{s['tm']} {s['vehicle']} {s['component']} {s['failure']}"
            for s in snippets
        ]
        vecs = np.array(embed(texts), dtype="float32")
        np.savez_compressed(idx_path, vecs=vecs,
                            ids=np.array([s["id"] for s in snippets]))
        return cls(snippets, vecs)

    def search(self, query: str, k: int = 3) -> list[tuple[float, dict]]:
        q = np.array(embed([query])[0], dtype="float32")
        q = q / (np.linalg.norm(q) + 1e-9)
        scores = self.vecs @ q
        order = np.argsort(-scores)[:k]
        return [(float(scores[i]), self.snippets[i]) for i in order]
