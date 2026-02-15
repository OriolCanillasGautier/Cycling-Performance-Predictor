# Cycling Performance Predictor

A NiceGUI-based cycling simulator that estimates either:

- **time/speed from power** (Power → Time), or
- **required power from target time** (Time → Power).

The model combines gravity, rolling resistance, aerodynamics, drivetrain losses, and optional drafting effects. The interface supports 26 European languages with full internationalization.

---

## Table of Contents

1. [Physics Model](#physics-model) – Detailed mechanics and calculations
2. [How to Use](#how-to-use) – Installation, quick start, and usage guide
3. [Structure & Development](#structure--development) – Project organization, architecture, and troubleshooting

---

## Physics Model

### Overview

All internals use SI units (meters, seconds, kilograms, watts, etc.).

The power calculation is based on fundamental cycling mechanics:

$$
P = (F_g + F_r + F_a) \cdot \frac{v}{1-L}
$$

Where:
- $F_g$: gravitational force (climbing)
- $F_r$: rolling resistance
- $F_a$: aerodynamic drag
- $v$: velocity (m/s)
- $L$: drivetrain loss fraction (default 0.035)

### 1) Air Density vs Elevation

Air density decreases exponentially with elevation:

$$
\rho(h) = 1.225 \cdot e^{-h/8400}
$$

where $h$ is elevation in meters. Sea level ≈ 1.225 kg/m³.

### 2) Forces

Let:

- $m$: total mass (rider + bike/gear), kg
- $g = 9.8066\ \text{m/s}^2$
- $s$: grade as decimal (`Gradient (%) / 100`)
- $C_{rr}$: rolling resistance coefficient
- $C_dA$: drag area (m²)
- $v$: ground speed (m/s)
- $w$: wind speed (m/s), positive = headwind

#### Gravity force (climbing)

Grade is converted to angle via $\theta = \arctan(s)$:

$$
F_g = m g \sin(\arctan(s))
$$

#### Rolling resistance force

$$
F_r = m g \cos(\arctan(s)) C_{rr}
$$

#### Aerodynamic drag force

Relative air speed accounts for wind:

$$
v_r = v + w
$$

Drag force (preserving direction):

$$
F_a = \frac{1}{2}\rho C_dA\, v_r\,|v_r|
$$

Using $v_r|v_r|$ ensures correct sign behavior (headwind increases drag, tailwind reduces it).

### 3) Power Model

With drivetrain loss fraction $L$ (default `0.035`):

$$
P = (F_g + F_r + F_a)\cdot \frac{v}{1-L}
$$

The app also returns component powers (`gravity`, `aero`, `rolling`) and their percentage split of positive-resistance power.

### 4) Two Calculation Modes

#### Power → Time

Given target power, the solver finds velocity using binary search (`cycling_power_velocity_search`) and computes:

$$
t = \frac{d}{v}
$$

where $d$ is distance in meters.

#### Time → Power

Given target time, it computes target velocity directly:

$$
v = \frac{d}{t}
$$

Then evaluates the power equation at that velocity.

### 5) Elevation Handling

The UI asks for **Start Elevation (m)**. The model uses **average route elevation** for air density, computed as:

$$
h_{avg} = h_{start} + \frac{\Delta h}{2},\quad \Delta h = d_{horiz}\cdot s
$$

where:

- $d_{horiz}$ is distance in meters,
- $s$ is decimal grade.

Implemented in `compute_avg_elevation()`.

### 6) Drafting Model

When drafting is enabled, CdA is scaled by a reduction factor based on:

- **number of riders** in the group
- **rider position** (1 = front, no reduction)
- **optional rotating paceline** duty cycle (% time at front)
- **gap between riders** (closer = more draft benefit)
- **speed** (aero benefit increases at higher speeds)

Front rider experiences no reduction (factor = 1.0). Riders behind get lower effective drag (factor < 1.0).

The **dynamic model** uses speed-dependent and position-dependent calculations. The **legacy model** provides a simpler baseline for comparison.

The app estimates group power distribution and displays rider cards showing individual effort and savings.

### 7) Key Parameters

| Parameter | Unit | Description | Typical Range |
|-----------|------|-------------|----------------|
| Power | W | Rider watts | 50 - 500 |
| Total Mass | kg | Rider + bike | 60 - 100 |
| Gradient | % | Road slope | -10 to 20 |
| Distance | km | Segment length | 0.1 - 100 |
| Start Elevation | m | Starting altitude | 0 - 3000 |
| CdA | m² | Drag area | 0.15 - 0.50 |
| Crr | - | Rolling resistance | 0.003 - 0.008 |
| Wind | km/h | Headwind positive | -20 to 20 |
| Air Density | kg/m³ | At elevation | 1.0 - 1.3 |

---

## How to Use

### Requirements

- Python **3.10+** recommended (3.9+ may work)
- pip

### Installation

#### 1) Clone or open the folder

```bash
git clone https://github.com/OriolCanillasGautier/Cycling-Performance-Predictor.git
cd Cycling-Performance-Predictor
```

#### 2) Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3) Install dependencies

```bash
pip install -r requirements.txt
```

#### 4) Run the app

**Windows PowerShell (direct execution via virtualenv bootstrap):**

```powershell
.\perf_predictor.py
```

**Any platform (standard Python):**

```bash
python perf_predictor.py
```

The NiceGUI server will start on **http://localhost:7860**.

### Quick Start Guide

1. **Select language** from top-right selector (26 European languages available).

2. **Pick calculation mode:**
   - **Power → Time**: Input power, get predicted speed and time.
   - **Time → Power**: Input target time, get required power.

3. **Enter physical parameters:**
   - Body Weight (kg)
   - Bike / Gear Weight (kg)

4. **Configure route and environment:**
   - Gradient (%)
   - Distance (km)
   - Start Elevation (m)
   - Wind (km/h) – headwind positive, tailwind negative

5. **Set resistance model:**
   - Bike type: road or MTB (auto-fills Crr)
   - CdA (drag area m²)

6. **Optional: Enable drafting**
   - Group size (number of riders)
   - Position in line (1 = front)
   - Gap between riders (meters)
   - Enable rotating paceline for duty cycle

7. **Click Calculate Performance**

Results display in a detailed dialog showing:
- Power breakdown (gravity, aero, rolling)
- Time/speed prediction
- Drafting analysis and group power distribution
- Warnings for extreme combinations

**Note:** The production UI uses the dynamic drafting model only. Legacy comparison is available in benchmark tools.

### Output Interpretation

- **Summary cards**: Mode, speed/time, power/kg, drafting status
- **Predicted performance**: Key outcome for your selected mode
- **Power details**: 
  - Gravity power (climbing load)
  - Aerodynamic power (air resistance)
  - Rolling power (tire resistance)
  - Each shown in watts, W/kg, and percentage
- **Drafting section** (when enabled): Group power, power savings, and rider visualization

Warnings appear for extreme combinations (e.g., very low speed on steep gradients, very high W/kg demands).

### Inputs and Units

- **Power**: watts (W)
- **Target time**: `MM:SS` or `H:MM:SS` format
- **Weights**: kilograms (kg)
- **Gradient**: percent (%)
- **Distance**: kilometers (km)
- **Start elevation**: meters (m)
- **Wind**: km/h in UI (converted to m/s internally)
- **CdA**: m² (square meters)
- **Crr**: unitless (coefficient)

### Default Values

Common defaults in the UI:

- CdA: `0.40`
- Crr (road asphalt): `0.0050`
- Body weight: `70 kg`
- Bike/gear weight: `8.0 kg`
- Distance: `10 km`
- Drivetrain loss: `3.5%`

Terrain presets provided for both `road` and `mtb` in [app/cycling_physics.py](app/cycling_physics.py).

### Benchmark Tools

The benchmark system allows detailed testing and comparison of drafting models.

#### Run benchmark CLI

```bash
python benchmark/benchmark_drafting.py
```

Compares dynamic vs legacy models across JSON-defined scenarios. Outputs a detailed table showing power differences, drafting percentages, and CdA multipliers.

#### Run benchmark web UI

```bash
python benchmark/benchmark_web.py
```

Interactive visualization with plotly charts:
- Power comparison bars (dynamic vs legacy)
- Power difference analysis
- CdA multiplier trends
- Gap vs power scatter plot
- Full detailed results table

**Learn more:** See [benchmark/README.md](benchmark/README.md) for detailed configuration and custom formula integration.

---

## Structure & Development

### Project Structure

**Root** – Main application and documentation:
- `perf_predictor.py` – NiceGUI UI, event wiring, and calculation orchestration
- `requirements.txt` – Python dependencies
- `LICENSE`, `README.md`, `.gitignore` – Metadata

**app/** – Core cycling physics:
- `cycling_physics.py` – Physics engine, drafting models, utility functions
- `styles.css` – Dark theme and NiceGUI component overrides
- `languagepacks.json` – 26-language internationalization (auto-generated)

**benchmark/** – Testing and comparison tools:
- `benchmark_web.py` – Interactive web UI with charts (plotly)
- `benchmark_drafting.py` – CLI benchmark runner
- `benchmark_engine.py` – Shared calculation engine
- `benchmark_scenarios.json` – Test scenario definitions (customizable)
- `README.md` – Detailed benchmark documentation and custom formula guide

### Development Environment

#### Running in development mode

The app launches with auto-reload on file changes:

```python
ui.run(
    title="Performance Predictor",
    favicon=_FAVICON,
    port=7860,
    dark=True,
    reload=True,
)
```

If port 7860 is busy, change the `port` parameter in [perf_predictor.py](perf_predictor.py).

#### Modifying styles

All CSS styling is centralized in [app/styles.css](app/styles.css) for easy maintenance and organization.

#### Adding languages

Edit [app/languagepacks.json](app/languagepacks.json) to add or modify translations. The app supports 26 European languages.

### Troubleshooting

#### ModuleNotFoundError: No module named 'nicegui'

Ensure dependencies are installed in the active virtual environment:

```bash
pip install -r requirements.txt
```

On Windows, the app includes a virtualenv path bootstrap to support direct .py execution. If running from a different shell/IDE, ensure the venv is activated first.

#### PowerShell blocks script activation

Run once (current user):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then reactivate `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
```

#### Port already in use

Change the port in [perf_predictor.py](perf_predictor.py):

```python
ui.run(port=8000)  # Or another available port
```

#### Import errors from app modules

Verify the project structure is intact and your current working directory is the project root. The app uses relative imports assuming execution from the root folder.

#### Benchmark scenarios not found

Ensure you're running benchmark scripts from the project root:

```bash
python benchmark/benchmark_drafting.py
```

If running from `benchmark/` folder:

```bash
cd ..
python benchmark/benchmark_drafting.py
```

### Architecture Notes

- **Modular design**: Physics calculations isolated in `cycling_physics.py`; UI logic in `perf_predictor.py`
- **Internationalization**: Language packs loaded dynamically; new languages require only JSON additions
- **Drafting comparison**: Legacy model retained for historical comparison; production uses dynamic model
- **CSS organization**: Centralized styling prevents UI fragmentation
- **Benchmark isolation**: Benchmark system self-contained and independently runnable

---

## Additional Notes

- This tool is an **engineering approximation**, not a lab-grade physiological model.
- Real-world performance influenced by additional factors: fatigue, transient efforts, yaw angle, tire pressure, drivetrain specifics, road texture, gearing efficiency, etc.
- All model parameters (CRR, CdA, drivetrain loss) are configurable per scenario.
- The benchmark system supports adding custom formulas and calculations. See [benchmark/README.md](benchmark/README.md).

---

## License

See [LICENSE](LICENSE)


