# catalog.py
# -----------------------------------------------------------------
# Predefined prompt examples + dynamic driver catalog from pylabdrivers
# -----------------------------------------------------------------

from labautomate.driver_loader import get_driver_catalog, get_drivers_path

# -----------------------------------------------------------------
# Dynamic driver catalog — auto-generated from installed pylabdrivers
# -----------------------------------------------------------------
try:
    pump_file_catalog = get_driver_catalog()
except FileNotFoundError:
    pump_file_catalog = {}


# -----------------------------------------------------------------
# Showcase 1 — Dash app: four lab pumps (ISCO, Reaxus, Knauer, Harvard)
# -----------------------------------------------------------------
SHOWCASE1 = """Project Overview

I am designing a Python Dash web application for the remote control and automation of four laboratory pumps: Teledyne ISCO, Teledyne Reaxus, Azura Knauer, and Harvard Syringe pumps. These pumps are supported by the PyLabDrivers package, which provides the necessary Python drivers. The web application's layout is divided into four sections, each with rounded borders. The first row contains sections for controlling the Teledyne ISCO (left) and Teledyne Reaxus (right) pumps, while the second row contains sections for the Azura Knauer (left) and Harvard Syringe (right) pumps. Serial communication is used for all four pumps.

User Interface Design

Teledyne ISCO Section

Buttons
- "Connect ISCO"
- "Set & Run ISCO"
- "Disconnect ISCO"

Inputs
- USB COM port (e.g., COM3)
- Flowrate setpoint

Dropdowns
- Flowrate units (ML/MIN, ML/HR, UL/MIN, UL/HR)
- Pressure units (ATM, BAR, KPA, PSI)

Teledyne Reaxus Section

Buttons
- "Connect Reaxus"
- "Set Reaxus"
- "Run Reaxus"
- "Stop Reaxus"
- "Disconnect Reaxus"

Inputs
- USB COM port
- Flowrate setpoint

Azura Knauer Section

Buttons
- "Connect Knauer"
- "Run Knauer"
- "Disconnect Knauer"

Inputs
- USB COM port
- Flowrate setpoint

Dropdown
- Pump head size (50 ml, 10 ml)

Harvard Syringe Pump Section

Buttons
- "Connect Harvard"
- "Run Harvard"
- "Disconnect Harvard"

Inputs
- USB COM port
- Flowrate infusion setpoint
- Syringe volume setpoint

Indicator
- Displays actual infusion rate every 5 seconds

Default Unit
- Flowrate unit set to ml/min

Functionality and Logic

Teledyne ISCO Section

- Connect: Initializes the ISCO pump, sets it to Remote mode, and configures constant flow mode with specified units.
- Set & Run: Sets the specified flowrate setpoint and runs the pump.
- Disconnect: Stops the pump, clears settings, returns to local mode, and disconnects serial communication.

Teledyne Reaxus Section

- Connect: Establishes serial connection.
- Set: Configures the specified flowrate setpoint.
- Run: Starts the pump.
- Stop: Stops the pump.
- Disconnect: Terminates the serial connection.

Azura Knauer Section

- Connect: Establishes serial connection, sets to Remote mode, and selects pump head size.
- Run: Configures the flowrate and starts the pump.
- Disconnect: Stops the pump, returns to local mode, and disconnects serial communication.

Harvard Syringe Pump Section

- Connect: Establishes serial connection and sets syringe volume.
- Run: Configures the infusion rate, runs the pump, and updates the infusion rate every 5 seconds.
- Disconnect: Stops the pump, clears settings, and disconnects serial communication.

Technical Implementation

Ensure that the output IDs for the callback functions are unique across all sections to avoid any conflicts or errors.

Documentation and References

Reference to PyLabDrivers package documentation."""


# -----------------------------------------------------------------
# Showcase 2 — New driver: Teledyne ReaXus LD-Class pump
# (used as the pre-filled example in the Driver tab)
# -----------------------------------------------------------------
SHOWCASE2_DRIVER = """Project Overview

I am working on automating the Teledyne ReaXus LD-Class pump, which is a high-pressure dual piston pump. This pump has hardware differences compared to the existing Teledyne ReaXus pump driver available in the PyLabDrivers package (specifically, the teledynereaxus.py file). My goal is to develop a Python driver for the Teledyne ReaXus LD-Class pump, following the object-oriented structure and style of the existing Teledyne ReaXus pump driver.

User Interface Design

Not applicable (focus on driver development).

Functionality and Logic

The Python driver should be implemented as a class that:
- Accepts a USB port argument (e.g., COM3).
- Uses predefined serial communication settings based on the manual.

The class should include the following methods:
- send_command(command)
- read_response()
- connect()
- disconnect()
- run_pump()
- stop_pump()
- get_status()
- get_flowrate()  # in ml/min
- set_flowrate(flowrate)  # in ml/min
- get_pressure()
- get_pressure_unit()
- set_upper_pressure(pressure)
- set_lower_pressure(pressure)
- get_upper_pressure()
- get_lower_pressure()
- get_maximum_pressure()
- get_maximum_flow()
- enable_keypad()
- disable_keypad()

Technical Implementation

Follow the object-oriented structure and style of the existing Teledyne ReaXus pump driver.
Implement serial communication settings as per the manual documentation.
Include a commented section at the end of the driver code demonstrating how to use the driver effectively.

Documentation and References

Refer to Appendix A on page 33 of the manual documentation for details on the Rear Panel Serial Communications Port.
Carefully review pages 33 to 40 to understand the serial command format and the available commands for this pump.
Reference to PyLabDrivers package documentation."""


# -----------------------------------------------------------------
# Showcase 3 — Dash app: PAT tools (Ocean Optics + Mettler Toledo)
# -----------------------------------------------------------------
SHOWCASE3 = """Project Overview

I am developing a Python Dash web application for the remote control of three separate online Process Analytical Technology (PAT) tools:
- Ocean Optics HDX Spectrometer for UV-Vis spectroscopy
- Mettler Toledo React IR for IR spectroscopy
- Mettler Toledo React Raman for Raman spectroscopy

The web application will consist of two independent tabs:
- Tab 1: Ocean Optics HDX Spectrometer (UV-Vis Spectroscopy)
- Tab 2: Mettler Toledo React IR and React Raman Spectrometers

Each tab operates independently, meaning that actions in one tab do not interfere with the other. Users can switch between tabs without disrupting ongoing operations.

User Interface Design

Tab 1: Ocean Optics HDX Spectrometer

Input Boxes:
- Directory for saving Excel data
- Integration time
- Scans to average
- Boxcar width

Buttons:
- Connect HDX
- Disconnect HDX
- Save Wavelength
- Save Dark Reference
- Save Light Reference
- Save Sample Spectra

Message Box: Displays status messages based on user actions.

Data Visualization:
- Two empty plots for displaying:
  - Raw intensity sample data versus wavelength
  - Absorbance intensity sample data versus wavelength

Plot Buttons:
- Plot Raw Intensity Data
- Plot Absorbance Data
- Clear Data

Tab 2: Mettler Toledo React IR and React Raman Spectrometers

Input Boxes:
- OPC UA Server URL
- Directory for saving Excel files
- Node ID 1 for React IR
- Node ID 2 for React IR
- Node ID 1 for React Raman
- Node ID 2 for React Raman

Buttons:
- Run MT Spectrometers
- Stop MT Spectrometers

Plots:
- Plot 1: Displays values for React IR Node ID 1 and Node ID 2 over time.
- Plot 2: Displays values for React Raman Node ID 1 and Node ID 2 over time.

Message Box: Shows corresponding messages when the Run and Stop buttons are pressed.

Functionality and Logic

Tab 1: Ocean Optics HDX Spectrometer

- Connect Button: Opens serial communication using the Ocean Optics driver and displays a success message.
- Disconnect Button: Closes the serial channel and shows a corresponding message.
- Save Wavelength Button: Saves wavelength data as wavelength.csv in the user-defined directory and displays a confirmation message.
- Save Dark Reference Button: Saves UV intensity data (when the UV light source is off) as DR.csv and shows a confirmation message.
- Save Light Reference Button: Saves UV intensity data (when the UV light source is on) as LR.csv and displays a confirmation message.
- Save Sample Spectra Button: Saves UV intensity data as Sample 1.csv, Sample 2.csv, etc., based on user-defined settings, with a confirmation message for each save.
- Plot Raw Intensity Data Button: Displays available sample files as y-values against wavelength as x-values, with a legend for each sample.
- Plot Absorbance Data Button: Applies Beer-Lambert law to calculate absorbance for each sample and plots it against wavelength, using the formula:
  Absorbance = Log10(((Intensity of Sample) - (Intensity of Dark Reference)) / ((Intensity of Light Reference) - (Intensity of Dark Reference)))
- Clear Data Button: Refreshes both plots and clears all previous data.

Tab 2: Mettler Toledo React IR and React Raman Spectrometers

- Run MT Spectrometers Button:
  - Starts a timer (refreshes the time counter).
  - Initiates data acquisition via the OPC UA communication protocol using the provided server URL and Node IDs for both IR and Raman spectrometers.
  - Appends data every 5 seconds to a list and updates both plots with the new data points.
- Stop MT Spectrometers Button:
  - Stops the data acquisition process.
  - Disconnects communication with the OPC UA client.
  - When the user presses the Run button again, both plots and the time counter will refresh, allowing for a new data acquisition session.

Technical Implementation

Ensure that the output IDs for the callback functions are unique across all sections to avoid any conflicts or errors.
Utilize the Ocean Optics driver (oceanoptics.py) for serial communication with the HDX Spectrometer.
Implement OPC UA communication protocol for Mettler Toledo React IR and React Raman spectrometers by importing Python's opcua library.

Documentation and References

Reference to OPC UA server communication and example for Mettler Toledo instruments.
Ocean Optics driver documentation."""


# -----------------------------------------------------------------
# Showcase 4 — Dash app: automated dynamic flow experiment
# -----------------------------------------------------------------
SHOWCASE4 = """Project Overview

I want to design a Python Dash webapp to perform an automated dynamic flow experimental run by controlling two Teledyne ISCO pumps, one Equilibar Pressure controller, two VICI Valco Valves, Vapourtec platform (specifically R4 module and reactor 1 on that module), and Mettler Toledo React IR instrument. The automated dynamic run includes three phases: (i) initial pre-ramp steady state period, ramp period, and post-ramp period. During the initial pre-ramp steady state period, pumps will run and flow at constant initial flowrates for a certain period of time. Then, during the ramp period, all the pumps' flowrates will linearly decrease to their minimum flowrates, and they will stay at the minimum flowrate for a certain duration during the post-ramp period.

User Interface Design

Input Boxes:
- Reactor Volume (e.g., 20000 uL)
- Dead Volume (e.g., 100 uL)
- Initial Steady State Pre-Ramp time (e.g., 600 seconds)
- Post-Ramp Duration (e.g., 2700 seconds)
- Ramp Duration (e.g., 60 minutes)
- Start Flow Rate (e.g., 1000 uL/min)
- End Flow Rate (e.g., 333 uL/min)
- Recording Interval Time (e.g., 5 seconds)
- USB COM port for Teledyne ISCO Pump 1
- USB COM port for Teledyne ISCO Pump 2
- USB COM port for Equilibar Pressure Controller
- Pressure setpoint for Equilibar Pressure Controller
- USB COM port for VICI Valco Valve 1
- USB COM port for VICI Valco Valve 2
- IP address for Vapourtec platform (e.g., 192.168.0.100)
- Port number for Vapourtec platform (e.g., 43344)
- Target temperature setpoint for Vapourtec platform
- OPC URL address for Mettler Toledo React IR communication
- Node ID 1 for Mettler Toledo React IR
- Node ID 2 for Mettler Toledo React IR
- Directory for saving data in an excel file
- Filename (e.g., Run 1)

Indicators:
- Actual pressure reading from the Equilibar pressure controller
- Actual valve position for Valve 1
- Actual valve position for Valve 2
- Reaction temperature from Vapourtec platform
- Calculated minimum residence time
- Calculated maximum residence time
- Real-time value of tau
- Real-time value of F_of_tau
- Experiment timer

Buttons:
- Start Experiment
- Stop Experiment

Plot:
- 2D line-scatter plot for visualization of real-time peak values of Node ID1 and Node ID2 from Mettler Toledo React IR instrument

Functionality and Logic

Mathematical Functions:

Rate of flowrate change (rho):
  rho = ((End Flow Rate / 1000) - (Start Flow Rate / 1000)) / (Ramp Duration)

Residence time (tau):
  tau = (term1 - term2) / rho
  term1 = ((Start Flow Rate / 1000) + (rho * tf))
  term2 = math.sqrt(term1 ** 2 - (2 * rho * (Reactor Volume / 1000)))

Time for exiting the reactor (tf):
  tf = ((Start Flow Rate / 1000) / rho) + math.sqrt((((Start Flow Rate / 1000) / rho) - tm) ** 2 + (2 * (Dead Volume / 1000) / rho))
  tm = current elapsed time / 60

F_of_tau:
  F_of_tau = (Reactor Volume / 1000) / tau

Minimum residence time:
  min_residence_time = reactor volume / Start flow rate

Maximum residence time:
  max_residence_time = reactor volume / End flow rate

Experiment Logic:

Initialization:
- Connect and initialize Teledyne ISCO Pump 1 and set it to constant flow mode.
- Connect and initialize Teledyne ISCO Pump 2 and set it to constant flow mode.
- Connect VICI Valco Valve 1 and Valve 2.
- Connect Equilibar pressure controller.
- Connect to Vapourtec platform and get connected to RSeries via manual control mode and Reactor 1 on R4 module.
- Connect to Mettler Toledo's OPC UA server and introduce Node ID 1 and Node ID 2.

Set Initial Flow Rates:
- Teledyne ISCO Pump 1 Flowrate Setpoint = Start Flowrate / 1000 (to convert from uL/min to mL/min)
- Teledyne ISCO Pump 2 Flowrate Setpoint = (Start Flowrate / 5) / 1000 (to convert from uL/min to mL/min)

Set Temperature and Pressure:
- Set temperature for Reactor 1 in R4 module and start manual control mode.
- Set valve 1 at position 1 and valve 2 at position 1.
- Set the setpoint for Equilibar pressure controller.

Pre-Ramp Steady State:
- Run pumps at initial flowrates.
- Record values for Node ID 1 and Node ID 2 from Mettler Toledo React IR.
- Record values every recording interval.

Ramp Period:
- Change pump flowrates every time interval within the ramp.
- Calculate tm, tf, tau, and F_of_tau.
- Start sample collection when tau equals minimum residence time.

Post-Ramp Period:
- Continue sample collection and data recording.
- Save data to excel file every 15 minutes.

Cleanup:
- Stop and clear all pumps.
- Set temperature on Vapourtec to 25 C and stop manual control.
- Set Equilibar pressure controller to 0.
- Set valves to position 1.
- Disconnect all devices.

Sample Collection Logic:

Once the calculated tau within the ramp period is greater than or equal to the minimum residence time, start the sample collection process.
The sample collection process involves switching Valve 1 to position 2 (collection) and Valve 2 to positions 1 through 28 sequentially.
Each sample collection cycle lasts 5 minutes, with the first 3 minutes for collection and the remaining 2 minutes for switching Valve 1 back to position 1 (waste) and preparing Valve 2 for the next position.
This process continues until 28 samples are collected.

Technical Implementation

Implement logic to handle server disconnection for Mettler Toledo React IR and reconnect to the server.
If Node ID 1 or Node ID 2 values are NaN due to server disconnection, record the previous value until reconnection is successful.
Provide the complete code for the webapp, including the layout, mathematical functions, experiment logic, sample collection logic, and exception handling.

Documentation and References

Reference to OPC UA server communication and example for Mettler Toledo instruments."""


predefined_prompts = {
    "Showcase 1: Dash app — four lab pumps (ISCO, Reaxus, Knauer, Harvard)": SHOWCASE1,
    "Showcase 3: Dash app — PAT tools (Ocean Optics + Mettler Toledo)": SHOWCASE3,
    "Showcase 4: Dash app — automated dynamic flow experiment": SHOWCASE4,
}
