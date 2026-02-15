# Cycling Performance Predictor

A Gradio-based cycling simulator that estimates either:

- **time/speed from power** (`Power → Time`), or
- **required power from target time** (`Time → Power`).

The model combines gravity, rolling resistance, aerodynamics, drivetrain losses, and optional drafting effects.

---

## Project Structure

- [perf_predictor.py](perf_predictor.py): Gradio UI, event wiring, and orchestration.
- [cycling_physics.py](cycling_physics.py): all physics equations, helper utilities, drafting logic, and HTML builders.
- [styles.css](styles.css): dark theme and component styling.
- [requirements.txt](requirements.txt): Python dependencies.

---

## Requirements

- Python **3.10+** recommended (3.8+ may work depending on dependency versions)
- pip

---

## Installation

### 1) Clone or open the folder

```bash
git clone <your-repo-url>
cd Cycling-Performance-Predictor
```

### 2) Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Run the app

```bash
python perf_predictor.py
```

Then open the local URL printed by Gradio (usually `http://localhost:7860`).

---

## Quick Usage

1. Pick mode:
   - `Power → Time`: input power, get predicted speed and time.
   - `Time → Power`: input target time, get required power.
2. Enter rider+bike mass:
   - `Body Weight (kg)`
   - `Bike / Gear Weight (kg)`
3. Enter route/environment:
   - `Gradient (%)`
   - `Distance (km)`
   - `Start Elevation (m)`
   - `Wind (km/h)` (headwind positive, tailwind negative)
4. Set resistance model:
   - bike type + terrain (prefills `Crr`)
   - `CdA`
5. Optional: enable drafting.
6. Click **Calculate Performance**.

---

## Physics Model (Detailed)

All internals use SI units.

### 1) Air density vs elevation

$$
\rho(h) = 1.225 \cdot e^{-h/8400}
$$

where $h$ is elevation in meters.

### 2) Forces

Let:

- $m$: total mass (rider + bike/gear), kg
- $g = 9.8066\ \text{m/s}^2$
- $s$: grade as decimal (`Gradient (%) / 100`)
- $C_{rr}$: rolling resistance coefficient
- $C_dA$: drag area (m²)
- $v$: ground speed (m/s)
- $w$: wind speed (m/s), positive = headwind

#### Gravity force

Grade is converted to angle via $\theta = \arctan(s)$:

$$
F_g = m g \sin(\arctan(s))
$$

#### Rolling resistance force

$$
F_r = m g \cos(\arctan(s)) C_{rr}
$$

#### Aerodynamic drag force

Relative air speed:

$$
v_r = v + w
$$

Drag:

$$
F_a = \frac{1}{2}\rho C_dA\, v_r\,|v_r|
$$

Using $v_r|v_r|$ preserves direction/sign behavior correctly.

### 3) Power model

With drivetrain loss fraction $L$ (default `0.035`):

$$
P = (F_g + F_r + F_a)\cdot \frac{v}{1-L}
$$

The app also returns component powers (`gravity`, `aero`, `rolling`) and their percentage split of positive-resistance power.

---

## Two Calculation Modes

### `Power → Time`

Given target power, the solver finds velocity using binary search (`cycling_power_velocity_search`) and computes:

$$
t = \frac{d}{v}
$$

where $d$ is distance in meters.

### `Time → Power`

Given target time, it computes target velocity directly:

$$
v = \frac{d}{t}
$$

Then evaluates the power equation at that velocity.

---

## Elevation Handling

The UI asks for **Start Elevation (m)**. The model uses **average route elevation** for air density, computed as:

$$
h_{avg} = h_{start} + \frac{\Delta h}{2},\quad \Delta h = d_{horiz}\cdot s
$$

where:

- $d_{horiz}$ is distance in meters,
- $s$ is decimal grade.

Implemented in `compute_avg_elevation()`.

---

## Drafting Model

When drafting is enabled, CdA is scaled by a reduction factor based on:

- number of riders,
- rider position,
- optional rotating paceline duty cycle.

Front rider has no reduction (factor = 1.0). Riders behind get lower effective drag (factor < 1.0). The app also estimates group power distribution and displays rider cards.

---

## Inputs and Units

- Power: watts (W)
- Target time: `MM:SS` or `H:MM:SS`
- Weights: kilograms (kg)
- Gradient: percent (%)
- Distance: kilometers (km)
- Start elevation: meters (m)
- Wind: km/h in UI, converted to m/s internally
- CdA: m²
- Crr: unitless

---

## Defaults / Presets

Common defaults in UI:

- CdA: `0.40`
- Crr (road asphalt): `0.0050`
- Body weight: `70 kg`
- Bike/gear weight: `8.0 kg`
- Distance: `10 km`
- Drivetrain loss: `3.5%` (in model)

Terrain presets are provided for both `road` and `mtb` in [cycling_physics.py](cycling_physics.py).

---

## Output Interpretation

- **Summary cards**: mode, speed/time, power/wkg, drafting status.
- **Predicted performance**: key outcome for selected mode.
- **Power details**:
  - gravity power (climbing load),
  - aerodynamic power,
  - rolling power,
  - each with W, W/kg, and percentage.
- **Drafting section** (when enabled): group power, variance, and rider visualization.

Warnings are shown for extreme combinations (e.g., very low speed on steep gradients, very high W/kg demands).

---

## Running in Development

The app launches with:

```python
app.launch(server_name="localhost", server_port=7860, share=False, quiet=False)
```

If port 7860 is busy, change `server_port` in [perf_predictor.py](perf_predictor.py).

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'gradio'`

Install dependencies in the active environment:

```bash
pip install -r requirements.txt
```

### PowerShell blocks script activation

Run once (current user):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then reactivate `.venv`.

### Gradio output mismatch error

If you modify UI outputs, ensure the return tuple length in `calculate_performance()` and `_error()` exactly matches `_outputs`.

---

## Notes

- This tool is an engineering approximation, not a lab-grade physiological model.
- Real-world performance is influenced by additional factors (fatigue, transient efforts, yaw angle, tire pressure, drivetrain specifics, road texture variability, etc.).

---

## License

See [LICENSE](LICENSE).
