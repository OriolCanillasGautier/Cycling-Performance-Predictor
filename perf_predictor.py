#!/usr/bin/env python3
"""
Cycling Performance Predictor
Exact replica of Sauce4Strava's performance predictor
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
            
            estimate = CyclingPhysics.cycling_power_estimate(
                velocity, slope, weight, crr, cda, elevation, wind, loss
            )
            
            diff = abs(estimate.watts - power)
            if diff < best_diff and velocity > 0:
                best_diff = diff
                best_estimate = estimate
            
            # Early exit if we found a very close match
            if diff < 0.1:
                break
        
        return best_estimate if best_diff < max(5.0, abs(power * 0.02)) else None

def cycling_draft_drag_reduction(riders: int, position: int) -> float:
    """Calculate drag reduction factor for drafting"""
    if riders < 2 or position < 1 or position > riders:
        return 1.0
    
    # Coefficients based on van Druenen & Blocken research
    coefficients = {
        2: {"base": 0.65, "decay": 0.8},
        3: {"base": 0.60, "decay": 0.75},
        4: {"base": 0.55, "decay": 0.70},
        5: {"base": 0.52, "decay": 0.68},
        6: {"base": 0.50, "decay": 0.65},
        7: {"base": 0.48, "decay": 0.63},
        8: {"base": 0.46, "decay": 0.62},
    }
    
    if riders > 8:
        position = max(1, int(8 / riders * position))
        riders = 8
    
    c = coefficients[riders]
    if position == 1:
        return 1.0  # No draft benefit at front
    else:
        # Progressive benefit based on position
        position_factor = (riders - position) / (riders - 1)
        return c["base"] + (1 - c["base"]) * (1 - c["decay"]) * position_factor

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

def calculate_cyclist_powers(riders, position, rotating, work_pct, power, cda, draft_reduction_func):
    """Calculate individual cyclist powers for drafting visualization"""
    cyclist_data = []
    
    if rotating:
        # Rotating paceline
        front_time = work_pct / 100.0
        for i in range(1, riders + 1):
            if i == position:
                avg_power = power
                time_at_front = front_time
            else:
                avg_power = power * 0.98  # Slight variation for other riders
                time_at_front = (1 - front_time) / (riders - 1) if riders > 1 else 0
            
            cyclist_data.append({
                "position": i,
                "power": int(avg_power),
                "time_pct": time_at_front * 100,
                "is_you": i == position
            })
    else:
        # Static positions
        for i in range(1, riders + 1):
            draft_factor = draft_reduction_func(riders, i)
            estimated_power = power / draft_factor if draft_factor > 0 else power
            cyclist_data.append({
                "position": i,
                "power": int(estimated_power),
                "time_pct": 0,
                "is_you": i == position
            })
    
    return cyclist_data

def create_cyclist_visualization(cyclist_data):
    """Create HTML visualization of cyclists with their power values"""
    if not cyclist_data:
        return ""
    
    html = '<div style="display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; padding: 15px; background: #f8f9fa; border-radius: 8px;">'
    
    for cyclist in cyclist_data:
        you_indicator = " (You)" if cyclist["is_you"] else ""
        time_info = f" - {cyclist['time_pct']:.0f}%" if cyclist["time_pct"] > 0 else ""
        
        html += f'''
        <div style="text-align: center; padding: 10px; border: 2px solid {'#007acc' if cyclist['is_you'] else '#ccc'}; border-radius: 8px; background: {'#f0f8ff' if cyclist['is_you'] else '#fff'};">
            <div style="font-size: 24px;">🚴</div>
            <div style="font-size: 12px; font-weight: bold;">Pos. {cyclist["position"]}{you_indicator}</div>
            <div style="font-size: 14px; color: #333;">{cyclist["power"]}w{time_info}</div>
        </div>
        '''
    
    html += '</div>'
    return html

def calculate_performance(
    # Original performance inputs (user-editable)
    orig_power, orig_time_input, orig_speed_input,
    # Prediction inputs
    power, body_weight, gear_weight, slope, distance, elevation, wind,
    cda, crr, drafting, riders, position, rotating, work_pct, bike_type, terrain
):
    """Main calculation function"""
    try:
        if power <= 0 or body_weight <= 0 or gear_weight < 0 or distance <= 0:
            return create_error_output()
        
        # Convert units
        total_weight = body_weight + gear_weight
        slope_decimal = slope / 100.0
        distance_m = distance * 1000
        wind_ms = wind / 3.6
        
        # Apply drafting for predicted performance
        effective_cda = cda
        group_power = power
        power_variance = 0
        draft_info = ""
        cyclist_viz = ""
        
        if drafting and riders >= 2:
            if rotating:
                # Rotating paceline
                front_time = work_pct / 100.0
                draft_reduction = 1 - (1 - cycling_draft_drag_reduction(riders, riders)) * (1 - front_time)
                effective_cda = cda * draft_reduction
                draft_info = f"Rotating: {work_pct:.0f}% time at front"
                
                # Calculate power variance
                front_draft = 1.0
                back_draft = cycling_draft_drag_reduction(riders, riders)
                power_variance = ((1/back_draft - 1/front_draft) / (1/back_draft + 1/front_draft)) * 100
                
            else:
                # Static position
                draft_reduction = cycling_draft_drag_reduction(riders, position)
                effective_cda = cda * draft_reduction
                draft_info = f"Position {position}/{riders}"
            
            # Create cyclist visualization
            cyclist_data = calculate_cyclist_powers(riders, position, rotating, work_pct, power, cda, cycling_draft_drag_reduction)
            cyclist_viz = create_cyclist_visualization(cyclist_data)
            
            # Calculate average group power
            if cyclist_data:
                group_power = sum(c["power"] for c in cyclist_data) / len(cyclist_data)
        
        # Calculate predicted performance (with potential modifications)
        predicted_estimate = CyclingPhysics.cycling_power_velocity_search(
            power, slope_decimal, total_weight, crr, effective_cda, elevation, wind_ms
        )
        
        if predicted_estimate and predicted_estimate.velocity > 0:
            # Predicted performance  
            pred_time_seconds = distance_m / predicted_estimate.velocity
            pred_speed_kmh = predicted_estimate.velocity * 3.6
            pred_wkg = power / total_weight  # Include bike weight
            
            # Original performance (user inputs or defaults)
            orig_time_formatted = orig_time_input if orig_time_input else format_time(pred_time_seconds)
            orig_speed_formatted = f"{orig_speed_input:.1f}" if orig_speed_input is not None else f"{pred_speed_kmh:.1f}"
            orig_wkg_formatted = f"{orig_power / total_weight:.1f}" if orig_power and orig_power > 0 else f"{pred_wkg:.1f}"
            
            # Time difference calculation
            time_diff_str = ""
            if orig_time_input:
                try:
                    # Parse time input (MM:SS or H:MM:SS)
                    time_parts = orig_time_input.split(':')
                    if len(time_parts) == 2:
                        orig_time_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                    elif len(time_parts) == 3:
                        orig_time_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                    else:
                        orig_time_seconds = pred_time_seconds
                    
                    time_diff = pred_time_seconds - orig_time_seconds
                    if abs(time_diff) > 1:
                        if time_diff > 0:
                            time_diff_str = f" (+{format_time(abs(time_diff))})"
                        else:
                            time_diff_str = f" (-{format_time(abs(time_diff))})"
                except:
                    time_diff_str = ""
            
            # Power breakdown
            total_power_components = abs(predicted_estimate.g_watts) + abs(predicted_estimate.a_watts) + abs(predicted_estimate.r_watts)
            if total_power_components > 0:
                gravity_pct = abs(predicted_estimate.g_watts) / total_power_components * 100
                aero_pct = abs(predicted_estimate.a_watts) / total_power_components * 100
                rolling_pct = abs(predicted_estimate.r_watts) / total_power_components * 100
            else:
                gravity_pct = aero_pct = rolling_pct = 0
            
            return create_success_output(
                orig_time=orig_time_formatted,
                orig_speed=orig_speed_formatted,
                orig_wkg=orig_wkg_formatted,
                pred_time=format_time(pred_time_seconds),
                pred_speed=f"{pred_speed_kmh:.1f}", 
                pred_wkg=f"{pred_wkg:.1f}",
                time_diff=time_diff_str,
                gravity_watts=f"{predicted_estimate.g_watts:.0f}",
                gravity_wkg=f"{predicted_estimate.g_watts / total_weight:.1f}",
                gravity_pct=f"{gravity_pct:.0f}",
                aero_watts=f"{predicted_estimate.a_watts:.0f}",
                aero_wkg=f"{predicted_estimate.a_watts / total_weight:.1f}",
                aero_pct=f"{aero_pct:.0f}",
                rolling_watts=f"{predicted_estimate.r_watts:.0f}",
                rolling_wkg=f"{predicted_estimate.r_watts / total_weight:.1f}",
                rolling_pct=f"{rolling_pct:.0f}",
                position_desc=get_cda_position(cda),
                group_power=f"{group_power:.0f}" if drafting else "",
                power_variance=f"{power_variance:.0f}" if drafting else "",
                draft_info=draft_info,
                cyclist_viz=cyclist_viz,
                show_drafting=drafting,
                status="valid"
            )
        else:
            return create_error_output()
            
    except Exception as e:
        return create_error_output(f"Error: {str(e)}")

def create_success_output(**kwargs):
    """Create successful calculation output"""
    return (
        kwargs["status"],
        kwargs["orig_time"], kwargs["orig_speed"], kwargs["orig_wkg"],
        kwargs["pred_time"], kwargs["pred_speed"], kwargs["pred_wkg"], kwargs["time_diff"],
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
        "invalid", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", 
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
    </style>
    
    <div class="performance-predictor">
        <h1>Performance Predictor</h1>
        <p><em>The Performance Predictor is a cycling power calculator that lets you examine the impact of altered performance factors.</em></p>
        <p><strong>Change these parameters to see the estimated effect on performance.</strong></p>
    </div>
    """)
    
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
            power = gr.Number(value=250, label="Predicted Power (w)", minimum=50)
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
    bike_type.change(update_terrain_options, inputs=[bike_type], outputs=[terrain])
    bike_type.change(update_crr_value, inputs=[bike_type, terrain], outputs=[crr])
    terrain.change(update_crr_value, inputs=[bike_type, terrain], outputs=[crr])
    cda.change(update_position_description, inputs=[cda], outputs=[position_info])
    riders.change(update_position_max, inputs=[riders], outputs=[position])
    rotating.change(update_rotating_visibility, inputs=[rotating], outputs=[work_pct])
    
    # Main calculation with button
    inputs = [
        orig_power, orig_time_input, orig_speed_input,  # Original performance inputs
        power, body_weight, gear_weight, slope, distance, elevation, wind,
        cda, crr, drafting, riders, position, rotating, work_pct, bike_type, terrain
    ]
    
    outputs = [status, orig_time, orig_speed, orig_wkg, pred_time, pred_speed, pred_wkg, 
               time_diff, gravity_power, aero_power, rolling_power, position_info, 
               group_power, power_variance, draft_info_display, cyclist_visualization, drafting_section]
    
    # Calculate button click event
    calculate_btn.click(calculate_performance, inputs=inputs, outputs=outputs)
    
    # Initial calculation
    app.load(calculate_performance, inputs=inputs, outputs=outputs)

if __name__ == "__main__":
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        quiet=False
    )