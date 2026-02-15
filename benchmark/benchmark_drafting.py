"""JSON-driven drafting benchmark (CLI).

Compares dynamic vs legacy draft model using DIY power calculations:
- Inputs: distance, gradient, time/speed, mass, air density, CRR, drivetrain, CdA
- CdA interpolation by drafting percentage:
  * men:   0% draft -> 0.3500, 100% draft -> 0.2625
  * women: lower baseline (configured in benchmark_scenarios.json)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark_engine import run_benchmark


def main() -> None:
    source = Path(__file__).with_name("benchmark_scenarios.json")
    result = run_benchmark(source)

    print("=" * 120)
    print("DRAFTING BENCHMARK (DIY POWER METHOD)")
    print("=" * 120)
    print(f"Scenarios file: {result['source']}")
    print()
    print(
        f"{'ID':<4} {'Name':<28} {'Sex':<6} {'R':>2} {'P':>2} {'km/h':>6} {'Gap':>5} "
        f"{'DynDraft%':>10} {'LegDraft%':>10} {'DynCdA':>8} {'LegCdA':>8} "
        f"{'DynW':>8} {'LegW':>8} {'DiffW':>8}"
    )
    print("-" * 120)

    for r in result["rows"]:
        print(
            f"{r['id']:<4} {r['name'][:28]:<28} {r['sex'][:6]:<6} "
            f"{r['riders']:>2} {r['position']:>2} {r['speed_kmh']:>6.1f} {r['gap_m']:>5.2f} "
            f"{r['dyn_draft_pct']:>10.1f} {r['leg_draft_pct']:>10.1f} "
            f"{r['dyn_cda']:>8.4f} {r['leg_cda']:>8.4f} "
            f"{r['dyn_power_w']:>8.1f} {r['leg_power_w']:>8.1f} {r['power_diff_w']:>8.1f}"
        )

    s = result["summary"]
    print("-" * 120)
    print(f"Scenario count : {s['scenario_count']}")
    print(f"Mean dyn power : {s['mean_dyn_power_w']:.2f} W")
    print(f"Mean leg power : {s['mean_leg_power_w']:.2f} W")
    print(f"Mean diff      : {s['mean_diff_w']:+.2f} W")
    print(f"Min / Max diff : {s['min_diff_w']:+.2f} W / {s['max_diff_w']:+.2f} W")
    print(f"Dyn > Leg      : {s['dyn_gt_leg_count']}")
    print(f"Dyn < Leg      : {s['dyn_lt_leg_count']}")


if __name__ == "__main__":
    main()
