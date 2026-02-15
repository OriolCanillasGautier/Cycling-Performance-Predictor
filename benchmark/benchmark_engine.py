import json
import math
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.cycling_physics import (
    cycling_draft_drag_reduction,
    cycling_draft_drag_reduction_legacy,
)

G = 9.80665


def _merge(defaults: dict, override: dict) -> dict:
    merged = dict(defaults)
    merged.update(override)
    return merged


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _scenario_speed_kmh(s: dict) -> float:
    speed = float(s.get("speed_kmh", 0) or 0)
    if speed > 0:
        return speed

    distance_km = float(s.get("distance_km", 0) or 0)
    time_s = float(s.get("time_s", 0) or 0)
    if distance_km > 0 and time_s > 0:
        return distance_km / (time_s / 3600.0)

    raise ValueError(
        f"Scenario {s.get('id', '?')} needs either speed_kmh or distance_km+time_s"
    )


def _cda_for_draft(s: dict, draft_fraction: float) -> float:
    draft_fraction = _clamp(draft_fraction, 0.0, 1.0)
    sex = str(s.get("sex", "male")).lower()

    if sex in {"female", "woman", "women", "f"}:
        cda0 = float(s["cda_women_0"])
        cda100 = float(s["cda_women_100"])
    else:
        cda0 = float(s["cda_men_0"])
        cda100 = float(s["cda_men_100"])

    return cda0 + (cda100 - cda0) * draft_fraction


def _diy_power_w(s: dict, speed_kmh: float, effective_cda: float) -> float:
    v = speed_kmh / 3.6
    m = float(s["total_mass_kg"])
    rho = float(s["air_density"])
    crr = float(s["crr"])
    eta = max(1e-6, float(s["drivetrain_efficiency"]))

    grade = float(s["gradient_pct"]) / 100.0
    theta = math.atan(grade)

    f_gravity = m * G * math.sin(theta)
    f_roll = m * G * math.cos(theta) * crr
    f_aero = 0.5 * rho * effective_cda * v * v

    wheel_power = (f_gravity + f_roll + f_aero) * v
    return wheel_power / eta


def run_benchmark(scenarios_path: str | Path) -> dict:
    p = Path(scenarios_path)
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    defaults = payload.get("defaults", {})
    scenarios = payload.get("scenarios", [])
    rows = []

    for raw in scenarios:
        s = _merge(defaults, raw)

        riders = int(s["riders"])
        position = int(s["position"])
        gap_m = float(s.get("gap_m", 0.5))
        speed_kmh = _scenario_speed_kmh(s)

        dyn_mult = cycling_draft_drag_reduction(
            riders, position, speed_kmh=speed_kmh, gap_m=gap_m
        )
        leg_mult = cycling_draft_drag_reduction_legacy(
            riders, position, speed_kmh=speed_kmh, gap_m=gap_m
        )

        dyn_draft = 1.0 - dyn_mult
        leg_draft = 1.0 - leg_mult

        dyn_cda = _cda_for_draft(s, dyn_draft)
        leg_cda = _cda_for_draft(s, leg_draft)

        dyn_power = _diy_power_w(s, speed_kmh, dyn_cda)
        leg_power = _diy_power_w(s, speed_kmh, leg_cda)

        row = {
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "sex": s.get("sex", "male"),
            "riders": riders,
            "position": position,
            "speed_kmh": round(speed_kmh, 2),
            "gap_m": round(gap_m, 2),
            "distance_km": float(s.get("distance_km", 0)),
            "gradient_pct": float(s["gradient_pct"]),
            "dyn_draft_pct": dyn_draft * 100.0,
            "leg_draft_pct": leg_draft * 100.0,
            "dyn_cda": dyn_cda,
            "leg_cda": leg_cda,
            "dyn_power_w": dyn_power,
            "leg_power_w": leg_power,
            "power_diff_w": dyn_power - leg_power,
            "power_diff_pct": ((dyn_power - leg_power) / leg_power * 100.0) if leg_power else 0.0,
        }
        rows.append(row)

    diffs = [r["power_diff_w"] for r in rows] or [0.0]

    summary = {
        "scenario_count": len(rows),
        "mean_dyn_power_w": mean([r["dyn_power_w"] for r in rows]) if rows else 0.0,
        "mean_leg_power_w": mean([r["leg_power_w"] for r in rows]) if rows else 0.0,
        "mean_diff_w": mean(diffs),
        "min_diff_w": min(diffs),
        "max_diff_w": max(diffs),
        "dyn_gt_leg_count": sum(1 for d in diffs if d > 0),
        "dyn_lt_leg_count": sum(1 for d in diffs if d < 0),
    }

    return {
        "source": str(p),
        "defaults": defaults,
        "rows": rows,
        "summary": summary,
    }
