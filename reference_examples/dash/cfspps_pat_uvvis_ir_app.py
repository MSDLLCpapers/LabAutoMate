import dash 
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
import pandas as pd
import os
import time
import json
import csv
import numpy as np
from opcua import Client
import rseriesopc as rs
import threading

# Define a global stop event
stop_event = threading.Event()

# Define the main automation function for the Vapourtec system
def run_vapourtec_system(experiment_counter, threshold, save_directory, stop_event):
    try:
        IPAdress = "20.20.200.200"
        client = rs.RSeriesClient("opc.tcp://" + IPAdress + ":22222")
        client.connect()
        rseries = client.getRSeries()
        experiment = rseries.getExperiment()
        reactionManager = experiment.getReactionManager()
        reactionList = reactionManager.getReactionList()
        rows = reactionList.split("\n")
        rows.pop()
        num_reactions = len(rows) - 1
        reactionParameters = reactionManager.getReactionParameters()
        rj = json.loads(reactionParameters)
        stringDelimiter = rj["CSVStringSeparator"]
        decimalDelimiter = rj["CSVDecimalPoint"]
        rl = list(csv.reader(rows, delimiter=stringDelimiter))
        rl = [[sel.replace(decimalDelimiter, ".") for sel in el] for el in rl]
        manualControl = rseries.getManualControl()
        detector = manualControl.getDetector().getWavelengthNode()
        reaction_status = None
        switch_button = False
        peak_counter = 1

        def save_data_to_excel(data, file_path):
            df = pd.DataFrame(data, columns=['Time', 'Wavelength1', 'Wavelength2', 'Wavelength3', 'Wavelength4'])
            df.to_excel(file_path, index=False)

        def calculate_integral(data):
            time_values = np.array([row[0] for row in data])
            wavelength1_values = np.array([row[1] for row in data])
            wavelength2_values = np.array([row[2] for row in data])
            wavelength3_values = np.array([row[3] for row in data])
            wavelength4_values = np.array([row[4] for row in data])
            integral_value1 = np.trapz(wavelength1_values, time_values)
            integral_value2 = np.trapz(wavelength2_values, time_values)
            integral_value3 = np.trapz(wavelength3_values, time_values)
            integral_value4 = np.trapz(wavelength4_values, time_values)
            return integral_value1, integral_value2, integral_value3, integral_value4

        integrals_file_path = os.path.join(save_directory, "peak_integrals.xlsx")
        if os.path.exists(integrals_file_path):
            integrals_df = pd.read_excel(integrals_file_path)
            peak_integrals = integrals_df.values.tolist()
            peak_counter = int(peak_integrals[-1][0]) + 1
            base_integral1, base_integral2, base_integral3, base_integral4 = peak_integrals[0][1:5]
        else:
            peak_integrals = []
            base_integral1, base_integral2, base_integral3, base_integral4 = None, None, None, None

        while experiment_counter < num_reactions:
            reactionManager.startReaction()
            time.sleep(2)
            recording_data = []
            recording = False
            while True:
                if stop_event.is_set():
                    manualControl.stopAll()
                    break
                status = reactionManager.getCurrentReactionStatus()
                reaction_status = int(status)
                values = detector.get_value()
                Wavelength1 = values[0]
                Wavelength2 = values[1]
                Wavelength3 = values[2]
                Wavelength4 = values[3]
                time.sleep(1)
                if (Wavelength1 > threshold or Wavelength2 > threshold or Wavelength3 > threshold or Wavelength4 > threshold) and not recording:
                    recording = True
                    recording_data = []
                if recording:
                    recording_data.append([time.time(), Wavelength1, Wavelength2, Wavelength3, Wavelength4])
                if (Wavelength1 < threshold and Wavelength2 < threshold and Wavelength3 < threshold and Wavelength4 < threshold) and recording:
                    recording = False
                    file_path = os.path.join(save_directory, f"peak_{peak_counter}.xlsx")
                    save_data_to_excel(recording_data, file_path)
                    integral_value1, integral_value2, integral_value3, integral_value4 = calculate_integral(recording_data)
                    peak_integrals.append([peak_counter, integral_value1, integral_value2, integral_value3, integral_value4])
                    if peak_counter == 1:
                        base_integral1, base_integral2, base_integral3, base_integral4 = integral_value1, integral_value2, integral_value3, integral_value4
                    area_ratio1 = integral_value1 / base_integral1
                    area_ratio2 = integral_value2 / base_integral2
                    area_ratio3 = integral_value3 / base_integral3
                    area_ratio4 = integral_value4 / base_integral4
                    peak_integrals[-1].extend([area_ratio1, area_ratio2, area_ratio3, area_ratio4])
                    integrals_df = pd.DataFrame(peak_integrals, columns=[
                        'Peak Number', 'Integral Value Wavelength1', 'Integral Value Wavelength2', 'Integral Value Wavelength3', 'Integral Value Wavelength4',
                        'Area Ratio Wavelength1', 'Area Ratio Wavelength2', 'Area Ratio Wavelength3', 'Area Ratio Wavelength4'
                    ])
                    integrals_df.to_excel(integrals_file_path, index=False)
                    peak_counter += 1
                if reaction_status in [13, 24] and not switch_button:
                    experiment_counter += 1
                    switch_button = True
                if reaction_status == 0 or (reaction_status == 0 and experiment_counter == num_reactions):
                    break
            if stop_event.is_set():
                manualControl.stopAll()
                break
            if reaction_status == 0:
                break
            if reaction_status == 0 and experiment_counter == num_reactions:
                break
        client.disconnect()
        print("Setup is completely disconnected!")

    except Exception as e:
        print(f"An error occurred: {e}")

# Define the main automation function for the IR spectroscopy system
def run_ir_spectroscopy_system(url, node_ids, threshold, save_directory):
    try:
        client = Client(url)
        client.connect()
        peak_data = []
        peak_counter = 1
        node_objects = [client.get_node(node_id) for node_id in node_ids]

        def save_data_to_excel(data, file_path):
            df = pd.DataFrame(data, columns=['Peak Number', 'Max Value'])
            df.to_excel(file_path, index=False)

        integrals_file_path = os.path.join(save_directory, "IR_integrals.xlsx")
        if os.path.exists(integrals_file_path):
            integrals_df = pd.read_excel(integrals_file_path)
            peak_data = integrals_df.values.tolist()
            peak_counter = int(peak_data[-1][0]) + 1
        else:
            peak_data = []

        while True:
            max_values = [-np.inf for _ in node_ids]
            recording = False
            while True:
                if stop_event.is_set():
                    break
                current_values = [node.get_value() for node in node_objects]
                print(f"Current Values: {current_values}")
                time.sleep(1)
                if any(value > threshold for value in current_values):
                    recording = True
                if recording:
                    max_values = [max(max_values[i], current_values[i]) for i in range(len(node_ids))]
                if all(value < threshold for value in current_values) and recording:
                    recording = False
                    peak_data.append([peak_counter, max(max_values)])
                    save_data_to_excel(peak_data, integrals_file_path)
                    peak_counter += 1
                    break
            if stop_event.is_set():
                break
        client.disconnect()
        print("IR Spectroscopy system disconnected!")

    except Exception as e:
        print(f"An error occurred: {e}")

# Define the stop function for the IR spectroscopy system
def stop_ir_spectroscopy_system(url):
    stop_event.set() # Set the stop event to signal stopping the system

# Define the Dash app
app = dash.Dash(__name__)
app.title = "CF-SPPS Real-time PAT App"
app.layout = html.Div([
    dcc.Tabs([
        dcc.Tab(label='PAT with UV-Vis', children=[
            html.Div([
                html.H1("CF-SPPS Real-time PAT App", style={'textAlign': 'center'}),
                dcc.Input(id='directory-input', type='text', placeholder='Enter directory to save Excel files', style={'width': '400px', 'margin': 'auto', 'display': 'block'}),
                html.Div([
                    dcc.Input(id='experiment-counter-input', type='number', placeholder='Enter experiment counter', value=1, style={'margin-right': '20px'}),
                    dcc.Input(id='threshold-input', type='number', placeholder='Enter threshold value', value=0.5, style={'margin-right': '20px'}),
                    html.Button('Start Experiment', id='start-button', n_clicks=0, style={'margin-right': '20px'}),
                    html.Button('Emergency Stop', id='stop-button', n_clicks=0)
                ], style={'textAlign': 'center', 'margin': '20px 0'}),
                html.Div(id='current-experiment', style={'margin-top': '20px', 'textAlign': 'center'}),
                dcc.Interval(id='interval-component', interval=1*1000, n_intervals=0),
                html.Div([
                    html.Div([
                        dcc.Graph(id='integral-plot')
                    ], className="six columns"),
                    html.Div([
                        dcc.Graph(id='latest-peak-plot')
                    ], className="six columns")
                ], className="row")
            ])
        ]),
        dcc.Tab(label='PAT with IR', children=[
            html.Div([
                html.H1("CF-SPPS Real-time PAT App", style={'textAlign': 'center'}),
                dcc.Input(id='ir-url-input', type='text', placeholder='Enter OPC UA URL', style={'width': '400px', 'margin': 'auto', 'display': 'block'}),
                dcc.Input(id='node-count-input', type='number', placeholder='Enter number of variables', value=1, style={'margin-top': '20px'}),
                html.Div(id='node-id-inputs', style={'margin-top': '20px'}),
                html.Div([
                    dcc.Input(id='ir-threshold-input', type='number', placeholder='Enter threshold value', value=0.5, style={'margin-right': '20px'}),
                    html.Button('Start IR', id='start-ir-button', n_clicks=0, style={'margin-right': '20px'}),
                    html.Button('Stop IR', id='stop-ir-button', n_clicks=0)
                ], style={'textAlign': 'center', 'margin': '20px 0'}),
                html.Div(id='current-ir-experiment', style={'margin-top': '20px', 'textAlign': 'center'}),
                dcc.Interval(id='ir-interval-component', interval=1*1000, n_intervals=0),
                dcc.Graph(id='ir-integral-plot')
            ])
        ])
    ])
])

# Callback to dynamically create node ID input fields
@app.callback(
    Output('node-id-inputs', 'children'),
    Input('node-count-input', 'value')
)
def update_node_id_inputs(count):
    if count is None:
        count = 0
    return [dcc.Input(id={'type': 'node-id-input', 'index': i}, type='text', placeholder=f'Node ID {i+1}', style={'width': '400px', 'margin-top': '10px'}) for i in range(count)]

# Callback to control the UV-Vis experiment
@app.callback(
    Output('current-experiment', 'children'),
    Output('start-button', 'disabled'),
    Output('stop-button', 'disabled'),
    Input('start-button', 'n_clicks'),
    Input('stop-button', 'n_clicks'),
    State('directory-input', 'value'),
    State('experiment-counter-input', 'value'),
    State('threshold-input', 'value')
)
def control_uv_experiment(start_clicks, stop_clicks, directory, experiment_counter, threshold):
    global stop_event
    ctx = dash.callback_context
    if not ctx.triggered:
        return "", False, True
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'start-button':
        if directory and experiment_counter is not None and threshold is not None:
            stop_event.clear() # Clear the stop event before starting
            thread_1 = threading.Thread(target=run_vapourtec_system, args=(experiment_counter, threshold, directory, stop_event))
            thread_1.start()
            return "UV Spectroscopy is running...", True, False
    if button_id == 'stop-button':
        stop_event.set() # Set the stop event to signal stopping
        return "Setup is completely disconnected!", False, True
    return "", False, True

# Callback to control the IR experiment
@app.callback(
    Output('current-ir-experiment', 'children'),
    Output('start-ir-button', 'disabled'),
    Output('stop-ir-button', 'disabled'),
    Input('start-ir-button', 'n_clicks'),
    Input('stop-ir-button', 'n_clicks'),
    State('ir-url-input', 'value'),
    State('node-count-input', 'value'),
    State({'type': 'node-id-input', 'index': dash.dependencies.ALL}, 'value'),
    State('directory-input', 'value'),
    State('ir-threshold-input', 'value')
)
def control_ir_experiment(start_clicks, stop_clicks, url, node_count, node_ids, directory, threshold):
    ctx = dash.callback_context
    if not ctx.triggered:
        return "", False, True
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'start-ir-button':
        if url and node_count is not None and all(node_ids) and directory and threshold is not None:
            stop_event.clear() # Clear the stop event before starting
            thread_3 = threading.Thread(target=run_ir_spectroscopy_system, args=(url, node_ids, threshold, directory))
            thread_3.start()
            return "IR Spectroscopy is running...", True, False
    if button_id == 'stop-ir-button':
        stop_event.set() # Set the stop event to signal stopping
        return "IR Spectroscopy setup is disconnected!", False, True
    return "", False, True

# Callback to update the UV-Vis plots periodically
@app.callback(
    Output('integral-plot', 'figure'),
    Output('latest-peak-plot', 'figure'),
    Input('interval-component', 'n_intervals'),
    State('directory-input', 'value')
)
def update_uv_plots(n_intervals, directory):
    if not directory or not os.path.exists(directory):
        return {}, {}
    integrals_file_path = os.path.join(directory, "peak_integrals.xlsx")
    if not os.path.exists(integrals_file_path):
        return {}, {}
    integrals_df = pd.read_excel(integrals_file_path)
    if integrals_df.empty:
        return {}, {}
    bar_data = []
    shapes = []
    for i, row in integrals_df.iterrows():
        bar_data.append(go.Bar(
            x=[f'Peak {row["Peak Number"]} - 280nm'],
            y=[row['Integral Value Wavelength1']],
            name=f'Wavelength1 Peak {row["Peak Number"]}',
            width=0.5
        ))
        bar_data.append(go.Bar(
            x=[f'Peak {row["Peak Number"]} - 340nm'],
            y=[row['Integral Value Wavelength2']],
            name=f'Wavelength2 Peak {row["Peak Number"]}',
            width=0.5
        ))
        bar_data.append(go.Bar(
            x=[f'Peak {row["Peak Number"]} - 350nm'],
            y=[row['Integral Value Wavelength3']],
            name=f'Wavelength3 Peak {row["Peak Number"]}',
            width=0.5
        ))
        bar_data.append(go.Bar(
            x=[f'Peak {row["Peak Number"]} - 360nm'],
            y=[row['Integral Value Wavelength4']],
            name=f'Wavelength4 Peak {row["Peak Number"]}',
            width=0.5
        ))
        shapes.append({
            'type': 'line',
            'x0': i * 4 + 3.5,
            'x1': i * 4 + 3.5,
            'y0': 0,
            'y1': max([row['Integral Value Wavelength1'], row['Integral Value Wavelength2'], row['Integral Value Wavelength3'], row['Integral Value Wavelength4']]),
            'line': {
                'color': 'black',
                'width': 1,
                'dash': 'dash'
            }
        })
    bar_layout = go.Layout(
        title='Integral Values at Each Wavelength',
        barmode='group',
        showlegend=False,
        xaxis={'title': 'Peak Number'},
        yaxis={'title': 'Integral Value'},
        title_x=0.5,
        bargap=0.15,
        bargroupgap=0.1,
        shapes=shapes
    )
    bar_figure = go.Figure(data=bar_data, layout=bar_layout)
    latest_peak_file = os.path.join(directory, f"peak_{int(integrals_df['Peak Number'].max())}.xlsx")
    if os.path.exists(latest_peak_file):
        latest_peak_df = pd.read_excel(latest_peak_file)
        line_data = [
            go.Scatter(x=latest_peak_df['Time'], y=latest_peak_df['Wavelength1'], mode='lines', name='Wavelength1'),
            go.Scatter(x=latest_peak_df['Time'], y=latest_peak_df['Wavelength2'], mode='lines', name='Wavelength2'),
            go.Scatter(x=latest_peak_df['Time'], y=latest_peak_df['Wavelength3'], mode='lines', name='Wavelength3'),
            go.Scatter(x=latest_peak_df['Time'], y=latest_peak_df['Wavelength4'], mode='lines', name='Wavelength4')
        ]
        line_layout = go.Layout(
            title='Latest Peak Intensities at Different Wavelengths',
            xaxis=dict(title='Time'),
            yaxis=dict(title='Intensity'),
            title_x=0.5,
        )
        line_figure = go.Figure(data=line_data, layout=line_layout)
    else:
        line_figure = {}
    return bar_figure, line_figure

# Callback to update the IR plot periodically
@app.callback(
    Output('ir-integral-plot', 'figure'),
    Input('ir-interval-component', 'n_intervals'),
    State('directory-input', 'value')
)
def update_ir_plot(n_intervals, directory):
    if not directory or not os.path.exists(directory):
        return {}
    integrals_file_path = os.path.join(directory, "IR_integrals.xlsx")
    if not os.path.exists(integrals_file_path):
        return {}
    integrals_df = pd.read_excel(integrals_file_path)
    if integrals_df.empty:
        return {}
    bar_data = []
    for i, row in integrals_df.iterrows():
        bar_data.append(go.Bar(
            x=[f'Peak {row["Peak Number"]}'],
            y=[row['Max Value']],
            name=f'Peak {row["Peak Number"]}',
            width=0.5
        ))
    bar_layout = go.Layout(
        title='Max Values at Each Peak',
        barmode='group',
        showlegend=False,
        xaxis={'title': 'Peak Number'},
        yaxis={'title': 'Max Value'},
        title_x=0.5,
        bargap=0.15,
        bargroupgap=0.1
    )
    return go.Figure(data=bar_data, layout=bar_layout)

# Run the Dash app
if __name__ == '__main__':
    app.run_server(debug=False)

