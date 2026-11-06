import dash
from dash import dcc, html, Input, Output, State, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import pandas as pd
import numpy as np
import os
import time
import threading
from oceanoptics import Spectrometer

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "PAT Spectroscopy Control"

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
  .nav-tabs .nav-link.active { color: #2563EB !important; border-bottom: 2px solid #2563EB !important; font-weight: 600; }
  .nav-tabs .nav-link { color: #1E293B; }
</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>'''

# ─── Global state ───────────────────────────────────────────────────────────────
spectrometer = None
hdx_connected = False
sample_counter = 0

# OPC UA state
opcua_client = None
opcua_running = False
opcua_stop_event = threading.Event()
mt_time_data = []
mt_ir_node1_data = []
mt_ir_node2_data = []
mt_raman_node1_data = []
mt_raman_node2_data = []
mt_start_time = 0

# ─── SVG Icon helper ────────────────────────────────────────────────────────────
def _svg_icon(svg_body: str) -> dcc.Markdown:
    return dcc.Markdown(
        f'<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#2563EB" stroke-width="1.5" style="vertical-align:middle;margin-right:6px">{svg_body}</svg>',
        dangerously_allow_html=True,
    )

SPECTROMETER_ICON = '<polygon points="4,20 12,4 20,20"/><line x1="20" y1="12" x2="24" y2="10"/><line x1="20" y1="16" x2="24" y2="16"/>'
GENERIC_ICON = '<polygon points="12,2 22,8 22,16 12,22 2,16 2,8"/>'

# ─── Tab 1 Layout: Ocean Optics HDX ─────────────────────────────────────────────
tab1_layout = html.Div([
    html.Div([
        html.Div([
            _svg_icon(SPECTROMETER_ICON),
            html.H5("Ocean Optics HDX Spectrometer"),
            html.Span("Disconnected", id="tab1-hdx-status", className="status-disconnected")
        ], className="card-header"),

        # Row 1: Input boxes
        dbc.Row([
            dbc.Col([
                dbc.Label("Directory", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab1-directory", type="text", placeholder="Enter directory path", style={"fontSize": "13px"})
            ], md=3),
            dbc.Col([
                dbc.Label("Integration Time (µs)", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab1-integration-time", type="number", placeholder="e.g. 100000", style={"fontSize": "13px"})
            ], md=3),
            dbc.Col([
                dbc.Label("Scans to Average", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab1-scans-avg", type="number", placeholder="e.g. 5", style={"fontSize": "13px"})
            ], md=3),
            dbc.Col([
                dbc.Label("Boxcar Width", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab1-boxcar", type="number", placeholder="e.g. 3", style={"fontSize": "13px"})
            ], md=3),
        ], className="mb-3"),

        # Row 2: Buttons
        dbc.Row([
            dbc.Col(dbc.Button("Connect HDX", id="tab1-connect-btn", n_clicks=0,
                               style={"backgroundColor": "#28a745", "borderColor": "#28a745", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Disconnect HDX", id="tab1-disconnect-btn", n_clicks=0,
                               style={"backgroundColor": "#dc3545", "borderColor": "#dc3545", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Save Wavelength", id="tab1-save-wl-btn", n_clicks=0,
                               style={"backgroundColor": "#2563EB", "borderColor": "#2563EB", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Save Dark Reference", id="tab1-save-dr-btn", n_clicks=0,
                               style={"backgroundColor": "#2563EB", "borderColor": "#2563EB", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Save Light Reference", id="tab1-save-lr-btn", n_clicks=0,
                               style={"backgroundColor": "#2563EB", "borderColor": "#2563EB", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Save Sample Spectra", id="tab1-save-sample-btn", n_clicks=0,
                               style={"backgroundColor": "#2563EB", "borderColor": "#2563EB", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
        ], className="mb-3"),

        # Row 3: Message box
        html.Div(id="tab1-message", className="status-msg", children="Ready. Connect the spectrometer to begin."),

        # Row 4: Plots
        dbc.Row([
            dbc.Col(dcc.Graph(id="tab1-raw-plot", figure=go.Figure().update_layout(
                title="Raw Intensity vs Wavelength",
                xaxis_title="Wavelength (nm)", yaxis_title="Intensity",
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                font=dict(color="#1E293B"),
                xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9")
            )), md=6),
            dbc.Col(dcc.Graph(id="tab1-abs-plot", figure=go.Figure().update_layout(
                title="Absorbance vs Wavelength",
                xaxis_title="Wavelength (nm)", yaxis_title="Absorbance",
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                font=dict(color="#1E293B"),
                xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9")
            )), md=6),
        ], className="mb-3"),

        # Row 5: Plot Buttons
        dbc.Row([
            dbc.Col(dbc.Button("Plot Raw Intensity Data", id="tab1-plot-raw-btn", n_clicks=0,
                               style={"backgroundColor": "#2563EB", "borderColor": "#2563EB", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Plot Absorbance Data", id="tab1-plot-abs-btn", n_clicks=0,
                               style={"backgroundColor": "#2563EB", "borderColor": "#2563EB", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Clear Data", id="tab1-clear-btn", n_clicks=0,
                               style={"backgroundColor": "#ffc107", "borderColor": "#ffc107", "color": "#1E293B", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
        ]),
    ], className="instrument-card"),
])

# ─── Tab 2 Layout: Mettler Toledo React IR & Raman ───────────────────────────────
tab2_layout = html.Div([
    html.Div([
        html.Div([
            _svg_icon(GENERIC_ICON),
            html.H5("React IR & React Raman Spectrometers"),
            html.Span("Stopped", id="tab2-mt-status", className="status-disconnected")
        ], className="card-header"),

        # Row 1: Input boxes
        dbc.Row([
            dbc.Col([
                dbc.Label("OPC UA Server URL", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab2-opc-url", type="text", placeholder="opc.tcp://localhost:62552/...", style={"fontSize": "13px"})
            ], md=4),
            dbc.Col([
                dbc.Label("Save Directory", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab2-directory", type="text", placeholder="Enter directory path", style={"fontSize": "13px"})
            ], md=4),
            dbc.Col([
                dbc.Label("React IR Node ID 1", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab2-ir-node1", type="text", placeholder="ns=2;s=...", style={"fontSize": "13px"})
            ], md=4),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([
                dbc.Label("React IR Node ID 2", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab2-ir-node2", type="text", placeholder="ns=2;s=...", style={"fontSize": "13px"})
            ], md=3),
            dbc.Col([
                dbc.Label("React Raman Node ID 1", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab2-raman-node1", type="text", placeholder="ns=2;s=...", style={"fontSize": "13px"})
            ], md=3),
            dbc.Col([
                dbc.Label("React Raman Node ID 2", style={"color": "#1E293B", "fontSize": "12px", "fontWeight": "500"}),
                dbc.Input(id="tab2-raman-node2", type="text", placeholder="ns=2;s=...", style={"fontSize": "13px"})
            ], md=3),
        ], className="mb-3"),

        # Row 2: Buttons
        dbc.Row([
            dbc.Col(dbc.Button("Run MT Spectrometers", id="tab2-run-btn", n_clicks=0,
                               style={"backgroundColor": "#28a745", "borderColor": "#28a745", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
            dbc.Col(dbc.Button("Stop MT Spectrometers", id="tab2-stop-btn", n_clicks=0,
                               style={"backgroundColor": "#dc3545", "borderColor": "#dc3545", "color": "#FFFFFF", "borderRadius": "4px", "fontWeight": "500"}), width="auto"),
        ], className="mb-3"),

        # Row 3: Message box
        html.Div(id="tab2-message", className="status-msg", children="Ready. Configure OPC UA settings and press Run."),

        # Row 4: Plots
        dbc.Row([
            dbc.Col(dcc.Graph(id="tab2-ir-plot", figure=go.Figure().update_layout(
                title="React IR Node Values vs Time",
                xaxis_title="Time (s)", yaxis_title="Value",
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                font=dict(color="#1E293B"),
                xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9")
            )), md=6),
            dbc.Col(dcc.Graph(id="tab2-raman-plot", figure=go.Figure().update_layout(
                title="React Raman Node Values vs Time",
                xaxis_title="Time (s)", yaxis_title="Value",
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                font=dict(color="#1E293B"),
                xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9")
            )), md=6),
        ]),

        # Interval for Tab 2 data updates
        dcc.Interval(id="tab2-interval", interval=5000, n_intervals=0, disabled=True),
    ], className="instrument-card"),
])

# ─── Main App Layout ─────────────────────────────────────────────────────────────
app.layout = html.Div([
    # Title bar
    html.Div([
        html.H1("PAT Spectroscopy Control"),
        html.P("Laboratory Automation")
    ], className="app-titlebar"),

    # Tabs
    dbc.Tabs([
        dbc.Tab(tab1_layout, label="Ocean Optics HDX Spectrometer", tab_id="tab-1",
                active_label_style={"color": "#2563EB"}),
        dbc.Tab(tab2_layout, label="React IR & React Raman", tab_id="tab-2",
                active_label_style={"color": "#2563EB"}),
    ], id="main-tabs", active_tab="tab-1", style={"padding": "12px 24px"}),

    # Footer
    html.Div("PAT Spectroscopy Control — Laboratory Automation", className="app-footer"),
], style={"minHeight": "100vh"})


# ═══════════════════════════════════════════════════════════════════════════════════
# TAB 1 CALLBACKS: Ocean Optics HDX Spectrometer
# ═══════════════════════════════════════════════════════════════════════════════════

@dash.callback(
    Output("tab1-message", "children"),
    Output("tab1-hdx-status", "children"),
    Output("tab1-hdx-status", "className"),
    Input("tab1-connect-btn", "n_clicks"),
    Input("tab1-disconnect-btn", "n_clicks"),
    Input("tab1-save-wl-btn", "n_clicks"),
    Input("tab1-save-dr-btn", "n_clicks"),
    Input("tab1-save-lr-btn", "n_clicks"),
    Input("tab1-save-sample-btn", "n_clicks"),
    State("tab1-directory", "value"),
    State("tab1-integration-time", "value"),
    State("tab1-scans-avg", "value"),
    State("tab1-boxcar", "value"),
    prevent_initial_call=True
)
def tab1_handle_actions(connect_clicks, disconnect_clicks, save_wl_clicks,
                        save_dr_clicks, save_lr_clicks, save_sample_clicks,
                        directory, integration_time, scans_avg, boxcar):
    global spectrometer, hdx_connected, sample_counter

    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    status_text = "Disconnected"
    status_class = "status-disconnected"

    if hdx_connected:
        status_text = "Connected"
        status_class = "status-connected"

    try:
        if triggered == "tab1-connect-btn":
            spectrometer = Spectrometer()
            spectrometer.connect()
            if integration_time:
                spectrometer.set_integration_time(int(integration_time))
            if scans_avg:
                spectrometer.set_scans_to_average(int(scans_avg))
            if boxcar:
                spectrometer.set_boxcar_width(int(boxcar))
            hdx_connected = True
            sample_counter = 0
            return (f"HDX Spectrometer connected successfully. Device ID: {spectrometer.device_id}",
                    "Connected", "status-connected")

        elif triggered == "tab1-disconnect-btn":
            if spectrometer and hdx_connected:
                spectrometer.disconnect()
                hdx_connected = False
                spectrometer = None
                return "HDX Spectrometer disconnected.", "Disconnected", "status-disconnected"
            else:
                return "Spectrometer not connected.", status_text, status_class

        elif triggered == "tab1-save-wl-btn":
            if not hdx_connected or spectrometer is None:
                return "Error: Spectrometer not connected.", status_text, status_class
            if not directory:
                return "Error: Please specify a directory.", status_text, status_class
            if not os.path.exists(directory):
                os.makedirs(directory)
            wavelengths = spectrometer.get_wavelengths()
            df = pd.DataFrame(wavelengths, columns=["Wavelength (nm)"])
            filepath = os.path.join(directory, "wavelength.csv")
            df.to_csv(filepath, index=False)
            return f"Wavelength data saved to {filepath}.", status_text, status_class

        elif triggered == "tab1-save-dr-btn":
            if not hdx_connected or spectrometer is None:
                return "Error: Spectrometer not connected.", status_text, status_class
            if not directory:
                return "Error: Please specify a directory.", status_text, status_class
            if not os.path.exists(directory):
                os.makedirs(directory)
            if integration_time:
                spectrometer.set_integration_time(int(integration_time))
            if scans_avg:
                spectrometer.set_scans_to_average(int(scans_avg))
            if boxcar:
                spectrometer.set_boxcar_width(int(boxcar))
            intensities = spectrometer.get_spectrum()
            df = pd.DataFrame(intensities, columns=["Intensity"])
            filepath = os.path.join(directory, "DR.csv")
            df.to_csv(filepath, index=False)
            return f"Dark Reference saved to {filepath}.", status_text, status_class

        elif triggered == "tab1-save-lr-btn":
            if not hdx_connected or spectrometer is None:
                return "Error: Spectrometer not connected.", status_text, status_class
            if not directory:
                return "Error: Please specify a directory.", status_text, status_class
            if not os.path.exists(directory):
                os.makedirs(directory)
            if integration_time:
                spectrometer.set_integration_time(int(integration_time))
            if scans_avg:
                spectrometer.set_scans_to_average(int(scans_avg))
            if boxcar:
                spectrometer.set_boxcar_width(int(boxcar))
            intensities = spectrometer.get_spectrum()
            df = pd.DataFrame(intensities, columns=["Intensity"])
            filepath = os.path.join(directory, "LR.csv")
            df.to_csv(filepath, index=False)
            return f"Light Reference saved to {filepath}.", status_text, status_class

        elif triggered == "tab1-save-sample-btn":
            if not hdx_connected or spectrometer is None:
                return "Error: Spectrometer not connected.", status_text, status_class
            if not directory:
                return "Error: Please specify a directory.", status_text, status_class
            if not os.path.exists(directory):
                os.makedirs(directory)
            if integration_time:
                spectrometer.set_integration_time(int(integration_time))
            if scans_avg:
                spectrometer.set_scans_to_average(int(scans_avg))
            if boxcar:
                spectrometer.set_boxcar_width(int(boxcar))
            # Determine next sample number
            existing = [f for f in os.listdir(directory) if f.startswith("Sample") and f.endswith(".csv")]
            if existing:
                nums = []
                for f in existing:
                    try:
                        n = int(f.replace("Sample ", "").replace("Sample", "").replace(".csv", "").strip())
                        nums.append(n)
                    except ValueError:
                        pass
                sample_counter_local = max(nums) + 1 if nums else 1
            else:
                sample_counter_local = 1
            intensities = spectrometer.get_spectrum()
            df = pd.DataFrame(intensities, columns=["Intensity"])
            filename = f"Sample {sample_counter_local}.csv"
            filepath = os.path.join(directory, filename)
            df.to_csv(filepath, index=False)
            return f"{filename} saved to {directory}.", status_text, status_class

    except Exception as e:
        return f"Error: {str(e)}", status_text, status_class

    return "No action taken.", status_text, status_class


@dash.callback(
    Output("tab1-raw-plot", "figure"),
    Output("tab1-abs-plot", "figure"),
    Input("tab1-plot-raw-btn", "n_clicks"),
    Input("tab1-plot-abs-btn", "n_clicks"),
    Input("tab1-clear-btn", "n_clicks"),
    State("tab1-directory", "value"),
    prevent_initial_call=True
)
def tab1_update_plots(raw_clicks, abs_clicks, clear_clicks, directory):
    triggered = ctx.triggered_id

    empty_raw = go.Figure().update_layout(
        title="Raw Intensity vs Wavelength",
        xaxis_title="Wavelength (nm)", yaxis_title="Intensity",
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font=dict(color="#1E293B"),
        xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9")
    )
    empty_abs = go.Figure().update_layout(
        title="Absorbance vs Wavelength",
        xaxis_title="Wavelength (nm)", yaxis_title="Absorbance",
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font=dict(color="#1E293B"),
        xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9")
    )

    if triggered == "tab1-clear-btn":
        return empty_raw, empty_abs

    if not directory or not os.path.exists(directory):
        raise PreventUpdate

    plot_colors = ["#2563EB", "#1E293B", "#60A5FA", "#5450E4"]

    if triggered == "tab1-plot-raw-btn":
        wl_path = os.path.join(directory, "wavelength.csv")
        if not os.path.exists(wl_path):
            raise PreventUpdate
        wavelengths = pd.read_csv(wl_path)["Wavelength (nm)"]
        sample_files = sorted([f for f in os.listdir(directory) if f.startswith("Sample") and f.endswith(".csv")])
        if not sample_files:
            raise PreventUpdate

        fig = go.Figure()
        for idx, sf in enumerate(sample_files):
            sample_data = pd.read_csv(os.path.join(directory, sf))["Intensity"]
            color = plot_colors[idx % len(plot_colors)]
            fig.add_trace(go.Scatter(x=wavelengths, y=sample_data, mode='lines', name=sf.replace(".csv", ""),
                                     line=dict(color=color)))
        fig.update_layout(
            title="Raw Intensity vs Wavelength",
            xaxis_title="Wavelength (nm)", yaxis_title="Intensity",
            plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
            font=dict(color="#1E293B"),
            xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9"),
            legend=dict(font=dict(color="#1E293B"))
        )
        return fig, dash.no_update

    elif triggered == "tab1-plot-abs-btn":
        wl_path = os.path.join(directory, "wavelength.csv")
        dr_path = os.path.join(directory, "DR.csv")
        lr_path = os.path.join(directory, "LR.csv")
        if not all(os.path.exists(p) for p in [wl_path, dr_path, lr_path]):
            raise PreventUpdate

        wavelengths = pd.read_csv(wl_path)["Wavelength (nm)"]
        DR = pd.read_csv(dr_path)["Intensity"].values
        LR = pd.read_csv(lr_path)["Intensity"].values

        sample_files = sorted([f for f in os.listdir(directory) if f.startswith("Sample") and f.endswith(".csv")])
        if not sample_files:
            raise PreventUpdate

        fig = go.Figure()
        for idx, sf in enumerate(sample_files):
            sample_data = pd.read_csv(os.path.join(directory, sf))["Intensity"].values
            epsilon = 1e-10
            numerator = sample_data - DR + epsilon
            denominator = LR - DR + epsilon
            ratio = numerator / denominator
            ratio = np.where(ratio <= 0, epsilon, ratio)
            absorbance = -np.log10(ratio)
            color = plot_colors[idx % len(plot_colors)]
            fig.add_trace(go.Scatter(x=wavelengths, y=absorbance, mode='lines', name=sf.replace(".csv", ""),
                                     line=dict(color=color)))
        fig.update_layout(
            title="Absorbance vs Wavelength",
            xaxis_title="Wavelength (nm)", yaxis_title="Absorbance",
            plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
            font=dict(color="#1E293B"),
            xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9"),
            legend=dict(font=dict(color="#1E293B"))
        )
        return dash.no_update, fig

    raise PreventUpdate


# ═══════════════════════════════════════════════════════════════════════════════════
# TAB 2 CALLBACKS: Mettler Toledo React IR & React Raman
# ═══════════════════════════════════════════════════════════════════════════════════

def opcua_data_thread(url, ir_node1_id, ir_node2_id, raman_node1_id, raman_node2_id, save_directory):
    """Background thread that reads OPC UA nodes every 5 seconds."""
    global opcua_client, opcua_running, mt_time_data, mt_ir_node1_data, mt_ir_node2_data
    global mt_raman_node1_data, mt_raman_node2_data, mt_start_time

    try:
        from opcua import Client as OpcuaClient
        opcua_client = OpcuaClient(url)
        opcua_client.connect()
        mt_start_time = time.time()

        ir_node1 = opcua_client.get_node(ir_node1_id) if ir_node1_id else None
        ir_node2 = opcua_client.get_node(ir_node2_id) if ir_node2_id else None
        raman_node1 = opcua_client.get_node(raman_node1_id) if raman_node1_id else None
        raman_node2 = opcua_client.get_node(raman_node2_id) if raman_node2_id else None

        while not opcua_stop_event.is_set():
            elapsed = time.time() - mt_start_time
            mt_time_data.append(elapsed)

            try:
                val1 = ir_node1.get_value() if ir_node1 else 0
            except Exception:
                val1 = 0
            try:
                val2 = ir_node2.get_value() if ir_node2 else 0
            except Exception:
                val2 = 0
            try:
                val3 = raman_node1.get_value() if raman_node1 else 0
            except Exception:
                val3 = 0
            try:
                val4 = raman_node2.get_value() if raman_node2 else 0
            except Exception:
                val4 = 0

            mt_ir_node1_data.append(val1)
            mt_ir_node2_data.append(val2)
            mt_raman_node1_data.append(val3)
            mt_raman_node2_data.append(val4)

            time.sleep(5)

        # Save data on stop
        if save_directory:
            try:
                if not os.path.exists(save_directory):
                    os.makedirs(save_directory)
                df = pd.DataFrame({
                    "Time (s)": mt_time_data,
                    "IR Node 1": mt_ir_node1_data,
                    "IR Node 2": mt_ir_node2_data,
                    "Raman Node 1": mt_raman_node1_data,
                    "Raman Node 2": mt_raman_node2_data,
                })
                filepath = os.path.join(save_directory, "MT_Spectrometer_Data.xlsx")
                df.to_excel(filepath, index=False)
            except Exception:
                pass

    except Exception as e:
        pass
    finally:
        try:
            if opcua_client:
                opcua_client.disconnect()
        except Exception:
            pass
        opcua_running = False


@dash.callback(
    Output("tab2-message", "children"),
    Output("tab2-mt-status", "children"),
    Output("tab2-mt-status", "className"),
    Output("tab2-interval", "disabled"),
    Input("tab2-run-btn", "n_clicks"),
    Input("tab2-stop-btn", "n_clicks"),
    State("tab2-opc-url", "value"),
    State("tab2-directory", "value"),
    State("tab2-ir-node1", "value"),
    State("tab2-ir-node2", "value"),
    State("tab2-raman-node1", "value"),
    State("tab2-raman-node2", "value"),
    prevent_initial_call=True
)
def tab2_run_stop(run_clicks, stop_clicks, opc_url, save_dir,
                  ir_node1, ir_node2, raman_node1, raman_node2):
    global opcua_running, mt_time_data, mt_ir_node1_data, mt_ir_node2_data
    global mt_raman_node1_data, mt_raman_node2_data

    triggered = ctx.triggered_id

    if triggered == "tab2-run-btn":
        if not opc_url:
            return "Error: OPC UA Server URL is required.", "Stopped", "status-disconnected", True
        if opcua_running:
            return "Already running.", "Running", "status-connected", False

        # Clear previous data
        mt_time_data.clear()
        mt_ir_node1_data.clear()
        mt_ir_node2_data.clear()
        mt_raman_node1_data.clear()
        mt_raman_node2_data.clear()

        opcua_stop_event.clear()
        opcua_running = True

        thread = threading.Thread(
            target=opcua_data_thread,
            args=(opc_url, ir_node1, ir_node2, raman_node1, raman_node2, save_dir),
            daemon=True
        )
        thread.start()
        return ("Data acquisition started. Plots update every 5 seconds.",
                "Running", "status-connected", False)

    elif triggered == "tab2-stop-btn":
        if not opcua_running:
            return "Not currently running.", "Stopped", "status-disconnected", True
        opcua_stop_event.set()
        opcua_running = False
        return ("Data acquisition stopped. Data saved to directory.",
                "Stopped", "status-disconnected", True)

    raise PreventUpdate


@dash.callback(
    Output("tab2-ir-plot", "figure"),
    Output("tab2-raman-plot", "figure"),
    Input("tab2-interval", "n_intervals"),
    prevent_initial_call=True
)
def tab2_update_plots(n_intervals):
    if not mt_time_data:
        raise PreventUpdate

    # IR Plot
    ir_fig = go.Figure()
    ir_fig.add_trace(go.Scatter(
        x=list(mt_time_data), y=list(mt_ir_node1_data),
        mode='lines+markers', name="IR Node ID 1",
        line=dict(color="#2563EB"), marker=dict(size=4)
    ))
    ir_fig.add_trace(go.Scatter(
        x=list(mt_time_data), y=list(mt_ir_node2_data),
        mode='lines+markers', name="IR Node ID 2",
        line=dict(color="#1E293B"), marker=dict(size=4)
    ))
    ir_fig.update_layout(
        title="React IR Node Values vs Time",
        xaxis_title="Time (s)", yaxis_title="Value",
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font=dict(color="#1E293B"),
        xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9"),
        legend=dict(font=dict(color="#1E293B"))
    )

    # Raman Plot
    raman_fig = go.Figure()
    raman_fig.add_trace(go.Scatter(
        x=list(mt_time_data), y=list(mt_raman_node1_data),
        mode='lines+markers', name="Raman Node ID 1",
        line=dict(color="#60A5FA"), marker=dict(size=4)
    ))
    raman_fig.add_trace(go.Scatter(
        x=list(mt_time_data), y=list(mt_raman_node2_data),
        mode='lines+markers', name="Raman Node ID 2",
        line=dict(color="#5450E4"), marker=dict(size=4)
    ))
    raman_fig.update_layout(
        title="React Raman Node Values vs Time",
        xaxis_title="Time (s)", yaxis_title="Value",
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font=dict(color="#1E293B"),
        xaxis=dict(gridcolor="#D9D9D9"), yaxis=dict(gridcolor="#D9D9D9"),
        legend=dict(font=dict(color="#1E293B"))
    )

    return ir_fig, raman_fig


# ─── Run the app ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050)