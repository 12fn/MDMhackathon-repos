"""Real-Kamiwaza plug-in for CAT-ROUTER.

The synthetic data/model_catalog.json mimics what Kamiwaza's catalog API
returns. To swap to a live Kamiwaza deployment, point KAMIWAZA_BASE_URL at
your gateway and call load_real() — it queries the OpenAI-compatible
/v1/models endpoint on the Kamiwaza Model Gateway, then enriches each model
record with the catalog metadata Kamiwaza's Inference Mesh exposes.

Endpoint contract (Kamiwaza Model Gateway):
  GET  ${KAMIWAZA_BASE_URL}/v1/models
       -> {"object": "list", "data": [{"id": "...", "object": "model", ...}]}
  GET  ${KAMIWAZA_BASE_URL}/v1/catalog/models   (Kamiwaza extension)
       -> {"data": [
              {"id": "...", "params_b": ..., "context_window": ...,
               "vision": bool, "tool_calls": bool,
               "scar_grade": "IL5", "hardware_home": "...",
               "license": "...", "training_cutoff": "..."}, ...]}

Required env:
  KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
  KAMIWAZA_API_KEY=<JWT or static>      # optional for some on-prem installs

Output: a list[dict] with the exact same shape as model_catalog.json so
src/router.py routing logic works unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

OUT_DIR = Path(__file__).parent
SCAR_DEFAULT = "IL4"


def _client_kwargs() -> dict[str, Any]:
    base = os.getenv("KAMIWAZA_BASE_URL")
    if not base:
        raise RuntimeError(
            "KAMIWAZA_BASE_URL not set. Example:\n"
            "  export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1\n"
            "  export KAMIWAZA_API_KEY=<token>\n"
        )
    headers = {"Accept": "application/json"}
    key = os.getenv("KAMIWAZA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return {"base": base.rstrip("/"), "headers": headers, "timeout": 12}


def _list_deployed() -> list[dict]:
    cfg = _client_kwargs()
    r = requests.get(f"{cfg['base']}/models", headers=cfg["headers"], timeout=cfg["timeout"])
    r.raise_for_status()
    return r.json().get("data", [])


def _list_catalog() -> list[dict]:
    """Kamiwaza catalog extension (richer metadata than vanilla /v1/models)."""
    cfg = _client_kwargs()
    try:
        r = requests.get(
            f"{cfg['base']}/catalog/models",
            headers=cfg["headers"],
            timeout=cfg["timeout"],
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except requests.RequestException:
        return []


def load_real() -> list[dict]:
    """Pull live Kamiwaza catalog + normalize to the local schema."""
    deployed = {m["id"]: m for m in _list_deployed()}
    enriched = {m["id"]: m for m in _list_catalog()}

    out: list[dict] = []
    for mid, m in deployed.items():
        e = enriched.get(mid, {})
        out.append({
            "model_id": mid,
            "display_name": e.get("display_name") or mid,
            "family": e.get("family", mid.split("/")[0] if "/" in mid else mid.split("-")[0]),
            "publisher": e.get("publisher", "unknown"),
            "parameters_b": e.get("params_b") or e.get("parameters_b") or 0,
            "active_parameters_b": e.get("active_params_b"),
            "context_window": e.get("context_window") or m.get("context_window") or 8192,
            "max_output": e.get("max_output", 4096),
            "modality": e.get("modality", ["text"]),
            "vision": bool(e.get("vision", False)),
            "tool_calls": bool(e.get("tool_calls", False)),
            "tokens_per_second": e.get("tokens_per_second", 50),
            "first_token_ms": e.get("first_token_ms", 400),
            "license": e.get("license", "unknown"),
            "training_cutoff": e.get("training_cutoff", "unknown"),
            "scar_grade": e.get("scar_grade", SCAR_DEFAULT),
            "hardware_home": e.get("hardware_home", "Kamiwaza pod"),
            "deployment": e.get("deployment", "vLLM"),
            "cost_per_1k_input_tokens": e.get("cost_per_1k_input_tokens", 0.001),
            "cost_per_1k_output_tokens": e.get("cost_per_1k_output_tokens", 0.003),
            "quality_score": e.get("quality_score", 0.80),
            "best_for": e.get("best_for", []),
            "weakness": e.get("weakness", ""),
        })
    return out


def write_catalog() -> Path:
    rows = load_real()
    out = OUT_DIR / "model_catalog.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"Wrote {len(rows)} live Kamiwaza catalog entries -> {out}")
    return out


if __name__ == "__main__":
    write_catalog()
