from .base import BaseDevice

# Based on work by krzysztof1111111111
# https://www.elektroda.pl/rtvforum/topic3499254.html


class PCWU(BaseDevice):
    """Hewalex PCWU heat pump device.

    Driven by PG-426-P01 (controller) and MG-426-P01 (executive module).
    Register map covers the executive module only (no controller settings).
    """

    REG_MAX_ADR = 536
    REG_MAX_NUM = 100
    REG_CONFIG_START = 302
    REG_STATUS_NUM = 104

    # Note on register 202 vs 304:
    # HeatPumpEnabled (reg 304) can be toggled when the G-426 controller is present.
    # With the controller off, register 202 (WaitingStatus) drops to 0 regardless of
    # reg 304. No known register reliably indicates "controller is off".

    registers = {

        # Status registers
        120: { 'type': 'date', 'name': 'date',  'desc': 'Date', 'options': None },
        124: { 'type': 'time', 'name': 'time',  'desc': 'Time', 'options': None },
        128: { 'type': 'te10', 'name': 'T1',    'desc': 'T1 - Ambient temperature', 'options': None },
        130: { 'type': 'te10', 'name': 'T2',    'desc': 'T2 - Tank bottom temperature', 'options': None },
        132: { 'type': 'te10', 'name': 'T3',    'desc': 'T3 - Tank top temperature', 'options': None },
        138: { 'type': 'te10', 'name': 'T6',    'desc': 'T6 - HP water inlet temperature', 'options': None },
        140: { 'type': 'te10', 'name': 'T7',    'desc': 'T7 - HP water outlet temperature', 'options': None },
        142: { 'type': 'te10', 'name': 'T8',    'desc': 'T8 - HP evaporator temperature', 'options': None },
        144: { 'type': 'te10', 'name': 'T9',    'desc': 'T9 - Temperature before compressor', 'options': None },
        146: { 'type': 'te10', 'name': 'T10',   'desc': 'T10 - Temperature after compressor', 'options': None },

        194: { 'type': 'bool', 'name': 'IsManual', 'desc': 'Manual mode active', 'options': None },
        196: { 'type': 'mask', 'name': [
            'FanON',            # Fan running (True/False)
            None,
            'CirculationPumpON',# Circulation pump running (True/False)
            None,
            None,
            'HeatPumpON',       # Heat pump running (True/False)
            None,
            None,
            None,
            None,
            None,
            'CompressorON',     # Compressor running (True/False)
            'HeaterEON',        # Electric heater active (True/False)
        ], 'options': None },
        198: { 'type': 'word', 'name': 'EV1',           'desc': 'Expansion valve position', 'options': None },
        202: { 'type': 'word', 'name': 'WaitingStatus', 'desc': '0 = available, 2 = disabled via register 304', 'options': None },

        # Config registers
        302: { 'type': 'word', 'name': 'InstallationScheme',   'options': [1,2,3,4,5,6,7,8,9],   'desc': 'Installation scheme (1-9)' },
        304: { 'type': 'bool', 'name': 'HeatPumpEnabled',      'options': [0,1],                  'desc': 'Heat pump on/off (True/False)' },
        306: { 'type': 'word', 'name': 'TapWaterSensor',       'options': [0,1,2],                'desc': 'Sensor controlling HP operation: 0=T2, 1=T3, 2=T7 (factory: T2)' },
        308: { 'type': 'te10', 'name': 'TapWaterTemp',         'options': list(range(100, 610, 10)), 'desc': 'Target water temperature [10-60 °C, factory: 50 °C]' },
        310: { 'type': 'te10', 'name': 'TapWaterHysteresis',   'options': list(range(20, 110, 10)),  'desc': 'HP start-up hysteresis [2-10 °C, factory: 5 °C]' },
        312: { 'type': 'te10', 'name': 'AmbientMinTemp',       'options': list(range(-100, 110, 10)),'desc': 'Minimum ambient temperature T1 [-10-10 °C]' },
        314: { 'type': 'tprg', 'name': 'TimeProgramHPM-F',     'options': None,                   'desc': 'Time program HP Mon-Fri (True/False per hour)' },
        318: { 'type': 'tprg', 'name': 'TimeProgramHPSat',     'options': None,                   'desc': 'Time program HP Saturday (True/False per hour)' },
        322: { 'type': 'tprg', 'name': 'TimeProgramHPSun',     'options': None,                   'desc': 'Time program HP Sunday (True/False per hour)' },
        326: { 'type': 'bool', 'name': 'AntiFreezingEnabled',  'options': [0,1],                  'desc': 'Anti-freezing protection (factory: YES)' },
        328: { 'type': 'word', 'name': 'WaterPumpOperationMode','options': [0,1],                 'desc': 'Water pump mode: 0=Continuous, 1=Synchronous' },
        330: { 'type': 'word', 'name': 'FanOperationMode',     'options': [0,1,2],                'desc': 'Fan mode: 0=Max, 1=Min, 2=Day/Night (factory: Max)' },
        332: { 'type': 'word', 'name': 'DefrostingInterval',   'options': None,                   'desc': 'Defrost cycle delay [30-90 min, factory: 45 min]' },
        334: { 'type': 'te10', 'name': 'DefrostingStartTemp',  'options': None,                   'desc': 'Temperature activating defrost [-30-0 °C, factory: -7 °C]' },
        336: { 'type': 'te10', 'name': 'DefrostingStopTemp',   'options': None,                   'desc': 'Temperature ending defrost [2-30 °C, factory: 13 °C]' },
        338: { 'type': 'word', 'name': 'DefrostingMaxTime',    'options': None,                   'desc': 'Maximum defrost duration [1-12 min, factory: 8 min]' },
        516: { 'type': 'bool', 'name': 'ExtControllerHPOFF',   'options': [0,1],                  'desc': 'External controller HP deactivation (factory: YES)' },
    }

    def disable(self, ser):
        """Disable the heat pump via register 304."""
        return self.writeRegister(ser, 304, 0)

    def enable(self, ser):
        """Enable the heat pump via register 304."""
        return self.writeRegister(ser, 304, 1)
