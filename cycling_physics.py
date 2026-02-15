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

_DRAFT_COEFFICIENTS = {
    2: {"base": 0.70, "decay": 0.85},
    3: {"base": 0.65, "decay": 0.80},
    4: {"base": 0.62, "decay": 0.78},
    5: {"base": 0.60, "decay": 0.76},
    6: {"base": 0.58, "decay": 0.74},
    7: {"base": 0.56, "decay": 0.72},
    8: {"base": 0.55, "decay": 0.70},
}


def cycling_draft_drag_reduction(riders: int, position: int) -> float:
    """CdA multiplier (1.0 = no benefit) for *position* in a group of *riders*."""
    if riders < 2 or position < 1 or position > riders:
        return 1.0
    if riders > 8:
        position = max(1, min(8, int(8 * position / riders)))
        riders = 8
    c = _DRAFT_COEFFICIENTS[riders]
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

def calculate_cyclist_powers(riders, position, rotating, work_pct, power, cda, draft_fn):
    data = []
    if rotating:
        ft = work_pct / 100.0
        bdr = draft_fn(riders, riders)
        fp = power / (ft + (1 - ft) * bdr)
        for i in range(1, riders + 1):
            cp = fp if i == 1 else fp * draft_fn(riders, i)
            data.append({"position": i, "power": int(cp),
                         "time_pct": work_pct if i == position else 0,
                         "is_you": i == position})
    else:
        ydf = draft_fn(riders, position)
        bp = power / ydf
        for i in range(1, riders + 1):
            df = draft_fn(riders, i)
            data.append({"position": i, "power": int(bp * df),
                         "time_pct": 0, "is_you": i == position})
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
