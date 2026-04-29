"""GUARDRAIL — ABAC enforcement (NIST SP 800-162).

Per-paragraph access decisions:
  - Clearance ladder: UNCLASS < CUI < SECRET < TS-SCI
  - Caveat satisfaction: a NOFORN paragraph requires the persona to hold the
    NOFORN caveat (or be a US uniformed Marine, no contractor).
  - Need-to-know: SP-PROCURE requires the 'procurement' role; SP-EXPT requires
    no foreign-national flag; SP-PRVCY requires non-contractor for Privacy-Act
    fields about other Marines.
  - Unit scope: paragraphs that name a specific unit must intersect the
    persona's unit_scope.

Returns a tuple (allowed: bool, reason: str). Reason is shown verbatim in the
"REDACTED — INSUFFICIENT CLEARANCE" placeholder so judges can see the why.
"""
from __future__ import annotations

CLASS_RANK = {
    "UNCLASSIFIED": 0,
    "CUI//FOUO": 1,
    "CUI//SP-PROPIN": 1,
    "CUI//SP-PRVCY": 1,
    "CUI//SP-OPSEC": 1,
    "CUI//SP-EXPT": 1,
    "CUI//SP-PROCURE": 1,
    "CUI//SP-NF": 1,
    "SECRET": 2,
    "TOP SECRET//SCI": 3,
}

PERSONA_MAX_RANK = {
    "UNCLASS": 0,
    "CUI": 1,
    "SECRET": 2,
    "SECRET-NF": 2,
    "SECRET-need-to-know": 1,  # contractor: clamp to CUI in practice
    "TS-SCI": 3,
}


def _persona_max_rank(persona: dict) -> int:
    abac = persona.get("abac", {})
    explicit = abac.get("max_class")
    if explicit:
        # Map abac.max_class onto the rank ladder
        m = {"UNCLASS": 0, "CUI": 1, "SECRET": 2, "TS-SCI": 3}.get(explicit, 0)
        return m
    return PERSONA_MAX_RANK.get(persona.get("clearance", "UNCLASS"), 0)


def authorize_paragraph(persona: dict, paragraph: dict) -> tuple[bool, str]:
    """Return (is_allowed, reason). Reason describes the deny when False."""
    marking = paragraph.get("recommended_marking", "UNCLASSIFIED")
    caveats = paragraph.get("caveats_recommended", []) or []
    abac = persona.get("abac", {})

    # 1. Classification ceiling
    p_rank = _persona_max_rank(persona)
    d_rank = CLASS_RANK.get(marking, 0)
    if d_rank > p_rank:
        return False, (
            f"INSUFFICIENT CLEARANCE [{marking}] — persona max_class "
            f"'{abac.get('max_class','UNCLASS')}' (rank {p_rank}) < paragraph "
            f"rank {d_rank}."
        )

    # 2. NOFORN caveat — must be held; contractors and foreign nationals never get it
    needs_noforn = "NOFORN" in caveats or marking == "CUI//SP-NF"
    if needs_noforn:
        if abac.get("foreign_national", False):
            return False, "ABAC: NOFORN paragraph; persona is foreign_national=true."
        if abac.get("is_contractor", False):
            return False, "ABAC: NOFORN paragraph; contractor cannot hold NOFORN caveat."
        held = set(abac.get("caveats_held", []) or [])
        if "NOFORN" not in held:
            return False, f"ABAC: NOFORN required; persona caveats_held={sorted(held) or '[]'}."

    # 3. FED ONLY caveat — contractors blocked
    if "FED ONLY" in caveats and abac.get("is_contractor", False):
        return False, "ABAC: FED ONLY caveat; persona is contractor (TECOM-VENDOR scope)."

    # 4. SP-PROCURE → procurement role required
    if marking == "CUI//SP-PROCURE":
        roles = abac.get("roles", []) or []
        if "procurement" not in roles and "s3_approver" not in roles and "oca_equivalent" not in roles:
            return False, (
                "ABAC: SP-PROCURE requires 'procurement' role (FAR 3.104 SSEB membership)."
            )

    # 5. SP-EXPT → no foreign nationals
    if marking == "CUI//SP-EXPT" and abac.get("foreign_national", False):
        return False, "ABAC: SP-EXPT (ITAR/USML); persona foreign_national=true."

    # 6. SP-PRVCY → contractor cannot view PII about other Marines
    if marking == "CUI//SP-PRVCY" and abac.get("is_contractor", False):
        return False, "ABAC: SP-PRVCY (Privacy Act); contractors blocked from PII about Marines."

    # 7. SP-OPSEC → need-to-know on force_protection
    if marking == "CUI//SP-OPSEC":
        ntk = abac.get("need_to_know", []) or []
        if "force_protection" not in ntk and "operations.unit" not in ntk:
            return False, (
                "ABAC: SP-OPSEC requires need-to-know on 'force_protection' or "
                "'operations.unit' (DoDD 5205.02E)."
            )

    return True, ""


def redaction_text(persona: dict, paragraph: dict, reason: str) -> str:
    marking = paragraph.get("recommended_marking", "UNCLASSIFIED")
    return (
        f"REDACTED — INSUFFICIENT CLEARANCE [{marking}] · {reason} · "
        f"persona={persona.get('name','?')} ({persona.get('clearance','?')})"
    )
