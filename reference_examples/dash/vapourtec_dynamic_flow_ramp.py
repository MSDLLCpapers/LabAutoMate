import rseriesopc as rs 
from opcua import Client
import time
import pandas as pd
import os
import math

# Vapourtec connection details
vapourtec_ip = "20.20.200.200"
vapourtec_opc_port = 22222
rseries_client = rs.RSeriesClient(f"opc.tcp://{vapourtec_ip}:{vapourtec_opc_port}")
rseries_client.connect()
rseries = rseries_client.getRSeries()
manualControl = rseries.getManualControl()

# Mettler Toledo OPC UA connection details
mettler_ip = "localhost:62552/iCOpcUaServer" # Provide the actual IP address
mettler_client = Client(f"opc.tcp://{mettler_ip}")
mettler_client.connect()
node_id = "ns=2;s=Local.iCIR.Probe4.Trends.Peak at 965 cm-1.Value" # Provide the Node ID for the IR peak area

# Helper functions for Vapourtec
def wait_until_temperature_reached(reactor, target_temp):
    while reactor.getTemperature() < target_temp:
        print(f"Current Temp: {reactor.getTemperature()} °C")
        time.sleep(1)

def switch_pump_valves_to_solvent(pump_a, pump_b):
    pump_a.setSRValveState(False) # Set pump A to solvent
    pump_b.setSRValveState(False) # Set pump B to solvent

def switch_pump_valves_to_reagent(pump_a, pump_b):
    pump_a.setSRValveState(True) # Set pump A to reagent
    pump_b.setSRValveState(True) # Set pump B to reagent

def set_flow_rates(pump_a, pump_b, flowrate_a, flowrate_b):
    pump_a.setFlowRate(flowrate_a)
    pump_b.setFlowRate(flowrate_b)

def calculate_tf(Q0, rho, tm, VD):
    return ((Q0 / 1000) / rho) + math.sqrt((((Q0 / 1000) / rho) - tm) ** 2 + (2 * (VD / 1000) / rho))

def calculate_tau(Q0, rho, tf, VR):
    term1 = ((Q0 / 1000) + (rho * tf))
    term2 = math.sqrt(term1 ** 2 - (2 * rho * (VR / 1000)))
    return (term1 - term2) / rho

def calculate_F_of_tau(VR, tau):
    return (VR / 1000) / tau

# Function to save data incrementally
def save_data(data, directory, ramp_number, part_number):
    filename = os.path.join(directory, f"Ramp_{ramp_number}_Part{part_number}.xlsx")
    df = pd.DataFrame(data, columns=["Time (min)", "Flowrate A", "Flowrate B", "tf", "tau", "F(tau)", "IR Area"])
    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")

# Function to find the next available Ramp file number
def get_ramp_number(directory):
    ramp_number = 1
    while os.path.exists(os.path.join(directory, f"Ramp_{ramp_number}_Part1.xlsx")):
        ramp_number += 1
    return ramp_number

# Experiment parameters
reactor_volume = 2100 # uL
dead_volume = 100 # uL
temperature_target = 80 # °C
wash_time = 120 # seconds
ramp_duration = 60 # minutes
flowrate_start = 4000 # ul/min (both pumps A and B combined)
flowrate_end = 200 # ul/min (both pumps A and B combined)
recording_interval = 10 # seconds
save_interval_minute = 30 # Save data every 30 minutes (1800 seconds)
initial_steady_time = 300 # 5 minutes of initial steady state (300 seconds)
Q0 = flowrate_start # Initial flowrate
Qend = flowrate_end # End flowrate
rho = ((Qend / 1000) - (Q0 / 1000)) / (ramp_duration) # Rate of flowrate change

# Maximum residence time
min_residence_time = reactor_volume / Q0
max_residence_time = reactor_volume / Qend

# Directory to save results
save_directory = r"C:\Users\YourName\Desktop\dynamic_experiment_results"

# Main experiment loop
def run_experiment(ramp_duration):
    reactor = manualControl.getR4I().getReactors()["4"] # Use Reactor 4 for the experiment
    pump_a = manualControl.getModule(0).getPumpA()
    pump_b = manualControl.getModule(0).getPumpB()

    manualControl.startManualControl()

    # Set reactor temperature and wait until target temperature is reached
    reactor.setTemperature(temperature_target)
    wait_until_temperature_reached(reactor, temperature_target)

    # Wash the reactor with solvent
    switch_pump_valves_to_solvent(pump_a, pump_b)
    set_flow_rates(pump_a, pump_b, 2000, 2000) # 2 ml/min for both pumps
    print("Washing reactor with solvent for 2 minutes...")
    time.sleep(wash_time)

    # Switch to reagent and run both pumps for 5 min at 2000 ul/min each (steady state)
    switch_pump_valves_to_reagent(pump_a, pump_b)
    print("Switching to reagent and running for 5 minutes...")

    data = []
    ramp_number = get_ramp_number(save_directory)
    part_number = 1

    # Start the initial steady-state period (5 minutes)
    start_time = time.time()
    for t in range(0, initial_steady_time, recording_interval):
        current_time = time.time() - start_time
        tm = current_time / 60 # convert to minutes

        # During initial steady state, tau is the minimum residence time, tf = "N/A"
        tau = min_residence_time
        F_of_tau = calculate_F_of_tau(reactor_volume, tau)

        # Get IR data
        ir_data = mettler_client.get_node(node_id).get_value() # Get IR data from Mettler Toledo

        # Record the data
        data.append([tm, 2000, 2000, "N/A", tau, F_of_tau, ir_data])
        print(f"t = {tm} min: Pump A = 2000, Pump B = 2000, tau = {tau}, F(tau) = {F_of_tau}, IR Data = {ir_data}")

        time.sleep(recording_interval)

    # After 5 minutes, start the ramp
    total_time_in_seconds = ramp_duration * 60
    elapsed_time = 0
    start_time = time.time()

    flowrate_a_start = flowrate_start / 2
    flowrate_b_start = flowrate_start / 2
    flowrate_a_end = flowrate_end / 2
    flowrate_b_end = flowrate_end / 2
    
    last_save_time = 0

    # Start the linear ramp
    while elapsed_time < total_time_in_seconds + 600: # Includes 10 minutes after ramp
        current_time = time.time() - start_time
        tm = current_time / 60 # convert to minutes
        elapsed_time = int(current_time)

        # Calculate flow rates
        if elapsed_time < total_time_in_seconds: # During ramp
            flowrate_a = flowrate_a_start + ((flowrate_a_end - flowrate_a_start) / total_time_in_seconds) * current_time
            flowrate_b = flowrate_b_start + ((flowrate_b_end - flowrate_b_start) / total_time_in_seconds) * current_time
        else: # After ramp
            flowrate_a = flowrate_a_end
            flowrate_b = flowrate_b_end

        # Set new flow rates
        set_flow_rates(pump_a, pump_b, flowrate_a, flowrate_b)

        # Calculate tf, tau, F of tau
        tf = calculate_tf(Q0, rho, tm, dead_volume)
        tau = calculate_tau(Q0, rho, tf, reactor_volume)

        if tau > max_residence_time:
            tau = max_residence_time

        F_of_tau = calculate_F_of_tau(reactor_volume, tau)

        # Get IR data
        ir_data = mettler_client.get_node(node_id).get_value() # Get IR data from Mettler Toledo

        # Record the data
        data.append([tm, flowrate_a, flowrate_b, tf, tau, F_of_tau, ir_data])
        print(f"t = {tm} min: Pump A = {flowrate_a}, Pump B = {flowrate_b}, tf = {tf}, tau = {tau}, F(tau) = {F_of_tau}, IR Data = {ir_data}")

        time.sleep(recording_interval)

        # Save data every 30 minutes
        if (tm - last_save_time) >= save_interval_minute:
            save_data(data, save_directory, ramp_number, part_number)
            part_number += 1
            last_save_time = tm
            data = [] # Clear data after saving

    # Final save after 10 minutes of steady flow
    save_data(data, save_directory, ramp_number, part_number)

    # Cleanup
    manualControl.stopAll()
    pump_a.setFlowRate(0)
    pump_b.setFlowRate(0)
    reactor.setTemperature(25)
    rseries_client.disconnect()
    mettler_client.disconnect()

if __name__ == "__main__":
    run_experiment(ramp_duration)

