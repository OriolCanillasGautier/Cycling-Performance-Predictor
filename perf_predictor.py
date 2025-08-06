#!/usr/bin/env python3
"""
Cycling Performance Predictor
Exact replica of Sauce4Strava's performance predictor with reverse calculation mode
"""

import gradio as gr
import math
from typing import Dict, List, Tuple, Optional, NamedTuple

class PowerEstimate(NamedTuple):
    """Result of power estimation calculations"""
    g_force: float
    r_force: float
    a_force: float
    force: float
    g_watts: float
    r_watts: float
    a_watts: float
    watts: float
    velocity: float

class CyclingPhysics:
    """Cycling physics calculations based on Sauce4Strava implementation"""
    
    @staticmethod
    def air_density(elevation: float) -> float:
        """Calculate air density based on elevation (m)"""
        return 1.225 * math.exp(-elevation / 8400)
    
    @staticmethod
    def gravity_force(slope: float, weight: float) -> float:
        """Calculate gravitational force component (N)"""
        return weight * 9.8066 * slope
    
    @staticmethod
    def rolling_resistance_force(slope: float, weight: float, crr: float) -> float:
        """Calculate rolling resistance force (N)"""
        return weight * 9.8066 * math.cos(math.atan(slope)) * crr
    
    @staticmethod
    def aero_drag_force(cda: float, air_density: float, velocity: float, wind: float = 0) -> float:
        """Calculate aerodynamic drag force (N)"""
        relative_velocity = velocity + wind
        return 0.5 * air_density * cda * relative_velocity * abs(relative_velocity)
    
    @staticmethod
    def cycling_power_estimate(velocity: float, slope: float, weight: float, 
                             crr: float, cda: float, elevation: float = 0, 
                             wind: float = 0, loss: float = 0.035) -> PowerEstimate:
        """Estimate power required for given velocity and conditions"""
        invert = -1 if velocity < 0 else 1
        
        fg = CyclingPhysics.gravity_force(slope, weight)
        fr = CyclingPhysics.rolling_resistance_force(slope, weight, crr) * invert
        fa = CyclingPhysics.aero_drag_force(cda, CyclingPhysics.air_density(elevation), velocity, wind)
        
        v_factor = velocity / (1 - loss)
        
        return PowerEstimate(
            g_force=fg,
            r_force=fr,
            a_force=fa,
            force=fg + fr + fa,
            g_watts=fg * v_factor * invert,
            r_watts=fr * v_factor * invert,
            a_watts=fa * v_factor * invert,
            watts=(fg + fr + fa) * v_factor * invert,
            velocity=velocity
        )
    
    @staticmethod
    def cycling_power_velocity_search(power: float, slope: float, weight: float,
                                    crr: float, cda: float, elevation: float = 0,
                                    wind: float = 0, loss: float = 0.035) -> Optional[PowerEstimate]:
        """Find the fastest positive velocity for the target power"""
        best_estimate = None
        best_diff = float('inf')
        
        # Search range -50 to +50 m/s with 0.01 m/s precision
        for v in range(-5000, 5001, 1):
            velocity = v / 100.0
            
            if velocity <= 0:
                continue
                
            estimate = CyclingPhysics.cycling_power_estimate(
                velocity, slope, weight, crr, cda, elevation, wind, loss
            )
            
            diff = abs(estimate.watts - power)
            if diff < best_diff:
                best_diff = diff
                best_estimate = estimate
            
            # Early exit if we found a very close match
            if diff < 0.1:
                break
        
        # Always return the best estimate we found (no tolerance check)
        return best_estimate
    
    @staticmethod
    def cycling_time_power_search(target_time: float, distance: float, slope: float, weight: float,
                                crr: float, cda: float, elevation: float = 0,
                                wind: float = 0, loss: float = 0.035) -> Optional[PowerEstimate]:
        """Find the power required for the target time over given distance"""
        target_velocity = distance / target_time  # m/s
        
        # First try: Direct calculation estimate
        air_density = 1.225 * math.exp(-elevation / 8400)
        fg = weight * 9.8066 * slope
        fr = weight * 9.8066 * math.cos(math.atan(slope)) * crr
        fa = 0.5 * air_density * cda * target_velocity * abs(target_velocity)
        
        estimated_power = (fg + fr + fa) * target_velocity / (1 - loss)
        
        # Test if this estimate works
        test_result = CyclingPhysics.cycling_power_velocity_search(
            estimated_power, slope, weight, crr, cda, elevation, wind, loss
        )
        
        if test_result and abs(test_result.velocity - target_velocity) < target_velocity * 0.1:
            return test_result
        
        # If direct estimate doesn't work, try powers around it
        for power_multiplier in [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.5, 3.0]:
            test_power = estimated_power * power_multiplier
            if test_power < 10 or test_power > 3000:
                continue
                
            result = CyclingPhysics.cycling_power_velocity_search(
                test_power, slope, weight, crr, cda, elevation, wind, loss
            )
            
            if result and abs(result.velocity - target_velocity) < target_velocity * 0.15:
                return result
        
        # Last resort: Try a range of fixed powers
        for test_power in [50, 75, 100, 150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 1000]:
            result = CyclingPhysics.cycling_power_velocity_search(
                test_power, slope, weight, crr, cda, elevation, wind, loss
            )
            
            if result and abs(result.velocity - target_velocity) < target_velocity * 0.2:
                return result
        
        # If nothing works, create a manual estimate
        return CyclingPhysics.cycling_power_estimate(
            target_velocity, slope, weight, crr, cda, elevation, wind, loss
        )

def cycling_draft_drag_reduction(riders: int, position: int) -> float:
    """Calculate drag reduction factor for drafting - FIXED"""
    if riders < 2 or position < 1 or position > riders:
        return 1.0
    
    # Improved coefficients based on research - more realistic values
    coefficients = {
        2: {"base": 0.70, "decay": 0.85},
        3: {"base": 0.65, "decay": 0.80},
        4: {"base": 0.62, "decay": 0.78},
        5: {"base": 0.60, "decay": 0.76},
        6: {"base": 0.58, "decay": 0.74},
        7: {"base": 0.56, "decay": 0.72},
        8: {"base": 0.55, "decay": 0.70},
    }
    
    if riders > 8:
        # Scale position proportionally for larger groups
        scaled_position = max(1, min(8, int(8 * position / riders)))
        riders = 8
        position = scaled_position
    
    c = coefficients[riders]
    if position == 1:
        return 1.0  # No draft benefit at front
    else:
        # More realistic progressive benefit calculation
        # Position 2 gets most benefit, further back gets progressively less
        max_benefit = c["base"]
        position_factor = (position - 1) / (riders - 1)  # 0 to 1 scale
        draft_reduction = max_benefit + (1 - max_benefit) * (position_factor * c["decay"])
        return min(1.0, draft_reduction)

TERRAIN_CRR = {
    "road": {
        "asphalt": 0.0050,
        "gravel": 0.0060, 
        "grass": 0.0070,
        "offroad": 0.0200,
        "sand": 0.0300
    },
    "mtb": {
        "asphalt": 0.0065,
        "gravel": 0.0075,
        "grass": 0.0090,
        "offroad": 0.0255,
        "sand": 0.0380
    }
}

def get_cda_position(cda):
    """Get riding position description based on CdA"""
    if cda < 0.23:
        return "Elite time trial equipment and positioning"
    elif cda < 0.30:
        return "Good time trial equipment and positioning / Triathlon"
    elif cda < 0.35:
        return "Road bike racing positions / Drop bar lows"
    elif cda < 0.50:
        return "Road bike climbing positions / Mountain bike XC"
    else:
        return "Upright position with casual clothing"

def format_time(seconds):
    """Format time in seconds to MM:SS or H:MM:SS"""
    if seconds <= 0:
        return "Invalid"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"

def parse_time_input(time_str):
    """Parse time input (MM:SS or H:MM:SS) to seconds - FIXED"""
    if not time_str or time_str.strip() == "":
        return None
    
    try:
        time_parts = time_str.strip().split(':')
        
        if len(time_parts) == 2:
            # Format MM:SS (minutes can be > 59)
            minutes = int(time_parts[0])
            seconds = int(time_parts[1])
            
            # Validate seconds
            if seconds < 0 or seconds >= 60:
                return None
                
            return minutes * 60 + seconds
            
        elif len(time_parts) == 3:
            # Format H:MM:SS
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            seconds = int(time_parts[2])
            
            # Validate minutes and seconds
            if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
                return None
                
            return hours * 3600 + minutes * 60 + seconds
        else:
            return None
            
    except ValueError:
        # Handle non-numeric input
        return None
    except Exception:
        return None

def calculate_cyclist_powers(riders, position, rotating, work_pct, power, cda, draft_reduction_func):
    """Calculate individual cyclist powers for drafting visualization - INSTANT SNAPSHOT"""
    cyclist_data = []
    
    if rotating:
        # Rotating paceline - show CURRENT instant snapshot, not averages
        front_time = work_pct / 100.0
        
        # Calculate the power needed at front (no draft) and at back (with draft)
        back_draft_reduction = draft_reduction_func(riders, riders)  # Maximum draft benefit
        
        # Back-calculate what the front/back powers are from your average power
        front_power = power / (front_time + (1 - front_time) * back_draft_reduction)
        back_power = front_power * back_draft_reduction
        
        # Show a snapshot: currently position 1 is at front, others draft
        for i in range(1, riders + 1):
            if i == 1:
                # Currently at front - high power, no draft
                current_power = front_power
                is_front = True
            else:
                # Currently drafting - low power, with draft benefit
                draft_factor = draft_reduction_func(riders, i)
                current_power = front_power * draft_factor
                is_front = False
            
            # Only show time percentage for YOUR position (not current front rider)
            show_time_pct = work_pct if i == position else 0
            
            cyclist_data.append({
                "position": i,
                "power": int(current_power),
                "time_pct": show_time_pct,  # Only YOUR position shows time %
                "is_you": i == position
            })
    else:
        # Static positions - calculate actual power needed for each position
        # The "power" parameter is what YOU are putting out
        # Others need different power based on their draft position
        your_draft_factor = draft_reduction_func(riders, position)
        base_power_needed = power / your_draft_factor  # Power needed without any draft
        
        for i in range(1, riders + 1):
            draft_factor = draft_reduction_func(riders, i)
            # Power this position needs = base power * their draft factor
            estimated_power = base_power_needed * draft_factor
            cyclist_data.append({
                "position": i,
                "power": int(estimated_power),
                "time_pct": 0,
                "is_you": i == position
            })
    
    return cyclist_data

def create_cyclist_visualization(cyclist_data):
    """Create HTML visualization of cyclists with their power values - IMPROVED ICONS"""
    if not cyclist_data:
        return ""
    
    html = '''
    <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; padding: 15px; 
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); 
                border-radius: 12px; border: 1px solid #dee2e6;">
    '''
    
    for cyclist in cyclist_data:
        you_indicator = " (You)" if cyclist["is_you"] else ""
        time_info = f"<div style='font-size: 10px; color: #666; margin-top: 2px;'>{cyclist['time_pct']:.0f}% front</div>" if cyclist["time_pct"] > 0 else ""
        
        # Better cyclist emoji and styling
        rider_emoji = "🚴‍♂️" if cyclist["position"] % 2 == 1 else "🚴‍♀️"
        border_color = "#007acc" if cyclist["is_you"] else "#6c757d"
        background_color = "#e3f2fd" if cyclist["is_you"] else "#ffffff"
        
        html += f'''
        <div style="text-align: center; padding: 8px; 
                    border: 2px solid {border_color}; 
                    border-radius: 10px; 
                    background: {background_color}; 
                    min-width: 70px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size: 28px; margin-bottom: 4px;">{rider_emoji}</div>
            <div style="font-size: 11px; font-weight: bold; color: #333;">
                Pos. {cyclist["position"]}{you_indicator}
            </div>
            <div style="font-size: 13px; color: #000; font-weight: 600; margin-top: 2px;">
                {cyclist["power"]}w
            </div>
            {time_info}
        </div>
        '''
    
    html += '</div>'
    return html

def calculate_performance(
    # Calculation mode
    calc_mode,
    # Original performance inputs (user-editable)
    orig_power, orig_time_input, orig_speed_input,
    # Prediction inputs
    power, target_time_input, body_weight, gear_weight, slope, distance, elevation, wind,
    cda, crr, drafting, riders, position, rotating, work_pct, bike_type, terrain
):
    """Main calculation function with reverse calculation support"""
    try:
        if body_weight <= 0 or gear_weight < 0 or distance <= 0:
            return create_error_output()
        
        # Convert units
        total_weight = body_weight + gear_weight
        slope_decimal = slope / 100.0
        distance_m = distance * 1000
        wind_ms = wind / 3.6
        
        # Apply drafting
        effective_cda = cda
        group_power = 0
        power_variance = 0
        draft_info = ""
        cyclist_viz = ""
        
        if drafting and riders >= 2:
            if rotating:
                # Rotating paceline - corrected calculation
                front_time = work_pct / 100.0
                # Average draft reduction over time
                back_draft_reduction = cycling_draft_drag_reduction(riders, riders)
                avg_draft_reduction = front_time * 1.0 + (1 - front_time) * back_draft_reduction
                effective_cda = cda * avg_draft_reduction
                draft_info = f"Rotating: {work_pct:.0f}% time at front"
                
                # Calculate power variance (difference between front and back)
                front_power_factor = 1.0
                back_power_factor = back_draft_reduction
                power_variance = abs(1/back_power_factor - 1/front_power_factor) / (1/back_power_factor) * 100
                
            else:
                # Static position
                draft_reduction = cycling_draft_drag_reduction(riders, position)
                effective_cda = cda * draft_reduction
                draft_info = f"Position {position}/{riders} (draft: {(1-draft_reduction)*100:.0f}%)"
                
                # Calculate power variance for static positions (front vs back)
                front_draft_factor = cycling_draft_drag_reduction(riders, 1)  # Position 1 (front)
                back_draft_factor = cycling_draft_drag_reduction(riders, riders)  # Last position
                if front_draft_factor > 0 and back_draft_factor > 0:
                    power_variance = abs((1/back_draft_factor) - (1/front_draft_factor)) / (1/back_draft_factor) * 100
        
        # Calculate based on mode
        if calc_mode == "Power → Time":
            if power <= 0:
                return create_error_output("Power must be greater than 0")
                
            # Calculate predicted performance (time from power)
            predicted_estimate = CyclingPhysics.cycling_power_velocity_search(
                power, slope_decimal, total_weight, crr, effective_cda, elevation, wind_ms
            )
            
            if predicted_estimate and predicted_estimate.velocity > 0:
                pred_time_seconds = distance_m / predicted_estimate.velocity
                pred_speed_kmh = predicted_estimate.velocity * 3.6
                pred_power = power
                calc_power = power
                
                # Create cyclist visualization for drafting
                if drafting and riders >= 2:
                    cyclist_data = calculate_cyclist_powers(riders, position, rotating, work_pct, power, cda, cycling_draft_drag_reduction)
                    cyclist_viz = create_cyclist_visualization(cyclist_data)
                    if cyclist_data:
                        group_power = sum(c["power"] for c in cyclist_data) / len(cyclist_data)
            else:
                return create_error_output("No valid solution found for these parameters")
                
        else:  # Time → Power
            target_time_seconds = parse_time_input(target_time_input)
            if not target_time_seconds or target_time_seconds <= 0:
                return create_error_output("Please enter a valid target time (MM:SS or H:MM:SS)")
            
            # Calculate required power for target time
            predicted_estimate = CyclingPhysics.cycling_time_power_search(
                target_time_seconds, distance_m, slope_decimal, total_weight, crr, effective_cda, elevation, wind_ms
            )
            
            if predicted_estimate and predicted_estimate.velocity > 0:
                pred_time_seconds = target_time_seconds
                pred_speed_kmh = predicted_estimate.velocity * 3.6
                pred_power = predicted_estimate.watts
                calc_power = pred_power
                
                # Create cyclist visualization for drafting
                if drafting and riders >= 2:
                    cyclist_data = calculate_cyclist_powers(riders, position, rotating, work_pct, calc_power, cda, cycling_draft_drag_reduction)
                    cyclist_viz = create_cyclist_visualization(cyclist_data)
                    if cyclist_data:
                        group_power = sum(c["power"] for c in cyclist_data) / len(cyclist_data)
            else:
                return create_error_output("No valid solution found for this target time")
        
        pred_wkg = calc_power / total_weight
        
        # Check for unrealistic values and add warnings
        speed_warning = ""
        power_warning = ""
        
        # Speed warnings with error percentages
        if pred_speed_kmh < 5.0:  # Less than 5 km/h is walking pace
            walking_speed = 5.0
            error_pct = abs(pred_speed_kmh - walking_speed) / walking_speed * 100
            speed_warning = f" ⚠️ Walking pace - check parameters ({error_pct:.0f}% below 5 km/h)"
        elif pred_speed_kmh < 8.0 and slope > 20:  # Very steep and very slow
            reasonable_speed = 8.0
            error_pct = abs(pred_speed_kmh - reasonable_speed) / reasonable_speed * 100
            speed_warning = f" ⚠️ Extremely steep - consider walking ({error_pct:.0f}% below 8 km/h)"
        elif pred_speed_kmh < 10.0 and slope > 15:  # Steep and slow
            reasonable_speed = 10.0
            error_pct = abs(pred_speed_kmh - reasonable_speed) / reasonable_speed * 100
            speed_warning = f" ⚠️ Very steep gradient ({error_pct:.0f}% below 10 km/h)"
        
        # Power warnings with w/kg thresholds
        if pred_wkg > 8.0:  # More than 8 w/kg is elite level
            elite_threshold = 8.0
            error_pct = (pred_wkg - elite_threshold) / elite_threshold * 100
            power_warning = f" ⚠️ Elite power level! ({error_pct:.0f}% above 8 w/kg)"
        elif pred_wkg > 6.0:  # More than 6 w/kg is very high
            high_threshold = 6.0
            error_pct = (pred_wkg - high_threshold) / high_threshold * 100
            power_warning = f" ⚠️ Very high power required ({error_pct:.0f}% above 6 w/kg)"
        
        # Original performance (user inputs or defaults)
        orig_time_formatted = orig_time_input if orig_time_input else format_time(pred_time_seconds)
        orig_speed_formatted = f"{orig_speed_input:.1f}" if orig_speed_input is not None else f"{pred_speed_kmh:.1f}"
        orig_wkg_formatted = f"{orig_power / total_weight:.1f}" if orig_power and orig_power > 0 else f"{pred_wkg:.1f}"
        
        # Time difference calculation
        time_diff_str = ""
        if orig_time_input:
            orig_time_seconds = parse_time_input(orig_time_input)
            if orig_time_seconds:
                time_diff = pred_time_seconds - orig_time_seconds
                if abs(time_diff) > 1:
                    if time_diff > 0:
                        time_diff_str = f" (+{format_time(abs(time_diff))})"
                    else:
                        time_diff_str = f" (-{format_time(abs(time_diff))})"
        
        # Power breakdown - fixed calculation
        gravity_watts = predicted_estimate.g_watts
        aero_watts = predicted_estimate.a_watts  
        rolling_watts = predicted_estimate.r_watts
        
        # Calculate percentages based on power components that require energy
        positive_components = []
        if gravity_watts > 0:  # Climbing
            positive_components.append(gravity_watts)
        if aero_watts > 0:  # Always positive (drag)
            positive_components.append(aero_watts)
        if rolling_watts > 0:  # Always positive (resistance)
            positive_components.append(rolling_watts)
        
        total_positive_power = sum(positive_components)
        
        if total_positive_power > 0:
            gravity_pct = (gravity_watts / total_positive_power * 100) if gravity_watts > 0 else 0
            aero_pct = aero_watts / total_positive_power * 100
            rolling_pct = rolling_watts / total_positive_power * 100
        else:
            gravity_pct = aero_pct = rolling_pct = 0
        
        return create_success_output(
            orig_time=orig_time_formatted,
            orig_speed=orig_speed_formatted,
            orig_wkg=orig_wkg_formatted,
            pred_time=format_time(pred_time_seconds),
            pred_speed=f"{pred_speed_kmh:.1f}{speed_warning}", 
            pred_power=f"{calc_power:.0f}{power_warning}",
            pred_wkg=f"{pred_wkg:.1f}",
            time_diff=time_diff_str,
            gravity_watts=f"{gravity_watts:.0f}",
            gravity_wkg=f"{gravity_watts / total_weight:.1f}",
            gravity_pct=f"{gravity_pct:.0f}",
            aero_watts=f"{aero_watts:.0f}",
            aero_wkg=f"{aero_watts / total_weight:.1f}",
            aero_pct=f"{aero_pct:.0f}",
            rolling_watts=f"{rolling_watts:.0f}",
            rolling_wkg=f"{rolling_watts / total_weight:.1f}",
            rolling_pct=f"{rolling_pct:.0f}",
            position_desc=get_cda_position(cda),
            group_power=f"{group_power:.0f}" if drafting and group_power > 0 else "",
            power_variance=f"{power_variance:.0f}" if drafting and power_variance > 0 else "",
            draft_info=draft_info,
            cyclist_viz=cyclist_viz,
            show_drafting=drafting,
            calc_mode=calc_mode,
            status="valid"
        )
            
    except Exception as e:
        return create_error_output(f"Error: {str(e)}")

def create_success_output(**kwargs):
    """Create successful calculation output"""
    return (
        kwargs["status"],
        kwargs["orig_time"], kwargs["orig_speed"], kwargs["orig_wkg"],
        kwargs["pred_time"], kwargs["pred_speed"], kwargs["pred_power"], kwargs["pred_wkg"], kwargs["time_diff"],
        f"{kwargs['gravity_watts']}w\n{kwargs['gravity_wkg']}w/kg ({kwargs['gravity_pct']}%)",
        f"{kwargs['aero_watts']}w\n{kwargs['aero_wkg']}w/kg ({kwargs['aero_pct']}%)", 
        f"{kwargs['rolling_watts']}w\n{kwargs['rolling_wkg']}w/kg ({kwargs['rolling_pct']}%)",
        kwargs["position_desc"],
        kwargs["group_power"] + "w" if kwargs["group_power"] else "",
        kwargs["power_variance"] + "%" if kwargs["power_variance"] else "",
        kwargs["draft_info"],
        kwargs["cyclist_viz"],
        gr.update(visible=kwargs["show_drafting"])
    )

def create_error_output(message="No velocity predicted for these parameters"):
    """Create error output"""
    return (
        "invalid", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", 
        gr.update(visible=False)
    )

# Create the Gradio interface
with gr.Blocks(title="Performance Predictor") as app:
    
    gr.HTML("""
    <style>
    .performance-predictor {
        max-width: 1200px;
        margin: 0 auto;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .heading {
        font-size: 1.2em;
        font-weight: bold;
        color: #333;
        margin: 20px 0 10px 0;
        border-bottom: 2px solid #007acc;
        padding-bottom: 5px;
    }
    .calculate-btn {
        background: #007acc !important;
        color: white !important;
        font-weight: bold !important;
        font-size: 1.1em !important;
        padding: 15px 30px !important;
        border-radius: 8px !important;
        margin: 20px 0 !important;
    }
    .mode-selector {
        background: #f8f9fa !important;
        border: 2px solid #007acc !important;
        border-radius: 8px !important;
        font-weight: bold !important;
    }
    </style>
    
    <div class="performance-predictor">
        <h1>Performance Predictor</h1>
        <p><em>The Performance Predictor is a cycling power calculator that lets you examine the impact of altered performance factors.</em></p>
        <p><strong>Choose calculation mode and change parameters to see the estimated effect on performance.</strong></p>
    </div>
    """)
    
    # Calculation mode selector
    calc_mode = gr.Radio(
        choices=["Power → Time", "Time → Power"],
        value="Power → Time",
        label="Calculation Mode",
        elem_classes="mode-selector"
    )
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.HTML('<div class="heading">Original Performance (editable):</div>')
            
            orig_power = gr.Number(value=250, label="Original Power (w)", minimum=0)
            orig_time_input = gr.Textbox(value="", label="Original Time (MM:SS or H:MM:SS)", placeholder="Ex: 15:30 or 1:15:30")
            orig_speed_input = gr.Number(value=None, label="Original Speed (km/h)", minimum=0)
            
            gr.HTML('<div class="heading">Rolling Resistance:</div>')
            
            bike_type = gr.Radio(
                choices=["road", "mtb"],
                value="road",
                label="Bike"
            )
            
            terrain = gr.Dropdown(
                choices=["asphalt", "gravel", "grass", "offroad", "sand"],
                value="asphalt",
                label="Crr / Terrain"
            )
            
            crr = gr.Number(
                value=0.0050,
                label="Crr",
                step=0.0005,
                minimum=0.001
            )
            
            gr.HTML('<div class="heading">Aerodynamic Resistance:</div>')
            
            cda = gr.Slider(
                minimum=0.15,
                maximum=0.7,
                step=0.01,
                value=0.40,
                label="CdA (m²)"
            )
            
            position_info = gr.Textbox(
                value=get_cda_position(0.40),
                label="Aerodynamic Position",
                interactive=False
            )
            
            gr.HTML('<div class="heading">Drafting:</div>')
            
            drafting = gr.Checkbox(label="Drafting", value=False)
            
            riders = gr.Slider(
                minimum=2, maximum=8, step=1, value=2,
                label="Riders"
            )
            
            rotating = gr.Checkbox(label="Rotating / Paceline", value=False)
            
            work_pct = gr.Slider(
                minimum=0, maximum=100, step=1, value=50,
                label="Time at Front (%)",
                visible=False
            )
            
            position = gr.Slider(
                minimum=1, maximum=8, step=1, value=2,
                label="Position"
            )
        
        with gr.Column(scale=1):
            # Mode-dependent inputs
            power = gr.Number(value=250, label="Power (w)", minimum=50, visible=True)
            target_time_input = gr.Textbox(value="", label="Target Time (MM:SS or H:MM:SS)", 
                                         placeholder="Ex: 15:30 or 1:15:30", visible=False)
            
            body_weight = gr.Number(value=70, label="Body Weight (kg)", minimum=30)
            gear_weight = gr.Number(value=13.0, label="Bike/Gear Weight (kg)", minimum=5)
            slope = gr.Number(value=0, label="Gradient (%)", step=0.1)
            distance = gr.Number(value=10, label="Distance (km)", minimum=0.1)
            elevation = gr.Number(value=0, label="Elevation (m)", step=50)
            wind = gr.Number(value=0, label="Wind (km/h)", step=1)
            
            # Calculate button
            calculate_btn = gr.Button("🔄 Calculate Performance", variant="primary", elem_classes="calculate-btn")
    
    # Results section
    gr.HTML('<div style="margin: 25px 0;"></div>')
    
    with gr.Row():
        with gr.Column():
            gr.HTML('<div class="heading">Original Performance:</div>')
            orig_time = gr.Textbox(label="Time", interactive=False)
            orig_speed = gr.Textbox(label="Speed (km/h)", interactive=False)
            orig_wkg = gr.Textbox(label="Watts/kg", interactive=False)
            
        with gr.Column():
            gr.HTML('<div class="heading">Predicted Performance:</div>')
            pred_time = gr.Textbox(label="Time", interactive=False)
            pred_speed = gr.Textbox(label="Speed (km/h)", interactive=False)
            pred_power = gr.Textbox(label="Power (w)", interactive=False)
            pred_wkg = gr.Textbox(label="Watts/kg", interactive=False)
            time_diff = gr.Textbox(label="Difference", interactive=False)
    
    gr.HTML('<div class="heading">Power Details:</div>')
    
    with gr.Row():
        gravity_power = gr.Textbox(label="Gravity", interactive=False, lines=2)
        aero_power = gr.Textbox(label="Aerodynamics", interactive=False, lines=2)
        rolling_power = gr.Textbox(label="Rolling", interactive=False, lines=2)
    
    # Drafting section
    with gr.Group() as drafting_section:
        gr.HTML('<div class="heading">Drafting:</div>')
        group_power = gr.Textbox(label="Group Power", interactive=False)
        power_variance = gr.Textbox(label="Power Variance", interactive=False)
        draft_info_display = gr.Textbox(label="Info", interactive=False)
        cyclist_visualization = gr.HTML(label="Cyclists")
    
    status = gr.Textbox(label="Status", visible=False)
    
    # Event handlers
    def update_input_visibility(mode):
        if mode == "Power → Time":
            return gr.Number(visible=True), gr.Textbox(visible=False)
        else:  # Time → Power
            return gr.Number(visible=False), gr.Textbox(visible=True)
    
    def update_terrain_options(bike_type_val):
        choices = list(TERRAIN_CRR[bike_type_val].keys())
        return gr.Dropdown(choices=choices, value=choices[0])
    
    def update_crr_value(bike_type_val, terrain_val):
        if terrain_val in TERRAIN_CRR[bike_type_val]:
            return TERRAIN_CRR[bike_type_val][terrain_val]
        return 0.0050
    
    def update_position_description(cda_val):
        return get_cda_position(cda_val)
    
    def update_position_max(riders_val):
        return gr.Slider(minimum=1, maximum=riders_val, step=1, value=min(2, riders_val))
    
    def update_rotating_visibility(rotating_val):
        return gr.Slider(visible=rotating_val)
    
    # Bind events
    calc_mode.change(update_input_visibility, inputs=[calc_mode], outputs=[power, target_time_input])
    bike_type.change(update_terrain_options, inputs=[bike_type], outputs=[terrain])
    bike_type.change(update_crr_value, inputs=[bike_type, terrain], outputs=[crr])
    terrain.change(update_crr_value, inputs=[bike_type, terrain], outputs=[crr])
    cda.change(update_position_description, inputs=[cda], outputs=[position_info])
    riders.change(update_position_max, inputs=[riders], outputs=[position])
    rotating.change(update_rotating_visibility, inputs=[rotating], outputs=[work_pct])
    
    # Main calculation with button
    inputs = [
        calc_mode,  # New calculation mode
        orig_power, orig_time_input, orig_speed_input,  # Original performance inputs
        power, target_time_input, body_weight, gear_weight, slope, distance, elevation, wind,
        cda, crr, drafting, riders, position, rotating, work_pct, bike_type, terrain
    ]
    
    outputs = [status, orig_time, orig_speed, orig_wkg, pred_time, pred_speed, pred_power, pred_wkg, 
               time_diff, gravity_power, aero_power, rolling_power, position_info, 
               group_power, power_variance, draft_info_display, cyclist_visualization, drafting_section]
    
    # Calculate button click event
    calculate_btn.click(calculate_performance, inputs=inputs, outputs=outputs)
    
    # Initial calculation
    app.load(calculate_performance, inputs=inputs, outputs=outputs)

if __name__ == "__main__":
    app.launch(
        server_name="localhost",
        server_port=7860,
        share=False,
        quiet=False
    )