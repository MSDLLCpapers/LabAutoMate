import dash 
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import os
import pandas as pd
import numpy as np
import plotly.graph_objs as go
from oceanoptics import Spectrometer
 
# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
 
# Create an instance of the Spectrometer class
spectrometer = Spectrometer()
 
# Layout of the app
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            dbc.Input(id="directory-input", type="text", placeholder="Specify directory for saving files", style={'margin-bottom': '10px'}),
        ]),
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Button("Connect", id="connect-btn", n_clicks=0, color="primary"),
            dbc.Button("Disconnect", id="disconnect-btn", n_clicks=0, color="danger", disabled=True, style={'margin-left': '10px'}),
            dbc.Button("Save Wavelength", id="save-wavelength-btn", n_clicks=0, color="secondary", style={'margin-left': '10px'}),
        ]),
    ], style={'margin-bottom': '20px'}),
    dbc.Row([
        dbc.Col([
            dbc.Input(id="integration-time-input", type="number", placeholder="Integration Time"),
        ]),
        dbc.Col([
            dbc.Input(id="scans-to-average-input", type="number", placeholder="Scans to Average"),
        ]),
        dbc.Col([
            dbc.Input(id="boxcar-width-input", type="number", placeholder="Boxcar Width"),
        ]),
    ], style={'margin-bottom': '20px'}),
    dbc.Row([
        dbc.Col([
            dbc.Button("Save Dark Reference", id="save-dark-btn", n_clicks=0, color="secondary"),
        ]),
        dbc.Col([
            dbc.Button("Save Light Reference", id="save-light-btn", n_clicks=0, color="secondary"),
        ]),
        dbc.Col([
            dbc.Button("Save Sample Spectra", id="save-sample-btn", n_clicks=0, color="secondary"),
        ]),
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Button("Plot Raw Data", id="plot-raw-btn", n_clicks=0, color="info"),
        ]),
        dbc.Col([
            dbc.Button("Plot Absorbance Data", id="plot-absorbance-btn", n_clicks=0, color="info"),
        ]),
        dbc.Col([
            dbc.Button("Clear Data", id="clear-btn", n_clicks=0, color="warning"),
        ]),
    ], style={'margin-top': '20px'}),
    dbc.Row([
        dbc.Col(dcc.Graph(id="raw-data-plot"), width=6),
        dbc.Col(dcc.Graph(id="absorbance-data-plot"), width=6),
    ]),
    html.Div(id="message-output", style={"margin-top": "20px"})
])
 
def get_next_sample_filename(directory):
    if not os.path.exists(directory):
        return "Sample 1.csv"
    files = os.listdir(directory)
    sample_files = sorted([f for f in files if f.startswith("Sample") and f.endswith(".csv")])
    if not sample_files:
        return "Sample 1.csv"
    last_file = sample_files[-1]
    last_number = int(last_file.split()[1].split('.')[0])
    next_number = last_number + 1
    return f"Sample {next_number}.csv"
 
def compute_absorbance_adjusted(Sample, DR, LR):
    epsilon = 1e-10 # Small number to prevent division by zero or negative values in log
    adjusted_numerator = Sample - DR + epsilon
    adjusted_denominator = LR - DR + epsilon
    ratio = adjusted_numerator / adjusted_denominator
    ratio = np.where(ratio <= 0, epsilon, ratio) # Ensure all values are positive for the log
    return -np.log10(ratio)
 
@app.callback( 
    [Output("connect-btn", "disabled"),
     Output("disconnect-btn", "disabled"),
     Output("message-output", "children"),
     Output("raw-data-plot", "figure"),
     Output("absorbance-data-plot", "figure")],
    [Input("connect-btn", "n_clicks"),
     Input("disconnect-btn", "n_clicks"),
     Input("save-wavelength-btn", "n_clicks"),
     Input("save-dark-btn", "n_clicks"),
     Input("save-light-btn", "n_clicks"),
     Input("save-sample-btn", "n_clicks"),
     Input("plot-raw-btn", "n_clicks"),
     Input("plot-absorbance-btn", "n_clicks"),
     Input("clear-btn", "n_clicks")],
    [State("directory-input", "value"),
     State("integration-time-input", "value"),
     State("scans-to-average-input", "value"),
     State("boxcar-width-input", "value")]
)
def handle_buttons(connect_clicks, disconnect_clicks, save_wavelength_clicks, save_dark_clicks, save_light_clicks, save_sample_clicks,
                   plot_raw_clicks, plot_absorbance_clicks, clear_clicks,
                   directory, integration_time, scans_to_average, boxcar_width):
    ctx = dash.callback_context

    if not ctx.triggered:
        return False, True, "", {}, {}

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == "connect-btn" and connect_clicks > 0:
        try:
            spectrometer.connect()
            return True, False, f"HDX spectrometer connected. Device ID: {spectrometer.device_id}", {}, {}
        except Exception as e:
            return False, True, f"Failed to connect spectrometer: {str(e)}", {}, {}

    elif button_id == "disconnect-btn" and disconnect_clicks > 0:
        try:
            spectrometer.disconnect()
            return False, True, "HDX spectrometer disconnected.", {}, {}
        except Exception as e:
            return True, False, f"Failed to disconnect spectrometer: {str(e)}", {}, {}

    elif button_id in ["save-wavelength-btn", "save-dark-btn", "save-light-btn", "save-sample-btn"] and directory:
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)

            if button_id == "save-wavelength-btn":
                wavelengths = spectrometer.get_wavelengths()
                df = pd.DataFrame(wavelengths, columns=["Wavelength (nm)"])
                filepath = os.path.join(directory, "Wavelength.csv")
            else:
                spectrometer.set_integration_time(integration_time)
                spectrometer.set_scans_to_average(scans_to_average)
                spectrometer.set_boxcar_width(boxcar_width)
                spectrum = spectrometer.get_spectrum()
                df = pd.DataFrame(spectrum, columns=["Intensity"])

                if button_id == "save-dark-btn":
                    filepath = os.path.join(directory, "DR.csv")
                elif button_id == "save-light-btn":
                    filepath = os.path.join(directory, "LR.csv")
                elif button_id == "save-sample-btn":
                    filename = get_next_sample_filename(directory)
                    filepath = os.path.join(directory, filename)

            df.to_csv(filepath, index=False)
            return dash.no_update, dash.no_update, f"{os.path.basename(filepath)} file saved in {directory}.", {}, {}
        except Exception as e:
            return dash.no_update, dash.no_update, f"Failed to save data: {str(e)}", {}, {}

    elif button_id == "plot-raw-btn" and plot_raw_clicks > 0 and directory:
        try:
            wavelength_filepath = os.path.join(directory, "Wavelength.csv")
            if not os.path.exists(wavelength_filepath):
                return dash.no_update, dash.no_update, "Wavelength data not found.", {}, {}

            wavelengths = pd.read_csv(wavelength_filepath)["Wavelength (nm)"]
            sample_files = sorted([f for f in os.listdir(directory) if f.startswith("Sample") and f.endswith(".csv")])

            raw_data_fig = go.Figure()
            for sample_file in sample_files:
                sample_data = pd.read_csv(os.path.join(directory, sample_file)).iloc[1:2069] # Skip the first row
                raw_data_fig.add_trace(go.Scatter(x=wavelengths, y=sample_data.squeeze(), mode='lines', name=sample_file))

            raw_data_fig.update_layout(title="Raw Data", xaxis_title="Wavelength (nm)", yaxis_title="Intensity")
            return dash.no_update, dash.no_update, "Raw data plotted.", raw_data_fig, {}
        except Exception as e:
            return dash.no_update, dash.no_update, f"Failed to plot raw data: {str(e)}", {}, {}

    elif button_id == "plot-absorbance-btn" and plot_absorbance_clicks > 0 and directory:
        try:
            wavelength_filepath = os.path.join(directory, "Wavelength.csv")
            dr_filepath = os.path.join(directory, "DR.csv")
            lr_filepath = os.path.join(directory, "LR.csv")
            if not os.path.exists(wavelength_filepath) or not os.path.exists(dr_filepath) or not os.path.exists(lr_filepath):
                return dash.no_update, dash.no_update, "Necessary reference data (Wavelength, DR, LR) not found.", {}, {}

            wavelengths = pd.read_csv(wavelength_filepath)["Wavelength (nm)"]
            DR = pd.read_csv(dr_filepath).iloc[1:2069].squeeze()
            LR = pd.read_csv(lr_filepath).iloc[1:2069].squeeze()

            sample_files = sorted([f for f in os.listdir(directory) if f.startswith("Sample") and f.endswith(".csv")])

            absorbance_fig = go.Figure()
            for sample_file in sample_files:
                Sample = pd.read_csv(os.path.join(directory, sample_file)).iloc[1:2069].squeeze()
                absorbance_data = compute_absorbance_adjusted(Sample, DR, LR)
                absorbance_fig.add_trace(go.Scatter(x=wavelengths, y=absorbance_data, mode='lines', name=sample_file))

            absorbance_fig.update_layout(title="Absorbance Data", xaxis_title="Wavelength (nm)", yaxis_title="Absorbance")
            return dash.no_update, dash.no_update, "Absorbance data plotted.", {}, absorbance_fig
        except Exception as e:
            return dash.no_update, dash.no_update, f"Failed to plot absorbance data: {str(e)}", {}, {}

    elif button_id == "clear-btn" and clear_clicks > 0:
        return dash.no_update, dash.no_update, "Plots cleared.", {}, {}

    return dash.no_update, dash.no_update, "", {}, {}

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
 
