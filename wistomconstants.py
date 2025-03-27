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
    "LGIN": {
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
    },

    "SMGR": { # System Manager operations
        "REST": "", # SET only
        "IP##": "_parse_smgr_ip_response",
        "FLSH": "", # SET only
        "SER#": "_parse_smgr_serial_response",
        "TIME": "_parse_smgr_time_response",
        "INFO": "_parse_smgr_info_response",
        "TEMP": "_parse_smgr_temp_response",
        "DUMP": "_parse_smgr_dump_response",
        "CLRD": "", # SET only
        "UPTI": "_parse_smgr_uptime_response",
        "INST": "_parse_smgr_inst_response",
        "SCFG": "_parse_smgr_scfg_response",
        "SATR": "", # SET only
        "SDTR": "", # SET only
        "SLTR": "_parse_smgr_sltr_response",
        "LED#": "_parse_smgr_led_response", # Not implemented
    },

    "SPEC": {
        # Spectrum parameter operations here
    },
}