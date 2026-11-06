import serial
import time


class TeledyneLDClassError(Exception):
    """Custom exception class for Teledyne ReaXus LD-Class pump errors."""
    pass


class TeledyneLDClass:
    """
    Driver for the Teledyne ReaXus LD-Class High Pressure Dual Piston Pump.

    Communicates via RS-232 serial interface using the protocol described in
    Appendix A of the LD-Class Operator Manual (903036Rx REV M).

    Serial settings (from manual):
        - Baud rate: 9600 (default)
        - Data bits: 8
        - Stop bits: 1
        - Parity: None
        - Termination character: '/' (response), carriage return (command)
    """

    def __init__(self, port):
        """
        Initializes the Teledyne ReaXus LD-Class pump instance.

        Parameters:
            port (str): The serial port to connect to (e.g., 'COM3' or '/dev/ttyUSB0').
        """
        self.port = port
        self.ser = None

    def connect(self):
        """
        Establishes a serial connection to the Teledyne LD-Class pump.

        Raises:
            TeledyneLDClassError: If there is an error opening the serial port.
        """
        try:
            self.ser = serial.Serial(
                self.port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2
            )
            time.sleep(0.5)
            print(f"Successfully connected to LD-Class pump on {self.port}.")
        except serial.SerialException as e:
            raise TeledyneLDClassError(f"Error opening serial port {self.port}: {e}")

    def disconnect(self):
        """
        Closes the serial connection to the pump if it is open.

        Raises:
            TeledyneLDClassError: If there is an error closing the serial port.
        """
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                print(f"Serial port {self.port} closed successfully.")
            except serial.SerialException as e:
                raise TeledyneLDClassError(f"Error closing serial port {self.port}: {e}")
            finally:
                self.ser = None
        else:
            print(f"Serial port {self.port} is already closed or was not opened.")

    def send_command(self, command):
        """
        Sends a command to the pump. A carriage return is appended to indicate
        the end of the transmitted string, which causes the pump to immediately
        respond to the received command.

        Parameters:
            command (str): The command string to send (e.g., 'RU', 'FI01200').

        Raises:
            TeledyneLDClassError: If the serial port is not open or a communication error occurs.
        """
        if not (self.ser and self.ser.is_open):
            raise TeledyneLDClassError("Serial port is not open.")
        full_command = command + "\r"
        try:
            self.ser.write(full_command.encode())
            time.sleep(0.2)
        except serial.SerialTimeoutException:
            raise TeledyneLDClassError("Timeout occurred while sending command.")
        except serial.SerialException as e:
            raise TeledyneLDClassError(f"Serial communication error: {e}")

    def read_response(self):
        """
        Reads the pump's response from the serial port until the termination
        character '/' is encountered. If an error response ('Er/') is received,
        a '#' character is sent to clear the command buffer, and an exception
        is raised.

        Returns:
            str: The decoded pump response string (including the '/' terminator).

        Raises:
            TeledyneLDClassError: If an error response is received, a timeout occurs,
                or a communication error occurs.
        """
        if not (self.ser and self.ser.is_open):
            raise TeledyneLDClassError("Serial port is not open.")
        try:
            response = self.ser.read_until(b'/')
            if not response:
                raise TimeoutError("No response received from pump (timeout).")
            response_str = response.decode().strip()
            if response_str.startswith("Er"):
                # Clear any residual characters from the command buffer.
                self.ser.write(b"#")
                raise TeledyneLDClassError(
                    f"Error response received from pump: {response_str}"
                )
            return response_str
        except TimeoutError as e:
            raise TeledyneLDClassError(f"Communication timeout: {e}")
        except serial.SerialException as e:
            raise TeledyneLDClassError(f"Serial communication error: {e}")

    def _query(self, command):
        """
        Sends a command and reads the response from the pump.

        Parameters:
            command (str): The command string to send.

        Returns:
            str: The pump's response string.

        Raises:
            TeledyneLDClassError: If communication fails.
        """
        self.send_command(command)
        return self.read_response()

    # ---------------------------
    # Pump control methods
    # ---------------------------

    def run_pump(self):
        """
        Starts the pump.

        Command: RU
        Expected Response: OK/

        Returns:
            str: The pump's response.

        Raises:
            TeledyneLDClassError: If communication fails.
        """
        return self._query("RU")

    def stop_pump(self):
        """
        Stops the pump.

        Command: ST
        Expected Response: OK/

        Returns:
            str: The pump's response.

        Raises:
            TeledyneLDClassError: If communication fails.
        """
        return self._query("ST")

    def get_status(self):
        """
        Retrieves the current status of the pump including flow rate,
        upper/lower pressure limits, pressure units, and run/stop state.

        Command: CS
        Expected Response: OK,<flow>,<UPL>,<LPL>,<p_units>,0,<R/S>,0/

        Returns:
            str: The pump's response string.

        Raises:
            TeledyneLDClassError: If communication fails.
        """
        return self._query("CS")

    def get_flowrate(self):
        """
        Retrieves the current flow rate in mL/min by querying the current
        conditions command.

        Command: CC
        Expected Response: OK,<pressure>,<flow>/

        Returns:
            float: The current flow rate in mL/min.

        Raises:
            TeledyneLDClassError: If communication fails or response cannot be parsed.
        """
        response = self._query("CC")
        try:
            # Response format: OK,<pressure>,<flow>/
            # Remove trailing '/' and split
            parts = response.rstrip('/').split(',')
            flow_str = parts[2].strip()
            return float(flow_str)
        except (IndexError, ValueError) as e:
            raise TeledyneLDClassError(
                f"Failed to parse flow rate from response '{response}': {e}"
            )

    def set_flowrate(self, flowrate):
        """
        Sets the pump's flow rate in mL/min. The value is sent as a 5-digit
        integer representation (e.g., 12.000 mL/min -> '12000', 1.200 mL/min -> '01200').

        The pump automatically determines decimal placement based on pump model:
            - 12 mL/min model: resolution 0.001 mL/min (FI12000 = 12.000)
            - 36 mL/min model: resolution 0.01 mL/min (FI03600 = 36.00)
            - 100 mL/min model: resolution 0.1 mL/min (FI01000 = 100.0)

        If the entered value exceeds the pump's maximum allowable flow rate,
        the pump will automatically set the flow rate to the maximum.

        Command: FIxxxxx
        Expected Response: OK,FI:<flow>/

        Parameters:
            flowrate (float or int): Desired flow rate in mL/min.

        Returns:
            str: The pump's response.

        Raises:
            TeledyneLDClassError: If communication fails.
            ValueError: If flowrate is negative.
        """
        if flowrate < 0:
            raise ValueError("Flow rate cannot be negative.")
        # Convert flow rate to the 5-digit integer format.
        # The pump interprets the digits based on its model.
        # We multiply by 1000 for the highest resolution (12 mL/min model).
        # For other models, the pump will interpret appropriately.
        flow_int = int(round(flowrate * 1000))
        flow_str = f"{flow_int:05d}"
        return self._query("FI" + flow_str)

    def get_pressure(self):
        """
        Retrieves the current operating pressure.

        Command: PR
        Expected Response: OK,<pressure>/

        Returns:
            float: The current pressure value.

        Raises:
            TeledyneLDClassError: If communication fails or response cannot be parsed.
        """
        response = self._query("PR")
        try:
            # Response format: OK,<pressure>/
            parts = response.rstrip('/').split(',')
            pressure_str = parts[1].strip()
            return float(pressure_str)
        except (IndexError, ValueError) as e:
            raise TeledyneLDClassError(
                f"Failed to parse pressure from response '{response}': {e}"
            )

    def get_pressure_unit(self):
        """
        Retrieves the current pressure units (e.g., 'psi', 'bar', 'MPa').

        Command: PU
        Expected Response: OK,<p_units>/

        Returns:
            str: The pressure unit string.

        Raises:
            TeledyneLDClassError: If communication fails or response cannot be parsed.
        """
        response = self._query("PU")
        try:
            # Response format: OK,<p_units>/
            parts = response.rstrip('/').split(',')
            units_str = parts[1].strip()
            return units_str
        except (IndexError, ValueError) as e:
            raise TeledyneLDClassError(
                f"Failed to parse pressure units from response '{response}': {e}"
            )

    def set_upper_pressure(self, pressure):
        """
        Sets the upper pressure limit for the pump. When the system pressure
        exceeds this limit, an upper pressure fault is triggered and the pump stops.

        Command: UPxxxxx
        Expected Response: OK/

        Parameters:
            pressure (int): The upper pressure limit value (in current pressure units).

        Returns:
            str: The pump's response.

        Raises:
            TeledyneLDClassError: If communication fails.
            ValueError: If pressure is negative.
        """
        if pressure < 0:
            raise ValueError("Upper pressure limit cannot be negative.")
        pressure_str = f"{int(pressure)}"
        return self._query("UP" + pressure_str)

    def set_lower_pressure(self, pressure):
        """
        Sets the lower pressure limit for the pump. When the system pressure
        falls below this limit, a lower pressure fault is triggered and the pump stops.

        Command: LPxxxxx
        Expected Response: OK/

        Parameters:
            pressure (int): The lower pressure limit value (in current pressure units).

        Returns:
            str: The pump's response.

        Raises:
            TeledyneLDClassError: If communication fails.
            ValueError: If pressure is negative.
        """
        if pressure < 0:
            raise ValueError("Lower pressure limit cannot be negative.")
        pressure_str = f"{int(pressure)}"
        return self._query("LP" + pressure_str)

    def get_upper_pressure(self):
        """
        Retrieves the current upper pressure limit.

        Command: UP
        Expected Response: OK,UP:<UPL>/

        Returns:
            float: The upper pressure limit value.

        Raises:
            TeledyneLDClassError: If communication fails or response cannot be parsed.
        """
        response = self._query("UP")
        try:
            # Response format: OK,UP:<UPL>/
            parts = response.rstrip('/').split(':')
            upl_str = parts[1].strip()
            return float(upl_str)
        except (IndexError, ValueError) as e:
            raise TeledyneLDClassError(
                f"Failed to parse upper pressure limit from response '{response}': {e}"
            )

    def get_lower_pressure(self):
        """
        Retrieves the current lower pressure limit.

        Command: LP
        Expected Response: OK,LP:<LPL>/

        Returns:
            float: The lower pressure limit value.

        Raises:
            TeledyneLDClassError: If communication fails or response cannot be parsed.
        """
        response = self._query("LP")
        try:
            # Response format: OK,LP:<LPL>/
            parts = response.rstrip('/').split(':')
            lpl_str = parts[1].strip()
            return float(lpl_str)
        except (IndexError, ValueError) as e:
            raise TeledyneLDClassError(
                f"Failed to parse lower pressure limit from response '{response}': {e}"
            )

    def get_maximum_pressure(self):
        """
        Retrieves the maximum allowable pressure for the pump.

        Command: MP
        Expected Response: OK,MP:<max_pressure>/

        Returns:
            float: The maximum allowable pressure.

        Raises:
            TeledyneLDClassError: If communication fails or response cannot be parsed.
        """
        response = self._query("MP")
        try:
            # Response format: OK,MP:<max_pressure>/
            parts = response.rstrip('/').split(':')
            mp_str = parts[1].strip()
            return float(mp_str)
        except (IndexError, ValueError) as e:
            raise TeledyneLDClassError(
                f"Failed to parse maximum pressure from response '{response}': {e}"
            )

    def get_maximum_flow(self):
        """
        Retrieves the maximum allowable flow rate for the pump in mL/min.

        Command: MF
        Expected Response: OK,MF:<max_flow>/

        Returns:
            float: The maximum allowable flow rate in mL/min.

        Raises:
            TeledyneLDClassError: If communication fails or response cannot be parsed.
        """
        response = self._query("MF")
        try:
            # Response format: OK,MF:<max_flow>/
            parts = response.rstrip('/').split(':')
            mf_str = parts[1].strip()
            return float(mf_str)
        except (IndexError, ValueError) as e:
            raise TeledyneLDClassError(
                f"Failed to parse maximum flow rate from response '{response}': {e}"
            )

    def enable_keypad(self):
        """
        Enables the front panel keypad buttons.

        Command: KE
        Expected Response: OK/

        Returns:
            str: The pump's response.

        Raises:
            TeledyneLDClassError: If communication fails.
        """
        return self._query("KE")

    def disable_keypad(self):
        """
        Disables the front panel keypad buttons.

        Command: KD
        Expected Response: OK/

        Returns:
            str: The pump's response.

        Raises:
            TeledyneLDClassError: If communication fails.
        """
        return self._query("KD")


if __name__ == "__main__":
    # -----------------------------------------------------------------------
    # Usage Example for the Teledyne ReaXus LD-Class Pump Driver
    # -----------------------------------------------------------------------
    # Replace 'COM3' with the appropriate serial port for your system.
    # On Linux, this might be '/dev/ttyUSB0' or '/dev/ttyACM0'.

    SERIAL_PORT = "COM3"

    pump = TeledyneLDClass(port=SERIAL_PORT)

    try:
        # Connect to the pump
        pump.connect()

        # Get pump identification
        print("Status:", pump.get_status())

        # Get maximum flow rate and pressure
        max_flow = pump.get_maximum_flow()
        print(f"Maximum flow rate: {max_flow} mL/min")

        max_pressure = pump.get_maximum_pressure()
        pressure_unit = pump.get_pressure_unit()
        print(f"Maximum pressure: {max_pressure} {pressure_unit}")

        # Set upper and lower pressure limits
        pump.set_upper_pressure(5000)
        pump.set_lower_pressure(0)
        print(f"Upper pressure limit: {pump.get_upper_pressure()} {pressure_unit}")
        print(f"Lower pressure limit: {pump.get_lower_pressure()} {pressure_unit}")

        # Set a flow rate (e.g., 1.000 mL/min)
        pump.set_flowrate(1.000)
        print(f"Flow rate set to 1.000 mL/min")

        # Start the pump
        pump.run_pump()
        print("Pump is running.")

        # Wait and read current conditions
        time.sleep(5)
        current_flow = pump.get_flowrate()
        current_pressure = pump.get_pressure()
        print(f"Current flow rate: {current_flow} mL/min")
        print(f"Current pressure: {current_pressure} {pressure_unit}")

        # Stop the pump
        pump.stop_pump()
        print("Pump stopped.")

        # Disable keypad (for remote-only control)
        pump.disable_keypad()
        print("Keypad disabled.")

        # Re-enable keypad
        pump.enable_keypad()
        print("Keypad enabled.")

    except TeledyneLDClassError as e:
        print(f"Pump error: {e}")
    finally:
        # Always disconnect when done
        pump.disconnect()