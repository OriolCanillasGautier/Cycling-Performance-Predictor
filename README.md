# Cycling Performance Predictor

A standalone Python application based on the Sauce4Strava performance predictor that calculates cycling performance metrics using advanced physics models.

## Features

- **Power-based velocity prediction**: Calculate speed and time for a given power output
- **Comprehensive physics model**: Includes gravity, rolling resistance, and aerodynamic forces
- **Drafting calculations**: Simulates performance benefits of riding in groups
- **Bike configuration**: Support for different bike types (road/MTB) and terrain surfaces
- **Aerodynamic positioning**: CdA values for different riding positions (TT, road, climbing, upright)
- **Environmental factors**: Accounts for elevation, wind, and slope

## Installation

1. **Install Python** (3.8 or higher)
   - Download from [python.org](https://www.python.org/downloads/)
   - Make sure to check "Add Python to PATH" during installation

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python perf_predictor.py
   ```

## Usage

### Basic Configuration

1. **Bike Configuration**:
   - Select bike type (Road or MTB)
   - Choose terrain (asphalt, gravel, grass, offroad, sand)
   - Adjust Crr (coefficient of rolling resistance) if needed

2. **Aerodynamics**:
   - Set CdA (drag coefficient × frontal area) using the slider or direct input
   - The position indicator shows your riding position based on CdA value

3. **Parameters**:
   - **Power**: Target power output in watts
   - **Body Weight**: Your weight in kg
   - **Gear Weight**: Bike + equipment weight in kg
   - **Slope**: Grade percentage (positive for uphill, negative for downhill)
   - **Distance**: Distance for time calculation in km
   - **Elevation**: Altitude in meters (affects air density)
   - **Wind**: Wind speed in km/h (positive for headwind)

### Drafting

Enable drafting to simulate riding in a group:
- **Riders**: Number of riders in the group (2-8)
- **Position**: Your position in the group (1 = front, higher = more draft benefit)

### Understanding Results

The application displays:
- **Time**: Predicted time to complete the distance
- **Speed**: Average speed in km/h
- **Power/Weight**: Power-to-weight ratio in W/kg
- **Power Breakdown**: How power is distributed between:
  - Gravity (climbing/descending)
  - Aerodynamic drag
  - Rolling resistance

## Physics Model

The calculations are based on the fundamental equation:
```
Power = (Gravity Force + Rolling Resistance + Aerodynamic Drag) × Velocity / (1 - Drivetrain Loss)
```

### Force Components

1. **Gravity Force**: `F_g = m × g × sin(slope)`
2. **Rolling Resistance**: `F_r = m × g × cos(slope) × Crr`
3. **Aerodynamic Drag**: `F_a = 0.5 × ρ × CdA × (v + wind)²`

Where:
- `m` = total mass (body + bike)
- `g` = gravitational acceleration (9.8066 m/s²)
- `ρ` = air density (altitude dependent)
- `v` = velocity

### Drafting Model

Drafting calculations use research-based coefficients from van Druenen & Blocken (2021) to determine CdA reduction based on group size and position.

## Default Values

- **CdA**: 0.40 m² (typical road position)
- **Crr**: 0.005 (road bike on asphalt)
- **Gear Weight**: 13 kg
- **Drivetrain Loss**: 3.5%

## Tips

- **CdA Values**:
  - 0.17-0.23: Elite time trial position
  - 0.23-0.30: Good time trial position
  - 0.30-0.35: Road racing position
  - 0.35-0.50: Climbing position
  - 0.50+: Upright position

- **Crr Values** vary by bike type and terrain:
  - Road bike on asphalt: 0.005
  - Mountain bike on asphalt: 0.0065
  - Gravel/dirt surfaces: 0.006-0.025
  - Sand: 0.030-0.038

## Technical Notes

- The velocity search algorithm finds solutions within 0.1W or 0.1% accuracy
- Air density calculation uses standard atmosphere model
- Settings are automatically saved to `perf_predictor_settings.json`
- All calculations use SI units internally with unit conversion for display

## Based on Sauce4Strava

This application reimplements the performance predictor from the Sauce4Strava browser extension, maintaining the same physics calculations and accuracy while providing a standalone desktop experience.
