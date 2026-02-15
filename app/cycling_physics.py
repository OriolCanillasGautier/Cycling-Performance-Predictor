#!/usr/bin/env python3
"""
Cycling Performance Predictor — Physics & helpers module.
All calculations, constants, formatters, and HTML-snippet builders live here.
"""

import math
from typing import Optional, NamedTuple


# ── Data ────────────────────────────────────────────────────────────────────

class PowerEstimate(NamedTuple):
    """Result of a single power-estimation calculation."""
    g_force: float
    r_force: float
    a_force: float
    force: float
    g_watts: float
    r_watts: float
    a_watts: float
    watts: float
    velocity: float


TERRAIN_CRR: dict[str, dict[str, float]] = {
    "road": {
        "asphalt": 0.0050,
        "gravel":  0.0060,
        "grass":   0.0070,
        "offroad": 0.0200,
        "sand":    0.0300,
    },
    "mtb": {
        "asphalt": 0.0065,
        "gravel":  0.0075,
        "grass":   0.0090,
        "offroad": 0.0255,
        "sand":    0.0380,
    },
}


# ── Physics ─────────────────────────────────────────────────────────────────

class CyclingPhysics:
    """Core cycling-physics equations (Sauce4Strava-compatible)."""

    @staticmethod
    def air_density(elevation: float) -> float:
        """Air density (kg/m³) at *elevation* metres above sea level."""
        return 1.225 * math.exp(-elevation / 8400)

    @staticmethod
    def gravity_force(slope: float, weight: float) -> float:
        """Gravity component (N) along the slope."""
        return weight * 9.8066 * math.sin(math.atan(slope))

    @staticmethod
    def rolling_resistance_force(slope: float, weight: float, crr: float) -> float:
        """Rolling resistance (N)."""
        return weight * 9.8066 * math.cos(math.atan(slope)) * crr

    @staticmethod
    def aero_drag_force(cda: float, rho: float, velocity: float, wind: float = 0) -> float:
        """Aerodynamic drag (N)."""
        vr = velocity + wind
        return 0.5 * rho * cda * vr * abs(vr)

    @staticmethod
    def cycling_power_estimate(
        velocity: float, slope: float, weight: float,
        crr: float, cda: float, elevation: float = 0,
        wind: float = 0, loss: float = 0.035,
    ) -> PowerEstimate:
        """Estimate watts for a given velocity & conditions."""
        inv = -1 if velocity < 0 else 1
        fg = CyclingPhysics.gravity_force(slope, weight)
        fr = CyclingPhysics.rolling_resistance_force(slope, weight, crr) * inv
        fa = CyclingPhysics.aero_drag_force(cda, CyclingPhysics.air_density(elevation), velocity, wind)
        vf = velocity / (1 - loss)
        return PowerEstimate(
            g_force=fg, r_force=fr, a_force=fa, force=fg + fr + fa,
            g_watts=fg * vf * inv, r_watts=fr * vf * inv,
            a_watts=fa * vf * inv, watts=(fg + fr + fa) * vf * inv,
            velocity=velocity,
        )

    @staticmethod
    def cycling_power_velocity_search(
        power: float, slope: float, weight: float,
        crr: float, cda: float, elevation: float = 0,
        wind: float = 0, loss: float = 0.035,
    ) -> Optional[PowerEstimate]:
        """Binary-search for the velocity that produces *power* watts."""
        if power <= 0:
            return None

        def _pw(v: float) -> PowerEstimate:
            return CyclingPhysics.cycling_power_estimate(v, slope, weight, crr, cda, elevation, wind, loss)

        lo, hi, cap = 0.01, 0.5, 120.0
        while hi < cap:
            if _pw(hi).watts >= power:
                break
            hi *= 1.5
        if hi >= cap:
            return _pw(cap)

        best = None
        for _ in range(64):
            mid = (lo + hi) / 2.0
            best = _pw(mid)
            if best.watts < power:
                lo = mid
            else:
                hi = mid
        return best

    @staticmethod
    def cycling_time_power_search(
        target_time: float, distance: float, slope: float, weight: float,
        crr: float, cda: float, elevation: float = 0,
        wind: float = 0, loss: float = 0.035,
    ) -> Optional[PowerEstimate]:
        """Direct calculation: power required for *target_time* over *distance*."""
        if target_time <= 0:
            return None
        v = distance / target_time
        if v <= 0:
            return None
        return CyclingPhysics.cycling_power_estimate(v, slope, weight, crr, cda, elevation, wind, loss)


# ── Drafting ────────────────────────────────────────────────────────────────
#
# Hybrid dynamic model based on:
#   - Blocken et al. (2018) CFD data: drag reduction vs gap distance
#   - Hagberg & McCole: speed-dependent benefit (18% at 32 km/h, 27%+ at 40 km/h)
#   - Experimental data: 27-66% reduction at 0.32-0.85m gaps
#
# The model computes a CdA multiplier (1.0 = no benefit, lower = more benefit)
# as a function of: group size, position, gap distance, and speed.

# ── Gap-distance model ──────────────────────────────────────────────────────
# Calibrated against Blocken et al. CFD data (at reference speed ~54 km/h):
#   gap 0.24m -> 75% reduction (multiplier 0.25)
#   gap 2.64m -> 48% reduction (multiplier 0.52)
#   gap 10.0m -> 23% reduction (multiplier 0.77)
#   gap 30.0m -> 12% reduction (multiplier 0.88)
#   gap 50.0m ->  7% reduction (multiplier 0.93)
#
# Fitted function: reduction = A * exp(-alpha * gap) + B * exp(-beta * gap)
# Double-exponential captures the steep near-field drop + slow far-field tail.

_GAP_A     = 0.54    # near-field amplitude
_GAP_ALPHA = 0.30    # near-field decay rate (1/m)
_GAP_B     = 0.25    # far-field amplitude
_GAP_BETA  = 0.025   # far-field decay rate (1/m)

def _gap_reduction(gap_m: float) -> float:
    """Drag reduction fraction (0..~0.78) from gap distance alone.

    Returns the fraction of drag that is *removed* for a single follower
    directly behind one leader at the reference speed (~54 km/h).
    """
    if gap_m <= 0:
        gap_m = 0.15  # wheel-to-wheel minimum
    return _GAP_A * math.exp(-_GAP_ALPHA * gap_m) + _GAP_B * math.exp(-_GAP_BETA * gap_m)

# ── Speed correction ────────────────────────────────────────────────────────
# Aero drag ~ v^2, so drafting benefit scales with speed.
# At low speed (<15 km/h) benefit is minimal; at high speed it saturates.
# Calibrated: benefit ~18% at 32 km/h, ~27% at 40 km/h (Hagberg & McCole).
# Reference speed for the gap model is 54 km/h (Blocken CFD).

_SPEED_REF = 54.0 / 3.6  # 15 m/s — reference speed for gap calibration

def _speed_factor(speed_ms: float) -> float:
    """Multiplicative correction for speed relative to reference.

    Returns a factor ~0 at very low speed, ~1.0 at reference speed,
    and >1.0 (capped) at very high speed.  Uses a power-law with
    exponent 1.2 to reflect the v^2 nature of aero drag while
    accounting for diminishing returns at extreme speeds.

    Calibrated against Hagberg & McCole data:
      ~15% reduction at 15 km/h (aero drag negligible)
      ~38% reduction at 32 km/h (18% whole-group average)
      ~50% reduction at 40 km/h (27% whole-group average)
      ~71% reduction at 54 km/h (Blocken reference)
    """
    if speed_ms <= 0:
        return 0.0
    ratio = speed_ms / _SPEED_REF
    return min(ratio ** 1.2, 1.6)

# ── Group-size bonus ────────────────────────────────────────────────────────
# Larger groups create a deeper and wider wake, increasing the benefit
# for riders further back.  Based on experimental observations:
#   2 riders: baseline (1.0x)
#   4 riders: ~10% more benefit
#   8 riders: ~20% more benefit

def _group_bonus(riders: int) -> float:
    """Multiplier on the base reduction that accounts for larger wake in bigger groups."""
    if riders <= 2:
        return 1.0
    # Logarithmic scaling: diminishing returns as group grows
    return 1.0 + 0.12 * math.log2(riders / 2)

# ── Position factor ─────────────────────────────────────────────────────────
# Position 2 (first follower) gets the most benefit.
# Positions further back get slightly less because the wake is partially
# "used up" by intermediate riders (each rider re-introduces some turbulence).
# However, in larger groups wake reinforcement partly compensates.
#
# Net effect: position 2 gets ~100% of the base reduction, position N gets
# a decaying fraction.

def _position_decay(position: int, riders: int) -> float:
    """Fraction of the base draft reduction that position *position* receives.

    Position 1 (leader) always returns 0.0 (no benefit).
    Position 2 returns 1.0 (full benefit).
    Subsequent positions decay gently.
    """
    if position <= 1:
        return 0.0
    if position == 2:
        return 1.0
    # Mild exponential decay for positions behind the first follower.
    # In a group of 8, position 8 still gets ~80% of position 2's benefit.
    decay_rate = 0.04  # per-position decay
    return max(0.3, math.exp(-decay_rate * (position - 2)))


def cycling_draft_drag_reduction(riders: int, position: int,
                                  speed_kmh: float = 40.0,
                                  gap_m: float = 0.5) -> float:
    """Dynamic CdA multiplier (1.0 = no benefit) for a rider at *position*
    in a group of *riders*, travelling at *speed_kmh* with *gap_m* metres
    between each wheel.

    The model combines four independent factors:
      1. Gap distance  — double-exponential fit to Blocken et al. CFD data
      2. Speed          — power-law scaling (aero drag ~ v^2)
      3. Group size     — logarithmic bonus for larger wakes
      4. Position       — mild decay for positions behind the first follower

    Returns a value in (0, 1].  Lower = more draft benefit.
    """
    if riders < 2 or position < 1 or position > riders:
        return 1.0
    if position == 1:
        return 1.0

    # Clamp inputs to reasonable ranges
    riders_eff = min(riders, 20)
    gap_clamped = max(0.15, min(gap_m, 100.0))
    speed_ms = max(0.0, speed_kmh / 3.6)

    # 1) Base reduction from gap distance (calibrated at reference speed)
    base_red = _gap_reduction(gap_clamped)

    # 2) Speed correction
    spd = _speed_factor(speed_ms)

    # 3) Group-size bonus
    grp = _group_bonus(riders_eff)

    # 4) Position decay
    pos = _position_decay(position, riders_eff)

    # Combined drag reduction fraction
    total_reduction = base_red * spd * grp * pos

    # Clamp: maximum realistic reduction is ~80% (multiplier 0.20)
    total_reduction = min(total_reduction, 0.80)

    return max(0.20, 1.0 - total_reduction)


# ── Legacy static model (for comparison / testing) ─────────────────────────

_LEGACY_DRAFT_COEFFICIENTS = {
    2: {"base": 0.70, "decay": 0.85},
    3: {"base": 0.65, "decay": 0.80},
    4: {"base": 0.62, "decay": 0.78},
    5: {"base": 0.60, "decay": 0.76},
    6: {"base": 0.58, "decay": 0.74},
    7: {"base": 0.56, "decay": 0.72},
    8: {"base": 0.55, "decay": 0.70},
}


def cycling_draft_drag_reduction_legacy(riders: int, position: int,
                                         speed_kmh: float = 40.0,
                                         gap_m: float = 0.5) -> float:
    """Old static CdA multiplier.  Ignores speed and gap (kept for A/B testing).

    Accepts the same signature as the dynamic version so they are
    interchangeable, but the extra arguments are silently ignored.
    """
    if riders < 2 or position < 1 or position > riders:
        return 1.0
    if riders > 8:
        position = max(1, min(8, int(8 * position / riders)))
        riders = 8
    c = _LEGACY_DRAFT_COEFFICIENTS[riders]
    if position == 1:
        return 1.0
    pf = (position - 1) / (riders - 1)
    return min(1.0, c["base"] + (1 - c["base"]) * pf * c["decay"])


# ── Small helpers ───────────────────────────────────────────────────────────

def get_cda_position(cda: float) -> str:
    if cda < 0.23:
        return "Elite time trial equipment and positioning"
    if cda < 0.30:
        return "Good time trial / Triathlon positioning"
    if cda < 0.35:
        return "Road bike racing / Drop bar lows"
    if cda < 0.50:
        return "Road climbing / Mountain bike XC"
    return "Upright position with casual clothing"


def format_time(seconds: float) -> str:
    if seconds <= 0:
        return "Invalid"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time_input(text: str) -> Optional[float]:
    """Parse ``MM:SS`` or ``H:MM:SS`` → seconds, or *None* on failure."""
    if not text or not text.strip():
        return None
    try:
        parts = text.strip().split(":")
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            if 0 <= s < 60:
                return m * 60 + s
        elif len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            if 0 <= m < 60 and 0 <= s < 60:
                return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        pass
    return None


def compute_avg_elevation(start_elev: float, slope_pct: float, distance_km: float) -> float:
    """Return average elevation above sea level for a constant-grade segment.

    *start_elev*  – elevation at km 0 (m)
    *slope_pct*   – gradient in % (e.g. 5 means 5 %)
    *distance_km* – horizontal distance (km)
    """
    gain = distance_km * 1000 * (slope_pct / 100.0)
    return max(0, start_elev + gain / 2.0)


# ── Cyclist-powers for drafting visual ──────────────────────────────────────

def calculate_cyclist_powers(riders, position, rotating, work_pct,
                             front_power, aero_watts, non_aero_watts,
                             draft_fn, speed_kmh=40.0, gap_m=0.5):
    """Return per-position powers at the same group speed.

    Drafting only reduces the aerodynamic drag component.  Gravity and
    rolling resistance are unaffected by the slipstream.

    ``front_power``    – total power of the front rider (no drafting)
    ``aero_watts``     – aerodynamic component of front_power
    ``non_aero_watts`` – gravity + rolling component (unchanged by drafting)
    ``speed_kmh`` and ``gap_m`` are forwarded to the dynamic draft function.
    """
    if riders < 2:
        return []

    position = max(1, min(riders, int(position)))
    data = []
    for i in range(1, riders + 1):
        df = draft_fn(riders, i, speed_kmh=speed_kmh, gap_m=gap_m)
        # Draft factor only applies to aero watts; non-aero stays the same
        drafted_aero = aero_watts * df
        cp = drafted_aero + non_aero_watts
        data.append({
            "position": i,
            "power": int(cp),
            "draft_factor": df,
            "time_pct": work_pct if rotating and i == position else 0,
            "is_you": i == position,
        })
    return data


# ── HTML snippet builders (dark-theme aware) ───────────────────────────────

def create_cyclist_visualization(cyclist_data: list, labels=None) -> str:
    if not cyclist_data:
        return ""
    labels = labels or {}
    pos_label = labels.get("cyclist_pos", "Pos.")
    you_label = labels.get("cyclist_you", "You")
    front_label = labels.get("cyclist_front", "front")

    html = '<div class="cyclist-row">'
    for c in cyclist_data:
        you_txt = f" ({you_label})" if c["is_you"] else ""
        pct = (f'<div class="cyclist-pct">{c["time_pct"]:.0f}% {front_label}</div>'
               if c["time_pct"] > 0 else "")
        # Emoji removed for a consistent UI without pictograms
        emoji = ""
        cls = "cyclist-card you" if c["is_you"] else "cyclist-card"
        html += (
            f'<div class="{cls}">'
            f'<div class="cyclist-emoji">{emoji}</div>'
            f'<div class="cyclist-pos">{pos_label} {c["position"]}{you_txt}</div>'
            f'<div class="cyclist-power">{c["power"]}w</div>'
            f'{pct}</div>'
        )
    html += "</div>"
    return html


def build_summary_html(calc_mode, pred_time, pred_speed, pred_power, pred_wkg, time_diff, draft_info, labels=None):
    labels = labels or {}
    mode_label = labels.get("mode_power_time", "Power → Time") if calc_mode == "Power → Time" else labels.get("mode_time_power", "Time → Power")
    draft_text = draft_info or labels.get("no_drafting", "No drafting")
    return f"""
    <div class="summary-grid">
        <div class="summary-card">
            <div class="summary-label">{labels.get("summary_mode", "Mode")}</div>
            <div class="summary-value">{mode_label}</div>
            <div class="summary-sub">{labels.get("summary_calculation", "Calculation")}</div>
        </div>
        <div class="summary-card">
            <div class="summary-label">{labels.get("summary_speed", "Speed")}</div>
            <div class="summary-value">{pred_speed} km/h</div>
            <div class="summary-sub">{labels.get("summary_time", "Time")} {pred_time}{time_diff}</div>
        </div>
        <div class="summary-card">
            <div class="summary-label">{labels.get("summary_power", "Power")}</div>
            <div class="summary-value">{pred_power} w</div>
            <div class="summary-sub">{pred_wkg} w/kg</div>
        </div>
        <div class="summary-card">
            <div class="summary-label">{labels.get("summary_drafting", "Drafting")}</div>
            <div class="summary-value">{draft_text}</div>
            <div class="summary-sub">{labels.get("summary_aero_impact", "Aero impact")}</div>
        </div>
    </div>"""


def build_power_breakdown_html(gravity_pct, aero_pct, rolling_pct, labels=None):
    labels = labels or {}
    return f"""
    <div class="bars">
        <div class="bar-row">
            <span class="bar-label">{labels.get("gravity", "Gravity")}</span>
            <div class="bar"><div class="fill gravity" style="width:{gravity_pct}%"></div></div>
            <span class="bar-value">{gravity_pct}%</span>
        </div>
        <div class="bar-row">
            <span class="bar-label">{labels.get("aerodynamics", "Aerodynamics")}</span>
            <div class="bar"><div class="fill aero" style="width:{aero_pct}%"></div></div>
            <span class="bar-value">{aero_pct}%</span>
        </div>
        <div class="bar-row">
            <span class="bar-label">{labels.get("rolling", "Rolling")}</span>
            <div class="bar"><div class="fill rolling" style="width:{rolling_pct}%"></div></div>
            <span class="bar-value">{rolling_pct}%</span>
        </div>
    </div>"""
