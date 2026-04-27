"""Synthetic egocentric scenario generator for EMBODIED.

Produces 8 procedural egocentric still frames depicting Marine training
scenarios (building entry, vehicle checkpoint, downed Marine, etc.) plus
scenarios.json with doctrinal context, and a cached sample of trainee runs
that pre-computes the hero LLM call so the demo is snappy.

Real dataset cited in README: Xperience-10M (large-scale egocentric multimodal
dataset of human experience for embodied AI / robot learning / world models).
The same 8-scenario shape (frames + doctrine refs + trainee turns) drops in
unchanged when a curated Xperience-10M subset is plugged in via
`data/load_real.py`.

Outputs:
  data/frames/scn_01.png ... scn_08.png   (procedural egocentric scenes)
  data/scenarios.json                     (8 scenarios with doctrine refs)
  data/cached_briefs.json                 (pre-computed hero brief samples)
"""
from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SEED = 1776
W, H = 768, 512
DATA_DIR = Path(__file__).parent
FRAMES_DIR = DATA_DIR / "frames"


# ---------------------------------------------------------------------------
# Scenario definitions — egocentric POVs a trainee Marine might face
# ---------------------------------------------------------------------------
SCENARIOS: list[dict] = [
    {
        "id": "scn_01",
        "title": "Doorway Entry — Urban Structure",
        "pov": "You are stacked second-man on a closed wooden door of a two-story residence. Friendly call-out: 'breach in 3'. No flash-bang loaded.",
        "scene_kind": "doorway",
        "doctrine_reference": "MCWP 3-35.3 'Military Operations on Urbanized Terrain' para 5-12 (room clearing — point of domination, button-hook)",
        "correct_actions": [
            "Maintain stack discipline; cover the deep corner on entry.",
            "Button-hook to your point of domination; do not cross the threshold of fire.",
            "Call out the room status: 'CLEAR' or 'CONTACT direction'.",
        ],
        "common_failures": [
            "Crossing into the fatal funnel without buttonhooking.",
            "Losing muzzle awareness on the lead man.",
            "Hesitating in the doorway (silhouette).",
        ],
    },
    {
        "id": "scn_02",
        "title": "Vehicle Checkpoint — Approaching Sedan",
        "pov": "You are senior Marine on a hasty TCP at dusk. A grey four-door sedan is rolling toward you at ~15 mph, single male driver visible, no passengers seen. Concertina is set 30m out.",
        "scene_kind": "checkpoint",
        "doctrine_reference": "MCRP 3-33.1A 'Civil Affairs Tactics, Techniques, and Procedures' Appendix B (escalation of force — shout, show, shove, shoot)",
        "correct_actions": [
            "Begin Escalation of Force: SHOUT — verbal + arm signal STOP at warning line.",
            "If non-compliant, SHOW — visible weapon presentation, laser/light to windshield.",
            "Continue EOF only as long as threat indicators remain ambiguous; do not skip steps.",
        ],
        "common_failures": [
            "Skipping straight to disabling fire on a non-hostile vehicle.",
            "Standing in the kill-funnel of the lane instead of off-axis.",
            "Failing to call up the contact to higher.",
        ],
    },
    {
        "id": "scn_03",
        "title": "Casualty Triage — Downed Marine",
        "pov": "You are first to your fallen squadmate after a single-shot contact. He is supine, conscious, gripping his right thigh; bright red blood is pulsing through his trousers. You are still in the same casualty-collection point with no immediate cover.",
        "scene_kind": "casualty",
        "doctrine_reference": "TCCC Guidelines (Tactical Combat Casualty Care) — Care Under Fire phase: stop the life-threatening hemorrhage with a tourniquet, then move to cover.",
        "correct_actions": [
            "Apply a CAT tourniquet HIGH AND TIGHT on the right thigh, mark TQ time.",
            "Drag casualty to nearest cover before transitioning to TFC phase.",
            "Call up 9-line MEDEVAC with grid + patient precedence.",
        ],
        "common_failures": [
            "Starting wound packing under direct fire instead of TQ.",
            "Removing gear / cutting clothes before stopping the bleed.",
            "Forgetting to mark the TQ time on the casualty's forehead.",
        ],
    },
    {
        "id": "scn_04",
        "title": "Vehicle Pre-Combat Inspection — JLTV Bay",
        "pov": "You are the assigned operator standing at the driver's side of a JLTV in the motor pool. Engine off. Your task: ECC pre-op inspection before convoy SP in 30 minutes.",
        "scene_kind": "vehicle_interior",
        "doctrine_reference": "TM 9-2320-450-10 'Operator Manual JLTV' — Before-Operation PMCS table 2-1 (fluids, tires, lights, comms, secure load)",
        "correct_actions": [
            "Walk-around: tires inflation + sidewall, fluid leaks under chassis, lights, mirrors.",
            "Cab: secure all loose gear, check seat belts, verify radio/intercom and BFT functional.",
            "Document deficiencies on DA Form 5988-E before turning over to convoy commander.",
        ],
        "common_failures": [
            "Skipping the underbody walk-around.",
            "Loose gear in the cab (becomes a projectile in a rollover).",
            "Not signing the 5988-E (no paper trail = the deficiency 'didn't exist').",
        ],
    },
    {
        "id": "scn_05",
        "title": "Hallway Cross — Two-Way Hostile Building",
        "pov": "You are halfway down a narrow second-floor hallway. An open door is on your left at 4m, another open door on your right at 7m. You hear a single English-language shout from the right-side room: 'STAY BACK!'",
        "scene_kind": "hallway",
        "doctrine_reference": "MCWP 3-35.3 para 5-21 (limited-penetration room clearing; pie the door before entry)",
        "correct_actions": [
            "Pie the right-side door from maximum standoff — do not cross the doorway.",
            "Call out positively to identify yourself: 'US MARINES — IDENTIFY YOURSELF'.",
            "Hold the cross-fire angle until the second team-member can mirror the left-side door.",
        ],
        "common_failures": [
            "Charging the door without pieing.",
            "Sweeping muzzle through the open left door while focused right.",
            "Failing to verbally challenge — escalates uncertainty.",
        ],
    },
    {
        "id": "scn_06",
        "title": "Night Perimeter — Movement at Treeline",
        "pov": "You are the awake half of a two-Marine fighting position at 0247. NVGs are down. You see two thermal silhouettes drifting laterally across the treeline 180m to your front. No challenge yet.",
        "scene_kind": "perimeter_night",
        "doctrine_reference": "MCWP 3-11.2 'Marine Rifle Squad' para 7-14 (challenge & password; positive ID before engagement)",
        "correct_actions": [
            "Wake your battle buddy silently — both eyes on the contact.",
            "Call up SALUTE to the COC over the line — do NOT engage on uncertain ID.",
            "Issue the unit challenge per SOI; engage only after positive hostile ID or hostile act.",
        ],
        "common_failures": [
            "Engaging unknown contacts at night without challenge.",
            "Going to white light (compromises position).",
            "Calling up after engaging instead of before.",
        ],
    },
    {
        "id": "scn_07",
        "title": "IED Indicator — Roadside Anomaly",
        "pov": "You are dismounted lead, walking point on a rural dirt road. 12m to your front, on the right shoulder, you see a freshly disturbed mound of dirt with a single piece of red fabric flagged on a stick beside it.",
        "scene_kind": "ied",
        "doctrine_reference": "MCRP 3-17.2A 'Explosive Ordnance Disposal' (IED 5-Cs: Confirm, Clear, Cordon, Check, Control)",
        "correct_actions": [
            "CONFIRM at distance — do not approach. Use optics.",
            "CLEAR personnel back to minimum 300m and CORDON the area.",
            "Call up 9-line UXO/IED report; request EOD; CHECK for secondary devices on egress route.",
        ],
        "common_failures": [
            "Walking up to 'just take a look'.",
            "Pulling/touching the flag (potential command wire).",
            "Pulling everyone into a single 100% bunched cordon (secondary device target).",
        ],
    },
    {
        "id": "scn_08",
        "title": "Civilian Crowd Approach — Local National Family",
        "pov": "You are squad-leader's point on a foot patrol through a village. Five local nationals — two adults, three children — are walking quickly toward you down the main street. Adults' hands are visible and empty.",
        "scene_kind": "civilian",
        "doctrine_reference": "MCRP 3-33.1A 'Civil Affairs TTP' chapter 4 (cultural engagement; presumption of non-combatant status absent hostile indicator)",
        "correct_actions": [
            "Maintain weapon at low-ready (NOT muzzle-up at family).",
            "Use the interpreter or established hand signals to halt politely at safe distance.",
            "Continue the patrol's mission; report contact to higher; do not escalate force absent hostile act.",
        ],
        "common_failures": [
            "Aggressive muzzle posture toward children.",
            "Ignoring the contact and walking past without acknowledgement.",
            "Using lethal force without a hostile act or hostile intent.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Procedural egocentric scene drawing
# ---------------------------------------------------------------------------
def _palette(name: str) -> dict[str, tuple[int, int, int]]:
    """A handful of dark, gritty palettes for different scene kinds."""
    base = {
        "sky": (28, 30, 36),
        "ground": (44, 38, 30),
        "wall": (60, 56, 50),
        "accent": (180, 70, 50),
        "hot": (240, 180, 80),
        "fog": (90, 88, 86),
    }
    if name == "checkpoint":
        base["sky"] = (40, 36, 44)
        base["ground"] = (48, 42, 36)
        base["accent"] = (220, 200, 80)
    elif name == "casualty":
        base["sky"] = (36, 28, 28)
        base["ground"] = (48, 30, 28)
        base["accent"] = (200, 40, 40)
    elif name == "perimeter_night":
        base["sky"] = (10, 14, 22)
        base["ground"] = (16, 22, 18)
        base["accent"] = (60, 200, 120)
        base["hot"] = (200, 240, 180)
    elif name == "ied":
        base["sky"] = (170, 150, 110)
        base["ground"] = (130, 100, 70)
        base["accent"] = (200, 40, 40)
    elif name == "civilian":
        base["sky"] = (180, 160, 130)
        base["ground"] = (110, 90, 70)
        base["accent"] = (90, 70, 60)
    elif name == "hallway":
        base["sky"] = (40, 38, 36)
        base["ground"] = (60, 54, 46)
        base["wall"] = (74, 66, 56)
    elif name == "vehicle_interior":
        base["sky"] = (50, 50, 56)
        base["ground"] = (35, 35, 40)
        base["wall"] = (60, 60, 66)
    return base


def _font(size: int = 14) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_doorway(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    # exterior wall plane
    d.rectangle([0, 0, W, H], fill=p["wall"])
    # ground line
    d.rectangle([0, int(H * 0.78), W, H], fill=p["ground"])
    # doorway frame
    fx0, fx1 = int(W * 0.32), int(W * 0.68)
    fy0, fy1 = int(H * 0.16), int(H * 0.86)
    d.rectangle([fx0 - 14, fy0 - 8, fx1 + 14, fy1 + 8], fill=(36, 32, 28))
    # interior darkness behind closed door
    d.rectangle([fx0, fy0, fx1, fy1], fill=(14, 12, 10))
    # door (closed) — wood-grain rectangles
    door_color = (80, 50, 28)
    d.rectangle([fx0 + 6, fy0 + 6, fx1 - 6, fy1 - 6], fill=door_color)
    for i in range(3):
        ry = fy0 + 30 + i * (fy1 - fy0 - 60) // 3
        d.rectangle([fx0 + 16, ry, fx1 - 16, ry + (fy1 - fy0 - 60) // 3 - 6],
                    outline=(40, 26, 14), width=2)
    # door handle
    d.ellipse([fx1 - 30, (fy0 + fy1) // 2 - 6, fx1 - 18, (fy0 + fy1) // 2 + 6],
              fill=(220, 180, 60))
    # silhouette of stack-1 Marine (left edge, partial)
    sm_x = int(W * 0.10)
    d.ellipse([sm_x - 22, int(H * 0.22), sm_x + 22, int(H * 0.30)], fill=(20, 22, 18))  # helmet
    d.rectangle([sm_x - 30, int(H * 0.30), sm_x + 30, int(H * 0.62)], fill=(28, 32, 24))  # torso
    # rifle muzzle pointing down-right
    d.line([sm_x + 12, int(H * 0.42), sm_x + 110, int(H * 0.58)], fill=(20, 18, 16), width=6)


def _draw_checkpoint(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    # sky / road
    d.rectangle([0, 0, W, int(H * 0.48)], fill=p["sky"])
    d.rectangle([0, int(H * 0.48), W, H], fill=p["ground"])
    # road perspective
    d.polygon([
        (W // 2 - 30, int(H * 0.48)),
        (W // 2 + 30, int(H * 0.48)),
        (W + 80, H),
        (-80, H),
    ], fill=(54, 50, 46))
    # lane stripes
    for i in range(6):
        y = int(H * 0.50 + i * (H * 0.50) / 6)
        w = 6 + i * 4
        d.rectangle([W // 2 - w, y, W // 2 + w, y + 4 + i], fill=(200, 180, 80))
    # concertina (left + right)
    for x in (90, W - 90):
        for r in range(0, 4):
            d.ellipse([x - 18 + r * 8, int(H * 0.66), x + 22 + r * 8, int(H * 0.70)],
                      outline=(180, 180, 180), width=2)
    # the sedan, mid-distance
    cx, cy = W // 2 + 6, int(H * 0.62)
    d.rectangle([cx - 60, cy - 24, cx + 60, cy + 14], fill=(110, 110, 116))
    d.rectangle([cx - 50, cy - 38, cx + 50, cy - 22], fill=(80, 82, 86))
    # windshield
    d.polygon([(cx - 44, cy - 22), (cx + 44, cy - 22),
               (cx + 36, cy - 36), (cx - 36, cy - 36)], fill=(40, 50, 60))
    # headlights (on)
    d.ellipse([cx - 56, cy - 6, cx - 42, cy + 6], fill=(255, 240, 180))
    d.ellipse([cx + 42, cy - 6, cx + 56, cy + 6], fill=(255, 240, 180))
    # warning sign on left shoulder
    d.polygon([(120, int(H * 0.58)), (160, int(H * 0.58)),
               (180, int(H * 0.66)), (160, int(H * 0.74)),
               (120, int(H * 0.74)), (100, int(H * 0.66))],
              fill=p["accent"], outline=(20, 20, 20), width=2)
    f = _font(13)
    d.text((118, int(H * 0.63)), "STOP", fill=(20, 20, 20), font=f)
    # rifle in lower-right of POV (your weapon)
    d.line([(W - 240, H - 30), (W - 60, H - 90)], fill=(20, 18, 16), width=8)
    d.rectangle([W - 80, H - 110, W - 40, H - 70], fill=(28, 28, 28))


def _draw_casualty(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, H], fill=p["ground"])
    # dust haze
    d.rectangle([0, 0, W, int(H * 0.5)], fill=(64, 50, 44))
    # the casualty supine
    cx, cy = W // 2, int(H * 0.62)
    # torso
    d.rectangle([cx - 110, cy - 30, cx + 110, cy + 30], fill=(46, 56, 42))
    # legs
    d.rectangle([cx + 90, cy - 24, cx + 230, cy + 24], fill=(46, 56, 42))
    # head + helmet
    d.ellipse([cx - 150, cy - 32, cx - 90, cy + 28], fill=(28, 32, 24))
    d.ellipse([cx - 144, cy - 26, cx - 96, cy + 22], fill=(170, 140, 110))  # face
    # boot
    d.rectangle([cx + 220, cy - 14, cx + 256, cy + 18], fill=(20, 16, 12))
    # bright red blood pool on right thigh
    for r in (40, 28, 18):
        d.ellipse([cx + 130 - r, cy + 10 - r // 2, cx + 130 + r, cy + 10 + r],
                  fill=p["accent"])
    # pulsing splatter
    for _ in range(40):
        rx = cx + 130 + rng.randint(-60, 80)
        ry = cy + 30 + rng.randint(-10, 50)
        rr = rng.randint(2, 5)
        d.ellipse([rx, ry, rx + rr, ry + rr], fill=(180, 30, 30))
    # your gloved hand entering frame from bottom
    d.ellipse([60, H - 90, 220, H + 60], fill=(48, 44, 38))


def _draw_vehicle_interior(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    # sky / motor pool ceiling
    d.rectangle([0, 0, W, int(H * 0.30)], fill=(70, 70, 78))
    d.rectangle([0, int(H * 0.30), W, H], fill=p["ground"])
    # JLTV body slab (large dark green)
    d.rectangle([60, int(H * 0.32), W - 60, int(H * 0.92)], fill=(50, 56, 44))
    # hood
    d.polygon([(60, int(H * 0.62)),
               (W - 60, int(H * 0.62)),
               (W - 120, int(H * 0.40)),
               (120, int(H * 0.40))],
              fill=(58, 64, 50))
    # windshield
    d.polygon([(140, int(H * 0.40)),
               (W - 140, int(H * 0.40)),
               (W - 180, int(H * 0.18)),
               (180, int(H * 0.18))],
              fill=(70, 90, 100))
    # door + handle
    d.rectangle([80, int(H * 0.62), int(W * 0.42), int(H * 0.92)], fill=(44, 50, 40))
    d.rectangle([int(W * 0.30), int(H * 0.74), int(W * 0.36), int(H * 0.78)], fill=(180, 180, 180))
    # tire
    d.ellipse([60, int(H * 0.78), 200, H], fill=(20, 18, 16))
    d.ellipse([90, int(H * 0.82), 170, int(H * 0.96)], fill=(60, 60, 60))
    # clipboard in your hand (POV)
    d.rectangle([W - 220, H - 180, W - 40, H - 30], fill=(220, 210, 180))
    f = _font(14)
    d.text((W - 200, H - 160), "DA 5988-E", fill=(20, 20, 20), font=f)
    d.text((W - 200, H - 140), "PMCS — Before Op", fill=(40, 40, 40), font=f)
    for i, line in enumerate(["[ ] Tires", "[ ] Fluids", "[ ] Lights",
                              "[ ] Comms", "[ ] Load"]):
        d.text((W - 200, H - 120 + i * 16), line, fill=(40, 40, 40), font=f)


def _draw_hallway(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    # vanishing-point hallway
    d.rectangle([0, 0, W, H], fill=p["ground"])
    d.polygon([(0, 0), (W, 0), (W // 2 + 60, H // 2), (W // 2 - 60, H // 2)], fill=(36, 32, 28))  # ceiling
    d.polygon([(0, H), (W, H), (W // 2 + 60, H // 2), (W // 2 - 60, H // 2)], fill=p["wall"])  # floor (front)
    d.polygon([(0, 0), (0, H), (W // 2 - 60, H // 2)], fill=(54, 48, 40))  # left wall
    d.polygon([(W, 0), (W, H), (W // 2 + 60, H // 2)], fill=(54, 48, 40))  # right wall
    # left open door (4m)
    d.polygon([(70, int(H * 0.30)), (180, int(H * 0.32)),
               (180, int(H * 0.78)), (70, int(H * 0.84))], fill=(14, 12, 10))
    # right open door (7m)
    d.polygon([(W - 200, int(H * 0.36)), (W - 110, int(H * 0.34)),
               (W - 110, int(H * 0.74)), (W - 200, int(H * 0.78))], fill=(14, 12, 10))
    # warm light spill from right door
    d.polygon([(W - 200, int(H * 0.36)), (W - 110, int(H * 0.34)),
               (W - 60, int(H * 0.78)), (W - 240, int(H * 0.84))],
              fill=(70, 56, 40))
    # rifle muzzle low-ready, lower right
    d.line([(W - 60, H - 20), (W - 180, H - 80)], fill=(20, 18, 16), width=8)


def _draw_perimeter_night(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, H], fill=p["sky"])
    d.rectangle([0, int(H * 0.62), W, H], fill=p["ground"])
    # treeline silhouette
    for x in range(0, W, 18):
        h = rng.randint(50, 110)
        d.polygon([(x, int(H * 0.62)), (x + 9, int(H * 0.62) - h), (x + 18, int(H * 0.62))],
                  fill=(8, 10, 14))
    # two thermal silhouettes (greenish bright glows)
    for cx in (W // 2 - 90, W // 2 - 30):
        for r in (24, 16, 10):
            d.ellipse([cx - r, int(H * 0.58) - r, cx + r, int(H * 0.58) + r],
                      fill=(p["hot"][0] - r * 4, p["hot"][1], p["hot"][2] - r * 2))
    # sandbag rim of fighting position (lower foreground)
    for i, x in enumerate(range(-20, W + 20, 60)):
        d.rectangle([x, H - 90 + (i % 2) * 12, x + 56, H - 50 + (i % 2) * 12],
                    fill=(54, 48, 36), outline=(30, 26, 20), width=2)
    # NVG vignette
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([-200, -100, W + 200, H + 200], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(80))
    img.putalpha(255)
    overlay = Image.new("RGBA", (W, H), (0, 80, 40, 80))
    img.alpha_composite(overlay)
    img_rgb = img.convert("RGB")
    img.paste(img_rgb)


def _draw_ied(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, int(H * 0.42)], fill=p["sky"])
    d.rectangle([0, int(H * 0.42), W, H], fill=p["ground"])
    # road perspective
    d.polygon([(W // 2 - 60, int(H * 0.42)),
               (W // 2 + 60, int(H * 0.42)),
               (W + 100, H), (-100, H)],
              fill=(150, 120, 80))
    # disturbed mound on right shoulder, at mid-distance
    mx, my = int(W * 0.66), int(H * 0.66)
    for r in (40, 28, 18, 10):
        d.ellipse([mx - r, my - r // 2, mx + r, my + r // 2],
                  fill=(70, 50, 30) if r > 20 else (90, 64, 38))
    # red rag flag on a stick beside the mound
    d.line([(mx + 30, my), (mx + 30, my - 60)], fill=(40, 30, 20), width=3)
    d.polygon([(mx + 30, my - 60), (mx + 60, my - 50), (mx + 30, my - 40)], fill=p["accent"])
    # power-line poles in the distance
    for x in (160, 360, 560):
        d.line([(x, int(H * 0.46)), (x, int(H * 0.30))], fill=(40, 30, 20), width=2)
        d.line([(x - 12, int(H * 0.32)), (x + 12, int(H * 0.32))], fill=(40, 30, 20), width=2)
    # dismount silhouette in lower-foreground (your buddy)
    d.ellipse([80, H - 200, 180, H - 100], fill=(40, 50, 36))
    d.rectangle([100, H - 110, 160, H - 20], fill=(50, 60, 44))


def _draw_civilian(img: Image.Image, p: dict, rng: random.Random) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, int(H * 0.40)], fill=p["sky"])
    d.rectangle([0, int(H * 0.40), W, H], fill=p["ground"])
    # mud-brick buildings on either side
    for x0 in (0, int(W * 0.66)):
        d.rectangle([x0, int(H * 0.20), x0 + int(W * 0.34), int(H * 0.74)], fill=(140, 110, 80))
        # small windows
        for wy in (int(H * 0.30), int(H * 0.46), int(H * 0.62)):
            for wx in range(x0 + 30, x0 + int(W * 0.34) - 30, 60):
                d.rectangle([wx, wy, wx + 22, wy + 28], fill=(40, 30, 20))
    # dirt street vanishing
    d.polygon([(int(W * 0.32), int(H * 0.42)),
               (int(W * 0.68), int(H * 0.42)),
               (W, H), (0, H)], fill=(120, 90, 60))
    # five figures approaching: 2 adults + 3 children
    sizes = [(int(H * 0.30), 0.92), (int(H * 0.30), 0.92),
             (int(H * 0.40), 0.55), (int(H * 0.42), 0.55), (int(H * 0.44), 0.48)]
    xs = [int(W * 0.40), int(W * 0.50), int(W * 0.36), int(W * 0.46), int(W * 0.56)]
    for (top_y, scale), x in zip(sizes, xs):
        h_h = int(40 * scale)
        h_w = int(28 * scale)
        body_h = int(120 * scale)
        body_w = int(60 * scale)
        # body (robe)
        d.rectangle([x - body_w // 2, top_y, x + body_w // 2, top_y + body_h],
                    fill=(180, 160, 120))
        # head
        d.ellipse([x - h_w // 2, top_y - h_h, x + h_w // 2, top_y], fill=(110, 80, 60))
    # rifle low-ready in lower-right (POV)
    d.line([(W - 60, H - 20), (W - 200, H - 100)], fill=(20, 18, 16), width=8)


DRAWERS = {
    "doorway": _draw_doorway,
    "checkpoint": _draw_checkpoint,
    "casualty": _draw_casualty,
    "vehicle_interior": _draw_vehicle_interior,
    "hallway": _draw_hallway,
    "perimeter_night": _draw_perimeter_night,
    "ied": _draw_ied,
    "civilian": _draw_civilian,
}


def _stamp_pov(img: Image.Image, label: str) -> None:
    """Add a faint top-bar HUD with the scenario title — egocentric helmet-cam vibe."""
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 28], fill=(0, 0, 0))
    f = _font(14)
    d.text((12, 6), f"HELMET-CAM  •  {label}", fill=(0, 255, 167), font=f)
    # corner crosshair
    cx, cy = W // 2, H // 2
    d.line([(cx - 14, cy), (cx + 14, cy)], fill=(0, 255, 167), width=1)
    d.line([(cx, cy - 14), (cx, cy + 14)], fill=(0, 255, 167), width=1)
    d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=(0, 255, 167), width=1)


def _render_scene(scn: dict) -> Image.Image:
    rng = random.Random(SEED + hash(scn["id"]) % 9999)
    p = _palette(scn["scene_kind"])
    img = Image.new("RGB", (W, H), p["sky"])
    DRAWERS[scn["scene_kind"]](img, p, rng)
    img = img.convert("RGB")
    # add light film grain
    noise = Image.effect_noise((W, H), 14).convert("RGB")
    img = Image.blend(img, noise, 0.05)
    _stamp_pov(img, scn["title"])
    return img


# ---------------------------------------------------------------------------
# Cached briefs — pre-compute the hero LLM call so the demo path is snappy
# ---------------------------------------------------------------------------
SAMPLE_TRAINEE_RUNS = [
    {
        "scenario_id": "scn_01",
        "trainee_response": "I push through the doorway and clear the room left to right.",
    },
    {
        "scenario_id": "scn_02",
        "trainee_response": "I raise my rifle and fire warning shots into the engine block.",
    },
    {
        "scenario_id": "scn_03",
        "trainee_response": "I rip open his trousers and pack the wound with combat gauze.",
    },
    {
        "scenario_id": "scn_07",
        "trainee_response": "I move closer to get a better look at what is under the dirt.",
    },
    {
        "scenario_id": "scn_06",
        "trainee_response": "I light them up — two thermal contacts at 180m, hostile until proven otherwise.",
    },
]


def _deterministic_eval(scn: dict, trainee_response: str) -> dict:
    """Cheap deterministic scorer used for cache pre-fill + offline fallback.

    Heuristic: keyword overlap with `correct_actions` minus penalties for
    keywords that match `common_failures`. Not for production — the live LLM
    call is the real evaluator. This exists so the demo never spinner-locks.
    """
    text = trainee_response.lower()
    correct_hits = sum(
        1 for a in scn["correct_actions"]
        for kw in _keywords(a) if kw in text
    )
    failure_hits = sum(
        1 for a in scn["common_failures"]
        for kw in _keywords(a) if kw in text
    )
    raw = 50 + correct_hits * 12 - failure_hits * 18
    score = max(0, min(100, raw))
    if score >= 80:
        cls = "doctrinally_correct"
        consequences = "Effective action — friendly survival likelihood high."
    elif score >= 60:
        cls = "tactical"
        consequences = "Generally sound, but missed at least one doctrinal step."
    elif failure_hits >= 1:
        cls = "risky"
        consequences = "Action matches a known doctrinal failure — likely casualty or civilian incident."
    else:
        cls = "hesitation"
        consequences = "Indecisive response — exposure window stays open."
    return {
        "action_classified_as": cls,
        "score": score,
        "doctrine_reference": scn["doctrine_reference"],
        "consequences_simulated": consequences,
        "coaching_feedback": (
            f"Re-anchor on {scn['doctrine_reference'].split(' ')[0]}. "
            f"Prioritized step missed: {scn['correct_actions'][0]}"
        ),
        "next_scenario_suggestion": "Repeat the scenario with the corrected sequence; then progress to the next.",
    }


def _keywords(s: str) -> list[str]:
    out: list[str] = []
    for w in s.lower().replace(",", " ").replace(".", " ").split():
        if len(w) >= 4 and w not in {"with", "into", "your", "from", "this",
                                     "that", "then", "step", "they", "them",
                                     "their", "have", "will"}:
            out.append(w)
    return out


def _precompute_briefs() -> None:
    """Pre-compute hero LLM evaluations for every sample run.

    Cache-first pattern (per AGENT_BRIEF_V2 §A): the live multimodal call only
    fires when the trainee enters a custom response. Sample runs read from this
    cache so the demo recording is snappy.

    On any LLM error, we still cache the deterministic baseline so the file
    always exists.
    """
    by_id = {s["id"]: s for s in SCENARIOS}
    out: dict[str, list[dict]] = {}

    # Try the LLM call but never block the build on it.
    llm_eval = None
    try:
        import sys
        # Repo root for `from shared.kamiwaza_client import chat`
        repo_root = Path(__file__).resolve().parents[3]
        # App root for `from src.coach import ...`
        app_root = Path(__file__).resolve().parents[1]
        for p in (str(repo_root), str(app_root)):
            if p not in sys.path:
                sys.path.insert(0, p)
        from src.coach import evaluate_text_only  # type: ignore
        llm_eval = evaluate_text_only
    except Exception as e:  # noqa: BLE001
        print(f"[generate] cache-prefill skipping LLM ({e}); using deterministic baseline.")

    for run in SAMPLE_TRAINEE_RUNS:
        scn = by_id[run["scenario_id"]]
        baseline = _deterministic_eval(scn, run["trainee_response"])
        evaluated: dict = baseline
        if llm_eval is not None:
            try:
                evaluated = llm_eval(scn, run["trainee_response"])
            except Exception as e:  # noqa: BLE001
                print(f"[generate] LLM eval failed for {scn['id']}: {e} — using baseline.")
        out.setdefault(run["scenario_id"], []).append({
            "trainee_response": run["trainee_response"],
            "evaluation": evaluated,
        })

    # Pre-cache an after-action narrative across the sample runs (hero brief)
    aar_path = Path(__file__).parent / "cached_briefs.json"
    sample_aar = {
        "trainee_callsign": "TRN-2-7-A",
        "n_attempts": len(SAMPLE_TRAINEE_RUNS),
        "summary": (
            "Across five rep'd egocentric scenarios, TRN-2-7-A demonstrates aggressive "
            "decision-making but compresses or skips doctrinal steps under perceived "
            "time pressure. Two attempts (vehicle checkpoint, night perimeter) escalated "
            "to lethal force without satisfying the EOF / positive-ID gates required by "
            "MCRP 3-33.1A and MCWP 3-11.2 respectively. Casualty triage opted for wound "
            "packing in the Care-Under-Fire phase instead of immediate tourniquet "
            "application. Recommend re-rep on EOF, positive-ID, and TCCC phase "
            "discipline before next graded iteration."
        ),
        "growth_areas": [
            "Escalation of Force discipline (shout / show / shove / shoot).",
            "Positive identification before engagement at night.",
            "TCCC phase awareness — Care Under Fire = TQ first, packing later.",
            "IED 5-Cs — confirm at distance, never approach.",
        ],
        "strengths": [
            "Decisiveness — never freezes; commits to an action.",
            "Forward-leaning aggression in room-clearing.",
        ],
        "next_iteration": "Re-run scn_02, scn_06, scn_03 with explicit step-by-step doctrine narration before action.",
    }
    out["_sample_aar"] = [{
        "trainee_callsign": sample_aar["trainee_callsign"],
        "evaluation": sample_aar,
    }]
    aar_path.write_text(json.dumps(out, indent=2))
    print(f"[generate] wrote cached_briefs.json ({len(out)} keys)")


def main() -> None:
    rng = random.Random(SEED)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    for scn in SCENARIOS:
        img = _render_scene(scn)
        out = FRAMES_DIR / f"{scn['id']}.png"
        img.save(out, "PNG")
        print(f"[generate] wrote {out.name}")
    (DATA_DIR / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2))
    print(f"[generate] wrote scenarios.json ({len(SCENARIOS)} scenarios)")
    _precompute_briefs()


if __name__ == "__main__":
    main()
