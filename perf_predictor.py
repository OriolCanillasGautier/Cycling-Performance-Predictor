#!/usr/bin/env python3
"""
Cycling Performance Predictor — NiceGUI UI.
Clean Material-Design interface with full i18n support (EN / CA / FR).
"""

import json
import os
from pathlib import Path
from nicegui import app, ui

from cycling_physics import (
    CyclingPhysics,
    TERRAIN_CRR,
    cycling_draft_drag_reduction,
    format_time,
    parse_time_input,
    compute_avg_elevation,
    calculate_cyclist_powers,
)

# ── Language packs ──────────────────────────────────────────────────────────

_LANG_PATH = os.path.join(os.path.dirname(__file__), "languagepacks.json")
with open(_LANG_PATH, encoding="utf-8") as _f:
    LANG = json.load(_f)

LANG_OPTIONS = {"en": "English", "ca": "Català", "fr": "Français"}

_FAVICON = Path(__file__).parent / "favicon.svg"
app.add_static_files("/static", Path(__file__).parent)


def t(key: str, lang: str = "en") -> str:
    return LANG.get(lang, LANG["en"]).get(key, LANG["en"].get(key, key))


def cda_position(cda: float, lang: str) -> str:
    if cda < 0.23:
        return t("cda_position_1", lang)
    if cda < 0.30:
        return t("cda_position_2", lang)
    if cda < 0.35:
        return t("cda_position_3", lang)
    if cda < 0.50:
        return t("cda_position_4", lang)
    return t("cda_position_5", lang)


# ── Core calculation ────────────────────────────────────────────────────────

def run_calculation(state: dict, lang: str) -> dict:
    body_w = state["body_weight"]
    gear_w = state["gear_weight"]
    if body_w <= 0 or gear_w < 0 or state["distance"] <= 0:
        return {"error": t("error_no_solution", lang)}

    total_weight = body_w + gear_w
    slope_dec = state["slope"] / 100.0
    dist_m = state["distance"] * 1000
    wind_ms = state["wind"] / 3.6
    elevation = compute_avg_elevation(
        state["start_elevation"], state["slope"], state["distance"]
    )

    cda_val = state["cda"]
    effective_cda = cda_val
    draft_info = ""
    group_power = 0
    cyclist_data = []

    if state["drafting"] and state["riders"] >= 2:
        riders = state["riders"]
        pos = state["position"]
        if state["rotating"]:
            ft = state["work_pct"] / 100.0
            bdr = cycling_draft_drag_reduction(riders, riders)
            effective_cda = cda_val * (ft + (1 - ft) * bdr)
            draft_info = t("draft_rotating", lang).format(work_pct=state["work_pct"])
        else:
            dr = cycling_draft_drag_reduction(riders, pos)
            effective_cda = cda_val * dr
            draft_info = t("draft_position", lang).format(
                position=pos, riders=riders, draft_pct=(1 - dr) * 100
            )

    mode = state["calc_mode"]
    if mode == "power_to_time":
        pw = state["power"]
        if pw <= 0:
            return {"error": t("error_power_positive", lang)}
        est = CyclingPhysics.cycling_power_velocity_search(
            pw, slope_dec, total_weight, state["crr"], effective_cda, elevation, wind_ms
        )
        if not est or est.velocity <= 0:
            return {"error": t("error_no_solution", lang)}
        pred_time_s = dist_m / est.velocity
        pred_speed = est.velocity * 3.6
        calc_power = pw
    else:
        ts = parse_time_input(state["target_time"])
        if not ts or ts <= 0:
            return {"error": t("error_invalid_target_time", lang)}
        est = CyclingPhysics.cycling_time_power_search(
            ts, dist_m, slope_dec, total_weight, state["crr"],
            effective_cda, elevation, wind_ms
        )
        if not est or est.velocity <= 0:
            return {"error": t("error_no_solution_target", lang)}
        pred_time_s = ts
        pred_speed = est.velocity * 3.6
        calc_power = est.watts

    if state["drafting"] and state["riders"] >= 2:
        cyclist_data = calculate_cyclist_powers(
            state["riders"], state["position"], state["rotating"],
            state["work_pct"], calc_power, cda_val, cycling_draft_drag_reduction,
        )
        if cyclist_data:
            group_power = sum(c["power"] for c in cyclist_data) / len(cyclist_data)

    pred_wkg = calc_power / total_weight
    gw, aw, rw = est.g_watts, est.a_watts, est.r_watts
    pos_sum = sum(x for x in (gw, aw, rw) if x > 0)
    gp = gw / pos_sum * 100 if gw > 0 and pos_sum else 0
    ap = aw / pos_sum * 100 if aw > 0 and pos_sum else 0
    rp = rw / pos_sum * 100 if rw > 0 and pos_sum else 0

    tdiff = ""
    if state.get("orig_time"):
        ots = parse_time_input(state["orig_time"])
        if ots:
            d = pred_time_s - ots
            if abs(d) > 1:
                tdiff = (
                    f" (+{format_time(abs(d))})"
                    if d > 0
                    else f" (-{format_time(abs(d))})"
                )

    return {
        "time": format_time(pred_time_s),
        "speed": f"{pred_speed:.1f}",
        "power": f"{calc_power:.0f}",
        "wkg": f"{pred_wkg:.2f}",
        "time_diff": tdiff,
        "gravity_w": f"{gw:.0f}",
        "gravity_wkg": f"{gw / total_weight:.1f}",
        "gravity_pct": f"{gp:.0f}",
        "aero_w": f"{aw:.0f}",
        "aero_wkg": f"{aw / total_weight:.1f}",
        "aero_pct": f"{ap:.0f}",
        "rolling_w": f"{rw:.0f}",
        "rolling_wkg": f"{rw / total_weight:.1f}",
        "rolling_pct": f"{rp:.0f}",
        "draft_info": draft_info,
        "group_power": f"{group_power:.0f}" if group_power else "",
        "cyclist_data": cyclist_data,
        "orig_power": state.get("orig_power", ""),
        "orig_time": state.get("orig_time", ""),
        "orig_speed": state.get("orig_speed", ""),
        "total_weight": total_weight,
    }


# ── UI Page ─────────────────────────────────────────────────────────────────

@ui.page("/")
def main_page():
    # Reactive state
    state = {
        "lang": "en",
        "calc_mode": "power_to_time",
        "power": 250,
        "target_time": "",
        "orig_power": 250,
        "orig_time": "",
        "orig_speed": 0,
        "body_weight": 70,
        "gear_weight": 8.0,
        "slope": 0,
        "distance": 10,
        "start_elevation": 0,
        "wind": 0,
        "cda": 0.40,
        "crr": 0.0050,
        "bike_type": "road",
        "terrain": "asphalt",
        "drafting": False,
        "riders": 2,
        "position": 2,
        "rotating": False,
        "work_pct": 50,
    }

    # Convenience
    def L():
        return state["lang"]

    # Dark background
    ui.query("body").style("background:#0b1120")

    # ── HEADER — must be direct page child ──
    with ui.header().classes(
        "items-center justify-between px-6 py-3 shadow-lg"
    ).style("background:#0f172a"):
        header_title = ui.label(t("app_title", L())).classes(
            "text-xl font-bold text-white tracking-tight"
        )
        ui.select(
            options=LANG_OPTIONS,
            value=state["lang"],
            on_change=lambda e: _change_lang(e.value),
        ).props('dense outlined dark color="blue-4"').classes("min-w-[140px]")

    # ── REFRESHABLE BODY ──
    @ui.refreshable
    def body_content():
        lang = L()

        # Subtitle
        with ui.column().classes("w-full max-w-6xl mx-auto px-4 mt-4 mb-1"):
            ui.label(t("app_subtitle", lang)).classes(
                "text-gray-400 text-sm italic"
            )

        with ui.column().classes("w-full max-w-6xl mx-auto px-4 gap-6 pb-8"):
            # Mode selector
            with ui.card().classes("w-full").style(
                "background:#111827;border:1px solid #374151"
            ):
                with ui.card_section():
                    ui.label(t("mode_label", lang)).classes(
                        "text-xs uppercase tracking-wide text-gray-400 mb-2"
                    )
                    ui.radio(
                        {
                            "power_to_time": t("mode_power_time", lang),
                            "time_to_power": t("mode_time_power", lang),
                        },
                        value=state["calc_mode"],
                        on_change=lambda e: (
                            state.__setitem__("calc_mode", e.value),
                            body_content.refresh(),
                        ),
                    ).props("inline dark color=blue-6")

            # Two-column layout
            with ui.row().classes("w-full gap-6 items-start flex-wrap"):
                # LEFT column
                with ui.column().classes("flex-1 gap-6 min-w-[320px]"):
                    _build_baseline(lang, state)
                    _build_rolling(lang, state, body_content)
                    _build_aero(lang, state, body_content)
                    _build_drafting(lang, state, body_content)

                # RIGHT column
                with ui.column().classes("flex-1 gap-6 min-w-[320px]"):
                    _build_prediction(lang, state)

            # Calculate
            ui.button(
                t("calc_button", lang),
                on_click=lambda: _calculate(),
            ).props("unelevated color=blue-7 size=lg no-caps").classes(
                "w-full max-w-md mx-auto mt-2 font-bold tracking-wide"
            )

    # ── Helpers ──
    def _change_lang(val):
        state["lang"] = val
        header_title.text = t("app_title", val)
        body_content.refresh()

    def _calculate():
        lang = L()
        res = run_calculation(state, lang)
        if "error" in res:
            ui.notify(res["error"], type="negative", position="top")
            return
        _show_results_dialog(res, lang)

    # First render
    body_content()


# ── Section card builders (module-level) ────────────────────────────────────

def _heading(text: str):
    ui.label(text).classes(
        "text-xs uppercase tracking-wide text-blue-400 font-bold"
        " border-b border-blue-800 pb-1 mb-2 w-full"
    )


def _build_baseline(lang, state):
    with ui.card().classes("w-full").style(
        "background:#111827;border:1px solid #374151"
    ):
        with ui.card_section().classes("gap-4"):
            _heading(t("section_baseline", lang))
            ui.number(
                label=t("label_orig_power", lang),
                value=state["orig_power"], min=0, step=1, suffix="W",
                on_change=lambda e: state.__setitem__("orig_power", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_orig_power", lang)
            )
            ui.input(
                label=t("label_orig_time", lang),
                value=state["orig_time"],
                placeholder=t("placeholder_time_example", lang),
                on_change=lambda e: state.__setitem__("orig_time", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_orig_time", lang)
            )
            ui.number(
                label=t("label_orig_speed", lang),
                value=state["orig_speed"], min=0, step=0.1, suffix="km/h",
                on_change=lambda e: state.__setitem__("orig_speed", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_orig_speed", lang)
            )


def _build_rolling(lang, state, refreshable):
    bike_opts = {"road": t("bike_road", lang), "mtb": t("bike_mtb", lang)}
    terrain_keys = list(TERRAIN_CRR[state["bike_type"]].keys())
    terrain_opts = {k: t(f"terrain_{k}", lang) for k in terrain_keys}

    def _bike_changed(val):
        state["bike_type"] = val
        keys = list(TERRAIN_CRR[val].keys())
        state["terrain"] = keys[0]
        state["crr"] = TERRAIN_CRR[val][keys[0]]
        refreshable.refresh()

    def _terrain_changed(val):
        state["terrain"] = val
        state["crr"] = TERRAIN_CRR[state["bike_type"]].get(val, 0.0050)
        refreshable.refresh()

    with ui.card().classes("w-full").style(
        "background:#111827;border:1px solid #374151"
    ):
        with ui.card_section().classes("gap-4"):
            _heading(t("section_rolling", lang))
            ui.select(
                options=bike_opts, value=state["bike_type"],
                label=t("label_bike", lang),
                on_change=lambda e: _bike_changed(e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full")
            ui.select(
                options=terrain_opts, value=state["terrain"],
                label=t("label_terrain", lang),
                on_change=lambda e: _terrain_changed(e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full")
            ui.number(
                label=t("label_crr", lang),
                value=state["crr"], min=0.001, step=0.0005, format="%.4f",
                on_change=lambda e: state.__setitem__("crr", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_crr", lang)
            )


def _build_aero(lang, state, refreshable):
    with ui.card().classes("w-full").style(
        "background:#111827;border:1px solid #374151"
    ):
        with ui.card_section().classes("gap-4"):
            _heading(t("section_aero", lang))
            ui.label(f"CdA: {state['cda']:.2f} m²").classes(
                "text-white text-sm font-medium"
            )
            ui.slider(
                min=0.15, max=0.70, step=0.01, value=state["cda"],
                on_change=lambda e: (
                    state.__setitem__("cda", e.value),
                    refreshable.refresh(),
                ),
            ).props("dark color=blue-6 label-always")
            ui.label(cda_position(state["cda"], lang)).classes(
                "text-xs text-gray-400 italic"
            )
            ui.label(t("info_cda", lang)).classes("text-[11px] text-gray-600")


def _build_drafting(lang, state, refreshable):
    with ui.card().classes("w-full").style(
        "background:#111827;border:1px solid #374151"
    ):
        with ui.card_section().classes("gap-4"):
            _heading(t("section_drafting", lang))
            ui.switch(
                t("label_enable_drafting", lang), value=state["drafting"],
                on_change=lambda e: (
                    state.__setitem__("drafting", e.value),
                    refreshable.refresh(),
                ),
            ).props("dark color=blue-6")
            if state["drafting"]:
                ui.number(
                    label=t("label_riders", lang),
                    value=state["riders"], min=2, max=8, step=1,
                    on_change=lambda e: (
                        state.__setitem__("riders", int(e.value)),
                        refreshable.refresh(),
                    ),
                ).props("dense outlined dark color=blue-4").classes("w-full")
                ui.switch(
                    t("label_rotating", lang), value=state["rotating"],
                    on_change=lambda e: (
                        state.__setitem__("rotating", e.value),
                        refreshable.refresh(),
                    ),
                ).props("dark color=blue-6")
                if state["rotating"]:
                    ui.number(
                        label=t("label_time_front", lang),
                        value=state["work_pct"], min=0, max=100, step=1, suffix="%",
                        on_change=lambda e: state.__setitem__("work_pct", e.value),
                    ).props("dense outlined dark color=blue-4").classes("w-full")
                else:
                    ui.number(
                        label=t("label_your_position", lang),
                        value=state["position"], min=1, max=state["riders"], step=1,
                        on_change=lambda e: state.__setitem__(
                            "position", int(e.value)
                        ),
                    ).props("dense outlined dark color=blue-4").classes("w-full")


def _build_prediction(lang, state):
    with ui.card().classes("w-full").style(
        "background:#111827;border:1px solid #374151"
    ):
        with ui.card_section().classes("gap-4"):
            _heading(t("section_prediction", lang))

            if state["calc_mode"] == "power_to_time":
                ui.number(
                    label=t("label_power", lang),
                    value=state["power"], min=1, step=1, suffix="W",
                    on_change=lambda e: state.__setitem__("power", e.value),
                ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                    t("info_power", lang)
                )
            else:
                ui.input(
                    label=t("label_target_time", lang),
                    value=state["target_time"],
                    placeholder=t("placeholder_time_example", lang),
                    on_change=lambda e: state.__setitem__("target_time", e.value),
                ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                    t("info_target_time", lang)
                )

            ui.element("div").classes("w-full border-t border-gray-700 my-1")

            ui.number(
                label=t("label_body_weight", lang),
                value=state["body_weight"], min=30, step=0.5, suffix="kg",
                on_change=lambda e: state.__setitem__("body_weight", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_body_weight", lang)
            )
            ui.number(
                label=t("label_gear_weight", lang),
                value=state["gear_weight"], min=0, step=0.1, suffix="kg",
                on_change=lambda e: state.__setitem__("gear_weight", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_gear_weight", lang)
            )

            ui.element("div").classes("w-full border-t border-gray-700 my-1")

            ui.number(
                label=t("label_gradient", lang),
                value=state["slope"], step=0.1, suffix="%",
                on_change=lambda e: state.__setitem__("slope", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_gradient", lang)
            )
            ui.number(
                label=t("label_distance", lang),
                value=state["distance"], min=0.1, step=0.1, suffix="km",
                on_change=lambda e: state.__setitem__("distance", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_distance", lang)
            )
            ui.number(
                label=t("label_start_elevation", lang),
                value=state["start_elevation"], step=10, suffix="m",
                on_change=lambda e: state.__setitem__("start_elevation", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_start_elevation", lang)
            )
            ui.number(
                label=t("label_wind", lang),
                value=state["wind"], step=1, suffix="km/h",
                on_change=lambda e: state.__setitem__("wind", e.value),
            ).props("dense outlined dark color=blue-4").classes("w-full").tooltip(
                t("info_wind", lang)
            )


# ── Results dialog ──────────────────────────────────────────────────────────

def _show_results_dialog(res, lang):
    with ui.dialog().props("maximized=false") as dlg, \
         ui.card().classes("w-full max-w-3xl").style(
             "background:#0f172a;color:white;max-height:90vh;overflow-y:auto"
         ):
        # Title bar
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label(t("results_title", lang)).classes(
                "text-lg font-bold text-white"
            )
            ui.button(icon="close", on_click=dlg.close).props(
                "flat round dense color=grey-5"
            )

        ui.separator().props("dark")

        # Summary cards
        with ui.row().classes("w-full gap-3 my-3 flex-wrap"):
            _result_card(t("summary_time", lang),
                         res["time"], res["time_diff"])
            _result_card(t("summary_speed", lang),
                         f'{res["speed"]} km/h', "")
            _result_card(t("summary_power", lang),
                         f'{res["power"]} W', f'{res["wkg"]} W/kg')
            if res["draft_info"]:
                sub = (f'{t("label_group_power", lang)}: {res["group_power"]}W'
                       if res["group_power"] else "")
                _result_card(t("summary_drafting", lang),
                             res["draft_info"], sub)

        ui.separator().props("dark")

        # Power breakdown
        ui.label(t("section_power_breakdown", lang)).classes(
            "text-sm uppercase tracking-wide text-blue-400 font-bold mt-2"
        )
        _power_bar(t("gravity", lang), res["gravity_pct"], res["gravity_w"], "amber")
        _power_bar(t("aerodynamics", lang), res["aero_pct"], res["aero_w"], "blue")
        _power_bar(t("rolling", lang), res["rolling_pct"], res["rolling_w"], "green")

        # Comparison
        if res["orig_time"] or (
            res["orig_power"] and float(res["orig_power"] or 0) > 0
        ):
            ui.separator().props("dark").classes("my-2")
            ui.label(t("section_comparison", lang)).classes(
                "text-sm uppercase tracking-wide text-blue-400 font-bold mt-1"
            )
            with ui.row().classes("w-full gap-4 mt-2"):
                with ui.column().classes("flex-1"):
                    ui.label(t("section_original", lang)).classes(
                        "text-xs text-gray-400 uppercase mb-1"
                    )
                    if res["orig_power"]:
                        tw = res["total_weight"]
                        op = float(res["orig_power"])
                        ui.label(
                            f'{t("summary_power", lang)}: {op:.0f} W '
                            f'({op / tw:.1f} W/kg)'
                        ).classes("text-sm text-gray-300")
                    if res["orig_time"]:
                        ui.label(
                            f'{t("summary_time", lang)}: {res["orig_time"]}'
                        ).classes("text-sm text-gray-300")
                with ui.column().classes("flex-1"):
                    ui.label(t("section_predicted", lang)).classes(
                        "text-xs text-gray-400 uppercase mb-1"
                    )
                    ui.label(
                        f'{t("summary_power", lang)}: {res["power"]} W '
                        f'({res["wkg"]} W/kg)'
                    ).classes("text-sm text-gray-300")
                    ui.label(
                        f'{t("summary_time", lang)}: {res["time"]}'
                    ).classes("text-sm text-gray-300")

        # Drafting visualization
        if res["cyclist_data"]:
            ui.separator().props("dark").classes("my-2")
            ui.label(t("section_drafting_details", lang)).classes(
                "text-sm uppercase tracking-wide text-blue-400 font-bold mt-1"
            )
            with ui.row().classes("gap-2 mt-2 flex-wrap"):
                for c in res["cyclist_data"]:
                    is_you = c["is_you"]
                    style = (
                        "background:#1e3a5f;border:2px solid #3b82f6"
                        if is_you
                        else "background:#111827;border:1px solid #374151"
                    )
                    with ui.card().classes("p-3 min-w-[80px] text-center").style(style):
                        tag = f' ({t("cyclist_you", lang)})' if is_you else ""
                        ui.label(
                            f'{t("cyclist_pos", lang)} {c["position"]}{tag}'
                        ).classes("text-xs text-gray-300 font-bold")
                        ui.label(f'{c["power"]}W').classes(
                            "text-base font-bold text-white"
                        )
                        if c["time_pct"] > 0:
                            ui.label(
                                f'{c["time_pct"]:.0f}% {t("cyclist_front", lang)}'
                            ).classes("text-[10px] text-gray-500")

        # Close
        with ui.row().classes("w-full justify-end mt-4"):
            ui.button(
                t("close_button", lang), on_click=dlg.close
            ).props("unelevated color=blue-7 no-caps")

    dlg.open()


def _result_card(label, value, sub):
    with ui.card().classes("flex-1 min-w-[140px] p-3").style(
        "background:#1e293b;border:1px solid #374151"
    ):
        ui.label(label).classes(
            "text-[11px] uppercase tracking-wide text-gray-400 mb-1"
        )
        ui.label(value).classes("text-lg font-bold text-white")
        if sub:
            ui.label(sub).classes("text-xs text-gray-500")


def _power_bar(label, pct_str, watts_str, color):
    pct = float(pct_str or 0)
    with ui.row().classes("w-full items-center gap-3 my-1"):
        ui.label(label).classes("w-28 text-sm text-gray-300")
        with ui.element("div").classes(
            "flex-1 h-3 rounded-full overflow-hidden"
        ).style("background:#374151"):
            ui.element("div").classes(
                f"h-full rounded-full bg-{color}-500"
            ).style(f"width:{pct}%;transition:width 0.4s ease")
        ui.label(f"{pct_str}% · {watts_str}W").classes(
            "text-xs text-gray-400 w-28 text-right"
        )


# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Performance Predictor",
        favicon=_FAVICON,
        port=7860,
        dark=True,
        reload=False,
    )
