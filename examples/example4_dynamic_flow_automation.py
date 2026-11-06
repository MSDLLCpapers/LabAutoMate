import dash
from dash import dcc, html, Input, Output, State, ctx, callback
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import pandas as pd
import numpy as np
import os
import re
import math
import time
import threading
from datetime import datetime

from pylabdrivers.teledyneisco import TeledyneISCO
from pylabdrivers.equilibarpc import Equilibar
from pylabdrivers.vicivalco import VICI

try:
    from opcua import Client as OPCClient
except ImportError:
    OPCClient = None

try:
    import rseriesopc as rs
except ImportError:
    rs = None

# ─────────────────────────────────────────────────────────────────────────────
# Global State
# ─────────────────────────────────────────────────────────────────────────────
experiment_state = {
    "running": False,
    "phase": "idle",  # idle, pre_ramp, ramp, post_ramp, cleanup, done
    "elapsed_seconds": 0,
    "start_time": None,
    "tau": 0.0,
    "F_of_tau": 0.0,
    "pressure_reading": 0.0,
    "valve1_pos": "N/A",
    "valve2_pos": "N/A",
    "reactor_temp": 0.0,
    "min_res_time": 0.0,
    "max_res_time": 0.0,
    "node1_values": [],
    "node2_values": [],
    "time_values": [],
    "status_msg": "Ready.",
    "error_msg": "",
    "current_flow1": 0.0,
    "current_flow2": 0.0,
    "sample_count": 0,
}

stop_event = threading.Event()
experiment_thread = None

# Instrument objects (not connected at import time)
isco1 = None
isco2 = None
equilibar = None
valve1 = None
valve2 = None
vapourtec_client = None
vapourtec_manual_control = None
opc_client = None
opc_node1 = None
opc_node2 = None

# ─────────────────────────────────────────────────────────────────────────────
# Dash App
# ─────────────────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)
app.title = "Dynamic Flow Experiment Controller"

app.index_string = '''<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
  body { font-family: -apple-system, Helvetica Neue, Arial, sans-serif; background: #F7F7F7; color: #1E293B; margin: 0; }
  .app-titlebar { background: #1E293B; color: #FFFFFF; padding: 12px 24px; border-left: 4px solid #2563EB; }
  .app-titlebar h1 { margin: 0; font-size: 1.4rem; font-weight: 700; color: #FFFFFF; }
  .app-titlebar p { margin: 0; font-size: 0.85rem; color: #60A5FA; }
  .instrument-card { background: #FFFFFF; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); padding: 16px; margin-bottom: 12px; }
  .card-header { display: flex; align-items: center; gap: 10px; border-bottom: 2px solid #2563EB; padding-bottom: 8px; margin-bottom: 12px; }
  .card-header h5 { color: #1E293B; font-weight: 600; margin: 0; font-size: 1rem; }
  .status-connected { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; border-radius: 12px; padding: 2px 10px; font-size: 11px; font-weight: 500; }
  .status-disconnected { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; border-radius: 12px; padding: 2px 10px; font-size: 11px; font-weight: 500; }
  .status-msg { background: #F0F0F0; border-radius: 4px; padding: 8px 12px; font-style: italic; color: #555; font-size: 12px; min-height: 32px; margin-top: 8px; }
  .app-footer { border-top: 1px solid #D9D9D9; padding: 8px 24px; font-size: 11px; color: #888; background: #FFFFFF; margin-top: 16px; }
  input, select, .Select-control { border: 1px solid #D9D9D9 !important; border-radius: 4px !important; }
  .sidebar-section { max-height: 80vh; overflow-y: auto; padding-right: 8px; }
  .indicator-box { background: #FFFFFF; border: 1px solid #D9D9D9; border-radius: 6px; padding: 8px 12px; text-align: center; margin-bottom: 8px; }
  .indicator-label { font-size: 11px; color: #888; margin-bottom: 2px; }
  .indicator-value { font-size: 1.1rem; font-weight: 600; color: #1E293B; }
</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>'''


# ─────────────────────────────────────────────────────────────────────────────
# SVG Icons
# ─────────────────────────────────────────────────────────────────────────────
def _svg_icon(svg_body: str) -> dcc.Markdown:
    return dcc.Markdown(
        f'<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#2563EB" stroke-width="1.5" style="vertical-align:middle;margin-right:6px">{svg_body}</svg>',
        dangerously_allow_html=True,
    )


PUMP_ICON = '<rect x="3" y="9" width="14" height="6"/><rect x="17" y="11" width="4" height="2"/><circle cx="5" cy="12" r="1.5" fill="#2563EB"/>'
PRESSURE_ICON = '<circle cx="12" cy="12" r="9"/><line x1="12" y1="12" x2="17" y2="7" stroke-width="2"/><circle cx="12" cy="12" r="1.5" fill="#2563EB"/>'
GENERIC_ICON = '<polygon points="12,2 22,8 22,16 12,22 2,16 2,8"/>'
DATA_ICON = '<rect x="2" y="14" width="4" height="8"/><rect x="10" y="8" width="4" height="14"/><rect x="18" y="4" width="4" height="18"/>'


# ─────────────────────────────────────────────────────────────────────────────
# Helper: input field
# ─────────────────────────────────────────────────────────────────────────────
def make_input(label, id_, type_="text", value="", placeholder=""):
    return dbc.Row([
        dbc.Col(dbc.Label(label, style={"fontSize": "12px", "marginBottom": "2px", "color": "#1E293B"}), width=12),
        dbc.Col(dbc.Input(id=id_, type=type_, value=value, placeholder=placeholder, size="sm"), width=12),
    ], className="mb-2")


# ─────────────────────────────────────────────────────────────────────────────
# Layout: Sidebar (Inputs)
# ─────────────────────────────────────────────────────────────────────────────
sidebar = dbc.Col([
    html.Div([
        html.Div([_svg_icon(GENERIC_ICON), html.H5("Experiment Parameters")], className="card-header"),
        make_input("Reactor Volume (µL)", "input-reactor-vol", "number", 20000),
        make_input("Dead Volume (µL)", "input-dead-vol", "number", 100),
        make_input("Pre-Ramp Steady State Time (s)", "input-pre-ramp-time", "number", 600),
        make_input("Post-Ramp Duration (s)", "input-post-ramp-time", "number", 2700),
        make_input("Ramp Duration (min)", "input-ramp-duration", "number", 60),
        make_input("Start Flow Rate (µL/min)", "input-start-flow", "number", 1000),
        make_input("End Flow Rate (µL/min)", "input-end-flow", "number", 333),
        make_input("Recording Interval (s)", "input-rec-interval", "number", 5),
    ], className="instrument-card"),

    html.Div([
        html.Div([_svg_icon(PUMP_ICON), html.H5("ISCO Pumps")], className="card-header"),
        make_input("ISCO Pump 1 COM Port", "input-isco1-port", "text", "COM3"),
        make_input("ISCO Pump 2 COM Port", "input-isco2-port", "text", "COM4"),
    ], className="instrument-card"),

    html.Div([
        html.Div([_svg_icon(PRESSURE_ICON), html.H5("Equilibar BPR")], className="card-header"),
        make_input("Equilibar COM Port", "input-equilibar-port", "text", "COM5"),
        make_input("Pressure Setpoint (psi)", "input-pressure-sp", "number", 100),
    ], className="instrument-card"),

    html.Div([
        html.Div([_svg_icon(GENERIC_ICON), html.H5("VICI Valves")], className="card-header"),
        make_input("Valve 1 COM Port", "input-valve1-port", "text", "COM6"),
        make_input("Valve 2 COM Port", "input-valve2-port", "text", "COM7"),
    ], className="instrument-card"),

    html.Div([
        html.Div([_svg_icon(GENERIC_ICON), html.H5("Vapourtec Platform")], className="card-header"),
        make_input("IP Address", "input-vapourtec-ip", "text", "192.168.0.100"),
        make_input("Port", "input-vapourtec-port", "number", 43344),
        make_input("Target Temperature (°C)", "input-vapourtec-temp", "number", 80),
    ], className="instrument-card"),

    html.Div([
        html.Div([_svg_icon(DATA_ICON), html.H5("Mettler Toledo React IR")], className="card-header"),
        make_input("OPC UA URL", "input-opc-url", "text", "opc.tcp://localhost:62552/iCOpcUaServer"),
        make_input("Node ID 1", "input-node-id1", "text", "ns=2;s=Local.iCIR.Probe1.Trends.Peak1.Value"),
        make_input("Node ID 2", "input-node-id2", "text", "ns=2;s=Local.iCIR.Probe1.Trends.Peak2.Value"),
    ], className="instrument-card"),

    html.Div([
        html.Div([_svg_icon(DATA_ICON), html.H5("Data Output")], className="card-header"),
        make_input("Save Directory", "input-save-dir", "text", "", "C:\\Data\\Experiment"),
        make_input("Filename", "input-filename", "text", "Run 1"),
    ], className="instrument-card"),

], width=4, className="sidebar-section", style={"maxHeight": "88vh", "overflowY": "auto", "paddingRight": "8px"})


# ─────────────────────────────────────────────────────────────────────────────
# Layout: Main Area (Indicators, Buttons, Plot)
# ─────────────────────────────────────────────────────────────────────────────
def indicator(label, id_):
    return dbc.Col(html.Div([
        html.Div(label, className="indicator-label"),
        html.Div("—", id=id_, className="indicator-value"),
    ], className="indicator-box"), md=4, lg=True)


main_area = dbc.Col([
    # Indicators
    html.Div([
        html.Div([_svg_icon(PRESSURE_ICON), html.H5("Live Indicators")], className="card-header"),
        dbc.Row([
            indicator("Pressure (psi)", "ind-pressure"),
            indicator("Valve 1 Pos", "ind-valve1"),
            indicator("Valve 2 Pos", "ind-valve2"),
        ]),
        dbc.Row([
            indicator("Reactor Temp (°C)", "ind-temp"),
            indicator("Min Res. Time (min)", "ind-min-res"),
            indicator("Max Res. Time (min)", "ind-max-res"),
        ]),
        dbc.Row([
            indicator("τ (min)", "ind-tau"),
            indicator("F(τ) (mL/min)", "ind-f-tau"),
            indicator("Experiment Timer", "ind-timer"),
        ]),
    ], className="instrument-card"),

    # Buttons
    html.Div([
        html.Div([_svg_icon(GENERIC_ICON), html.H5("Experiment Control")], className="card-header"),
        dbc.Row([
            dbc.Col(dbc.Button("Start Experiment", id="btn-start", n_clicks=0,
                               style={"backgroundColor": "#28a745", "borderColor": "#28a745", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Stop Experiment", id="btn-stop", n_clicks=0,
                               style={"backgroundColor": "#dc3545", "borderColor": "#dc3545", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
        ], className="mb-2"),
        html.Div("", id="exp-status-msg", className="status-msg"),
    ], className="instrument-card"),

    # Plot
    html.Div([
        html.Div([_svg_icon(DATA_ICON), html.H5("React IR Real-Time Data")], className="card-header"),
        dcc.Graph(id="ir-plot", style={"height": "380px"}),
    ], className="instrument-card"),

    # Interval
    dcc.Interval(id="interval-update", interval=2000, n_intervals=0),

], width=8)


# ─────────────────────────────────────────────────────────────────────────────
# Full Layout
# ─────────────────────────────────────────────────────────────────────────────
app.layout = html.Div([
    html.Div([html.H1("Dynamic Flow Experiment Controller"), html.P("Laboratory Automation")], className="app-titlebar"),
    dbc.Container([
        dbc.Row([sidebar, main_area], className="mt-3"),
    ], fluid=True),
    html.Div("Laboratory Automation", className="app-footer"),
])


# ─────────────────────────────────────────────────────────────────────────────
# Experiment Thread Logic
# ─────────────────────────────────────────────────────────────────────────────
def experiment_worker(params):
    """Background thread that runs the full experiment."""
    global isco1, isco2, equilibar, valve1, valve2
    global vapourtec_client, vapourtec_manual_control
    global opc_client, opc_node1, opc_node2, experiment_state

    reactor_vol = params["reactor_vol"]
    dead_vol = params["dead_vol"]
    pre_ramp_time = params["pre_ramp_time"]
    post_ramp_time = params["post_ramp_time"]
    ramp_duration_min = params["ramp_duration"]
    start_flow = params["start_flow"]
    end_flow = params["end_flow"]
    rec_interval = params["rec_interval"]
    save_dir = params["save_dir"]
    filename = params["filename"]

    # Derived
    ramp_duration_sec = ramp_duration_min * 60
    Q0 = start_flow  # µL/min
    Qend = end_flow
    rho = ((Qend / 1000.0) - (Q0 / 1000.0)) / ramp_duration_min  # mL/min per min
    min_res_time = reactor_vol / start_flow  # minutes
    max_res_time = reactor_vol / end_flow  # minutes

    experiment_state["min_res_time"] = min_res_time
    experiment_state["max_res_time"] = max_res_time
    experiment_state["node1_values"] = []
    experiment_state["node2_values"] = []
    experiment_state["time_values"] = []
    experiment_state["sample_count"] = 0

    data_records = []
    last_node1 = 0.0
    last_node2 = 0.0
    last_save_time = time.time()

    def update_status(msg):
        experiment_state["status_msg"] = msg

    def read_opc_values():
        nonlocal last_node1, last_node2
        n1, n2 = last_node1, last_node2
        if opc_client is not None and opc_node1 is not None and opc_node2 is not None:
            try:
                val1 = opc_node1.get_value()
                if val1 is not None and not (isinstance(val1, float) and math.isnan(val1)):
                    n1 = float(val1)
                    last_node1 = n1
            except Exception:
                n1 = last_node1
            try:
                val2 = opc_node2.get_value()
                if val2 is not None and not (isinstance(val2, float) and math.isnan(val2)):
                    n2 = float(val2)
                    last_node2 = n2
            except Exception:
                n2 = last_node2
        return n1, n2

    def read_pressure():
        if equilibar is not None:
            try:
                response = equilibar.get_response()
                if response:
                    p = equilibar.get_pressure(response)
                    experiment_state["pressure_reading"] = p
                    return p
            except Exception:
                pass
        return experiment_state["pressure_reading"]

    def read_valve_positions():
        if valve1 is not None:
            try:
                experiment_state["valve1_pos"] = valve1.get_current_position()
            except Exception:
                pass
        if valve2 is not None:
            try:
                experiment_state["valve2_pos"] = valve2.get_current_position()
            except Exception:
                pass

    def read_reactor_temp():
        if vapourtec_manual_control is not None:
            try:
                r4 = vapourtec_manual_control.getR4I()
                reactor = r4.getReactors()["1"]
                t = reactor.getTemperature()
                if t and t != -1000:
                    experiment_state["reactor_temp"] = t
            except Exception:
                pass

    def save_data_to_excel(records, force=False):
        nonlocal last_save_time
        now = time.time()
        if force or (now - last_save_time >= 900):  # every 15 min
            if records and save_dir:
                try:
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir)
                    filepath = os.path.join(save_dir, f"{filename}.xlsx")
                    cols = ["Time_s", "Phase", "Flow1_mL_min", "Flow2_mL_min", "tau_min", "F_tau_mL_min", "Node1", "Node2", "Pressure_psi"]
                    df = pd.DataFrame(records, columns=cols)
                    df.to_excel(filepath, index=False)
                    last_save_time = now
                except Exception as e:
                    experiment_state["error_msg"] = f"Save error: {e}"

    # ─── INITIALIZATION ─────────────────────────────────────────────────────
    try:
        update_status("Connecting instruments...")

        # ISCO Pump 1
        try:
            isco1 = TeledyneISCO(port=params["isco1_port"])
            isco1.connect()
            isco1.initialize()
            isco1.set_constantflow_mode()
            update_status("ISCO Pump 1 connected.")
        except Exception as e:
            experiment_state["error_msg"] = f"ISCO1 error: {e}"

        if stop_event.is_set():
            return

        # ISCO Pump 2
        try:
            isco2 = TeledyneISCO(port=params["isco2_port"])
            isco2.connect()
            isco2.initialize()
            isco2.set_constantflow_mode()
            update_status("ISCO Pump 2 connected.")
        except Exception as e:
            experiment_state["error_msg"] = f"ISCO2 error: {e}"

        if stop_event.is_set():
            return

        # Equilibar
        try:
            equilibar = Equilibar(port=params["equilibar_port"])
            equilibar.connect()
            update_status("Equilibar connected.")
        except Exception as e:
            experiment_state["error_msg"] = f"Equilibar error: {e}"

        if stop_event.is_set():
            return

        # VICI Valves
        try:
            valve1 = VICI(port=params["valve1_port"])
            valve1.connect()
            update_status("Valve 1 connected.")
        except Exception as e:
            experiment_state["error_msg"] = f"Valve1 error: {e}"

        try:
            valve2 = VICI(port=params["valve2_port"])
            valve2.connect()
            update_status("Valve 2 connected.")
        except Exception as e:
            experiment_state["error_msg"] = f"Valve2 error: {e}"

        if stop_event.is_set():
            return

        # Vapourtec
        try:
            if rs is not None:
                vapourtec_url = f"opc.tcp://{params['vapourtec_ip']}:{params['vapourtec_port']}"
                vapourtec_client = rs.RSeriesClient(vapourtec_url)
                vapourtec_client.connect()
                rseries_obj = vapourtec_client.getRSeries()
                vapourtec_manual_control = rseries_obj.getManualControl()
                update_status("Vapourtec connected.")
        except Exception as e:
            experiment_state["error_msg"] = f"Vapourtec error: {e}"

        if stop_event.is_set():
            return

        # Mettler Toledo OPC UA
        try:
            if OPCClient is not None and params["opc_url"]:
                opc_client = OPCClient(params["opc_url"])
                opc_client.connect()
                opc_node1 = opc_client.get_node(params["node_id1"])
                opc_node2 = opc_client.get_node(params["node_id2"])
                update_status("Mettler Toledo OPC connected.")
        except Exception as e:
            experiment_state["error_msg"] = f"OPC error: {e}"

        if stop_event.is_set():
            return

        # ─── SET INITIAL CONDITIONS ─────────────────────────────────────────
        update_status("Setting initial conditions...")

        # Set flowrates: Pump 1 = Start Flow / 1000 (mL/min), Pump 2 = (Start Flow / 5) / 1000
        flow1_ml = start_flow / 1000.0
        flow2_ml = (start_flow / 5.0) / 1000.0

        try:
            if isco1:
                isco1.set_flowrate(flow1_ml)
            if isco2:
                isco2.set_flowrate(flow2_ml)
        except Exception as e:
            experiment_state["error_msg"] = f"Set flow error: {e}"

        experiment_state["current_flow1"] = flow1_ml
        experiment_state["current_flow2"] = flow2_ml

        # Vapourtec: set temperature, start manual control
        try:
            if vapourtec_manual_control:
                r4 = vapourtec_manual_control.getR4I()
                reactor = r4.getReactors()["1"]
                reactor.setTemperature(params["vapourtec_temp"])
                vapourtec_manual_control.startManualControl()
        except Exception as e:
            experiment_state["error_msg"] = f"Vapourtec temp error: {e}"

        # Set valves to position 1
        try:
            if valve1:
                valve1.switch(1)
            if valve2:
                valve2.switch(1)
        except Exception as e:
            experiment_state["error_msg"] = f"Valve set error: {e}"

        # Set Equilibar pressure
        try:
            if equilibar:
                equilibar.set_setpoint(params["pressure_sp"])
        except Exception as e:
            experiment_state["error_msg"] = f"Equilibar set error: {e}"

        # Run pumps
        try:
            if isco1:
                isco1.run()
            if isco2:
                isco2.run()
        except Exception as e:
            experiment_state["error_msg"] = f"Pump run error: {e}"

        if stop_event.is_set():
            return

        # ─── PRE-RAMP PHASE ─────────────────────────────────────────────────
        experiment_state["phase"] = "pre_ramp"
        experiment_state["start_time"] = time.time()
        update_status("Pre-Ramp Steady State phase...")

        pre_ramp_elapsed = 0
        while pre_ramp_elapsed < pre_ramp_time and not stop_event.is_set():
            loop_start = time.time()
            experiment_state["elapsed_seconds"] = pre_ramp_elapsed

            # Read sensors
            read_pressure()
            read_valve_positions()
            read_reactor_temp()
            n1, n2 = read_opc_values()

            experiment_state["tau"] = min_res_time
            experiment_state["F_of_tau"] = (reactor_vol / 1000.0) / min_res_time if min_res_time > 0 else 0

            experiment_state["time_values"].append(pre_ramp_elapsed)
            experiment_state["node1_values"].append(n1)
            experiment_state["node2_values"].append(n2)

            data_records.append([pre_ramp_elapsed, "pre_ramp", flow1_ml, flow2_ml, min_res_time, experiment_state["F_of_tau"], n1, n2, experiment_state["pressure_reading"]])

            save_data_to_excel(data_records)

            sleep_time = max(0, rec_interval - (time.time() - loop_start))
            if stop_event.wait(timeout=sleep_time):
                break
            pre_ramp_elapsed += rec_interval

        if stop_event.is_set():
            experiment_state["phase"] = "cleanup"
            # Fall through to cleanup
            raise InterruptedError("Stopped by user")

        # ─── RAMP PHASE ─────────────────────────────────────────────────────
        experiment_state["phase"] = "ramp"
        update_status("Ramp phase - decreasing flowrates...")

        ramp_start_time = time.time()
        total_elapsed_at_ramp_start = pre_ramp_time
        sample_collection_started = False
        current_valve2_pos = 1
        collection_cycle_start = None
        collecting = False

        ramp_elapsed = 0
        while ramp_elapsed < ramp_duration_sec and not stop_event.is_set():
            loop_start = time.time()
            ramp_elapsed = time.time() - ramp_start_time
            total_elapsed = total_elapsed_at_ramp_start + ramp_elapsed
            experiment_state["elapsed_seconds"] = int(total_elapsed)

            # Linear interpolation of flowrate
            fraction = ramp_elapsed / ramp_duration_sec
            current_flow_ul = start_flow + (end_flow - start_flow) * fraction
            flow1_now = current_flow_ul / 1000.0
            flow2_now = (current_flow_ul / 5.0) / 1000.0

            try:
                if isco1:
                    isco1.set_flowrate(flow1_now)
                if isco2:
                    isco2.set_flowrate(flow2_now)
            except Exception:
                pass

            experiment_state["current_flow1"] = flow1_now
            experiment_state["current_flow2"] = flow2_now

            # Calculate tau, tf, F(tau)
            tm = ramp_elapsed / 60.0  # minutes into ramp

            try:
                Q0_ml = Q0 / 1000.0
                VD_ml = dead_vol / 1000.0
                VR_ml = reactor_vol / 1000.0

                # tf calculation
                term_a = Q0_ml / rho
                inner = ((Q0_ml / rho) - tm) ** 2 + (2 * VD_ml / rho)
                if inner < 0:
                    inner = 0
                tf = term_a + math.sqrt(inner)

                # tau calculation
                term1 = Q0_ml + (rho * tf)
                inner2 = term1 ** 2 - (2 * rho * VR_ml)
                if inner2 < 0:
                    inner2 = 0
                term2 = math.sqrt(inner2)
                if abs(rho) > 1e-12:
                    tau = (term1 - term2) / rho
                else:
                    tau = min_res_time

                if tau > max_res_time:
                    tau = max_res_time
                if tau < min_res_time:
                    tau = min_res_time

                F_of_tau = VR_ml / tau if tau > 0 else 0

                experiment_state["tau"] = tau
                experiment_state["F_of_tau"] = F_of_tau

            except Exception:
                tau = min_res_time
                F_of_tau = 0
                experiment_state["tau"] = tau
                experiment_state["F_of_tau"] = F_of_tau

            # Sample collection logic
            if tau >= min_res_time and not sample_collection_started:
                sample_collection_started = True
                collection_cycle_start = time.time()
                collecting = True
                current_valve2_pos = 1
                try:
                    if valve1:
                        valve1.switch(2)  # Collection position
                    if valve2:
                        valve2.switch(current_valve2_pos)
                except Exception:
                    pass
                experiment_state["sample_count"] = 1

            if sample_collection_started and experiment_state["sample_count"] <= 28:
                cycle_elapsed = time.time() - collection_cycle_start
                if collecting and cycle_elapsed >= 180:  # 3 minutes collection
                    collecting = False
                    try:
                        if valve1:
                            valve1.switch(1)  # Waste
                    except Exception:
                        pass
                elif not collecting and cycle_elapsed >= 300:  # 5 min total cycle
                    experiment_state["sample_count"] += 1
                    if experiment_state["sample_count"] <= 28:
                        current_valve2_pos += 1
                        collecting = True
                        collection_cycle_start = time.time()
                        try:
                            if valve1:
                                valve1.switch(2)
                            if valve2:
                                valve2.switch(current_valve2_pos)
                        except Exception:
                            pass

            # Read sensors
            read_pressure()
            read_valve_positions()
            read_reactor_temp()
            n1, n2 = read_opc_values()

            experiment_state["time_values"].append(int(total_elapsed))
            experiment_state["node1_values"].append(n1)
            experiment_state["node2_values"].append(n2)

            data_records.append([total_elapsed, "ramp", flow1_now, flow2_now, tau, F_of_tau, n1, n2, experiment_state["pressure_reading"]])
            save_data_to_excel(data_records)

            sleep_time = max(0, rec_interval - (time.time() - loop_start))
            if stop_event.wait(timeout=sleep_time):
                break

        if stop_event.is_set():
            raise InterruptedError("Stopped by user")

        # ─── POST-RAMP PHASE ────────────────────────────────────────────────
        experiment_state["phase"] = "post_ramp"
        update_status("Post-Ramp phase - holding minimum flowrate...")

        # Set to end flow
        flow1_end = end_flow / 1000.0
        flow2_end = (end_flow / 5.0) / 1000.0
        try:
            if isco1:
                isco1.set_flowrate(flow1_end)
            if isco2:
                isco2.set_flowrate(flow2_end)
        except Exception:
            pass

        experiment_state["current_flow1"] = flow1_end
        experiment_state["current_flow2"] = flow2_end

        post_ramp_start = time.time()
        total_at_post_start = total_elapsed_at_ramp_start + ramp_duration_sec

        post_elapsed = 0
        while post_elapsed < post_ramp_time and not stop_event.is_set():
            loop_start = time.time()
            post_elapsed = time.time() - post_ramp_start
            total_elapsed = total_at_post_start + post_elapsed
            experiment_state["elapsed_seconds"] = int(total_elapsed)
            experiment_state["tau"] = max_res_time
            experiment_state["F_of_tau"] = (reactor_vol / 1000.0) / max_res_time if max_res_time > 0 else 0

            # Continue sample collection
            if sample_collection_started and experiment_state["sample_count"] <= 28:
                cycle_elapsed = time.time() - collection_cycle_start
                if collecting and cycle_elapsed >= 180:
                    collecting = False
                    try:
                        if valve1:
                            valve1.switch(1)
                    except Exception:
                        pass
                elif not collecting and cycle_elapsed >= 300:
                    experiment_state["sample_count"] += 1
                    if experiment_state["sample_count"] <= 28:
                        current_valve2_pos += 1
                        collecting = True
                        collection_cycle_start = time.time()
                        try:
                            if valve1:
                                valve1.switch(2)
                            if valve2:
                                valve2.switch(current_valve2_pos)
                        except Exception:
                            pass

            read_pressure()
            read_valve_positions()
            read_reactor_temp()
            n1, n2 = read_opc_values()

            experiment_state["time_values"].append(int(total_elapsed))
            experiment_state["node1_values"].append(n1)
            experiment_state["node2_values"].append(n2)

            data_records.append([total_elapsed, "post_ramp", flow1_end, flow2_end, max_res_time, experiment_state["F_of_tau"], n1, n2, experiment_state["pressure_reading"]])
            save_data_to_excel(data_records)

            sleep_time = max(0, rec_interval - (time.time() - loop_start))
            if stop_event.wait(timeout=sleep_time):
                break

        if stop_event.is_set():
            raise InterruptedError("Stopped by user")

        experiment_state["phase"] = "cleanup"
        update_status("Experiment complete. Cleaning up...")

    except InterruptedError:
        update_status("Experiment stopped by user. Cleaning up...")
    except Exception as e:
        experiment_state["error_msg"] = f"Experiment error: {e}"
        update_status(f"Error: {e}")
    finally:
        # ─── CLEANUP ────────────────────────────────────────────────────────
        try:
            if isco1:
                isco1.stop()
                isco1.clearall()
                isco1.disconnect()
        except Exception:
            pass

        try:
            if isco2:
                isco2.stop()
                isco2.clearall()
                isco2.disconnect()
        except Exception:
            pass

        try:
            if vapourtec_manual_control:
                r4 = vapourtec_manual_control.getR4I()
                reactor = r4.getReactors()["1"]
                reactor.setTemperature(25)
                vapourtec_manual_control.stopAll()
            if vapourtec_client:
                vapourtec_client.disconnect()
        except Exception:
            pass

        try:
            if equilibar:
                equilibar.set_setpoint(0)
                equilibar.disconnect()
        except Exception:
            pass

        try:
            if valve1:
                valve1.switch(1)
                valve1.disconnect()
        except Exception:
            pass

        try:
            if valve2:
                valve2.switch(1)
                valve2.disconnect()
        except Exception:
            pass

        try:
            if opc_client:
                opc_client.disconnect()
        except Exception:
            pass

        # Final save
        save_data_to_excel(data_records, force=True)

        experiment_state["running"] = False
        experiment_state["phase"] = "done"
        update_status("Experiment finished and all instruments disconnected.")

        isco1 = None
        isco2 = None
        equilibar = None
        valve1 = None
        valve2 = None
        vapourtec_client = None
        vapourtec_manual_control = None
        opc_client = None
        opc_node1 = None
        opc_node2 = None


# ─────────────────────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────────────────────
@callback(
    Output("exp-status-msg", "children"),
    Input("btn-start", "n_clicks"),
    Input("btn-stop", "n_clicks"),
    State("input-reactor-vol", "value"),
    State("input-dead-vol", "value"),
    State("input-pre-ramp-time", "value"),
    State("input-post-ramp-time", "value"),
    State("input-ramp-duration", "value"),
    State("input-start-flow", "value"),
    State("input-end-flow", "value"),
    State("input-rec-interval", "value"),
    State("input-isco1-port", "value"),
    State("input-isco2-port", "value"),
    State("input-equilibar-port", "value"),
    State("input-pressure-sp", "value"),
    State("input-valve1-port", "value"),
    State("input-valve2-port", "value"),
    State("input-vapourtec-ip", "value"),
    State("input-vapourtec-port", "value"),
    State("input-vapourtec-temp", "value"),
    State("input-opc-url", "value"),
    State("input-node-id1", "value"),
    State("input-node-id2", "value"),
    State("input-save-dir", "value"),
    State("input-filename", "value"),
    prevent_initial_call=True,
)
def handle_start_stop(start_clicks, stop_clicks,
                      reactor_vol, dead_vol, pre_ramp_time, post_ramp_time,
                      ramp_duration, start_flow, end_flow, rec_interval,
                      isco1_port, isco2_port, equilibar_port, pressure_sp,
                      valve1_port, valve2_port, vapourtec_ip, vapourtec_port,
                      vapourtec_temp, opc_url, node_id1, node_id2,
                      save_dir, filename):
    global experiment_thread

    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    if triggered == "btn-start":
        if experiment_state["running"]:
            return "Experiment already running."

        # Validate critical inputs
        if not reactor_vol or not start_flow or not end_flow:
            return "Error: Please fill in all required parameters."

        stop_event.clear()
        experiment_state["running"] = True
        experiment_state["phase"] = "initializing"
        experiment_state["error_msg"] = ""
        experiment_state["status_msg"] = "Starting..."

        params = {
            "reactor_vol": float(reactor_vol),
            "dead_vol": float(dead_vol) if dead_vol else 100,
            "pre_ramp_time": float(pre_ramp_time) if pre_ramp_time else 600,
            "post_ramp_time": float(post_ramp_time) if post_ramp_time else 2700,
            "ramp_duration": float(ramp_duration) if ramp_duration else 60,
            "start_flow": float(start_flow),
            "end_flow": float(end_flow),
            "rec_interval": float(rec_interval) if rec_interval else 5,
            "isco1_port": isco1_port or "COM3",
            "isco2_port": isco2_port or "COM4",
            "equilibar_port": equilibar_port or "COM5",
            "pressure_sp": float(pressure_sp) if pressure_sp else 100,
            "valve1_port": valve1_port or "COM6",
            "valve2_port": valve2_port or "COM7",
            "vapourtec_ip": vapourtec_ip or "192.168.0.100",
            "vapourtec_port": int(vapourtec_port) if vapourtec_port else 43344,
            "vapourtec_temp": float(vapourtec_temp) if vapourtec_temp else 80,
            "opc_url": opc_url or "",
            "node_id1": node_id1 or "",
            "node_id2": node_id2 or "",
            "save_dir": save_dir or "",
            "filename": filename or "Run_1",
        }

        experiment_thread = threading.Thread(target=experiment_worker, args=(params,), daemon=True)
        experiment_thread.start()
        return "Experiment started. Initializing instruments..."

    elif triggered == "btn-stop":
        if not experiment_state["running"]:
            return "No experiment running."
        stop_event.set()
        return "Stop signal sent. Cleaning up..."

    raise PreventUpdate


@callback(
    Output("ind-pressure", "children"),
    Output("ind-valve1", "children"),
    Output("ind-valve2", "children"),
    Output("ind-temp", "children"),
    Output("ind-min-res", "children"),
    Output("ind-max-res", "children"),
    Output("ind-tau", "children"),
    Output("ind-f-tau", "children"),
    Output("ind-timer", "children"),
    Output("ir-plot", "figure"),
    Output("exp-status-msg", "children", allow_duplicate=True),
    Input("interval-update", "n_intervals"),
    prevent_initial_call=True,
)
def update_indicators(n):
    # Format timer
    elapsed = experiment_state["elapsed_seconds"]
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    secs = int(elapsed % 60)
    timer_str = f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # Build plot
    fig = go.Figure()
    if experiment_state["time_values"]:
        # Limit to last 500 points for performance
        t_vals = experiment_state["time_values"][-500:]
        n1_vals = experiment_state["node1_values"][-500:]
        n2_vals = experiment_state["node2_values"][-500:]

        # Convert time to minutes for display
        t_min = [t / 60.0 for t in t_vals]

        fig.add_trace(go.Scatter(
            x=t_min, y=n1_vals, mode="lines+markers",
            name="Node ID 1", line=dict(color="#2563EB", width=2),
            marker=dict(size=3)
        ))
        fig.add_trace(go.Scatter(
            x=t_min, y=n2_vals, mode="lines+markers",
            name="Node ID 2", line=dict(color="#1E293B", width=2),
            marker=dict(size=3)
        ))

    fig.update_layout(
        xaxis=dict(title="Time (min)", gridcolor="#D9D9D9", color="#1E293B"),
        yaxis=dict(title="Peak Value", gridcolor="#D9D9D9", color="#1E293B"),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font=dict(color="#1E293B"),
        legend=dict(x=0.01, y=0.99),
        margin=dict(l=50, r=20, t=30, b=50),
    )

    # Status message
    status = experiment_state["status_msg"]
    if experiment_state["error_msg"]:
        status = f"{status} | {experiment_state['error_msg']}"

    pressure_str = f"{experiment_state['pressure_reading']:.2f}" if isinstance(experiment_state['pressure_reading'], (int, float)) else "—"
    tau_str = f"{experiment_state['tau']:.3f}" if isinstance(experiment_state['tau'], (int, float)) else "—"
    f_tau_str = f"{experiment_state['F_of_tau']:.4f}" if isinstance(experiment_state['F_of_tau'], (int, float)) else "—"
    min_res_str = f"{experiment_state['min_res_time']:.3f}" if experiment_state['min_res_time'] else "—"
    max_res_str = f"{experiment_state['max_res_time']:.3f}" if experiment_state['max_res_time'] else "—"
    temp_str = f"{experiment_state['reactor_temp']:.1f}" if isinstance(experiment_state['reactor_temp'], (int, float)) and experiment_state['reactor_temp'] != 0 else "—"

    return (
        pressure_str,
        str(experiment_state["valve1_pos"]),
        str(experiment_state["valve2_pos"]),
        temp_str,
        min_res_str,
        max_res_str,
        tau_str,
        f_tau_str,
        timer_str,
        fig,
        status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050)