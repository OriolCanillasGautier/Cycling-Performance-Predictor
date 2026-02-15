# Cycling Performance Predictor - Benchmark System

This folder contains the benchmarking system for comparing cycling physics calculations, specifically focusing on drafting models and power estimation under different riding conditions.

## Overview

The benchmark system evaluates and compares two drafting models:
- **Dynamic Model** (`cycling_draft_drag_reduction`): Modern, physics-based drafting calculations
- **Legacy Model** (`cycling_draft_drag_reduction_legacy`): Traditional baseline for comparison

Power is calculated using the DIY (Do-It-Yourself) method based on aerodynamic drag, rolling resistance, and gravitational forces.

---

## System Architecture

### Core Components

1. **benchmark_engine.py** - Main computation engine
2. **benchmark_scenarios.json** - Test scenario data and configuration
3. **benchmark_drafting.py** - CLI interface for running benchmarks
4. **benchmark_web.py** - Web-based visualization interface

### Data Flow

```
benchmark_scenarios.json (scenarios + defaults)
          ↓
   run_benchmark()
          ↓
   Per scenario:
   - Load parameters (merge defaults with scenario overrides)
   - Calculate speed (from km/h or distance+time)
   - Compute draft multipliers (dynamic vs legacy)
   - Interpolate CdA based on draft percentage
   - Calculate power using DIY method
   ↓
   Return: rows (per-scenario results) + summary (statistics)
```

---

## How to Add a New Formula or Calculation

### Step 1: Understand the Current Calculation Pipeline

The benchmark system follows this calculation sequence:

```python
# 1. Speed determination
speed_kmh = scenario["speed_kmh"]  # Direct or computed from distance+time

# 2. Draft effect calculation
dyn_mult = cycling_draft_drag_reduction(riders, position, speed_kmh, gap_m)
# Returns: fraction of CdA to apply (0.0 = full draft benefit, 1.0 = no draft)

# 3. CdA interpolation (aerodynamic coefficient)
dyn_draft = 1.0 - dyn_mult  # Percentage of drafting benefit (0-1)
dyn_cda = cda_0 + (cda_100 - cda_0) * dyn_draft
# Linear interpolation between upright (0%) and fully drafting (100%)

# 4. Power calculation (DIY method)
power = (f_gravity + f_roll + f_aero) * velocity / drivetrain_efficiency
# f_gravity: mass * g * sin(gradient)
# f_roll: mass * g * cos(gradient) * CRR
# f_aero: 0.5 * air_density * CdA * velocity^2
```

### Step 2: Create Your Custom Calculation Function

Add your formula as a new module in the benchmark folder. Example:

```python
# benchmark/custom_power_model.py

def custom_power_calculation(
    speed_kmh: float,
    mass_kg: float,
    gradient_pct: float,
    cda: float,
    crr: float = 0.005,
    air_density: float = 1.225,
    drivetrain_efficiency: float = 0.975,
    **kwargs
) -> float:
    """
    Calculate power using a custom formula.
    
    Args:
        speed_kmh: Rider speed in km/h
        mass_kg: Total mass (rider + bike) in kg
        gradient_pct: Road gradient as percentage
        cda: Coefficient of drag × frontal area
        crr: Coefficient of rolling resistance
        air_density: Air density in kg/m³ (sea level ≈ 1.225)
        drivetrain_efficiency: Drivetrain loss factor (0.975 = 2.5% loss)
        **kwargs: Additional parameters for flexibility
    
    Returns:
        float: Power in watts
    """
    import math
    
    G = 9.80665  # Gravitational acceleration
    v = speed_kmh / 3.6  # Convert to m/s
    
    # Calculate forces
    grade = gradient_pct / 100.0
    theta = math.atan(grade)
    
    f_gravity = mass_kg * G * math.sin(theta)
    f_roll = mass_kg * G * math.cos(theta) * crr
    f_aero = 0.5 * air_density * cda * v * v
    
    # Total wheel power
    wheel_power = (f_gravity + f_roll + f_aero) * v
    
    # Apply drivetrain efficiency losses
    return wheel_power / drivetrain_efficiency
```

### Step 3: Integrate the Calculation into benchmark_engine.py

Modify the `run_benchmark()` function to call your custom calculation:

```python
# At the top of benchmark_engine.py, import your function
from benchmark.custom_power_model import custom_power_calculation

# In run_benchmark(), add calculation to the per-scenario loop:
def run_benchmark(scenarios_path: str | Path) -> dict:
    # ... existing code ...
    
    for raw in scenarios:
        s = _merge(defaults, raw)
        
        # ... existing calculations for dyn_power and leg_power ...
        
        # Add your custom calculation
        custom_power = custom_power_calculation(
            speed_kmh=speed_kmh,
            mass_kg=float(s["total_mass_kg"]),
            gradient_pct=float(s["gradient_pct"]),
            cda=dyn_cda,  # Use dynamic CdA or create your own
            crr=float(s["crr"]),
            air_density=float(s["air_density"]),
            drivetrain_efficiency=float(s["drivetrain_efficiency"])
        )
        
        # Add to row output
        row = {
            # ... existing fields ...
            "custom_power_w": custom_power,
            "custom_vs_dyn_diff": custom_power - dyn_power,
        }
        rows.append(row)
    
    # ... rest of function ...
```

### Step 4: Update the Scenario JSON Configuration

If your formula requires new parameters, add them to `benchmark_scenarios.json`:

```json
{
  "defaults": {
    "distance_km": 12.0,
    "gradient_pct": 6.0,
    "total_mass_kg": 78.0,
    "air_density": 1.225,
    "crr": 0.005,
    "drivetrain_efficiency": 0.975,
    "cda_men_0": 0.35,
    "cda_men_100": 0.2625,
    "cda_women_0": 0.31,
    "cda_women_100": 0.2325,
    "your_custom_param": 0.42
  },
  "scenarios": [
    {
      "id": "S01",
      "name": "Your test scenario",
      "your_custom_param": 0.50
    }
  ]
}
```

### Step 5: Add Output Display

Update the CLI (`benchmark_drafting.py`) to show your custom calculation:

```python
# In the print statement formatting:
print(
    f"{'ID':<4} {'Name':<28} {'DynW':>8} {'LegW':>8} {'CustomW':>8} {'DiffW':>8}"
)

for r in result["rows"]:
    print(
        f"{r['id']:<4} {r['name'][:28]:<28} "
        f"{r['dyn_power_w']:>8.1f} {r['leg_power_w']:>8.1f} "
        f"{r['custom_power_w']:>8.1f} {r['custom_vs_dyn_diff']:>8.1f}"
    )
```

---

## How to Use the Benchmark System

### Method 1: CLI (Command Line)

**Run the benchmark and display results in terminal:**

```bash
cd Cycling-Performance-Predictor
python benchmark/benchmark_drafting.py
```

**Output example:**
```
============================================================
DRAFTING BENCHMARK (DIY POWER METHOD)
============================================================
Scenarios file: benchmark/benchmark_scenarios.json

ID   Name                         Sex    R  P   km/h   Gap  DynDraft%  LegDraft%  DynCdA  LegCdA  DynW  LegW   DiffW
---- ---------------------------- ------ -- -- ------ ----- ---------- ---------- -------- -------- -------- -------- --------
S01  Pair close moderate          male   2  2  38.0  0.45       44.4       40.0    0.3145  0.3200   245.3   258.7   -13.4
...
```

### Method 2: Web Interface

**Launch interactive visualization with charts:**

```bash
cd Cycling-Performance-Predictor
python benchmark/benchmark_web.py
```

Then open your browser (typically `http://localhost:8080`)

**Features:**
- Summary statistics cards
- Interactive charts comparing models
- Scenario-by-scenario results table
- Real-time updates when scenarios change

### Method 3: Python API

**Use the benchmark engine in your own code:**

```python
from pathlib import Path
from benchmark.benchmark_engine import run_benchmark

# Run benchmark
result = run_benchmark(Path("benchmark/benchmark_scenarios.json"))

# Access results
rows = result["rows"]          # List of per-scenario calculations
summary = result["summary"]    # Aggregate statistics

# Iterate through scenarios
for row in rows:
    print(f"Scenario {row['id']}: {row['dyn_power_w']:.1f}W (dyn) vs {row['leg_power_w']:.1f}W (leg)")

# Access summary
print(f"Mean power difference: {summary['mean_diff_w']:+.2f} W")
```

---

## Scenario Configuration Details

### Structure of benchmark_scenarios.json

```json
{
  "defaults": {
    // Global defaults applied to all scenarios
    "distance_km": 12.0,
    "gradient_pct": 6.0,
    "total_mass_kg": 78.0,
    "air_density": 1.225,
    "crr": 0.005,
    "drivetrain_efficiency": 0.975,
    "cda_men_0": 0.35,
    "cda_men_100": 0.2625,
    "cda_women_0": 0.31,
    "cda_women_100": 0.2325
  },
  "scenarios": [
    {
      "id": "S01",
      "name": "Pair close moderate",
      "sex": "male",
      "riders": 2,
      "position": 2,
      "gap_m": 0.45,
      "speed_kmh": 38.0,
      // Any field here overrides the default
    }
  ]
}
```

### Key Parameters Explained

| Parameter | Unit | Description | Typical Range |
|-----------|------|-------------|----------------|
| `speed_kmh` | km/h | Riding speed | 15 - 55 |
| `distance_km` | km | Segment distance | 5 - 50 |
| `time_s` | seconds | Segment duration (alternative to speed_kmh) | 300 - 3600 |
| `gradient_pct` | % | Road slope (negative = downhill) | -5 to 15 |
| `total_mass_kg` | kg | Rider + bike weight | 60 - 100 |
| `air_density` | kg/m³ | Air density (sea level ≈ 1.225) | 1.0 - 1.3 |
| `crr` | unitless | Coefficient of rolling resistance | 0.003 - 0.008 |
| `drivetrain_efficiency` | unitless | Drivetrain loss factor | 0.95 - 0.99 |
| `cda_men_0` | m² | CdA at 0% draft (men, upright) | 0.30 - 0.40 |
| `cda_men_100` | m² | CdA at 100% draft (men, fully aero) | 0.20 - 0.30 |
| `cda_women_0` | m² | CdA at 0% draft (women) | 0.25 - 0.35 |
| `cda_women_100` | m² | CdA at 100% draft (women) | 0.15 - 0.25 |
| `riders` | count | Number of riders in group | 2 - 20 |
| `position` | count | Position in line (1 = front) | 1 - riders |
| `gap_m` | meters | Distance between riders | 0.2 - 5.0 |

### Speed Determination (Priority Order)

1. **Explicit speed_kmh**: Used if provided
   ```json
   {"speed_kmh": 38.0}
   ```

2. **Computed from distance + time**: Calculated as `km / (seconds / 3600)`
   ```json
   {"distance_km": 12.0, "time_s": 1200}  // 12 km in 1200s = 36 km/h
   ```

3. **Error**: Must have one or the other
   ```python
   # Raises ValueError if neither is valid
   raise ValueError("Scenario needs either speed_kmh or distance_km+time_s")
   ```

---

## Advanced: Creating a Custom Drafting Model

### Example: Adding a New Draft Algorithm

```python
# benchmark/custom_drafting_model.py

def my_advanced_drafting(
    riders: int,
    position: int,
    speed_kmh: float,
    gap_m: float,
) -> float:
    """
    Custom drafting model with gap and speed dependence.
    
    Returns:
        float: CdA multiplier (0.0 = full drafting, 1.0 = no draft)
    """
    import math
    
    # Position-based drag reduction (deeper positions = more draft benefit)
    position_factor = (position - 1) / max(1, riders - 1)  # 0 to 1
    
    # Speed-dependent benefit (higher speeds = more aerodynamic benefit)
    speed_factor = min(1.0, speed_kmh / 50.0)
    
    # Gap-dependent (closer = more draft)
    gap_factor = math.exp(-gap_m / 0.3)
    
    # Combined effect
    draft_benefit = position_factor * speed_factor * gap_factor
    
    # Convert to CdA multiplier (0 = full draft, 1 = no draft)
    return 1.0 - draft_benefit
```

### Integration

```python
# In benchmark_engine.py:
from benchmark.custom_drafting_model import my_advanced_drafting

# In run_benchmark():
custom_draft_mult = my_advanced_drafting(
    riders, position, speed_kmh=speed_kmh, gap_m=gap_m
)
custom_draft = 1.0 - custom_draft_mult
custom_cda = _cda_for_draft(s, custom_draft)
custom_power = _diy_power_w(s, speed_kmh, custom_cda)
```

---

## Understanding the Power Calculation

### DIY Power Method Formula

The power calculation follows basic physics:

```
Power = (F_gravity + F_rolling + F_aerodynamic) × velocity / efficiency

Where:
  F_gravity = m × g × sin(θ)           [Force due to slope]
  F_rolling = m × g × cos(θ) × CRR     [Rolling resistance]
  F_aero = 0.5 × ρ × CdA × v²          [Aerodynamic drag]
  θ = atan(gradient)                    [Slope angle in radians]
  ρ = air_density                       [Air density]
  v = speed_kmh / 3.6                   [Speed in m/s]
```

### Component Breakdown

**Example: 250W at 40 km/h, 6% gradient, 78 kg rider**

```
Gravitational force:     ~65 N  →  74 W
Rolling resistance:      ~39 N  →  44 W
Aerodynamic drag:        ~25 N  → 113 W
                                 -------
Total wheel power:               231 W
÷ Drivetrain loss (2.5%):        243 W  (rider watts)
```

---

## Example: Complete Custom Calculation

### Scenario: Adding a "Slipstream Bonus" Formula

**1. Create the formula file:**

```python
# benchmark/slipstream_bonus_model.py

def slipstream_bonus(riders: int, position: int, gap_m: float) -> float:
    """
    Advanced drafting with exponential slipstream bonus for followers.
    """
    if position == 1:
        return 1.0  # Leader gets no draft
    
    if gap_m > 2.0:
        return 1.0  # Too far back, no draft benefit
    
    # Exponential improvement for closer gaps
    gap_benefit = math.exp(-gap_m / 0.4)
    
    # Position improves draft (deeper position = more benefit)
    position_benefit = 0.3 + 0.7 * (riders - position) / (riders - 1)
    
    return 1.0 - (gap_benefit * position_benefit)
```

**2. Update benchmark_engine.py:**

```python
from benchmark.slipstream_bonus_model import slipstream_bonus

# Add to scenario loop:
bonus_mult = slipstream_bonus(riders, position, gap_m=gap_m)
bonus_draft = 1.0 - bonus_mult
bonus_cda = _cda_for_draft(s, bonus_draft)
bonus_power = _diy_power_w(s, speed_kmh, bonus_cda)

row["bonus_draft_pct"] = bonus_draft * 100.0
row["bonus_power_w"] = bonus_power
row["bonus_vs_dyn"] = bonus_power - dyn_power
```

**3. Run and compare:**

```bash
python benchmark/benchmark_drafting.py
```

Now you'll see the bonus model's power output compared to dynamic and legacy models.

---

## Troubleshooting

### "Scenario needs either speed_kmh or distance_km+time_s"

**Problem:** A scenario doesn't specify speed properly.

**Solution:**
```json
// Good:
{"speed_kmh": 38.0}
// or
{"distance_km": 12.0, "time_s": 1200}

// Bad:
{}  // Missing both
{"distance_km": 12.0}  // Missing time
```

### Results showing NaN or Infinity

**Problem:** Invalid calculation parameters.

**Causes:**
- `drivetrain_efficiency` ≤ 0
- `air_density` ≤ 0
- Negative power in denominator

**Solution:** Validate parameter ranges in your scenario JSON.

### Import errors

**Problem:** `ModuleNotFoundError: No module named 'benchmark.custom_model'`

**Solution:**
```python
# Ensure __init__.py exists in benchmark folder
touch benchmark/__init__.py

# Or use absolute imports
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from custom_model import your_function
```

---

## File Reference

### benchmark_engine.py
- **Purpose:** Core computation engine
- **Key functions:**
  - `run_benchmark(scenarios_path)`: Main entry point
  - `_scenario_speed_kmh(s)`: Calculate speed from scenario
  - `_cda_for_draft(s, draft_fraction)`: Interpolate CdA
  - `_diy_power_w(s, speed_kmh, effective_cda)`: Calculate power

### benchmark_scenarios.json
- **Purpose:** Test scenarios and default parameters
- **Structure:** `defaults` + `scenarios` array
- **Usage:** Configuration-driven testing

### benchmark_drafting.py
- **Purpose:** CLI interface for terminal output
- **Usage:** `python benchmark/benchmark_drafting.py`

### benchmark_web.py
- **Purpose:** Interactive web visualization
- **Usage:** `python benchmark/benchmark_web.py`
- **Requirements:** `nicegui`, `plotly`

---

## Quick Start Template

To add your formula quickly:

```python
# benchmark/my_formula.py
def my_power_calc(speed_kmh, mass_kg, gradient_pct, cda, **kwargs) -> float:
    import math
    G = 9.80665
    v = speed_kmh / 3.6
    grade = gradient_pct / 100.0
    theta = math.atan(grade)
    
    f_gravity = mass_kg * G * math.sin(theta)
    f_roll = mass_kg * G * math.cos(theta) * kwargs.get("crr", 0.005)
    f_aero = 0.5 * kwargs.get("air_density", 1.225) * cda * v * v
    
    wheel_power = (f_gravity + f_roll + f_aero) * v
    return wheel_power / kwargs.get("drivetrain_efficiency", 0.975)
```

Then in `benchmark_engine.py`:

```python
from benchmark.my_formula import my_power_calc

# In loop:
my_power = my_power_calc(
    speed_kmh, float(s["total_mass_kg"]), float(s["gradient_pct"]), dyn_cda, **s
)
```

---

## Contributing

When adding new formulas:

1. **Document the formula** with docstrings
2. **Add test scenarios** that exercise your formula
3. **Update benchmark_scenarios.json** if new parameters needed
4. **Update benchmark_drafting.py** output format to show results
5. **Test thoroughly** with edge cases (steep climbs, high speeds, etc.)

---

For questions or to report issues, refer to the main [README.md](../README.md).
