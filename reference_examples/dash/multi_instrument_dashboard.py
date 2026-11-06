import dash
from dash import dcc, html, Input, Output, State, ctx
import threading
import time
import os
import re
import pandas as pd
from azuraknauerserial import AzuraKnauerPump
from vicivalco import VICI, ValcoValveError
from equilibarpc import Equilibar, EquilibarError
import plotly.graph_objs as go
from DP9800Omega import DP9800
import rseriesopc as rs
from dash.exceptions import PreventUpdate

# Initialize the Dash app with tabs support
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Define global variables for Vapourtec
client = None
manual_control = None
vapourtec_flow_rate_a = 0
vapourtec_flow_rate_b = 0
pressure_a = 0
pressure_b = 0
vapourtec_reactor_temperatures = [0, 0, 0, 0]


# Global update interval variables (in milliseconds)
tab1_update_interval = 3000  # default 3 seconds

# Global variables
dp9800 = None
temp_monitoring = False
temperatures = [None] * 8
temp_update_interval = 5000  # 5 seconds in milliseconds
pump1 = None
pump1_flowrate = 0
valve = None
equilibar = None
current_pressure = None
recording = False
data = []
start_time = time.time()
run_number = 1
plotting_active = False
# Modify the plot_data structure to include separate timestamps for each plot
plot_data = {
    "pressure": {"timestamps": [], "data": []},
    "temperatures": {"timestamps": [], "data": [[] for _ in range(8)]},
    "vapourtec_temperatures": {"timestamps": [], "data": [[] for _ in range(4)]},
    "vapourtec_flowrates": {"timestamps": [], "A": [], "B": []}
}

current_valve_position = "N/A"
valve_monitoring = False

# Global variables for plotting status
plotting_pressure_active = False
plotting_temp_active = False
plotting_vapourtec_temp_active = False
plotting_vapourtec_flowrate_active = False
start_time_pressure = 0
start_time_omega = 0
start_time_vapourtec_temp = 0
start_time_vapourtec_flowrate = 0

recording_start_time = time.time()

# App layout with tabs
app.layout = html.Div([
    html.H1("Lab Automation Dashboard",
            style={"text-align": "center", "margin-bottom": "20px"}),
    dcc.Tabs([
        # Tab 1: Manual Control and Monitoring
        dcc.Tab(label='Manual Control and Monitoring', children=[

            # New Vapourtec Section
            html.Div([
                html.H1("Vapourtec System Control", style={"text-align": "center", "margin-bottom": "20px"}),

                # IP address and port input fields
                html.Div([
                    html.Div([
                        html.Label("IP Address:", style={"margin-right": "10px"}),
                        dcc.Input(id="ip-address", type="text", value="20.20.200.200", style={"border-radius": "5px", "padding": "5px"}),
                    ], style={"display": "inline-block", "margin-right": "20px"}),
                    html.Div([
                        html.Label("Port:", style={"margin-right": "10px"}),
                        dcc.Input(id="port", type="text", value="22222", style={"border-radius": "5px", "padding": "5px"}),
                    ], style={"display": "inline-block"}),
                ], style={"text-align": "center", "margin-bottom": "20px"}),

                # Start and Stop Manual Control buttons
                html.Div([
                    html.Button("Start Manual Control", id="start-manual-control", n_clicks=0, style={"border-radius": "5px", "padding": "5px 10px"}),
                    html.Button("Stop Manual Control", id="stop-manual-control", n_clicks=0, disabled=True, style={"border-radius": "5px", "padding": "5px 10px", "margin-left": "10px"}),
                ], style={"text-align": "center", "margin-bottom": "20px"}),

                # Wrapper for Pump A and Pump B
                html.Div([
                    # Pump A settings
                    html.Div([
                        html.H2("Pump A", style={"text-align": "center"}),
                        html.Div([
                            html.Div([
                                html.Label("Setpoint (ml/min):", style={"margin-right": "10px"}),
                                dcc.Input(id="pump-a-setpoint", type="number", value=0, min=0, step=0.01, style={"border-radius": "5px", "padding": "5px", "width": "100px"}),
                            ], style={"display": "inline-block", "margin-right": "20px"}),
                            html.Div([
                                html.Label("Actual Flow Rate (ml/min):", style={"margin-right": "10px"}),
                                html.Div(id="pump-a-flowrate", children="0", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                            ], style={"display": "inline-block"}),
                        ], style={"text-align": "center", "margin-bottom": "10px"}),
                        html.Div([
                            html.Button("Start Pump A", id="start-pump-a", n_clicks=0, style={"border-radius": "5px", "padding": "5px 10px"}),
                            html.Button("Stop Pump A", id="stop-pump-a", n_clicks=0, disabled=True, style={"border-radius": "5px", "padding": "5px 10px", "margin-left": "10px"}),
                            html.Button("Set Flowrate A", id="set-flowrate-a", n_clicks=0, style={"border-radius": "5px", "padding": "5px 10px", "margin-left": "10px"}),
                        ], style={"text-align": "center", "margin-bottom": "10px"}),
                        html.Div([
                            html.Div([
                                html.Label("Solvent/Reagent Valve:", style={"margin-right": "10px"}),
                                dcc.RadioItems(
                                    id="pump-a-sr-valve",
                                    options=[{"label": "Solvent", "value": False}, {"label": "Reagent", "value": True}],
                                    value=False,
                                    labelStyle={"display": "inline-block", "margin-right": "10px"}
                                ),
                                html.Div(id="pump-a-sr-valve-status", children="Solvent", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                            ], style={"display": "inline-block", "margin-right": "20px"}),
                            html.Div([
                                html.Label("Load/Inject Valve:", style={"margin-right": "10px"}),
                                dcc.RadioItems(
                                    id="pump-a-li-valve",
                                    options=[{"label": "Load", "value": False}, {"label": "Inject", "value": True}],
                                    value=False,
                                    labelStyle={"display": "inline-block", "margin-right": "10px"}
                                ),
                                html.Div(id="pump-a-li-valve-status", children="Load", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                            ], style={"display": "inline-block"}),
                        ], style={"text-align": "center", "margin-bottom": "20px"}),
                        html.Div([
                            html.Label("Pump A Pressure (bar):", style={"margin-right": "10px"}),
                            html.Div(id="pump-a-pressure", children="N/A", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                        ], style={"text-align": "center", "margin-bottom": "10px"}),
                    ], style={"width": "48%", "display": "inline-block", "vertical-align": "top", "border": "2px solid #888", "border-radius": "10px", "padding": "20px", "box-sizing": "border-box"}),
                    
                    # Pump B settings
                    html.Div([
                        html.H2("Pump B", style={"text-align": "center"}),
                        html.Div([
                            html.Div([
                                html.Label("Setpoint (ml/min):", style={"margin-right": "10px"}),
                                dcc.Input(id="pump-b-setpoint", type="number", value=0, min=0, step=0.01, style={"border-radius": "5px", "padding": "5px", "width": "100px"}),
                            ], style={"display": "inline-block", "margin-right": "20px"}),
                            html.Div([
                                html.Label("Actual Flow Rate (ml/min):", style={"margin-right": "10px"}),
                                html.Div(id="pump-b-flowrate", children="0", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                            ], style={"display": "inline-block"}),
                        ], style={"text-align": "center", "margin-bottom": "10px"}),
                        html.Div([
                            html.Button("Start Pump B", id="start-pump-b", n_clicks=0, style={"border-radius": "5px", "padding": "5px 10px"}),
                            html.Button("Stop Pump B", id="stop-pump-b", n_clicks=0, disabled=True, style={"border-radius": "5px", "padding": "5px 10px", "margin-left": "10px"}),
                            html.Button("Set Flowrate B", id="set-flowrate-b", n_clicks=0, style={"border-radius": "5px", "padding": "5px 10px", "margin-left": "10px"}),
                        ], style={"text-align": "center", "margin-bottom": "10px"}),
                        html.Div([
                            html.Div([
                                html.Label("Solvent/Reagent Valve:", style={"margin-right": "10px"}),
                                dcc.RadioItems(
                                    id="pump-b-sr-valve",
                                    options=[{"label": "Solvent", "value": False}, {"label": "Reagent", "value": True}],
                                    value=False,
                                    labelStyle={"display": "inline-block", "margin-right": "10px"}
                                ),
                                html.Div(id="pump-b-sr-valve-status", children="Solvent", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                            ], style={"display": "inline-block", "margin-right": "20px"}),
                            html.Div([
                                html.Label("Load/Inject Valve:", style={"margin-right": "10px"}),
                                dcc.RadioItems(
                                    id="pump-b-li-valve",
                                    options=[{"label": "Load", "value": False}, {"label": "Inject", "value": True}],
                                    value=False,
                                    labelStyle={"display": "inline-block", "margin-right": "10px"}
                                ),
                                html.Div(id="pump-b-li-valve-status", children="Load", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                            ], style={"display": "inline-block"}),
                        ], style={"text-align": "center", "margin-bottom": "20px"}),
                        html.Div([
                            html.Label("Pump B Pressure (bar):", style={"margin-right": "10px"}),
                            html.Div(id="pump-b-pressure", children="N/A", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                        ], style={"text-align": "center", "margin-bottom": "10px"}),
                    ], style={"width": "48%", "display": "inline-block", "vertical-align": "top", "border": "2px solid #888", "border-radius": "10px", "padding": "20px", "box-sizing": "border-box"})
                ], style={"text-align": "center", "margin-bottom": "20px", "border": "2px solid #888", "border-radius": "10px", "padding": "20px", "display": "flex", "justify-content": "space-between"}),

                # R4 Reactor Temperatures
                html.Div([
                    html.H2("R4 Reactor Module", style={"text-align": "center"}),
                    html.Div([
                        html.Div([
                            html.H4(f"Reactor {i+1} Settings", style={"text-align": "center"}),
                            html.Div([
                                html.Label("Setpoint (°C):", style={"margin-right": "10px"}),
                                dcc.Input(id=f"reactor-{i+1}-setpoint", type="number", placeholder=f"Setpoint Reactor {i+1} (°C)", value=0, style={"border-radius": "5px", "padding": "5px", "width": "100px"}),
                            ], style={"display": "inline-block", "margin-right": "20px"}),
                            html.Div([
                                html.Label("Actual Temperature (°C):", style={"margin-right": "10px"}),
                                html.Div(id=f"reactor-{i+1}-temperature", children="0", style={"display": "inline-block", "border-radius": "5px", "padding": "5px", "background-color": "#f0f0f0"}),
                            ], style={"display": "inline-block"}),
                        ], style={"width": "22%", "display": "inline-block", "vertical-align": "top"}) for i in range(4)
                    ], style={"text-align": "center", "margin-bottom": "20px", "display": "flex", "justify-content": "space-between"}),
                ], style={"border": "2px solid #888", "border-radius": "10px", "padding": "20px"})
            ], style={"margin-bottom": "20px"}),

            # Merged Section for Various Controls and Data Recording
            html.Div([
                html.H2("Control and Monitoring"),

                # Omega DP9800, Azura Knauer on left and VICI Valco, Equilibar, Data Recording on right
                html.Div([
                    # Left Column
                    html.Div([
                        html.H3("Omega DP9800 Temperature Monitoring"),
                        html.Label("COM Port:"),
                        dcc.Input(id="dp9800-com-port", type="text", placeholder="Enter COM Port (e.g., COM9)", value="COM5"),
                        html.Div([
                            html.Div([
                                html.H5(f"Channel {i + 1}"),
                                html.Div(f"Channel {i + 1} Temperature: ---", id=f"temp-channel-{i}-indicator",
                                        style={"margin-top": "10px"})
                            ], style={
                                "margin": "10px",
                                "padding": "10px",
                                "border": "1px solid #ddd",
                                "border-radius": "5px",
                                "width": "100%",
                                "text-align": "center"
                            }) for i in range(8)
                        ], style={"display": "flex", "justify-content": "space-between", "flex-wrap": "wrap"}),
                        html.Div([
                            html.Button("Start Temperature Monitoring", id="start-temp-button", n_clicks=0, disabled=False),
                            html.Button("Stop Temperature Monitoring", id="stop-temp-button", n_clicks=0, disabled=True),
                        ], style={"text-align": "center", "margin-top": "20px", "margin-bottom": "20px"}),
                    ], style={"width": "48%", "display": "inline-block", "vertical-align": "top"}),

                    # Right Column: Azura Knauer Pump, VICI Valco Valve, Equilibar, Data Recording
                    html.Div([
                        html.Div([
                            html.H3("Azura Knauer Pump Control (Serial)"),
                            html.Div([
                                html.H5("Pump 1 Settings"),
                                html.Label("COM Port:", style={"display": "block", "text-align": "center"}),
                                dcc.Input(id="pump1-com-port", type="text", placeholder="Enter COM Port", value= "COM8", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                                dcc.Input(id="pump1-flowrate", type="number", placeholder="Flowrate (mL/min)", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                                html.Label("Pump Head Size:", style={"display": "block", "text-align": "center"}),
                                dcc.Dropdown(
                                    id="pump1-head-size-tab1",
                                    options=[{"label": "10 mL", "value": "10"},
                                             {"label": "50 mL", "value": "50"}],
                                    placeholder="Select Pump Head Size",
                                    value="10",
                                    style={"margin-left": "auto", "margin-right": "auto", "display": "block", "width": "50%"}
                                ),
                                html.Div([
                                    html.Button("Start Pump 1", id="start-pump1-button", n_clicks=0, disabled=False),
                                    html.Button("Set Flowrate", id="set-pump1-button", n_clicks=0, disabled=True, style={"margin-left": "10px"}),
                                    html.Button("Stop Pump 1", id="stop-pump1-button", n_clicks=0, disabled=True, style={"margin-left": "10px"}),
                                ], style={"margin-top": "10px", "text-align": "center"}),
                            ], style={"margin": "10px", "padding": "10px", 
                                      "border": "1px solid #ddd", "border-radius": "10px", 
                                      "width": "100%", "text-align": "center"}),
                        ], style={"width": "100%", "margin-bottom": "20px"}),

                        # VICI Valco Valve Section
                        html.Div([
                            html.H3("VICI Valco Valve Control"),
                            html.Label("COM Port:", style={"display": "block", "text-align": "center"}),
                            dcc.Input(id="valve-port", type="text", placeholder="COM Port", value="COM7", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                            html.Div(id="current-valve-position", children="---", style={"margin-left": "auto", "margin-right": "auto", "display": "block", "margin-bottom": "10px"}),
                            html.Label("Position Setpoint:", style={"display": "block", "text-align": "center"}),
                            dcc.Input(id="valve-position", type="number", placeholder="Valve Position", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                            html.Div([
                                html.Button("Connect", id="connect-valve-button", n_clicks=0, disabled=False),
                                html.Button("Switch", id="switch-valve-button", n_clicks=0, disabled=True, style={"margin-left": "10px"}),
                                html.Button("Disconnect", id="disconnect-valve-button", n_clicks=0, disabled=True, style={"margin-left": "10px"}),
                            ], style={"text-align": "center", "margin-top": "20px"}),
                        ], style={"width": "100%", "margin-bottom": "20px", "border": "1px solid #ddd", "border-radius": "10px", "padding": "10px", "text-align": "center"}),

                        html.Div([
                            html.H3("Equilibar Pressure Controller"),
                            html.Label("COM Port:", style={"display": "block", "text-align": "center"}),
                            dcc.Input(id="equilibar-port", type="text", placeholder="COM Port", value="COM9", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                            html.Div(id="current-pressure", children="---", style={"margin-left": "auto", "margin-right": "auto", "display": "block", "margin-bottom": "10px"}),
                            html.Label("Pressure Setpoint:", style={"display": "block", "text-align": "center"}),
                            dcc.Input(id="pressure-setpoint", type="number", placeholder="Pressure Setpoint", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                            html.Div([
                                html.Button("Connect", id="connect-equilibar-button", n_clicks=0, disabled=False),
                                html.Button("Set", id="set-equilibar-button", n_clicks=0, disabled=True, style={"margin-left": "10px"}),
                                html.Button("Disconnect", id="disconnect-equilibar-button", n_clicks=0, disabled=True, style={"margin-left": "10px"}),
                            ], style={"text-align": "center", "margin-top": "20px"}),
                        ], style={"width": "100%", "margin-bottom": "20px", "border": "1px solid #ddd", "border-radius": "10px", "padding": "10px", "text-align": "center"}),

                        html.Div([
                            html.H3("Data Recording"),
                            html.Label("Directory:", style={"display": "block", "text-align": "center"}),
                            dcc.Input(id="directory-input", type="text", placeholder="Enter directory for saving excel data", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                            html.Label("File Name Prefix:", style={"display": "block", "text-align": "center"}),
                            dcc.Input(id="filename-prefix-input", type="text", placeholder="Enter file name prefix", style={"margin-left": "auto", "margin-right": "auto", "display": "block"}),
                            html.Div([
                                html.Button("Start Recording", id="start-recording-button", n_clicks=0, disabled=False),
                                html.Button("Stop Recording", id="stop-recording-button", n_clicks=0, disabled=True, style={"margin-left": "10px"}),
                            ], style={"text-align": "center", "margin-top": "20px"}),
                        ], style={"width": "100%", "border": "1px solid #ddd", "border-radius": "10px", "padding": "10px", "text-align": "center"}),
                    ], style={"width": "48%", "display": "inline-block", "vertical-align": "top", "margin-left": "2%"}),
                ], style={"margin-bottom": "40px", "border": "1px solid #ddd", "padding": "20px", "border-radius": "10px"}),

            ], style={"border": "2px solid #888", "border-radius": "10px", "padding": "20px", "margin-bottom": "20px"}),
                                      
            # Real-Time Plotting Section
            html.Div([
                html.H2("Real-Time Data Plotting"),
                html.Div([
                    # Pressure Plot
                    html.Div([
                        html.H5("Pressure Plot (Equilibar)"),
                        dcc.Graph(id="pressure-graph"),
                    ], style={"width": "100%", "padding": "10px"}),

                    # Temperature Plot
                    html.Div([
                        html.H5("Temperature Plot (OMEGA DP9800)"),
                        dcc.Graph(id="temp-plot"),
                    ], style={"width": "100%", "padding": "10px"}),

                    # Vapourtec Temperature Plot
                    html.Div([
                        html.H5("Reactor Temperatures (Vapourtec)"),
                        dcc.Graph(id="vapourtec-temp-plot"),
                    ], style={"width": "100%", "padding": "10px"}),

                    # Vapourtec Flowrate Plot
                    html.Div([
                        html.H5("Flow Rates (Vapourtec)"),
                        dcc.Graph(id="vapourtec-flowrate-plot"),
                    ], style={"width": "100%", "padding": "10px"}),

                    # Start and Stop Button
                    html.Div([
                        html.Button("Start Plotting", id="start-plot-button-all", n_clicks=0),
                        html.Button("Stop Plotting", id="stop-plot-button-all", n_clicks=0, disabled=True),
                    ], style={"text-align": "center", "margin-top": "10px"}),
                ], style={"border": "2px solid #888", "border-radius": "10px", "padding": "20px"}),

                # Interval components for handling real-time updates
                dcc.Interval(id="plot-interval", interval=tab1_update_interval, disabled=True),
                dcc.Interval(id="interval", interval=tab1_update_interval, n_intervals=0),
                dcc.Interval(id="equilibar-interval", interval=tab1_update_interval, disabled=True),
                dcc.Interval(id="valve-interval", interval=tab1_update_interval, disabled=True),
                dcc.Interval(id="temp-update-interval", interval=tab1_update_interval, disabled=True),
            ], style={"border": "2px solid #888", "border-radius": "10px", "padding": "20px"})
        ])
    ])
])




# Vapourtec Callbacks
@app.callback(
    [Output("start-manual-control", "disabled"),
     Output("stop-manual-control", "disabled")],
    [Input("start-manual-control", "n_clicks"),
     Input("stop-manual-control", "n_clicks")],
    [State("ip-address", "value"),
     State("port", "value")]
)
def start_stop_manual_control(start_clicks, stop_clicks, ip_address, port):
    global client, manual_control
    
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if trigger_id == "start-manual-control":
        try:
            client = rs.RSeriesClient(f"opc.tcp://{ip_address}:{port}")
            client.connect()
            manual_control = client.getRSeries().getManualControl()
            manual_control.startManualControl()
            return True, False
        except Exception as e:
            print(f"Error starting manual control: {e}")
            return False, True
    elif trigger_id == "stop-manual-control":
        if manual_control is not None:
            manual_control.stopAll()
        if client is not None:
            client.disconnect()
        client = None
        manual_control = None
        return False, True
    else:
        return False, True

# Callback for Pump A
@app.callback(
    [Output("start-pump-a", "disabled"),
     Output("stop-pump-a", "disabled"),
     Output("set-flowrate-a", "disabled")],
    [Input("start-pump-a", "n_clicks"),
     Input("stop-pump-a", "n_clicks"),
     Input("set-flowrate-a", "n_clicks")],
    [State("pump-a-setpoint", "value")]
)
def handle_pump_a(start_clicks, stop_clicks, set_flowrate_clicks, setpoint):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "start-pump-a":
        if manual_control is not None:
            pump_a = manual_control.getModule(0).getPumpA()
            return True, False, False
        else:
            return False, True, True
    elif trigger_id == "stop-pump-a":
        if manual_control is not None:
            pump_a = manual_control.getModule(0).getPumpA()
            pump_a.setFlowRate(0)
            return False, True, True
        else:
            return False, True, True
    elif trigger_id == "set-flowrate-a":
        if manual_control is not None:
            pump_a = manual_control.getModule(0).getPumpA()
            pump_a.setFlowRate(setpoint * 1000)
            return True, False, False
        else:
            return False, True, True
    else:
        return False, True, True

@app.callback(
    Output("pump-a-flowrate", "children"),
    Input("interval", "n_intervals")
)
def update_pump_a_flowrate(n):
    global vapourtec_flow_rate_a
    if manual_control is not None:
        try:
            pump_a = manual_control.getModule(0).getPumpA()
            flowrate = pump_a.getFlowRate() / 1000
            vapourtec_flow_rate_a = flowrate
            return f"{flowrate:.2f}"
        except Exception as e:
            print(f"Error reading Pump A flowrate: {e}")
            return "N/A"
    return "N/A"

@app.callback(
    Output("pump-a-sr-valve-status", "children"),
    [Input("pump-a-sr-valve", "value"),
     Input("interval", "n_intervals")]
)
def update_pump_a_sr_valve(valve_state, n):
    if manual_control is not None:
        pump_a = manual_control.getModule(0).getPumpA()
        pump_a.setSRValveState(valve_state)
        return "Reagent" if valve_state else "Solvent"
    else:
        return "Solvent"

@app.callback(
    Output("pump-a-li-valve-status", "children"),
    [Input("pump-a-li-valve", "value"),
     Input("interval", "n_intervals")]
)
def update_pump_a_li_valve(valve_state, n):
    if manual_control is not None:
        pump_a = manual_control.getModule(0).getPumpA()
        pump_a.setILValveState(valve_state)
        return "Inject" if valve_state else "Load"
    else:
        return "Load"

# Callback for Pump B
@app.callback(
    [Output("start-pump-b", "disabled"),
     Output("stop-pump-b", "disabled"),
     Output("set-flowrate-b", "disabled")],
    [Input("start-pump-b", "n_clicks"),
     Input("stop-pump-b", "n_clicks"),
     Input("set-flowrate-b", "n_clicks")],
    [State("pump-b-setpoint", "value")]
)
def handle_pump_b(start_clicks, stop_clicks, set_flowrate_clicks, setpoint):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "start-pump-b":
        if manual_control is not None:
            pump_b = manual_control.getModule(0).getPumpB()
            return True, False, False
        else:
            return False, True, True
    elif trigger_id == "stop-pump-b":
        if manual_control is not None:
            pump_b = manual_control.getModule(0).getPumpB()
            pump_b.setFlowRate(0)
            return False, True, True
        else:
            return False, True, True
    elif trigger_id == "set-flowrate-b":
        if manual_control is not None:
            pump_b = manual_control.getModule(0).getPumpB()
            pump_b.setFlowRate(setpoint * 1000)
            return True, False, False
        else:
            return False, True, True
    else:
        return False, True, True


@app.callback(
    Output("pump-b-flowrate", "children"),
    Input("interval", "n_intervals")
)
def update_pump_b_flowrate(n):
    global vapourtec_flow_rate_b
    if manual_control is not None:
        try:
            pump_b = manual_control.getModule(0).getPumpB()
            flowrate = pump_b.getFlowRate() / 1000
            vapourtec_flow_rate_b = flowrate
            return f"{flowrate:.2f}"
        except Exception as e:
            print(f"Error reading Pump B flowrate: {e}")
            return "N/A"
    return "N/A"

@app.callback(
    Output("pump-b-sr-valve-status", "children"),
    [Input("pump-b-sr-valve", "value"),
     Input("interval", "n_intervals")]
)
def update_pump_b_sr_valve(valve_state, n):
    if manual_control is not None:
        pump_b = manual_control.getModule(0).getPumpB()
        pump_b.setSRValveState(valve_state)
        return "Reagent" if valve_state else "Solvent"
    else:
        return "Solvent"

@app.callback(
    Output("pump-b-li-valve-status", "children"),
    [Input("pump-b-li-valve", "value"),
     Input("interval", "n_intervals")]
)
def update_pump_b_li_valve(valve_state, n):
    if manual_control is not None:
        pump_b = manual_control.getModule(0).getPumpB()
        pump_b.setILValveState(valve_state)
        return "Inject" if valve_state else "Load"
    else:
        return "Load"

# Callback to update pump pressures
@app.callback(
    [Output("pump-a-pressure", "children"),
     Output("pump-b-pressure", "children")],
    Input("interval", "n_intervals")
)
def update_pump_pressures(n):
    global pressure_a, pressure_b
    if manual_control is not None:
        try:
            pressure_a = manual_control.getModule(0).getPumpsPressures()[2]
            pressure_b = manual_control.getModule(0).getPumpsPressures()[1]
            return f"{pressure_a:.2f} bar", f"{pressure_b:.2f} bar"
        except Exception as e:
            print(f"Error reading pump pressures: {e}")
            return "N/A", "N/A"
    return "N/A", "N/A"


@app.callback(
    [Output(f"reactor-{i+1}-temperature", "children") for i in range(4)],
    Input("interval", "n_intervals")
)


def update_reactor_temperatures(n):
    global vapourtec_reactor_temperatures
    if manual_control is not None:
        reactors = [manual_control.getR4I().getReactors()[str(i+1)] for i in range(4)]
        try:
            temperatures = [reactor.getTemperature() for reactor in reactors]
            vapourtec_reactor_temperatures = [temp if temp != -1000 else "N/A" for temp in temperatures]
            return [f"{temp:.2f}" if temp != "N/A" else "N/A" for temp in vapourtec_reactor_temperatures]
        except Exception as e:
            print(f"Error reading reactor temperatures: {e}")
            return ["N/A"] * 4
    return ["N/A"] * 4


# Function to start monitoring temperatures from the DP9800 device
def monitor_temperatures(com_port):
    global dp9800, temp_monitoring, temperatures, tab1_update_interval
    try:
        dp9800 = DP9800(port=com_port)
        while temp_monitoring:
            try:
                # Read all 8 temperatures in one go
                temperatures = dp9800.read_all_temperatures()
            except Exception as e:
                print(f"Error reading temperatures: {e}")
                temperatures = [None] * 8  # Reset all to None on error
            time.sleep(tab1_update_interval / 1000)
    except Exception as e:
        print(f"Error initializing DP9800: {e}")
    finally:
        if dp9800:
            dp9800.disconnect()
            dp9800 = None
        temperatures = [None] * 8

@app.callback(
    [Output("start-temp-button", "disabled"),
     Output("stop-temp-button", "disabled"),
     Output("temp-update-interval", "disabled")],
    [Input("start-temp-button", "n_clicks"),
     Input("stop-temp-button", "n_clicks")],  # Removed connect-all and disconnect-all
    [State("dp9800-com-port", "value")]
)
def handle_temp_buttons(start_clicks, stop_clicks, com_port):
    global temp_monitoring
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else None

    if triggered_id not in ["start-temp-button", "stop-temp-button"]:
        return False, True, True  # Initial state

    start_clicks = start_clicks or 0
    stop_clicks = stop_clicks or 0

    if triggered_id == "start-temp-button":
        if not com_port:
            return False, True, True
        temp_monitoring = True
        threading.Thread(target=monitor_temperatures, args=(com_port,), daemon=True).start()
        return True, False, False

    elif triggered_id == "stop-temp-button":
        temp_monitoring = False
        return False, True, True

    return False, True, True

@app.callback(
    [Output(f"temp-channel-{i}-indicator", "children") for i in range(8)],
    [Input("temp-update-interval", "n_intervals")]
)
def update_temp_indicators(n):
    global temperatures
    return [
        f"Channel {i + 1} Temperature: {temperatures[i]:.2f}°C" if temperatures[i] is not None else f"Channel {i + 1} Temperature: ---"
        for i in range(8)
    ]


# Pump 1 Callback
@app.callback(
    [Output("start-pump1-button", "disabled"),
     Output("set-pump1-button", "disabled"),
     Output("stop-pump1-button", "disabled")],
    [Input("start-pump1-button", "n_clicks"),
     Input("set-pump1-button", "n_clicks"),
     Input("stop-pump1-button", "n_clicks")],
    [State("pump1-com-port", "value"),
     State("pump1-flowrate", "value"),
     State("pump1-head-size-tab1", "value")]
)
def handle_pump1(start_clicks, set_clicks, stop_clicks, com_port, flowrate, head_size):
    global pump1, pump1_flowrate
    ctx = dash.callback_context
    if not ctx.triggered:
        return False, True, True
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "start-pump1-button":
        try:
            pump1 = AzuraKnauerPump(com_port)
            pump1.connect()
            pump1.set_remote()
            head_type = int(head_size) if head_size else 10
            pump1.set_head_type(head_type)
            pump1_flowrate = float(flowrate) if flowrate is not None else 0
            pump1.set_flow(int(pump1_flowrate * 1000))  # Convert mL/min to μl/min
            pump1.start()
        except Exception as e:
            print(f"Error starting Pump 1: {e}")
        return True, False, False  # start disabled; set & stop enabled

    elif triggered_id == "set-pump1-button":
        try:
            new_flowrate = float(flowrate) if flowrate is not None else 0
            pump1.set_flow(int(new_flowrate * 1000))
            pump1_flowrate = new_flowrate
        except Exception as e:
            print(f"Error setting Pump 1 flowrate: {e}")
        return True, False, False

    elif triggered_id == "stop-pump1-button":
        try:
            pump1.set_flow(0)
            pump1.stop()
            pump1.set_local()
            pump1.disconnect()
            pump1_flowrate = 0
        except Exception as e:
            print(f"Error stopping Pump 1: {e}")
        return False, True, True  # start enabled; set & stop disabled

    return False, True, True

# Function to start monitoring the valve in a separate thread
def start_valve_monitoring():
    global valve, valve_monitoring, current_valve_position
    valve_monitoring = True
    while valve_monitoring:
        try:
            current_valve_position = valve.get_current_position().lstrip("CP0")
            time.sleep(1)
        except ValcoValveError as e:
            print(f"Error: {e}")
            valve_monitoring = False

# Valve Callbacks
@app.callback(
    [Output("connect-valve-button", "disabled"),
     Output("switch-valve-button", "disabled"),
     Output("disconnect-valve-button", "disabled"),
     Output("valve-interval", "disabled")],
    [Input("connect-valve-button", "n_clicks"),
     Input("switch-valve-button", "n_clicks"),
     Input("disconnect-valve-button", "n_clicks")],
    [State("valve-port", "value"), State("valve-position", "value")]
)
def handle_valve_buttons(connect_clicks, switch_clicks, disconnect_clicks, port, position):
    global valve, valve_monitoring
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "connect-valve-button":
        try:
            valve = VICI(port)
            valve.connect()
            valve_monitoring = True
            threading.Thread(target=start_valve_monitoring).start()
            return True, False, False, False  # enable connect; disable switch & disconnect; enable interval
        except ValcoValveError as e:
            print(f"Error: {e}")
            return False, True, True, True

    elif triggered_id == "switch-valve-button":
        try:
            valve.switch(position)
        except ValcoValveError as e:
            print(f"Error: {e}")
        return True, False, False, False  # enable connect; disable switch & disconnect; enable interval

    elif triggered_id == "disconnect-valve-button":
        valve_monitoring = False
        if valve:
            valve.disconnect()
        return False, True, True, True  # disable connect; enable switch & disconnect; disable interval

    return False, True, True, True  # default state


# Callback to update valve current position on the UI
@app.callback(
    Output("current-valve-position", "children"),
    [Input("valve-interval", "n_intervals")]
)
def update_valve_position(n):
    global current_valve_position
    return f"Current Position: {current_valve_position}" if current_valve_position else "Current Position: ---"


# Function to start monitoring the Equilibar in a separate thread
def start_equilibar_monitoring():
    global equilibar, equilibar_monitoring, current_pressure
    equilibar_monitoring = True
    while equilibar_monitoring:
        try:
            response = equilibar.get_response()
            current_pressure = equilibar.get_pressure(response)
            time.sleep(1)
        except EquilibarError as e:
            print(f"Error: {e}")
            equilibar_monitoring = False

# Equilibar Callbacks
@app.callback(
    [Output("connect-equilibar-button", "disabled"),
     Output("set-equilibar-button", "disabled"),
     Output("disconnect-equilibar-button", "disabled"),
     Output("equilibar-interval", "disabled")],
    [Input("connect-equilibar-button", "n_clicks"),
     Input("set-equilibar-button", "n_clicks"),
     Input("disconnect-equilibar-button", "n_clicks")],
    [State("equilibar-port", "value"), State("pressure-setpoint", "value")]
)
def handle_equilibar_buttons(connect_clicks, set_clicks, disconnect_clicks, port, setpoint):
    global equilibar, equilibar_monitoring
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "connect-equilibar-button":
        try:
            equilibar = Equilibar(port)
            equilibar.connect()
            equilibar_monitoring = True
            threading.Thread(target=start_equilibar_monitoring).start()
            return True, False, False, False  # enable connect; disable set & disconnect; enable interval
        except EquilibarError as e:
            print(f"Error: {e}")
            return False, True, True, True

    elif triggered_id == "set-equilibar-button":
        try:
            equilibar.set_setpoint(setpoint)
        except EquilibarError as e:
            print(f"Error: {e}")
        return True, False, False, False  # enable connect; disable set & disconnect; enable interval

    elif triggered_id == "disconnect-equilibar-button":
        equilibar_monitoring = False
        if equilibar:
            equilibar.disconnect()
        return False, True, True, True  # disable connect; enable set & disconnect; disable interval

    return False, True, True, True  # default state

# Callback to update Equilibar current pressure on the UI
@app.callback(
    Output("current-pressure", "children"),
    [Input("equilibar-interval", "n_intervals")]
)
def update_pressure(n):
    global current_pressure
    return f"Current Pressure: {current_pressure} psi" if current_pressure else "Current Pressure: ---"


# Function to start recording data in a separate thread
def start_recording_thread(directory, filename_prefix):
    global recording, data, run_number, recording_start_time
    global vapourtec_flow_rate_a, vapourtec_flow_rate_b, pressure_a, pressure_b
    global vapourtec_reactor_temperatures, temperatures, current_valve_position

    if not os.path.exists(directory):
        os.makedirs(directory)

    while recording:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

        # Collect data
        flowrate1 = pump1_flowrate if pump1_flowrate is not None else "N/A"
        pressure = current_pressure if current_pressure is not None else "N/A"
        vapourtec_flow_a = vapourtec_flow_rate_a if vapourtec_flow_rate_a is not None else "N/A"
        vapourtec_flow_b = vapourtec_flow_rate_b if vapourtec_flow_rate_b is not None else "N/A"
        reactor_temps = [vapourtec_reactor_temperatures[i] if vapourtec_reactor_temperatures[i] is not None else "N/A" for i in range(4)]
        dp9800_temps = [temperatures[i] if temperatures[i] is not None else "N/A" for i in range(8)]
        valve_position = current_valve_position if current_valve_position is not None else "N/A"
        pump_a_pressure = pressure_a if pressure_a is not None else "N/A"
        pump_b_pressure = pressure_b if pressure_b is not None else "N/A"

        data.append([timestamp, flowrate1, pressure, vapourtec_flow_a, vapourtec_flow_b, valve_position] + reactor_temps + dp9800_temps + [pump_a_pressure, pump_b_pressure])

        # Save to excel if data exceeds 1 minute
        if (time.time() - recording_start_time) >= 60:
            save_data_to_excel(directory, run_number, filename_prefix, append=True)
            data.clear()
            recording_start_time = time.time()

        time.sleep(tab1_update_interval / 1000)
        

@app.callback(
    [Output("start-recording-button", "disabled"),
     Output("stop-recording-button", "disabled")],
    [Input("start-recording-button", "n_clicks"),
     Input("stop-recording-button", "n_clicks")],
    [State("directory-input", "value"),
     State("filename-prefix-input", "value")]
)
def handle_recording_buttons(start_clicks, stop_clicks, directory, filename_prefix):
    global recording, data, run_number, recording_start_time
    
    if not filename_prefix:
        filename_prefix = "Run"
    
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else None

    if triggered_id == "start-recording-button":
        recording_start_time = time.time()
        if not directory:
            return False, True  # No directory specified

        if not recording:
            run_number = get_next_run_number(directory, filename_prefix)
            data = []  # Clear the data list at the start of recording
            recording_start_time = time.time()

        recording = True
        threading.Thread(target=start_recording_thread, args=(directory, filename_prefix)).start()
        return True, False

    elif triggered_id == "stop-recording-button":
        recording = False
        save_data_to_excel(directory, run_number, filename_prefix, append=True)
        return False, True

    return False, True

        

def save_data_to_excel(directory, run_number, filename_prefix, append=False):
    file_path = os.path.join(directory, f"{filename_prefix}_{run_number}.xlsx")

    columns = ['Timestamp', 'Kanuer Pump Flowrate', 'Pressure', 'Vapourtec Flow Rate A', 'Vapourtec Flow Rate B', 'Valve Position',
               'Reactor 1 Temp', 'Reactor 2 Temp', 'Reactor 3 Temp', 'Reactor 4 Temp',
               'DP9800 Temp 1', 'DP9800 Temp 2', 'DP9800 Temp 3', 'DP9800 Temp 4', 'DP9800 Temp 5', 'DP9800 Temp 6', 'DP9800 Temp 7', 'DP9800 Temp 8', 'pump_A_pressure', 'pump_B_pressure']
    new_data = pd.DataFrame(data, columns=columns)
    new_data = new_data.fillna('N/A')

    if append and os.path.exists(file_path):
        existing_data = pd.read_excel(file_path)
        existing_data = existing_data.fillna('N/A')
        df = pd.concat([existing_data, new_data], ignore_index=True)
    else:
        df = new_data

    df.to_excel(file_path, index=False)
    print(f"Data saved to {file_path}")


def get_next_run_number(directory, filename_prefix):
    existing_files = os.listdir(directory)
    run_numbers = [int(re.search(rf'{filename_prefix}_(\d+)\.xlsx', file).group(1)) 
                   for file in existing_files if re.search(rf'{filename_prefix}_(\d+)\.xlsx', file)]
    return max(run_numbers, default=0) + 1



@app.callback(
    [Output("start-plot-button-all", "disabled"),
     Output("stop-plot-button-all", "disabled"),
     Output("plot-interval", "disabled"),
     Output("pressure-graph", "figure"),
     Output("temp-plot", "figure"),
     Output("vapourtec-temp-plot", "figure"),
     Output("vapourtec-flowrate-plot", "figure")],
    [Input("start-plot-button-all", "n_clicks"),
     Input("stop-plot-button-all", "n_clicks"),
     Input("plot-interval", "n_intervals")]
)
def update_plots(start_clicks, stop_clicks, n_intervals):
    global plotting_active, current_pressure, plot_data, vapourtec_reactor_temperatures
    global vapourtec_flow_rate_a, vapourtec_flow_rate_b, temperatures
    global start_time

    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Initialize default return values
    pressure_figure = go.Figure()
    temp_figure = go.Figure()
    vapourtec_temp_figure = go.Figure()
    vapourtec_flowrate_figure = go.Figure()

    start_plot_all_disabled = False
    stop_plot_all_disabled = True
    plot_interval_disabled = True

    if triggered_id == "start-plot-button-all":
        start_time = time.time()
        plotting_active = True
        plot_data["pressure"]["timestamps"].clear()
        plot_data["pressure"]["data"].clear()
        plot_data["temperatures"]["timestamps"].clear()
        for i in range(len(plot_data["temperatures"]["data"])):
            plot_data["temperatures"]["data"][i].clear()
        plot_data["vapourtec_temperatures"]["timestamps"].clear()
        for i in range(len(plot_data["vapourtec_temperatures"]["data"])):
            plot_data["vapourtec_temperatures"]["data"][i].clear()
        plot_data["vapourtec_flowrates"]["timestamps"].clear()
        plot_data["vapourtec_flowrates"]["A"].clear()
        plot_data["vapourtec_flowrates"]["B"].clear()

    elif triggered_id == "stop-plot-button-all":
        plotting_active = False

    if plotting_active:
        # Append data for pressure
        current_time = time.time() - start_time
        plot_data["pressure"]["timestamps"].append(current_time)
        plot_data["pressure"]["data"].append(current_pressure if current_pressure is not None else 0)

        # Append data for temperatures
        plot_data["temperatures"]["timestamps"].append(current_time)
        for i in range(len(plot_data["temperatures"]["data"])):
            plot_data["temperatures"]["data"][i].append(temperatures[i] if temperatures[i] is not None else 0)

        # Append data for Vapourtec temperatures
        plot_data["vapourtec_temperatures"]["timestamps"].append(current_time)
        for i in range(len(plot_data["vapourtec_temperatures"]["data"])):
            plot_data["vapourtec_temperatures"]["data"][i].append(vapourtec_reactor_temperatures[i] if vapourtec_reactor_temperatures[i] is not None else 0)

        # Append data for Vapourtec flowrates
        plot_data["vapourtec_flowrates"]["timestamps"].append(current_time)
        plot_data["vapourtec_flowrates"]["A"].append(vapourtec_flow_rate_a if vapourtec_flow_rate_a is not None else 0)
        plot_data["vapourtec_flowrates"]["B"].append(vapourtec_flow_rate_b if vapourtec_flow_rate_b is not None else 0)

        # Create figures for plots
        pressure_figure = {
            'data': [
                go.Scatter(
                    x=plot_data["pressure"]["timestamps"],
                    y=plot_data["pressure"]["data"],
                    mode='lines+markers',
                    name='Pressure'
                )
            ],
            'layout': {
                'title': 'Real-Time Pressure Data',
                'xaxis': {'title': 'Time'},
                'yaxis': {'title': 'Pressure (psi)'},
            }
        }

        temp_traces = [
            go.Scatter(
                x=plot_data["temperatures"]["timestamps"],
                y=plot_data["temperatures"]["data"][i],
                mode='lines+markers',
                name=f"Temperature {i + 1}"
            )
            for i in range(len(plot_data["temperatures"]["data"])-5)
        ]
        temp_figure = {
            'data': temp_traces,
            'layout': {
                'title': 'Real-Time Temperature Data (Omega DP9800)',
                'xaxis': {'title': 'Time'},
                'yaxis': {'title': 'Temperature (°C)'},
            }
        }

        vapourtec_temp_traces = [
            go.Scatter(
                x=plot_data["vapourtec_temperatures"]["timestamps"],
                y=plot_data["vapourtec_temperatures"]["data"][i],
                mode='lines+markers',
                name=f"Reactor {i + 1} Temp"
            )
            for i in range(len(plot_data["vapourtec_temperatures"]["data"]))
        ]
        vapourtec_temp_figure = {
            'data': vapourtec_temp_traces,
            'layout': {
                'title': 'Real-Time Reactor Temperatures (Vapourtec)',
                'xaxis': {'title': 'Time'},
                'yaxis': {'title': 'Temperature (°C)'},
            }
        }

        vapourtec_flowrate_traces = [
            go.Scatter(
                x=plot_data["vapourtec_flowrates"]["timestamps"],
                y=plot_data["vapourtec_flowrates"]["A"],
                mode='lines+markers',
                name='Flow Rate A'
            ),
            go.Scatter(
                x=plot_data["vapourtec_flowrates"]["timestamps"],
                y=plot_data["vapourtec_flowrates"]["B"],
                mode='lines+markers',
                name='Flow Rate B'
            )
        ]
        vapourtec_flowrate_figure = {
            'data': vapourtec_flowrate_traces,
            'layout': {
                'title': 'Real-Time Flow Rates (Vapourtec)',
                'xaxis': {'title': 'Time'},
                'yaxis': {'title': 'Flow Rate (ul/min)'},
            }
        }

        start_plot_all_disabled = True
        stop_plot_all_disabled = False
        plot_interval_disabled = False

    return [start_plot_all_disabled, stop_plot_all_disabled, plot_interval_disabled, pressure_figure,
            temp_figure, vapourtec_temp_figure, vapourtec_flowrate_figure]



if __name__ == "__main__":
    app.run (debug=True)









# Modify the data recording function to include pump pressures
def start_recording_thread(directory, filename_prefix):
    global recording, data, run_number, recording_start_time
    global vapourtec_flow_rate_a, vapourtec_flow_rate_b
    global vapourtec_reactor_temperatures, temperatures, current_valve_position

    if not os.path.exists(directory):
        os.makedirs(directory)

    while recording:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

        # Collect data
        flowrate1 = pump1_flowrate if pump1_flowrate is not None else "N/A"
        pressure = current_pressure if current_pressure is not None else "N/A"
        vapourtec_flow_a = vapourtec_flow_rate_a if vapourtec_flow_rate_a is not None else "N/A"
        vapourtec_flow_b = vapourtec_flow_rate_b if vapourtec_flow_rate_b is not None else "N/A"
        reactor_temps = [vapourtec_reactor_temperatures[i] if vapourtec_reactor_temperatures[i] is not None else "N/A" for i in range(4)]
        dp9800_temps = [temperatures[i] if temperatures[i] is not None else "N/A" for i in range(8)]
        valve_position = current_valve_position if current_valve_position is not None else "N/A"
        pump_a_pressure = manual_control.getModule(0).getPumpsPressures()[2] if manual_control is not None else "N/A"
        pump_b_pressure = manual_control.getModule(0).getPumpsPressures()[1] if manual_control is not None else "N/A"

        data.append([timestamp, flowrate1, pressure, vapourtec_flow_a, vapourtec_flow_b, valve_position] + reactor_temps + dp9800_temps + [pump_a_pressure, pump_b_pressure])

        # Save to excel if data exceeds 1 minute
        if (time.time() - recording_start_time) >= 60:
            save_data_to_excel(directory, run_number, filename_prefix, append=True)
            data.clear()
            recording_start_time = time.time()

        time.sleep(tab1_update_interval / 1000)

