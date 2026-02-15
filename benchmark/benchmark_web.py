#!/usr/bin/env python3
"""Web benchmark viewer for drafting models with charts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nicegui import ui
import plotly.graph_objects as go
import plotly.express as px

from benchmark_engine import run_benchmark


SCENARIOS_PATH = Path(__file__).with_name("benchmark_scenarios.json")


def build_page() -> None:
    ui.dark_mode().enable()

    with ui.column().classes("w-full p-6 gap-4"):
        ui.label("Drafting Benchmark (DIY method)").classes("text-2xl font-bold")
        ui.label(
            "CdA interpolation: men 0.3500→0.2625, women lower baseline; "
            "power from distance/gradient/time(or speed)/mass/rho/CRR/drivetrain"
        ).classes("text-sm text-gray-400")

        summary_row = ui.row().classes("gap-4 flex-wrap")
        charts_row = ui.row().classes("w-full gap-4 flex-wrap")
        table_container = ui.column().classes("w-full")

        def render() -> None:
            result = run_benchmark(SCENARIOS_PATH)
            rows = result["rows"]
            s = result["summary"]

            summary_row.clear()
            charts_row.clear()
            table_container.clear()

            with summary_row:
                for label, value in [
                    ("Scenarios", str(s["scenario_count"])),
                    ("Mean dyn power", f"{s['mean_dyn_power_w']:.1f} W"),
                    ("Mean legacy power", f"{s['mean_leg_power_w']:.1f} W"),
                    ("Mean diff", f"{s['mean_diff_w']:+.1f} W"),
                ]:
                    with ui.card().classes("p-3"):
                        ui.label(label).classes("text-xs text-gray-400")
                        ui.label(value).classes("text-lg font-semibold")

            # Charts
            with charts_row:
                # Power comparison chart
                with ui.column().classes("flex-1 min-w-[400px]"):
                    ui.label("Power Comparison").classes("text-sm font-bold text-blue-400 mb-2")
                    fig_power = go.Figure()
                    for r in rows:
                        fig_power.add_trace(go.Bar(
                            name=r["id"], x=[r["id"]], y=[r["dyn_power_w"]], 
                            marker_color="rgba(59, 130, 246, 0.8)", showlegend=False,
                            text=f"{r['dyn_power_w']:.0f}W", textposition="outside"
                        ))
                        fig_power.add_trace(go.Bar(
                            name=r["id"], x=[r["id"]], y=[r["leg_power_w"]], 
                            marker_color="rgba(107, 114, 128, 0.6)", showlegend=False,
                            text=f"{r['leg_power_w']:.0f}W", textposition="outside"
                        ))
                    fig_power.update_layout(
                        barmode="group", height=300, margin=dict(l=0, r=0, t=0, b=0),
                        paper_bgcolor="rgba(15,23,42,1)", plot_bgcolor="rgba(30,41,59,1)",
                        font=dict(color="white", size=10), hovermode="closest",
                        xaxis=dict(title="Scenario", showgrid=False),
                        yaxis=dict(title="Power (W)", showgrid=True, gridcolor="rgba(100,100,100,0.2)")
                    )
                    ui.plotly(fig_power).classes("w-full")

                # Power difference chart
                with ui.column().classes("flex-1 min-w-[400px]"):
                    ui.label("Power Difference (Dyn - Legacy)").classes("text-sm font-bold text-blue-400 mb-2")
                    colors = ["red" if r["power_diff_w"] > 0 else "green" for r in rows]
                    fig_diff = go.Figure(data=[
                        go.Bar(x=[r["id"] for r in rows], y=[r["power_diff_w"] for r in rows],
                               marker_color=colors, text=[f"{r['power_diff_w']:+.0f}W" for r in rows],
                               textposition="outside", showlegend=False)
                    ])
                    fig_diff.update_layout(
                        height=300, margin=dict(l=0, r=0, t=0, b=0),
                        paper_bgcolor="rgba(15,23,42,1)", plot_bgcolor="rgba(30,41,59,1)",
                        font=dict(color="white", size=10), hovermode="closest",
                        xaxis=dict(title="Scenario", showgrid=False),
                        yaxis=dict(title="Difference (W)", showgrid=True, gridcolor="rgba(100,100,100,0.2)",
                                    zeroline=True, zerolinecolor="rgba(255,255,255,0.3)")
                    )
                    ui.plotly(fig_diff).classes("w-full")

            # CdA comparison
            with charts_row:
                with ui.column().classes("flex-1 min-w-[400px]"):
                    ui.label("CdA Multipliers").classes("text-sm font-bold text-blue-400 mb-2")
                    fig_cda = go.Figure()
                    fig_cda.add_trace(go.Scatter(x=[r["id"] for r in rows], y=[r["dyn_cda"] for r in rows],
                                                  mode="lines+markers", name="Dynamic",
                                                  line=dict(color="rgba(59,130,246,1)", width=2),
                                                  marker=dict(size=6)))
                    fig_cda.add_trace(go.Scatter(x=[r["id"] for r in rows], y=[r["leg_cda"] for r in rows],
                                                  mode="lines+markers", name="Legacy",
                                                  line=dict(color="rgba(107,114,128,1)", width=2, dash="dash"),
                                                  marker=dict(size=6)))
                    fig_cda.update_layout(
                        height=300, margin=dict(l=0, r=0, t=0, b=0),
                        paper_bgcolor="rgba(15,23,42,1)", plot_bgcolor="rgba(30,41,59,1)",
                        font=dict(color="white", size=10), hovermode="closest",
                        xaxis=dict(title="Scenario", showgrid=False),
                        yaxis=dict(title="CdA Multiplier", showgrid=True, gridcolor="rgba(100,100,100,0.2)")
                    )
                    ui.plotly(fig_cda).classes("w-full")

                # Scatter: Gap vs Power Diff
                with ui.column().classes("flex-1 min-w-[400px]"):
                    ui.label("Gap Distance vs Power Difference").classes("text-sm font-bold text-blue-400 mb-2")
                    fig_scatter = go.Figure(data=[
                        go.Scatter(x=[r["gap_m"] for r in rows], y=[r["power_diff_w"] for r in rows],
                                   mode="markers", marker=dict(size=8, color=[r["speed_kmh"] for r in rows],
                                                                colorscale="Viridis", showscale=True,
                                                                colorbar=dict(title="Speed km/h")),
                                   text=[r["id"] for r in rows], hovertemplate="%{text}<br>Gap: %{x:.2f}m<br>Diff: %{y:.1f}W")
                    ])
                    fig_scatter.update_layout(
                        height=300, margin=dict(l=0, r=0, t=0, b=0),
                        paper_bgcolor="rgba(15,23,42,1)", plot_bgcolor="rgba(30,41,59,1)",
                        font=dict(color="white", size=10), hovermode="closest",
                        xaxis=dict(title="Gap (m)", showgrid=True, gridcolor="rgba(100,100,100,0.2)"),
                        yaxis=dict(title="Power Diff (W)", showgrid=True, gridcolor="rgba(100,100,100,0.2)",
                                    zeroline=True, zerolinecolor="rgba(255,255,255,0.3)")
                    )
                    ui.plotly(fig_scatter).classes("w-full")

            # Table
            columns = [
                {"name": "id", "label": "ID", "field": "id", "sortable": True},
                {"name": "name", "label": "Name", "field": "name", "sortable": True},
                {"name": "sex", "label": "Sex", "field": "sex", "sortable": True},
                {"name": "riders", "label": "R", "field": "riders", "sortable": True},
                {"name": "position", "label": "P", "field": "position", "sortable": True},
                {"name": "speed_kmh", "label": "km/h", "field": "speed_kmh", "sortable": True},
                {"name": "gap_m", "label": "Gap", "field": "gap_m", "sortable": True},
                {"name": "dyn_draft_pct", "label": "DynDraft%", "field": "dyn_draft_pct", "sortable": True},
                {"name": "leg_draft_pct", "label": "LegDraft%", "field": "leg_draft_pct", "sortable": True},
                {"name": "dyn_cda", "label": "DynCdA", "field": "dyn_cda", "sortable": True},
                {"name": "leg_cda", "label": "LegCdA", "field": "leg_cda", "sortable": True},
                {"name": "dyn_power_w", "label": "DynW", "field": "dyn_power_w", "sortable": True},
                {"name": "leg_power_w", "label": "LegW", "field": "leg_power_w", "sortable": True},
                {"name": "power_diff_w", "label": "DiffW", "field": "power_diff_w", "sortable": True},
            ]

            for r in rows:
                for k in ("speed_kmh", "gap_m", "dyn_draft_pct", "leg_draft_pct", "dyn_cda", "leg_cda", "dyn_power_w", "leg_power_w", "power_diff_w"):
                    r[k] = round(r[k], 2)

            with table_container:
                ui.label("Detailed Results").classes("text-sm font-bold text-blue-400 mt-4 mb-2")
                ui.table(columns=columns, rows=rows, row_key="id", pagination=15).classes("w-full")
                ui.label(f"Source: {result['source']}").classes("text-xs text-gray-500 mt-2")

        with ui.row().classes("gap-2"):
            ui.button("Run benchmark", on_click=render).props("color=blue-7")

        render()


@ui.page("/")
def main_page() -> None:
    build_page()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Drafting Benchmark", reload=False)
