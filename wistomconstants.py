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