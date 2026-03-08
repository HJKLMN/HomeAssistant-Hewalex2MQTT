from .base import BaseDevice

# Based on work by aelias-eu
# https://github.com/aelias-eu/hewalex-geco-protocol


class ZPS(BaseDevice):
    """Hewalex ZPS solar boiler controller (G-422-P09).

    Register map covers the controller, including controller settings.
    """

    REG_MAX_ADR = 330
    REG_MAX_NUM = 76
    REG_CONFIG_START = 170

    registers = {

        # Status registers
        120: { 'type': 'date', 'name': 'date',                  'desc': 'Date', 'options': None },
        124: { 'type': 'time', 'name': 'time',                  'desc': 'Time', 'options': None },
        128: { 'type': 'temp', 'name': 'T1',                    'desc': 'T1 - Collectors temperature', 'options': None },
        130: { 'type': 'temp', 'name': 'T2',                    'desc': 'T2 - Tank bottom temperature', 'options': None },
        132: { 'type': 'temp', 'name': 'T3',                    'desc': 'T3 - Air separator temperature', 'options': None },
        134: { 'type': 'temp', 'name': 'T4',                    'desc': 'T4 - Tank top temperature', 'options': None },
        136: { 'type': 'temp', 'name': 'T5',                    'desc': 'T5 - Boiler outlet temperature', 'options': None },
        138: { 'type': 'temp', 'name': 'T6',                    'desc': 'T6', 'options': None },
        144: { 'type': 'word', 'name': 'CollectorPower',        'desc': 'Collector power (W)', 'options': None },
        148: { 'type': 'fl10', 'name': 'Consumption',           'desc': 'Consumption (W)', 'options': None },
        150: { 'type': 'bool', 'name': 'CollectorActive',       'desc': 'Collector active (True/False)', 'options': None },
        152: { 'type': 'fl10', 'name': 'FlowRate',              'desc': 'Flow rate (l/min)', 'options': None },
        154: { 'type': 'mask', 'name': [
            'CollectorPumpON',      # Collector pump (P) running
            None,
            'CirculationPumpON',    # Circulation pump (C) running
        ], 'options': None },
        156: { 'type': 'word', 'name': 'CollectorPumpSpeed',    'desc': 'Collector pump speed (0-15)', 'options': None },
        166: { 'type': 'fl10', 'name': 'TotalEnergy',           'desc': 'Total energy (kWh)', 'options': None },

        # Config registers
        170: { 'type': 'word', 'name': 'InstallationScheme',        'desc': 'Installation scheme (1-19)', 'options': None },
        172: { 'type': 'word', 'name': 'DisplayTimeout',            'desc': 'Display timeout (1-10 min)', 'options': None },
        174: { 'type': 'word', 'name': 'DisplayBrightness',         'desc': 'Display brightness (1-10)', 'options': None },
        176: { 'type': 'bool', 'name': 'AlarmSoundEnabled',         'desc': 'Alarm sound enabled (True/False)', 'options': None },
        178: { 'type': 'bool', 'name': 'KeySoundEnabled',           'desc': 'Key sound enabled (True/False)', 'options': None },
        180: { 'type': 'word', 'name': 'DisplayLanguage',           'desc': 'Display language: 0=PL, 1=EN, 2=DE, 3=FR, 4=PT, 5=ES, 6=NL, 7=IT, 8=CZ, 9=SL', 'options': None },
        182: { 'type': 'temp', 'name': 'FluidFreezingTemp',         'desc': 'Fluid freezing temperature', 'options': None },
        186: { 'type': 'fl10', 'name': 'FlowRateNominal',           'desc': 'Flow rate nominal (l/min)', 'options': None },
        188: { 'type': 'word', 'name': 'FlowRateMeasurement',       'desc': 'Flow rate measurement: 0=Rotameter, 1=Electronic G916, 2=Electronic', 'options': None },
        190: { 'type': 'f100', 'name': 'FlowRateWeight',            'desc': 'Flow rate weight (imp/l)', 'options': None },
        192: { 'type': 'bool', 'name': 'HolidayEnabled',            'desc': 'Holiday mode enabled (True/False)', 'options': None },
        194: { 'type': 'word', 'name': 'HolidayStartDay',           'desc': 'Holiday start day', 'options': None },
        196: { 'type': 'word', 'name': 'HolidayStartMonth',         'desc': 'Holiday start month', 'options': None },
        198: { 'type': 'word', 'name': 'HolidayStartYear',          'desc': 'Holiday start year', 'options': None },
        200: { 'type': 'word', 'name': 'HolidayEndDay',             'desc': 'Holiday end day', 'options': None },
        202: { 'type': 'word', 'name': 'HolidayEndMonth',           'desc': 'Holiday end month', 'options': None },
        204: { 'type': 'word', 'name': 'HolidayEndYear',            'desc': 'Holiday end year', 'options': None },
        206: { 'type': 'word', 'name': 'CollectorType',             'desc': 'Collector type: 0=Flat, 1=Tube', 'options': None },
        208: { 'type': 'temp', 'name': 'CollectorPumpHysteresis',   'desc': 'T1-T2 difference to activate collector pump', 'options': None },
        210: { 'type': 'temp', 'name': 'ExtraPumpHysteresis',       'desc': 'Temperature difference to activate extra pump', 'options': None },
        212: { 'type': 'temp', 'name': 'CollectorPumpMaxTemp',      'desc': 'Maximum T2 to turn off collector pump', 'options': None },
        214: { 'type': 'word', 'name': 'BoilerPumpMinTemp',         'desc': 'Minimum T5 to activate boiler pump', 'options': None },
        218: { 'type': 'word', 'name': 'HeatSourceMaxTemp',         'desc': 'Maximum T4 to turn off heat sources', 'options': None },
        220: { 'type': 'word', 'name': 'BoilerPumpMaxTemp',         'desc': 'Maximum T4 to turn off boiler pump', 'options': None },
        222: { 'type': 'bool', 'name': 'PumpRegulationEnabled',     'desc': 'Pump regulation enabled (True/False)', 'options': None },
        226: { 'type': 'word', 'name': 'HeatSourceMaxCollectorPower', 'desc': 'Maximum collector power to turn off heat sources (100-9900 W)', 'options': None },
        228: { 'type': 'bool', 'name': 'CollectorOverheatProtEnabled', 'desc': 'Collector overheat protection enabled (True/False)', 'options': None },
        230: { 'type': 'temp', 'name': 'CollectorOverheatProtMaxTemp', 'desc': 'Maximum T2 for overheat protection', 'options': None },
        232: { 'type': 'bool', 'name': 'CollectorFreezingProtEnabled', 'desc': 'Collector freezing protection enabled (True/False)', 'options': None },
        234: { 'type': 'word', 'name': 'HeatingPriority',           'desc': 'Heating priority', 'options': None },
        236: { 'type': 'bool', 'name': 'LegionellaProtEnabled',     'desc': 'Legionella protection enabled (True/False)', 'options': None },
        238: { 'type': 'bool', 'name': 'LockBoilerKWithBoilerC',    'desc': 'Lock boiler K with boiler C (True/False)', 'options': None },
        240: { 'type': 'bool', 'name': 'NightCoolingEnabled',       'desc': 'Night cooling enabled (True/False)', 'options': None },
        242: { 'type': 'temp', 'name': 'NightCoolingStartTemp',     'desc': 'Night cooling start temperature', 'options': None },
        244: { 'type': 'temp', 'name': 'NightCoolingStopTemp',      'desc': 'Night cooling stop temperature', 'options': None },
        246: { 'type': 'word', 'name': 'NightCoolingStopTime',      'desc': 'Night cooling stop time (hr)', 'options': None },
        248: { 'type': 'tprg', 'name': 'TimeProgramCM-F',           'desc': 'Time program C Mon-Fri (True/False per hour)', 'options': None },
        252: { 'type': 'tprg', 'name': 'TimeProgramCSat',           'desc': 'Time program C Saturday (True/False per hour)', 'options': None },
        256: { 'type': 'tprg', 'name': 'TimeProgramCSun',           'desc': 'Time program C Sunday (True/False per hour)', 'options': None },
        260: { 'type': 'tprg', 'name': 'TimeProgramKM-F',           'desc': 'Time program K Mon-Fri (True/False per hour)', 'options': None },
        264: { 'type': 'tprg', 'name': 'TimeProgramKSat',           'desc': 'Time program K Saturday (True/False per hour)', 'options': None },
        268: { 'type': 'tprg', 'name': 'TimeProgramKSun',           'desc': 'Time program K Sunday (True/False per hour)', 'options': None },
        278: { 'type': 'word', 'name': 'CollectorPumpMinRev',       'desc': 'Collector pump minimum speed (rev/min)', 'options': None },
        280: { 'type': 'word', 'name': 'CollectorPumpMaxRev',       'desc': 'Collector pump maximum speed (rev/min)', 'options': None },
        282: { 'type': 'word', 'name': 'CollectorPumpMinIncTime',   'desc': 'Collector pump minimum increase time (s)', 'options': None },
        284: { 'type': 'word', 'name': 'CollectorPumpMinDecTime',   'desc': 'Collector pump minimum decrease time (s)', 'options': None },
        286: { 'type': 'word', 'name': 'CollectorPumpStartupSpeed', 'desc': 'Collector pump startup speed (1-15)', 'options': None },
        288: { 'type': 'bool', 'name': 'PressureSwitchEnabled',     'desc': 'Pressure switch enabled (True/False)', 'options': None },
        290: { 'type': 'bool', 'name': 'TankOverheatProtEnabled',   'desc': 'Tank overheat protection enabled (True/False)', 'options': None },
        322: { 'type': 'bool', 'name': 'CirculationPumpEnabled',    'desc': 'Circulation pump enabled (True/False)', 'options': None },
        324: { 'type': 'word', 'name': 'CirculationPumpMode',       'desc': 'Circulation pump mode: 0=Discontinuous, 1=Continuous', 'options': None },
        326: { 'type': 'temp', 'name': 'CirculationPumpMinTemp',    'desc': 'Minimum T4 to activate circulation pump', 'options': None },
        328: { 'type': 'word', 'name': 'CirculationPumpONTime',     'desc': 'Circulation pump ON time (1-59 min)', 'options': None },
        330: { 'type': 'word', 'name': 'CirculationPumpOFFTime',    'desc': 'Circulation pump OFF time (1-59 min)', 'options': None },

        # Registers in config space with status-like behaviour
        312: { 'type': 'dwrd', 'name': 'TotalOperationTime', 'desc': 'Total operation time (min)', 'options': None },
        320: { 'type': 'word', 'name': 'Reg320',             'desc': 'Unknown register (value changes constantly)', 'options': None },
    }
