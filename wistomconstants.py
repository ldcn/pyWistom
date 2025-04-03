## Command identifiers (Chapter 11 Tables 11-2 to 11-10 in Wistom User Guide)

COMMAND_ID = {
    "LOGIN": b'\x00\x01',
    "LOGINRES": b'\x01\x01',
    "LOGOUT": b'\x00\x02',
    "SET": b'\x00\x03',
    "SETACK": b'\x01\x03',
    "SETNACK": b'\x02\x03',
    "GET": b'\x00\x04',
    "GETRES": b'\x01\x04',
    "GETERR": b'\x02\x04',
}

## Alarm command identifiers (Chapter 11 Tables 11-11 to 11-15 in Wistom User Guide)

ALARM_ID = {
    "NO_TIME": b'\x01\x05',     # Alarm type 0 (no time stamp)
    "SNMP": b'\x11\x05',        # Alarm type 1 (SNMP style)
    "EPOCH": b'\x21\x05',       # Alarm type 2 (Unix style)
    "UPTIME_MS": b'\x31\x05',   # Alarm type 3 (uptime in millisecond ticks)
    "EPOCH_MS": b'\x41\x05',    # Alarm type 4 (Unix style in milliseconds)
}

# Login result codes (described in page 82 Table 11-18 in Wistom User Guide)

LOGIN_RESULT = {
    "UL1": b'\x00\x00\x00\x01', # Logged in with user level 1
    "UL2": b'\x00\x00\x00\x02', # Logged in with user level 2
    "UL3": b'\x00\x00\x00\x03', # Logged in with user level 3
    "UL4": b'\x00\x00\x00\x04', # Logged in with user level 4
    "UL5": b'\x00\x00\x00\x05', # Logged in with user level 5
    "MAX_USERS_LOGGED_IN": b'\x10\x00\x00\x00',
    "MAX_USERS_SYSTEM": b'\x10\x00\x00\x01',
    "MAX_LOGIN_ATTEMPTS": b'\x10\x00\x00\x02',
    "DENIED": b'\x10\x00\x00\x03',
    "DENIED_FROM_INTERFACE": b'\x10\x00\x00\x04',
    "WRONG_PASSWORD": b'\x10\x00\x00\x07',
    "USER_NOT_FOUND": b'\x10\x00\x00\x08',
}

## Parsers for response headers
## Header structure is dependent on the command id

RESPONSE_HEADER_PARSER = {
    COMMAND_ID["LOGINRES"]: "_parse_loginres_header",
    COMMAND_ID["SETACK"]: "_parse_setack_header",
    COMMAND_ID["SETNACK"]: "_parse_setnack_header",
    COMMAND_ID["GETERR"]: "_parse_geterr_header",
    COMMAND_ID["GETRES"]: "_parse_getres_header",
}


## Response parsers for GET requests
##
## Commands that have no GET response (SET only) are included for error handling
## See API documentation or page 83-112 in the Wistom User Guide

RESPONSE_PARSER = {
    # The "LGIN" app-id is used both for logging into a wistom unit and when logged in
    # When logging in, the op-id "API2" will use API v2 responses,
    # while any other 4-letter combination will use API v1.
    # However "LGIN" is the op-id used in all proximion software.
    #
    # After login, the app-id "LGIN" will work with the other op-ids
    # that are shown below.
    "LGIN": { # Login / User management operations
        "LGIN": "_parse_apiv1_login_response",
        "API2": "_parse_apiv2_login_response",
        "CPWD": "", # SET only
        "COPW": "", # SET only
        "UADD": "", # SET only
        "UDEL": "", # SET only
        "UINF": "_parse_login_user_info_response",
        "SINF": "_parse_login_session_info_response", 
    },

    "ALMH": {
        # Alarm handler operations here
    },

    "OPM#": {
        # OPM operations here
        "AVRG": "_parse_opm_averages_response",
        "ENAB": "_parse_opm_enable_response",
        "CALC": "_parse_opm_power_calc_response",
        "OSNR": "_parse_opm_osnr_config_response",
        "CHCO": "_parse_opm_channel_config_response",
        "FRQO": "_parse_opm_frequency_option_response",
        "FSPC": "_parse_opm_frequency_spectrum_response",
        "WSPC": "_parse_opm_wavelength_spectrum_response",
        "CHNL": "_parse_opm_channel_status_response",
        "CHAL": "_parse_opm_all_channels_status_response",
        "TRSH": "_parse_opm_threshold_response",
        "MINL": "_parse_opm_min_level_response",
        "PCRI": "_parse_opm_peak_criteria_response",
        "TPWR": "_parse_opm_total_power_response",
        "FILW": "_parse_opm_filter_width_response",
        "SWHA": "_parse_opm_switch_handling_response",
    },

    "SMGR": { # System Manager operations
        "REST": "", # SET only
        "IP##": "_parse_network_info_response",
        "FLSH": "", # SET only
        "SER#": "_parse_serial_response",
        "TIME": "_parse_datetime_response",
        "INFO": "_parse_product_info_response",
        "TEMP": "_parse_system_temperature_response",
        "DUMP": "_parse_smgr_dump_response",
        "CLRD": "", # SET only
        "UPTI": "_parse_system_uptime_response",
        "INST": "_parse_smgr_inst_response",
        "SCFG": "_parse_snmp_config_response",
        "SATR": "", # SET only
        "SDTR": "", # SET only
        "SLTR": "_parse_list_snmp_trap_receivers_response",
        "LED#": "_parse_smgr_led_response", # Not implemented
    },

    "SPEC": {
        # Spectrum parameter operations here
    },

    "WSNS": { # Wistsense operations
        "ENAB": "_parse_wistsense_enable",
        "PORT": "_parse_wsns_port",
        "DATA": "_parse_wsns_data",
        "NEXT": "_parse_wsns_next",
        "PARA": "_parse_wsns_para",
        "FILT": "_parse_wsns_filt",
        "RAWB": "_parse_wsns_rawb",
    }
}

ERROR_CODE = {
    b'\x00\x00': "No error", # this "error" is in the api documentation
    b'\x00\x01': "Unknown error",
    b'\x00\x02': "No response",
    b'\x00\x03': "Request failed",
    b'\x00\x04': "Illegal application ID",
    b'\x00\x05': "Illegal operation ID",
    b'\x00\x06': "Illegal tag",
    b'\x00\x07': "Mandatory missing tags",
    b'\x00\x08': "Tag value too low",
    b'\x00\x09': "Tag value too high",
    b'\x00\x0a': "Invalid value",
    b'\x00\x0b': "Length mismatch",
    b'\x00\x0c': "Not initialized",
    b'\x00\x0d': "Invalid configuration",
    b'\x00\x0e': "Out of resources",
    b'\x00\x0f': "User level restriction",
    b'\x00\x10': "Operation not available for GET",
    b'\x00\x11': "Operation not available for SET",
}

## Tag parsers 

TAG_PARSER = {
    'LGIN': {
        'UINF': {
            1: "user_name",
            2: "user_level",
            3: "interfaces",
        },
    },
    'SMGR': {
        'INFO': {
            1: "hardware_product_number",
            2: "hardware_id_number", 
            3: "hardware_revision",
            4: "hardware_serial_number",
            17: "sensor_product_number",
            18: "sensor_id_number",
            19: "sensor_revision",
            20: "sensor_serial_number",
            33: "software_product_number",
            35: "software_revision",
            51: "firmware_revision",
            52: "pld_revision",
            53: "bootstrap_revision",
            54: "switch_software_revision",
            65: "unit_serial",
            66: "production_date",
            80: "start_calibration_frequency",
            81: "end_calibration_frequency",
            82: "start_calibration_temperature",
            83: "end_calibration_temperature",
        },
        'SER#': {
            1: "serial_interface",
            2: "baud_rate",
            3: "data_bits",
            4: "stop_bits",
            5: "parity_bit",
        },
    },
    'SPEC': {
        'CHNL': {
            1: "channel_id_map",
            2: "channel_id",
            100: "switch_port", # Appears in this order in the documentation 
            3: "activate_mask",
            4: "nominal_frequency",
            5: "nominal_power",
            6: "obsolete",
            7: "obsolete",
            8: "frequency_hysteresis",
            9: "obsolete",
            10: "obsolete",
            11: "obsolete",
            12: "osnr_warning",
            13: "osnr_alarm",
            14: "osnr_hysteresis",
            15: "osnr_delta_frequency",
            16: "opm_window",
            17: "delta_power_high_warning",
            18: "delta_power_low_warning",
            19: "delta_power_high_alarm",
            20: "delta_power_low_alarm",
            21: "power_hysteresis",
            22: "delta_frequency_high_warning",
            23: "delta_frequency_low_warning",
            24: "delta_frequency_high_alarm",
            25: "delta_frequency_low_alarm",
            26: "integration_interval",
            27: "channel_description",
        },
        'DELC': {
            2: "channel_id",
        },
        'CTBL': {
            1: "num_channels",
            2: "channel_table",
        }
    },
    'WSNS': {
        'NEXT': {
            101: "port_1_peak_frequencies",
            102: "port_2_peak_frequencies",
            103: "port_3_peak_frequencies",
            104: "port_4_peak_frequencies",
            105: "port_5_peak_frequencies",
            106: "port_6_peak_frequencies",
            107: "port_7_peak_frequencies",
            108: "port_8_peak_frequencies",
            109: "port_9_peak_frequencies",
            110: "port_10_peak_frequencies",
            111: "port_11_peak_frequencies",
            112: "port_12_peak_frequencies",
            113: "port_13_peak_frequencies",
            114: "port_14_peak_frequencies",
            115: "port_15_peak_frequencies",
            116: "port_16_peak_frequencies",
            151: "port_1_peak_widths",
            152: "port_2_peak_widths",
            153: "port_3_peak_widths",
            154: "port_4_peak_widths",
            155: "port_5_peak_widths",
            156: "port_6_peak_widths",
            157: "port_7_peak_widths",
            158: "port_8_peak_widths",
            159: "port_9_peak_widths",
            160: "port_10_peak_widths",
            161: "port_11_peak_widths",
            162: "port_12_peak_widths",
            163: "port_13_peak_widths",
            164: "port_14_peak_widths",
            165: "port_15_peak_widths",
            166: "port_16_peak_widths",
            201: "port_1_peak_amplitudes",
            202: "port_2_peak_amplitudes",
            203: "port_3_peak_amplitudes",
            204: "port_4_peak_amplitudes",
            205: "port_5_peak_amplitudes",
            206: "port_6_peak_amplitudes",
            207: "port_7_peak_amplitudes",
            208: "port_8_peak_amplitudes",
            209: "port_9_peak_amplitudes",
            210: "port_10_peak_amplitudes",
            211: "port_11_peak_amplitudes",
            212: "port_12_peak_amplitudes",
            213: "port_13_peak_amplitudes",
            214: "port_14_peak_amplitudes",
            215: "port_15_peak_amplitudes",
            216: "port_16_peak_amplitudes",
            3: "interferometer_linear_fit",
            4: "absolute_reference_linear_fit",
            5: "number_of_data_points",
            6: "first_and_last_crossing",
            7: "frequency_errors",
        },
        'PORT': {
            **{101 + i: f"port_{i + 1}" for i in range(50)}
        },
        'DATA': {
            1: "next_sensor_channel",
            2: "normalized_spectrum",
            11: "spectrum_data"
        },
        'PARA': { # According to documentation. May be incorrect.
            1: "lut_enabled",
            2: "peak_height_reference_lines",
            3: "frequency_delta",
            4: "filter_constant",
            5: "white_light_minimum",
            6: "interferometer_start_amplitude",
            7: "interferometer_minimum_step",
            8: "reference_averages",
            9: "interferometer_dispersion_compensation",
            10: "third_order_interferometer_disperson_compensation",
            11: "peak_interpolation_second_order_fit",
            **{101 + i: f"port_{i + 1}_threshold" for i in range(50)},
        },
    }
}

PORT_TYPE = {
    0: "Inactive",
    1: "Sensor port",
    2: "Gas cell reference port",
    3: "Interferometer port",
    4: "Interferometer port", # difference?
}