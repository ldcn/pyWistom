from wistomconstants import COMMAND_ID

# Parsers for response headers
# Header structure is dependent on the command id

RESPONSE_HEADER_PARSER = {
    COMMAND_ID["LOGINRES"]: "_parse_loginres_header",
    COMMAND_ID["SETACK"]: "_parse_setack_header",
    COMMAND_ID["SETNACK"]: "_parse_setnack_header",
    COMMAND_ID["GETERR"]: "_parse_geterr_header",
    COMMAND_ID["GETRES"]: "_parse_getres_header",
}


# Response parsers for GET requests
##
# Commands that have no GET response (SET only)
# are included for error handling
# See API documentation or page 83-112 in the Wistom User Guide

RESPONSE_PARSER = {
    "LGIN": {  # Login / User management operations
        # The "LGIN" app-id is used both for logging
        # into a wistom unit and when logged in
        #
        # When logging in, the op-id "API2" will use API v2 responses,
        # while any other 4-letter combination will use API v1.
        # However "LGIN" is the op-id used in all proximion software.
        #
        # After login, the app-id "LGIN" will work with the other op-ids
        # that are shown below.
        "LGIN": "_parse_apiv1_login_response",
        "API2": "_parse_apiv2_login_response",
        "CPWD": "",  # SET only
        "COPW": "",  # SET only
        "UADD": "",  # SET only
        "UDEL": "",  # SET only
        "UINF": "_parse_login_user_info_response",
        "SINF": "_parse_login_session_info_response",
    },
    "ALMH": {
        "SUBS": "",  # SET only — SETACK/SETNACK
        "UNSU": "",  # SET only — SETACK/SETNACK
        "ALRM": "_parse_almh_alrm_response",
    },
    "OPM#": {
        # OPM operations here
        "AVRG": "_parse_opm_averages_response",
        "ENAB": "_parse_opm_enable_response",
        "CALC": "_parse_opm_power_calc_response",
        "CNFG": "_parse_opm_config_response",  # incorrect description
        "OSNR": "_parse_opm_osnr_config_response",
        "CHCO": "_parse_opm_channel_config_response",
        "FRQO": "_parse_opm_frequency_option_response",
        "OUTP": "_parse_opm_output_spectrum_response",
        "RAWD": "_parse_opm_raw_data_response",
        "TSPC": "_parse_opm_time_spectrum_response",
        "FSPC": "_parse_opm_frequency_spectrum_response",
        "WSPC": "_parse_opm_wavelength_spectrum_response",
        "CSPC": "_parse_opm_compact_spectrum_response",
        "CHNL": "_parse_opm_channel_status_response",
        "CHAL": "_parse_opm_all_channels_status_response",
        "TRSH": "_parse_opm_threshold_response",
        "MINL": "_parse_opm_min_level_response",
        "PCRI": "_parse_opm_peak_criteria_response",
        "TPWR": "_parse_opm_total_power_response",
        "FILW": "_parse_opm_filter_width_response",
        "SWHA": "_parse_opm_switch_handling_response",
    },

    "PULF": {  # Pulse frequency control
        "COMP": "_parse_compensation_toggle",
        "PULS": "_parse_pulse_resonance_spectrum",
        "REGZ": "_parse_frequency_z_regulator",
        "REGV": "_parse_frequency_regulator_values",
        "REGC": "_parse_frequency_regulator_control",
        "RESC": "_parse_pulse_resonance_configuration",
        "RTEC": "_parse_repeat_time_event_control",
        "REGP": "_parse_frequency_pid_regulator",
    },

    "SMGR": {  # System Manager operations
        "REST": "",  # SET only
        "IP##": "_parse_network_info_response",
        "FLSH": "",  # SET only
        "SER#": "_parse_serial_response",
        "TIME": "_parse_datetime_response",
        "INFO": "_parse_product_info_response",
        "TEMP": "_parse_system_temperature_response",
        "DUMP": "_parse_smgr_dump_response",
        "CLRD": "",  # SET only
        "UPTI": "_parse_system_uptime_response",
        "INST": "_parse_smgr_inst_response",
        "SCFG": "_parse_snmp_config_response",
        "SATR": "",  # SET only
        "SDTR": "",  # SET only
        "SLTR": "_parse_list_snmp_trap_receivers_response",
        "LED#": "_parse_smgr_led_response",  # Not implemented
    },

    "SPEC": {
        "SWIN": "_parse_spec_swin_response",
        "SWMO": "_parse_spec_swmo_response",
        "SWCO": "_parse_spec_swco_response",
        "CTBL": "_parse_spec_ctbl_response",
        "CHNL": "_parse_spec_chnl_response",
        "DELC": "",  # SET only
    },

    "OCM#": {
        "ENAB": "_parse_ocm_enable_response",
    },

    "WICA": {  # Wistom Calibration operations
        "FRQC": "_parse_wica_frqc_response",
    },

    "WSNS": {  # Wistsense operations
        "ENAB": "_parse_wistsense_enable",
        "PORT": "_parse_wsns_port",
        "DATA": "_parse_wsns_data",
        "NEXT": "_parse_wsns_next",
        "PARA": "_parse_wsns_para",
        "FILT": "_parse_wsns_filt",
        "RAWB": "_parse_wsns_rawb",
    }
}
