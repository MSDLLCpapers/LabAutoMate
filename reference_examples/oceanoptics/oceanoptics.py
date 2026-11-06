from oceandirect.OceanDirectAPI import OceanDirectAPI, OceanDirectError 

class Spectrometer:

    def __init__(self):
        self.od = None
        self.device_id = None
        self.device = None
        self.initialize_od()

    def initialize_od(self):
        """Initialize the OceanDirectAPI and find devices."""
        self.od = OceanDirectAPI()
        device_count = self.od.find_usb_devices()
        device_ids = self.od.get_device_ids()

        if device_count == 0:
            raise Exception("No spectrometer devices found.")

        self.device_id = device_ids[0] # Store the first device ID for later use

    def connect(self):
        """Connect to the spectrometer using the stored device ID."""
        if self.od is None:
            self.initialize_od() # Reinitialize the API if it was previously shutdown

        if self.device_id is not None:
            self.device = self.od.open_device(self.device_id)
        else:
            raise Exception("Device ID is not set. Cannot connect to the spectrometer.")

    def set_integration_time(self, time):
        if self.device:
            self.device.set_integration_time(time)

    def set_scans_to_average(self, scans):
        if self.device:
            self.device.set_scans_to_average(scans)

    def set_boxcar_width(self, boxcar):
        if self.device:
            self.device.set_boxcar_width(boxcar)

    def get_spectrum(self):
        if self.device:
            return self.device.get_formatted_spectrum()

    def get_wavelengths(self):
        if self.device:
            return self.device.get_wavelengths()

    def disconnect(self):
        """Disconnect the spectrometer using the stored device ID, then shutdown the API."""
        if self.device_id is not None and self.od:
            self.od.close_device(self.device_id)
            self.od.shutdown() # Shut down the API
            self.od = None # Set od to None to indicate it's been shut down
        else:
            raise Exception("Device ID is not set or API is not initialized. Cannot disconnect the spectrometer.")

