import threading
import dash
from dash import dcc, html, callback, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

# Driver imports
import serial
from pylabdrivers.teledyneisco import TeledyneISCO
from pylabdrivers.teledynereaxus import TeledyneM1Reaxus
from pylabdrivers.azuraknauer_serial import AzuraKnauerPump
from pylabdrivers.harvard import HarvardSyringePump

# ── Module-level driver instances (not connected at import time) ──
pumps = {
    "isco": None,
    "reaxus": None,
    "knauer": None,
    "harvard": None,
}

connected = {
    "isco": False,
    "reaxus": False,
    "knauer": False,
    "harvard": False,
}

# ── Helper ──────────────────────────────────────────────────────
def safe_call(fn, *args, **kwargs):
    """Wraps a driver call in try/except. Returns (success, message)."""
    try:
        result = fn(*args, **kwargs)
        msg = str(result) if result is not None else "OK"
        return True, msg
    except Exception as exc:
        return False, str(exc)


def _svg_icon(svg_body: str) -> dcc.Markdown:
    return dcc.Markdown(
        f'<svg viewBox="0 0 24 24" width="22" height="22" fill="none" '
        f'stroke="#2563EB" stroke-width="1.5" '
        f'style="vertical-align:middle;margin-right:6px">{svg_body}</svg>',
        dangerously_allow_html=True,
    )


# SVG bodies
SVG_SYRINGE = '<rect x="3" y="9" width="14" height="6"/><rect x="17" y="11" width="4" height="2"/><circle cx="5" cy="12" r="1.5" fill="#2563EB"/>'
SVG_FLOW    = '<circle cx="12" cy="12" r="8"/><path d="M9 9 Q12 5 15 9"/><path d="M15 15 Q12 19 9 15"/>'
SVG_GENERIC = '<polygon points="12,2 22,8 22,16 12,22 2,16 2,8"/>'

# ── Button styles ────────────────────────────────────────────────
BTN_CONNECT    = {"backgroundColor":"#28a745","borderColor":"#28a745","color":"#FFFFFF","borderRadius":"4px","fontWeight":"500"}
BTN_DISCONNECT = {"backgroundColor":"#dc3545","borderColor":"#dc3545","color":"#FFFFFF","borderRadius":"4px","fontWeight":"500"}
BTN_RUN        = {"backgroundColor":"#2563EB","borderColor":"#2563EB","color":"#FFFFFF","borderRadius":"4px","fontWeight":"500"}
BTN_STOP       = {"backgroundColor":"#ffc107","borderColor":"#ffc107","color":"#1E293B","borderRadius":"4px","fontWeight":"500"}

# ── App init ─────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)
app.title = "Pump Control Panel"

app.index_string = '''<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
  body { font-family: -apple-system, Helvetica Neue, Arial, sans-serif; background: #F7F7F7; color: #1E293B; margin: 0; }
  .app-titlebar { background: #1E293B; color: #FFFFFF; padding: 12px 24px; border-left: 4px solid #2563EB; }
  .app-titlebar h1 { margin: 0; font-size: 1.4rem; font-weight: 700; color: #FFFFFF; }
  .app-titlebar p { margin: 0; font-size: 0.85rem; color: #60A5FA; }
  .instrument-card { background: #FFFFFF; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); padding: 16px; margin-bottom: 12px; }
  .card-header { display: flex; align-items: center; gap: 10px; border-bottom: 2px solid #2563EB; padding-bottom: 8px; margin-bottom: 12px; }
  .card-header h5 { color: #1E293B; font-weight: 600; margin: 0; font-size: 1rem; }
  .status-connected { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; border-radius: 12px; padding: 2px 10px; font-size: 11px; font-weight: 500; }
  .status-disconnected { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; border-radius: 12px; padding: 2px 10px; font-size: 11px; font-weight: 500; }
  .status-msg { background: #F0F0F0; border-radius: 4px; padding: 8px 12px; font-style: italic; color: #555; font-size: 12px; min-height: 32px; margin-top: 8px; }
  .app-footer { border-top: 1px solid #D9D9D9; padding: 8px 24px; font-size: 11px; color: #888; background: #FFFFFF; margin-top: 16px; }
  input, select, .Select-control { border: 1px solid #D9D9D9 !important; border-radius: 4px !important; }
  .label-text { font-size: 12px; font-weight: 600; color: #1E293B; margin-bottom: 4px; margin-top: 8px; }
  .actual-rate-box { background: #EFF6FF; border: 1px solid #60A5FA; border-radius: 6px; padding: 6px 12px; font-size: 13px; color: #1E293B; margin-top: 8px; }
</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>'''


# ════════════════════════════════════════════════════════════════
# LAYOUT
# ════════════════════════════════════════════════════════════════

def make_isco_card():
    return html.Div([
        html.Div([
            _svg_icon(SVG_SYRINGE),
            html.H5("Teledyne ISCO"),
            html.Span("Disconnected", id="isco-conn-badge", className="status-disconnected"),
        ], className="card-header"),

        html.Div("COM Port", className="label-text"),
        dbc.Input(id="isco-port", placeholder="COM3", debounce=True, size="sm"),

        html.Div("Flowrate Setpoint", className="label-text"),
        dbc.Input(id="isco-flowrate", type="number", placeholder="Flowrate setpoint", size="sm"),

        html.Div("Flowrate Units", className="label-text"),
        dcc.Dropdown(
            id="isco-flow-units",
            options=[{"label": u, "value": u} for u in ["ML/MIN", "ML/HR", "UL/MIN", "UL/HR"]],
            value="ML/MIN",
            clearable=False,
            style={"fontSize": "13px"},
        ),

        html.Div("Pressure Units", className="label-text"),
        dcc.Dropdown(
            id="isco-pressure-units",
            options=[{"label": u, "value": u} for u in ["ATM", "BAR", "KPA", "PSI"]],
            value="PSI",
            clearable=False,
            style={"fontSize": "13px"},
        ),

        html.Br(),
        dbc.Row([
            dbc.Col(dbc.Button("Connect ISCO",    id="isco-btn-connect",    n_clicks=0, size="sm", style=BTN_CONNECT),    width="auto"),
            dbc.Col(dbc.Button("Set & Run ISCO",  id="isco-btn-set-run",    n_clicks=0, size="sm", style=BTN_RUN,
                               disabled=True),    width="auto"),
            dbc.Col(dbc.Button("Disconnect ISCO", id="isco-btn-disconnect", n_clicks=0, size="sm", style=BTN_DISCONNECT,
                               disabled=True), width="auto"),
        ], className="g-2 mt-1"),

        html.Div(id="isco-status", className="status-msg", children="Ready."),
        dcc.Store(id="isco-connected", data=False),
    ], className="instrument-card")


def make_reaxus_card():
    return html.Div([
        html.Div([
            _svg_icon(SVG_FLOW),
            html.H5("Teledyne Reaxus"),
            html.Span("Disconnected", id="reaxus-conn-badge", className="status-disconnected"),
        ], className="card-header"),

        html.Div("COM Port", className="label-text"),
        dbc.Input(id="reaxus-port", placeholder="COM4", debounce=True, size="sm"),

        html.Div("Flowrate Setpoint", className="label-text"),
        dbc.Input(id="reaxus-flowrate", type="number", placeholder="Flowrate setpoint", size="sm"),

        html.Br(),
        dbc.Row([
            dbc.Col(dbc.Button("Connect Reaxus",    id="reaxus-btn-connect",    n_clicks=0, size="sm", style=BTN_CONNECT), width="auto"),
            dbc.Col(dbc.Button("Set Reaxus",        id="reaxus-btn-set",        n_clicks=0, size="sm", style=BTN_RUN,
                               disabled=True), width="auto"),
            dbc.Col(dbc.Button("Run Reaxus",        id="reaxus-btn-run",        n_clicks=0, size="sm", style=BTN_RUN,
                               disabled=True), width="auto"),
            dbc.Col(dbc.Button("Stop Reaxus",       id="reaxus-btn-stop",       n_clicks=0, size="sm", style=BTN_STOP,
                               disabled=True), width="auto"),
            dbc.Col(dbc.Button("Disconnect Reaxus", id="reaxus-btn-disconnect", n_clicks=0, size="sm", style=BTN_DISCONNECT,
                               disabled=True), width="auto"),
        ], className="g-2 mt-1"),

        html.Div(id="reaxus-status", className="status-msg", children="Ready."),
        dcc.Store(id="reaxus-connected", data=False),
    ], className="instrument-card")


def make_knauer_card():
    return html.Div([
        html.Div([
            _svg_icon(SVG_GENERIC),
            html.H5("Azura Knauer"),
            html.Span("Disconnected", id="knauer-conn-badge", className="status-disconnected"),
        ], className="card-header"),

        html.Div("COM Port", className="label-text"),
        dbc.Input(id="knauer-port", placeholder="COM5", debounce=True, size="sm"),

        html.Div("Flowrate Setpoint (µl/min)", className="label-text"),
        dbc.Input(id="knauer-flowrate", type="number", placeholder="Flowrate setpoint", size="sm"),

        html.Div("Pump Head Size", className="label-text"),
        dcc.Dropdown(
            id="knauer-head",
            options=[{"label": "10 ml", "value": "10"}, {"label": "50 ml", "value": "50"}],
            value="10",
            clearable=False,
            style={"fontSize": "13px"},
        ),

        html.Br(),
        dbc.Row([
            dbc.Col(dbc.Button("Connect Knauer",    id="knauer-btn-connect",    n_clicks=0, size="sm", style=BTN_CONNECT), width="auto"),
            dbc.Col(dbc.Button("Run Knauer",        id="knauer-btn-run",        n_clicks=0, size="sm", style=BTN_RUN,
                               disabled=True), width="auto"),
            dbc.Col(dbc.Button("Disconnect Knauer", id="knauer-btn-disconnect", n_clicks=0, size="sm", style=BTN_DISCONNECT,
                               disabled=True), width="auto"),
        ], className="g-2 mt-1"),

        html.Div(id="knauer-status", className="status-msg", children="Ready."),
        dcc.Store(id="knauer-connected", data=False),
    ], className="instrument-card")


def make_harvard_card():
    return html.Div([
        html.Div([
            _svg_icon(SVG_SYRINGE),
            html.H5("Harvard Syringe Pump"),
            html.Span("Disconnected", id="harvard-conn-badge", className="status-disconnected"),
        ], className="card-header"),

        html.Div("COM Port", className="label-text"),
        dbc.Input(id="harvard-port", placeholder="COM6", debounce=True, size="sm"),

        html.Div("Infusion Rate (ml/min)", className="label-text"),
        dbc.Input(id="harvard-flowrate", type="number", placeholder="Infusion rate (ml/min)", size="sm"),

        html.Div("Syringe Volume (ml)", className="label-text"),
        dbc.Input(id="harvard-syringe-vol", type="number", placeholder="Syringe volume (ml)", size="sm"),

        html.Div("Actual Infusion Rate", className="label-text"),
        html.Div("— ml/min", id="harvard-actual-rate", className="actual-rate-box"),

        dcc.Interval(id="harvard-interval", interval=5000, n_intervals=0, disabled=True),

        html.Br(),
        dbc.Row([
            dbc.Col(dbc.Button("Connect Harvard",    id="harvard-btn-connect",    n_clicks=0, size="sm", style=BTN_CONNECT), width="auto"),
            dbc.Col(dbc.Button("Run Harvard",        id="harvard-btn-run",        n_clicks=0, size="sm", style=BTN_RUN,
                               disabled=True), width="auto"),
            dbc.Col(dbc.Button("Disconnect Harvard", id="harvard-btn-disconnect", n_clicks=0, size="sm", style=BTN_DISCONNECT,
                               disabled=True), width="auto"),
        ], className="g-2 mt-1"),

        html.Div(id="harvard-status", className="status-msg", children="Ready."),
        dcc.Store(id="harvard-connected", data=False),
    ], className="instrument-card")


app.layout = html.Div([
    # Title bar
    html.Div([
        html.H1("Pump Control Panel"),
        html.P("Laboratory Automation — Multi-Pump Controller"),
    ], className="app-titlebar"),

    dbc.Container([
        # Row 1: ISCO + Reaxus
        dbc.Row([
            dbc.Col(make_isco_card(),   md=6),
            dbc.Col(make_reaxus_card(), md=6),
        ], className="mt-3"),
        # Row 2: Knauer + Harvard
        dbc.Row([
            dbc.Col(make_knauer_card(),  md=6),
            dbc.Col(make_harvard_card(), md=6),
        ], className="mt-2"),
    ], fluid=True),

    html.Div("Pump Control Panel — Laboratory Automation", className="app-footer"),
], style={"minHeight": "100vh", "background": "#F7F7F7"})


# ════════════════════════════════════════════════════════════════
# CALLBACKS — Teledyne ISCO
# ════════════════════════════════════════════════════════════════

@callback(
    Output("isco-status", "children"),
    Output("isco-connected", "data"),
    Output("isco-conn-badge", "children"),
    Output("isco-conn-badge", "className"),
    Output("isco-btn-set-run", "disabled"),
    Output("isco-btn-disconnect", "disabled"),
    Output("isco-btn-connect", "disabled"),
    Input("isco-btn-connect", "n_clicks"),
    State("isco-port", "value"),
    State("isco-flow-units", "value"),
    State("isco-pressure-units", "value"),
    prevent_initial_call=True,
)
def isco_connect(n, port, flow_units, pressure_units):
    if not n:
        raise PreventUpdate
    if not port:
        return "Please enter a COM port.", False, "Disconnected", "status-disconnected", True, True, False

    try:
        pump = TeledyneISCO(port=port)
        pump.connect()
        pump.initialize()                         # sets REMOTE
        pump.set_units(flow_units or "ML/MIN", pressure_units or "PSI")
        pump.set_constantflow_mode()
        pumps["isco"] = pump
        connected["isco"] = True
        return (
            f"Connected to ISCO on {port}. Remote mode + const-flow set.",
            True, "Connected", "status-connected",
            False, False, True,
        )
    except Exception as exc:
        connected["isco"] = False
        return (str(exc), False, "Disconnected", "status-disconnected", True, True, False)


@callback(
    Output("isco-status", "children", allow_duplicate=True),
    Input("isco-btn-set-run", "n_clicks"),
    State("isco-flowrate", "value"),
    State("isco-connected", "data"),
    prevent_initial_call=True,
)
def isco_set_run(n, flowrate, is_connected):
    if not n:
        raise PreventUpdate
    if not is_connected or pumps["isco"] is None:
        return "ISCO is not connected."
    if flowrate is None:
        return "Please enter a flowrate setpoint."
    pump = pumps["isco"]
    ok1, msg1 = safe_call(pump.set_flowrate, flowrate)
    if not ok1:
        return f"Set flowrate failed: {msg1}"
    ok2, msg2 = safe_call(pump.run)
    if not ok2:
        return f"Run failed: {msg2}"
    return f"ISCO running at {flowrate}."


@callback(
    Output("isco-status", "children", allow_duplicate=True),
    Output("isco-connected", "data", allow_duplicate=True),
    Output("isco-conn-badge", "children", allow_duplicate=True),
    Output("isco-conn-badge", "className", allow_duplicate=True),
    Output("isco-btn-set-run", "disabled", allow_duplicate=True),
    Output("isco-btn-disconnect", "disabled", allow_duplicate=True),
    Output("isco-btn-connect", "disabled", allow_duplicate=True),
    Input("isco-btn-disconnect", "n_clicks"),
    State("isco-connected", "data"),
    prevent_initial_call=True,
)
def isco_disconnect(n, is_connected):
    if not n:
        raise PreventUpdate
    pump = pumps["isco"]
    if pump is None or not is_connected:
        return ("ISCO not connected.", False, "Disconnected", "status-disconnected", True, True, False)
    safe_call(pump.stop)
    safe_call(pump.clearall)   # sends CLEAR + LOCAL
    safe_call(pump.disconnect)
    pumps["isco"] = None
    connected["isco"] = False
    return ("ISCO disconnected.", False, "Disconnected", "status-disconnected", True, True, False)


# ════════════════════════════════════════════════════════════════
# CALLBACKS — Teledyne Reaxus
# ════════════════════════════════════════════════════════════════

@callback(
    Output("reaxus-status", "children"),
    Output("reaxus-connected", "data"),
    Output("reaxus-conn-badge", "children"),
    Output("reaxus-conn-badge", "className"),
    Output("reaxus-btn-set", "disabled"),
    Output("reaxus-btn-run", "disabled"),
    Output("reaxus-btn-stop", "disabled"),
    Output("reaxus-btn-disconnect", "disabled"),
    Output("reaxus-btn-connect", "disabled"),
    Input("reaxus-btn-connect", "n_clicks"),
    State("reaxus-port", "value"),
    prevent_initial_call=True,
)
def reaxus_connect(n, port):
    if not n:
        raise PreventUpdate
    if not port:
        return ("Please enter a COM port.", False, "Disconnected", "status-disconnected",
                True, True, True, True, False)
    try:
        pump = TeledyneM1Reaxus(port=port)
        pump.connect()
        pumps["reaxus"] = pump
        connected["reaxus"] = True
        return (
            f"Connected to Reaxus on {port}.",
            True, "Connected", "status-connected",
            False, False, False, False, True,
        )
    except Exception as exc:
        connected["reaxus"] = False
        return (str(exc), False, "Disconnected", "status-disconnected",
                True, True, True, True, False)


@callback(
    Output("reaxus-status", "children", allow_duplicate=True),
    Input("reaxus-btn-set", "n_clicks"),
    State("reaxus-flowrate", "value"),
    State("reaxus-connected", "data"),
    prevent_initial_call=True,
)
def reaxus_set(n, flowrate, is_connected):
    if not n:
        raise PreventUpdate
    if not is_connected or pumps["reaxus"] is None:
        return "Reaxus is not connected."
    if flowrate is None:
        return "Please enter a flowrate setpoint."
    pump = pumps["reaxus"]
    try:
        flow_int = int(float(flowrate))
        ok, msg = safe_call(pump.set_flow_input, flow_int)
        return f"Reaxus flowrate set to {flow_int}." if ok else f"Set failed: {msg}"
    except Exception as exc:
        return f"Set failed: {exc}"


@callback(
    Output("reaxus-status", "children", allow_duplicate=True),
    Input("reaxus-btn-run", "n_clicks"),
    State("reaxus-connected", "data"),
    prevent_initial_call=True,
)
def reaxus_run(n, is_connected):
    if not n:
        raise PreventUpdate
    if not is_connected or pumps["reaxus"] is None:
        return "Reaxus is not connected."
    ok, msg = safe_call(pumps["reaxus"].run)
    return "Reaxus running." if ok else f"Run failed: {msg}"


@callback(
    Output("reaxus-status", "children", allow_duplicate=True),
    Input("reaxus-btn-stop", "n_clicks"),
    State("reaxus-connected", "data"),
    prevent_initial_call=True,
)
def reaxus_stop(n, is_connected):
    if not n:
        raise PreventUpdate
    if not is_connected or pumps["reaxus"] is None:
        return "Reaxus is not connected."
    ok, msg = safe_call(pumps["reaxus"].stop)
    return "Reaxus stopped." if ok else f"Stop failed: {msg}"


@callback(
    Output("reaxus-status", "children", allow_duplicate=True),
    Output("reaxus-connected", "data", allow_duplicate=True),
    Output("reaxus-conn-badge", "children", allow_duplicate=True),
    Output("reaxus-conn-badge", "className", allow_duplicate=True),
    Output("reaxus-btn-set", "disabled", allow_duplicate=True),
    Output("reaxus-btn-run", "disabled", allow_duplicate=True),
    Output("reaxus-btn-stop", "disabled", allow_duplicate=True),
    Output("reaxus-btn-disconnect", "disabled", allow_duplicate=True),
    Output("reaxus-btn-connect", "disabled", allow_duplicate=True),
    Input("reaxus-btn-disconnect", "n_clicks"),
    State("reaxus-connected", "data"),
    prevent_initial_call=True,
)
def reaxus_disconnect(n, is_connected):
    if not n:
        raise PreventUpdate
    pump = pumps["reaxus"]
    if pump is None or not is_connected:
        return ("Reaxus not connected.", False, "Disconnected", "status-disconnected",
                True, True, True, True, False)
    safe_call(pump.disconnect)
    pumps["reaxus"] = None
    connected["reaxus"] = False
    return ("Reaxus disconnected.", False, "Disconnected", "status-disconnected",
            True, True, True, True, False)


# ════════════════════════════════════════════════════════════════
# CALLBACKS — Azura Knauer
# ════════════════════════════════════════════════════════════════

@callback(
    Output("knauer-status", "children"),
    Output("knauer-connected", "data"),
    Output("knauer-conn-badge", "children"),
    Output("knauer-conn-badge", "className"),
    Output("knauer-btn-run", "disabled"),
    Output("knauer-btn-disconnect", "disabled"),
    Output("knauer-btn-connect", "disabled"),
    Input("knauer-btn-connect", "n_clicks"),
    State("knauer-port", "value"),
    State("knauer-head", "value"),
    prevent_initial_call=True,
)
def knauer_connect(n, port, head):
    if not n:
        raise PreventUpdate
    if not port:
        return ("Please enter a COM port.", False, "Disconnected", "status-disconnected",
                True, True, False)
    try:
        pump = AzuraKnauerPump(port=port)
        pump.connect()
        pump.set_remote()
        head_int = int(head) if head else 10
        pump.set_head_type(head_int)
        pumps["knauer"] = pump
        connected["knauer"] = True
        return (
            f"Connected to Knauer on {port}. Head: {head_int} ml.",
            True, "Connected", "status-connected",
            False, False, True,
        )
    except Exception as exc:
        connected["knauer"] = False
        return (str(exc), False, "Disconnected", "status-disconnected", True, True, False)


@callback(
    Output("knauer-status", "children", allow_duplicate=True),
    Input("knauer-btn-run", "n_clicks"),
    State("knauer-flowrate", "value"),
    State("knauer-connected", "data"),
    prevent_initial_call=True,
)
def knauer_run(n, flowrate, is_connected):
    if not n:
        raise PreventUpdate
    if not is_connected or pumps["knauer"] is None:
        return "Knauer is not connected."
    if flowrate is None:
        return "Please enter a flowrate setpoint."
    pump = pumps["knauer"]
    ok1, msg1 = safe_call(pump.set_flow, float(flowrate))
    if not ok1:
        return f"Set flow failed: {msg1}"
    ok2, msg2 = safe_call(pump.start)
    if not ok2:
        return f"Start failed: {msg2}"
    return f"Knauer running at {flowrate} µl/min."


@callback(
    Output("knauer-status", "children", allow_duplicate=True),
    Output("knauer-connected", "data", allow_duplicate=True),
    Output("knauer-conn-badge", "children", allow_duplicate=True),
    Output("knauer-conn-badge", "className", allow_duplicate=True),
    Output("knauer-btn-run", "disabled", allow_duplicate=True),
    Output("knauer-btn-disconnect", "disabled", allow_duplicate=True),
    Output("knauer-btn-connect", "disabled", allow_duplicate=True),
    Input("knauer-btn-disconnect", "n_clicks"),
    State("knauer-connected", "data"),
    prevent_initial_call=True,
)
def knauer_disconnect(n, is_connected):
    if not n:
        raise PreventUpdate
    pump = pumps["knauer"]
    if pump is None or not is_connected:
        return ("Knauer not connected.", False, "Disconnected", "status-disconnected",
                True, True, False)
    safe_call(pump.stop)
    safe_call(pump.set_local)
    safe_call(pump.disconnect)
    pumps["knauer"] = None
    connected["knauer"] = False
    return ("Knauer disconnected.", False, "Disconnected", "status-disconnected",
            True, True, False)


# ════════════════════════════════════════════════════════════════
# CALLBACKS — Harvard Syringe Pump
# ════════════════════════════════════════════════════════════════

@callback(
    Output("harvard-status", "children"),
    Output("harvard-connected", "data"),
    Output("harvard-conn-badge", "children"),
    Output("harvard-conn-badge", "className"),
    Output("harvard-btn-run", "disabled"),
    Output("harvard-btn-disconnect", "disabled"),
    Output("harvard-btn-connect", "disabled"),
    Output("harvard-interval", "disabled"),
    Input("harvard-btn-connect", "n_clicks"),
    State("harvard-port", "value"),
    State("harvard-syringe-vol", "value"),
    prevent_initial_call=True,
)
def harvard_connect(n, port, syringe_vol):
    if not n:
        raise PreventUpdate
    if not port:
        return ("Please enter a COM port.", False, "Disconnected", "status-disconnected",
                True, True, False, True)
    try:
        pump = HarvardSyringePump(port=port)
        pump.connect()
        if syringe_vol is not None:
            pump.set_syringe_volume(float(syringe_vol), "ml")
        pumps["harvard"] = pump
        connected["harvard"] = True
        vol_msg = f" Syringe vol: {syringe_vol} ml." if syringe_vol else ""
        return (
            f"Connected to Harvard on {port}.{vol_msg}",
            True, "Connected", "status-connected",
            False, False, True, False,
        )
    except Exception as exc:
        connected["harvard"] = False
        return (str(exc), False, "Disconnected", "status-disconnected",
                True, True, False, True)


@callback(
    Output("harvard-status", "children", allow_duplicate=True),
    Output("harvard-interval", "disabled", allow_duplicate=True),
    Input("harvard-btn-run", "n_clicks"),
    State("harvard-flowrate", "value"),
    State("harvard-connected", "data"),
    prevent_initial_call=True,
)
def harvard_run(n, flowrate, is_connected):
    if not n:
        raise PreventUpdate
    if not is_connected or pumps["harvard"] is None:
        return "Harvard is not connected.", True
    if flowrate is None:
        return "Please enter an infusion rate.", True
    pump = pumps["harvard"]
    ok1, msg1 = safe_call(pump.set_infusion_rate, float(flowrate), "ml/min")
    if not ok1:
        return f"Set rate failed: {msg1}", True
    ok2, msg2 = safe_call(pump.run_infuse)
    if not ok2:
        return f"Run failed: {msg2}", True
    return f"Harvard infusing at {flowrate} ml/min.", False


@callback(
    Output("harvard-status", "children", allow_duplicate=True),
    Output("harvard-connected", "data", allow_duplicate=True),
    Output("harvard-conn-badge", "children", allow_duplicate=True),
    Output("harvard-conn-badge", "className", allow_duplicate=True),
    Output("harvard-btn-run", "disabled", allow_duplicate=True),
    Output("harvard-btn-disconnect", "disabled", allow_duplicate=True),
    Output("harvard-btn-connect", "disabled", allow_duplicate=True),
    Output("harvard-interval", "disabled", allow_duplicate=True),
    Input("harvard-btn-disconnect", "n_clicks"),
    State("harvard-connected", "data"),
    prevent_initial_call=True,
)
def harvard_disconnect(n, is_connected):
    if not n:
        raise PreventUpdate
    pump = pumps["harvard"]
    if pump is None or not is_connected:
        return ("Harvard not connected.", False, "Disconnected", "status-disconnected",
                True, True, False, True)
    safe_call(pump.stop_pump)
    safe_call(pump.clear_volumes)
    safe_call(pump.disconnect)
    pumps["harvard"] = None
    connected["harvard"] = False
    return ("Harvard disconnected.", False, "Disconnected", "status-disconnected",
            True, True, False, True)


@callback(
    Output("harvard-actual-rate", "children"),
    Input("harvard-interval", "n_intervals"),
    State("harvard-connected", "data"),
    prevent_initial_call=True,
)
def harvard_poll(n_intervals, is_connected):
    if not is_connected or pumps["harvard"] is None:
        raise PreventUpdate
    ok, result = safe_call(pumps["harvard"].get_infusion_rate)
    if ok:
        return f"{result} ml/min"
    return f"Read error: {result}"


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=True)