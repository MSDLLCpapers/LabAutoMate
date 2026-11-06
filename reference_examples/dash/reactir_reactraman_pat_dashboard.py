import dash 
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import pandas as pd
import os
from scipy.integrate import trapezoid
import plotly.graph_objs as go
from threading import Thread, Event
import asyncio
from asyncua import Client
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Real-Time ReactIR and ReactRaman PAT Visualization Dashboard"

# Separate lists for each data stream and other necessary variables
time_data = []
ir_upstream_965 = []
ir_downstream_965 = []
ir_upstream_969 = []
ir_downstream_969 = []
ir_upstream_1012 = []
ir_downstream_1012 = []
ir_area_ratio = []
raman_4_methylpiperidine = []
raman_adduct = []
raman_fmoc = []
raman_4_methylpiperidine_area = []
raman_adduct_area = []
raman_fmoc_area = []

# Plot-specific lists
time_data_plot = []
ir_upstream_965_plot = []
ir_downstream_965_plot = []
ir_upstream_969_plot = []
ir_downstream_969_plot = []
ir_upstream_1012_plot = []
ir_downstream_1012_plot = []
ir_area_ratio_plot = []
raman_4_methylpiperidine_plot = []
raman_adduct_plot = []
raman_fmoc_plot = []
raman_4_methylpiperidine_area_plot = []
raman_adduct_area_plot = []
raman_fmoc_area_plot = []

# Track the last save index to only save new data
last_save_index = 0
upstream_peak_965_data = []
downstream_peak_965_data = []

raman_peak_data_4Methylpiperidine = []
raman_peak_data_Adduct = []
raman_peak_data_Fmoc = []

peak_complete = {
    "upstream": False,
    "downstream": False,
}

cancel_event = Event()

# Constants for periodic save and update intervals
update_interval = 10 # seconds
save_interval = 1200 # 20 minutes

# App layout with user feedback div
app.layout = html.Div([
    html.H1("Real-Time ReactIR and ReactRaman PAT Visualization Dashboard", style={'text-align': 'center'}),
    dbc.Row([
        dbc.Col(html.Div([
            html.Label("OPC UA Server URL:"),
            dcc.Input(id="opc-url", type="text", placeholder="Enter OPC UA Server URL", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Upstream IR Node ID (965 cm⁻¹):"),
            dcc.Input(id="upstream-node-id-965", type="text", placeholder="Enter Node ID", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Downstream IR Node ID (965 cm⁻¹):"),
            dcc.Input(id="downstream-node-id-965", type="text", placeholder="Enter Node ID", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Upstream IR Node ID (969 cm⁻¹):"),
            dcc.Input(id="upstream-node-id-969", type="text", placeholder="Enter Node ID", debounce=True)
        ]))
    ]),

    dbc.Row([
        dbc.Col(html.Div([
            html.Label("Downstream IR Node ID (969 cm⁻¹):"),
            dcc.Input(id="downstream-node-id-969", type="text", placeholder="Enter Node ID", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Upstream IR Node ID (1012 cm⁻¹):"),
            dcc.Input(id="upstream-node-id-1012", type="text", placeholder="Enter Node ID", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Downstream IR Node ID (1012 cm⁻¹):"),
            dcc.Input(id="downstream-node-id-1012", type="text", placeholder="Enter Node ID", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("4-Methylpiperidine Node ID:"),
            dcc.Input(id="methylpiperidine-node-id", type="text", placeholder="Enter Node ID", debounce=True)
        ]))
        
    ]),

    dbc.Row([
        dbc.Col(html.Div([
            html.Label("Adduct Node ID:"),
            dcc.Input(id="adduct-node-id", type="text", placeholder="Enter Node ID", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("F-moc Node ID:"),
            dcc.Input(id="f-moc-node-id", type="text", placeholder="Enter Node ID", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Save Directory:"),
            dcc.Input(id="save-dir", type="text", placeholder="Enter save directory path", debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Upstream Threshold (965 cm⁻¹):"),
            dcc.Input(id="upstream-threshold", type="number", placeholder="e.g., 0.02", value=0.02, debounce=True)
        ]))
    ]),

    dbc.Row([
        dbc.Col(html.Div([
            html.Label("Downstream Threshold (965 cm⁻¹):"),
            dcc.Input(id="downstream-threshold", type="number", placeholder="e.g. 0.02", value=0.02, debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("4-Methylpiperidine Threshold:"),
            dcc.Input(id="methylpiperidine-threshold", type="number", placeholder="e.g. 100", value=100, debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("Adduct Threshold:"),
            dcc.Input(id="adduct-threshold", type="number", placeholder="e.g., 100", value=100, debounce=True)
        ])),
        dbc.Col(html.Div([
            html.Label("F-moc Threshold:"),
            dcc.Input(id="f-moc-threshold", type="number", placeholder="e.g. 100", value=100, debounce=True)
        ]))
    ]),
  
    html.Br(),
    html.Div(id='input-warning', style={'color': 'red', 'text-align': 'center'}),
    dbc.Row([
        dbc.Col(dbc.Button("Run", id="run-button", color="success", disabled=False)),
        dbc.Col(dbc.Button("Stop", id="stop-button", color="danger", disabled=True))
    ]),
    html.Br(),
    dbc.Row([
        dbc.Col([
            html.Div("Upstream & Downstream IR Peak Tracking (965 cm⁻¹)", className="plot-title-box"),
            dcc.Graph(id="ir-plot-965")
        ], width=6),
        dbc.Col([
            html.Div("IR Area Ratio (Downstream/Upstream)", className="plot-title-box"),
            dcc.Graph(id="area-ratio-plot")
        ], width=6),
    ]),
    dbc.Row([
        dbc.Col([
            html.Div("Upstream & Downstream IR Peak Tracking (969 cm⁻¹)", className="plot-title-box"),
            dcc.Graph(id="ir-plot-969")
        ], width=6),
        dbc.Col([
            html.Div("Upstream & Downstream IR Peak Tracking (1012 cm⁻¹)", className="plot-title-box"),
            dcc.Graph(id="ir-plot-1012")
        ], width=6),
    ]),
    dbc.Row([
        dbc.Col([
            html.Div("Raman Tracking: 4-Methylpiperidine, Adduct, F-moc", className="plot-title-box"),
            dcc.Graph(id="raman-plot")
        ], width=6),
        dbc.Col([
            html.Div("4-Methylpiperidine Peak Area", className="plot-title-box"),
            dcc.Graph(id="methylpiperidine-area-plot")
        ], width=6),
    ]),
    dbc.Row([
        dbc.Col([
            html.Div("Adduct Peak Area", className="plot-title-box"),
            dcc.Graph(id="adduct-area-plot")
        ], width=6),
        dbc.Col([
            html.Div("F-moc Peak Area", className="plot-title-box"),
            dcc.Graph(id="f-moc-area-plot")
        ], width=6),
    ]),
    dcc.Interval(id="data-update-interval", interval=update_interval * 1000, n_intervals=0, disabled=True)
])

async def async_opcua_data_fetch(server_url, node_ids, thresholds, save_directory):
    global time_data, ir_upstream_965, ir_downstream_965, ir_upstream_969, ir_downstream_969, ir_upstream_1012, ir_downstream_1012, ir_area_ratio, raman_4_methylpiperidine, raman_adduct, raman_fmoc
    global raman_4_methylpiperidine_area, raman_adduct_area, raman_fmoc_area, current_time, last_save_time

    client = Client(server_url)
    try:
        await client.connect()
        logging.info("Connected to OPC UA server.")
        nodes = {name: client.get_node(node_id) for name, node_id in node_ids.items() if node_id}


        while not cancel_event.is_set():
            values = {}
            
            for name, node in nodes.items():
                try:
                    values[name] = await node.read_value()
                except Exception as e:
                    logging.warning(f"Error reading value from node {name}: {e}")
                    values[name] = "N/A"

            current_time += update_interval
            
            time_data.append(current_time)
            time_data_plot.append(current_time)
            
            ir_upstream_965.append(values.get("upstream_965", "N/A"))
            ir_upstream_965_plot.append(values.get("upstream_965", "N/A"))
            
            ir_downstream_965.append(values.get("downstream_965", "N/A"))
            ir_downstream_965_plot.append(values.get("downstream_965", "N/A"))

            ir_upstream_969.append(values.get("upstream_969", "N/A"))
            ir_upstream_969_plot.append(values.get("upstream_969", "N/A"))

            ir_downstream_969.append(values.get("downstream_969", "N/A"))
            ir_downstream_969_plot.append(values.get("downstream_969", "N/A"))

            ir_upstream_1012.append(values.get("upstream_1012", "N/A"))
            ir_upstream_1012_plot.append(values.get("upstream_1012", "N/A"))

            ir_downstream_1012.append(values.get("downstream_1012", "N/A"))
            ir_downstream_1012_plot.append(values.get("downstream_1012", "N/A"))
            
            raman_4_methylpiperidine.append(values.get("4-Methylpiperidine", "N/A"))
            raman_4_methylpiperidine_plot.append(values.get("4-Methylpiperidine", "N/A"))
            
            raman_adduct.append(values.get("Adduct", "N/A"))
            raman_adduct_plot.append(values.get("Adduct", "N/A"))
            
            raman_fmoc.append(values.get("F-moc", "N/A"))
            raman_fmoc_plot.append(values.get("F-moc", "N/A"))
            

            # IR Area Ratio Calculation Logic
            if values["upstream_965"] != "N/A" and values["upstream_965"] >= thresholds["upstream"]:
                upstream_peak_965_data.append(values["upstream_965"])
                peak_complete["upstream"] = False
            elif upstream_peak_965_data and values["upstream_965"] != "N/A" and values["upstream_965"] < thresholds["upstream"]:
                upstream_area = trapezoid(upstream_peak_965_data, dx=1)
                upstream_peak_965_data.clear()
                peak_complete["upstream"] = True


            if values["downstream_965"] != "N/A" and values["downstream_965"] >= thresholds["downstream"]:
                downstream_peak_965_data.append(values["downstream_965"])
                peak_complete["downstream"] = False
            elif downstream_peak_965_data and values["downstream_965"] != "N/A" and values["downstream_965"] < thresholds["downstream"]:
                downstream_area = trapezoid(downstream_peak_965_data, dx=1)
                downstream_peak_965_data.clear()
                peak_complete["downstream"] = True



            if peak_complete["upstream"] and peak_complete["downstream"]:
                area_ratio = downstream_area / upstream_area if upstream_area != 0 else "N/A"
                ir_area_ratio.append(area_ratio)
                ir_area_ratio_plot.append(area_ratio)
                peak_complete["upstream"] = peak_complete["downstream"] = False
            else:
                ir_area_ratio.append("N/A")
                ir_area_ratio_plot.append("N/A")

            # Raman Area Calculation Logic
            if values["4-Methylpiperidine"] != "N/A" and values["4-Methylpiperidine"] >= thresholds["4-Methylpiperidine"]:
                raman_peak_data_4Methylpiperidine.append(values["4-Methylpiperidine"])
                
            elif raman_peak_data_4Methylpiperidine and values["4-Methylpiperidine"] != "N/A" and values["4-Methylpiperidine"] < thresholds["4-Methylpiperidine"]:
                area = trapezoid(raman_peak_data_4Methylpiperidine, dx=1)
                raman_4_methylpiperidine_area.append(area)
                raman_4_methylpiperidine_area_plot.append(area)
                raman_peak_data_4Methylpiperidine.clear()
            else:
                raman_4_methylpiperidine_area.append("N/A")
                raman_4_methylpiperidine_area_plot.append("N/A")
            
            if values["Adduct"] != "N/A" and values["Adduct"] >= thresholds["Adduct"]:
                raman_peak_data_Adduct.append(values["Adduct"])
                
            elif raman_peak_data_Adduct and values["Adduct"] != "N/A" and values["Adduct"] < thresholds["Adduct"]:
                area = trapezoid(raman_peak_data_Adduct, dx=1)
                raman_adduct_area.append(area)
                raman_adduct_area_plot.append(area)
                raman_peak_data_Adduct.clear()
            else:
                raman_adduct_area.append("N/A")
                raman_adduct_area_plot.append("N/A")


            if values["F-moc"] != "N/A" and values["F-moc"] >= thresholds["F-moc"]:
                raman_peak_data_Fmoc.append(values["F-moc"])
            
            elif raman_peak_data_Fmoc and values["F-moc"] != "N/A" and values["F-moc"] < thresholds["F-moc"]:
                area = trapezoid(raman_peak_data_Fmoc, dx=1)
                raman_fmoc_area.append(area)
                raman_fmoc_area_plot.append(area)
                raman_peak_data_Fmoc.clear()
            else:
                raman_fmoc_area.append("N/A")
                raman_fmoc_area_plot.append("N/A")

            # Improved Save Data Mechanism
            if time.time() - last_save_time >= save_interval:
                save_data(save_directory)
                last_save_time = time.time()

            await asyncio.sleep(update_interval)

    except Exception as e:
        logging.error(f"Error in data fetch loop: {e}")
    finally:
        if client.session:
            await client.disconnect()
            logging.info("Disconnected from OPC UA server.")

# Function to save data
def save_data(directory):
    global last_save_index
    global time_data, ir_upstream_965, ir_downstream_965, ir_upstream_969, ir_downstream_969, ir_upstream_1012, ir_downstream_1012, ir_area_ratio
    global raman_4_methylpiperidine, raman_adduct, raman_fmoc
    global raman_4_methylpiperidine_area, raman_adduct_area, raman_fmoc_area

    try:
        if not os.path.isdir(directory):
            os.makedirs(directory)

        last_save_index += 1
        filename = f"output_data_{last_save_index}.xlsx"
        path = os.path.join(directory, filename)

        # Creating a dictionary for each list with its corresponding name
        data_dict = {
            "Time": time_data,
            "IR Upstream 965cm-1": ir_upstream_965,
            "IR Downstream 965cm-1": ir_downstream_965,
            "IR Upstream 969cm-1": ir_upstream_969,
            "IR Downstream 969cm-1": ir_downstream_969,
            "IR Upstream 1012cm-1": ir_upstream_1012,
            "IR Downstream 1012cm-1": ir_downstream_1012,
            "IR Area Ratio": ir_area_ratio,
            "4-Methylpiperidine": raman_4_methylpiperidine,
            "Adduct": raman_adduct,
            "Fmoc": raman_fmoc,
            "4-Methylpiperidine Area": raman_4_methylpiperidine_area,
            "Adduct Area": raman_adduct_area,
            "Fmoc Area": raman_fmoc_area
        }

        # Create a Pandas Excel writer object
        with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
            # Save each list in its own sheet
            for key, data_list in data_dict.items():
                # Create a DataFrame for each list and write to a separate sheet
                df = pd.DataFrame({key: data_list})
                df.to_excel(writer, sheet_name=key, index=False)

        logging.info(f"Data saved to {path}")

        # Clear all data lists after saving
        time_data.clear()
        ir_upstream_965.clear()
        ir_downstream_965.clear()
        ir_upstream_969.clear()
        ir_downstream_969.clear()
        ir_upstream_1012.clear()
        ir_downstream_1012.clear()
        ir_area_ratio.clear()
        raman_4_methylpiperidine.clear()
        raman_adduct.clear()
        raman_fmoc.clear()
        raman_4_methylpiperidine_area.clear()
        raman_adduct_area.clear()
        raman_fmoc_area.clear()

    except Exception as e:
        logging.error(f"Error saving data to {directory}: {e}")

@app.callback(
    [Output("run-button", "disabled"), Output("stop-button", "disabled"), Output("data-update-interval", "disabled"), Output("input-warning", "children")],
    [Input("run-button", "n_clicks"), Input("stop-button", "n_clicks")],
    [
        State("opc-url", "value"), 
        State("upstream-node-id-965", "value"),
        State("downstream-node-id-965", "value"),
        State("upstream-node-id-969", "value"),
        State("downstream-node-id-969", "value"), 
        State("upstream-node-id-1012", "value"),
        State("downstream-node-id-1012", "value"),  
        State("methylpiperidine-node-id", "value"),
        State("adduct-node-id", "value"), 
        State("f-moc-node-id", "value"),
        State("save-dir", "value"), 
        State("upstream-threshold", "value"),
        State("downstream-threshold", "value"), 
        State("methylpiperidine-threshold", "value"),
        State("adduct-threshold", "value"), 
        State("f-moc-threshold", "value")
    ]
)
def toggle_run_stop(run_clicks, stop_clicks, server_url, upstream_node_id_965, downstream_node_id_965,upstream_node_id_969, downstream_node_id_969,upstream_node_id_1012, downstream_node_id_1012, methyl_node_id, adduct_node_id, fmoc_node_id, save_dir, up_threshold, down_threshold, methyl_threshold, adduct_threshold, fmoc_threshold):
    if not (server_url and save_dir):
        return False, True, True, "Error: Missing required Server URL or Save Directory."

    if run_clicks or stop_clicks:
        if dash.callback_context.triggered_id == "run-button":
            node_ids = {
                "upstream_965": upstream_node_id_965,
                "downstream_965": downstream_node_id_965,
                "upstream_969": upstream_node_id_969,
                "downstream_969": downstream_node_id_969,
                "upstream_1012": upstream_node_id_1012,
                "downstream_1012": downstream_node_id_1012,
                "4-Methylpiperidine": methyl_node_id,
                "Adduct": adduct_node_id,
                "F-moc": fmoc_node_id
            }
            thresholds = {
                "upstream": up_threshold,
                "downstream": down_threshold,
                "4-Methylpiperidine": methyl_threshold,
                "Adduct": adduct_threshold,
                "F-moc": fmoc_threshold
            }
            thread = Thread(target=start_opcua_thread, args=(server_url, node_ids, thresholds, save_dir))
            thread.start()
            return True, False, False, ""

        elif dash.callback_context.triggered_id == "stop-button":
            stop_opcua_thread(save_dir)
            return False, True, True, ""
    raise PreventUpdate

def start_opcua_thread(server_url, node_ids, thresholds, save_directory):
    global time_data, ir_upstream_965, ir_downstream_965, ir_upstream_969, ir_downstream_969, ir_upstream_1012, ir_downstream_1012, ir_area_ratio, raman_4_methylpiperidine, raman_adduct, raman_fmoc
    global raman_4_methylpiperidine_area, raman_adduct_area, raman_fmoc_area, current_time, last_save_time

    # Clean data lists and reset time variables
    time_data.clear()
    ir_upstream_965.clear()
    ir_downstream_965.clear()
    ir_upstream_969.clear()
    ir_downstream_969.clear()
    ir_upstream_1012.clear()
    ir_downstream_1012.clear()
    ir_area_ratio.clear()
    raman_4_methylpiperidine.clear()
    raman_adduct.clear()
    raman_fmoc.clear()
    raman_4_methylpiperidine_area.clear()
    raman_adduct_area.clear()
    raman_fmoc_area.clear()
    current_time = 0
    last_save_time = time.time()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    cancel_event.clear()
    loop.run_until_complete(async_opcua_data_fetch(server_url, node_ids, thresholds, save_directory))

def stop_opcua_thread(save_directory):
    cancel_event.set()
    save_data(save_directory)

@app.callback(
    Output("ir-plot-965", "figure"),
    Output("area-ratio-plot", "figure"),
    Output("ir-plot-969", "figure"),
    Output("ir-plot-1012", "figure"),
    Output("raman-plot", "figure"),
    Output("methylpiperidine-area-plot", "figure"),
    Output("adduct-area-plot", "figure"),
    Output("f-moc-area-plot", "figure"),
    Input("data-update-interval", "n_intervals")
)
def update_plots(n_intervals):
    if not time_data:
        raise PreventUpdate

    # Existing plot configurations
    ir_965_fig = go.Figure()
    ir_965_fig.add_trace(go.Scatter(x=time_data_plot, y=ir_upstream_965_plot, mode="lines+markers", name="Upstream IR (965 cm⁻¹)"))
    ir_965_fig.add_trace(go.Scatter(x=time_data_plot, y=ir_downstream_965_plot, mode="lines+markers", name="Downstream IR (965 cm⁻¹)"))
    ir_965_fig.update_layout(title="Upstream & Downstream IR Peak Tracking (965 cm⁻¹)")

    area_ratio_fig = go.Figure([go.Bar(x=[i+1 for i in range(len(ir_area_ratio_plot))], y=[val for val in ir_area_ratio_plot if val != "N/A"])])
    area_ratio_fig.update_layout(title="Area Ratio (Downstream/Upstream)", xaxis_title="Iteration", yaxis_title="Area Ratio")


    # New plot for IR 969 cm⁻¹
    ir_969_fig = go.Figure()
    ir_969_fig.add_trace(go.Scatter(x=time_data_plot, y=ir_upstream_969_plot, mode="lines+markers", name="Upstream IR (969 cm⁻¹)"))
    ir_969_fig.add_trace(go.Scatter(x=time_data_plot, y=ir_downstream_969_plot, mode="lines+markers", name="Downstream IR (969 cm⁻¹)"))
    ir_969_fig.update_layout(title="Upstream & Downstream IR Peak Tracking (969 cm⁻¹)")

    # New plot for IR 1012 cm⁻¹
    ir_1012_fig = go.Figure()
    ir_1012_fig.add_trace(go.Scatter(x=time_data_plot, y=ir_upstream_1012_plot, mode="lines+markers", name="Upstream IR (1012 cm⁻¹)"))
    ir_1012_fig.add_trace(go.Scatter(x=time_data_plot, y=ir_downstream_1012_plot, mode="lines+markers", name="Downstream IR (1012 cm⁻¹)"))
    ir_1012_fig.update_layout(title="Upstream & Downstream IR Peak Tracking (1012 cm⁻¹)")

    # Existing Raman plot
    raman_fig = go.Figure()
    raman_fig.add_trace(go.Scatter(x=time_data_plot, y=raman_4_methylpiperidine_plot, mode="lines+markers", name="4-Methylpiperidine"))
    raman_fig.add_trace(go.Scatter(x=time_data_plot, y=raman_adduct_plot, mode="lines+markers", name="Adduct"))
    raman_fig.add_trace(go.Scatter(x=time_data_plot, y=raman_fmoc_plot, mode="lines+markers", name="F-moc"))
    raman_fig.update_layout(title="Raman Tracking")
    
    # Create filtered data for Raman area plots
    def create_bar_plot(data, title):
        valid_data = [val for val in data if val != "N/A"]
        x_values = list(range(1, len(valid_data) + 1))  # Sequential numbers for x-axis
        return go.Figure(data=[go.Bar(x=x_values, y=valid_data)]).update_layout(title=title)

    methyl_area_fig = create_bar_plot(raman_4_methylpiperidine_area_plot, "4-Methylpiperidine Peak Area")
    adduct_area_fig = create_bar_plot(raman_adduct_area_plot, "Adduct Peak Area")
    fmoc_area_fig = create_bar_plot(raman_fmoc_area_plot, "F-moc Peak Area")

    return ir_965_fig, area_ratio_fig, ir_969_fig, ir_1012_fig, raman_fig, methyl_area_fig, adduct_area_fig, fmoc_area_fig

if __name__ == "__main__":
    app.run_server(debug=True)
