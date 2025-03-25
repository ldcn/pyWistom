import socket
import struct

# Development Wistom IP and Port
# This is a WistSense system with serial number A23-00618
# It is located in the server room at the Proximion AB office in Kista
# To power cycle the unit, there is a web server running on 10.44.42.100
HOST = "10.44.40.218" 
PORT = 7734  

# Command identifiers ()

API_CID_LOGIN = b'\x00\x01'

API_CID_LOGINRES = b'\x01\x01'
API_CID_LOGOUT = b'\x00\x02'
API_CID_APISET = b'\x00\x03'
API_CID_APISETACK = b'\x01\x03'
API_CID_APISETNACK = b'\x02\x03'
API_CID_APIGET = b'\x00\x04'
API_CID_APIGETRES = b'\x01\x04'
API_CID_APIGETERR = b'\x02\x04'

# Alarm command identifiers (Chapter 11 Tables 11-15 in User Manual)

API_CID_ALARM_0 = b'\x01\x05' # Alarm type 0 (no time stamp)
API_CID_ALARM_1 = b'\x11\x05' # Alarm type 1 (SNMP style)
API_CID_ALARM_2 = b'\x21\x05' # Alarm type 2 (Unix style)
API_CID_ALARM_3 = b'\x31\x05' # Alarm type 3 (uptime in millisecond ticks)
API_CID_ALARM_4 = b'\x41\x05' # Alarm type 4 (Unix style in milliseconds)

# Alarm types (table 11-16)


# Login result codes (described in page 82 Table 11-18 of the API documentation)
API_LOGINRES_UL1 = b'\x00\x00\x00\x01' # Logged in with user level 1
API_LOGINRES_UL2 = b'\x00\x00\x00\x02' # Logged in with user level 2
API_LOGINRES_UL3 = b'\x00\x00\x00\x03' # Logged in with user level 3
API_LOGINRES_UL4 = b'\x00\x00\x00\x04' # Logged in with user level 4
API_LOGINRES_UL5 = b'\x00\x00\x00\x05' # Logged in with user level 5
API_LOGINRES_MAX_USERS_LOGGED_IN = b'\x10\x00\x00\x00'
API_LOGINRES_MAX_USERS_SYSTEM = b'\x10\x00\x00\x01'
API_LOGINRES_MAX_LOGIN_ATTEMPTS = b'\x10\x00\x00\x02'
API_LOGINRES_DENIED = b'\x10\x00\x00\x03'
API_LOGINRES_DENIED_FROM_INTERFACE = b'\x10\x00\x00\x04'
API_LOGINRES_WRONG_PASSWORD = b'\x10\x00\x00\x07'
API_LOGINRES_USER_NOT_FOUND = b'\x10\x00\x00\x08'

# test datastream (wistom login with wroot)

# hex_data = "0001004c4c47494e415049320000000c77726f6f740077726f6f7400" # login_cid, token, app_id, op_id, data_length, user_id, password
# binary_data = bytes.fromhex(hex_data)

def make_api_request(cid, token, app_id, op_id, data):
    data_length = len(data)
    return (cid 
            + token.to_bytes(2, 'big') 
            + app_id.encode('ascii') 
            + op_id.encode('ascii') 
            + data_length.to_bytes(4, 'big') 
            + data)

def get_login_info():
    user_id = input("Enter User ID: ")
    password = input("Enter Password: ")
    return (user_id, 
            password)

def login_payload(token, user_id, password):
    token += 1
    user_id_bytes = user_id.encode('ascii')
    password_bytes = password.encode('ascii')
    payload_length = len(user_id_bytes) + len(password_bytes) + 2
    payload = user_id_bytes + b'\x00' + password_bytes + b'\x00'
    return (API_CID_LOGIN 
            + token.to_bytes(2, 'big') 
            + 'LGIN'.encode('ascii') 
            + 'API2'.encode('ascii') 
            + payload_length.to_bytes(4, 'big') 
            + payload)

def debug_print(interpreted_data):
    print("Received Data:")
    for key, value in interpreted_data.items():
        print(f"{key}: {value}")

def dissect_data(data):
    command_id = data[0:2].hex()
    token = int.from_bytes(data[2:4], 'big')
    app_id = data[4:8].decode('ascii')
    op_id = data[8:12].decode('ascii')
    payload_length = int.from_bytes(data[12:16], 'big')
    payload = data[16:16+payload_length]
    
    return {
        "command_id": command_id,
        "token": token,
        "App": app_id,
        "Op": op_id,
        "payload_length": payload_length,
        "payload": payload
    }

def handle_login_response(interpreted_data):
    response_messages = {
        API_LOGINRES_UL1: "Login with user level 1",
        API_LOGINRES_UL2: "Login with user level 2",
        API_LOGINRES_UL3: "Login with user level 3",
        API_LOGINRES_UL4: "Login with user level 4",
        API_LOGINRES_UL5: "Login with user level 5",
        API_LOGINRES_MAX_USERS_LOGGED_IN: "Maximum users logged in",
        API_LOGINRES_MAX_USERS_SYSTEM: "Maximum users in system",
        API_LOGINRES_MAX_LOGIN_ATTEMPTS: "Maximum login attempts reached",
        API_LOGINRES_DENIED: "Login denied",
        API_LOGINRES_DENIED_FROM_INTERFACE: "Login denied from interface",
        API_LOGINRES_WRONG_PASSWORD: "Wrong password",
        API_LOGINRES_USER_NOT_FOUND: "User not found"
    }
    
    message = response_messages.get(interpreted_data["payload"], "Unknown response")
    print(message)
    # print(f"code: {interpreted_data['payload']}")

token = 0

login_payload = login_payload(token, *get_login_info())

print(f"Login Payload: {login_payload.hex()}")

def get_OPM_enable(token):
    cid = API_CID_APIGET
    token += 1
    app_id = 'OPM#'
    op_id = 'ENAB'
    data = b''
    return cid, token, app_id, op_id, data

def get_SMGR_info(token):
    cid = API_CID_APIGET
    token += 1
    app_id = 'SMGR'
    op_id = 'INFO'
    data = b''
    return cid, token, app_id, op_id, data

def get_SMGR_network_info(token):
    cid = API_CID_APIGET
    token += 1
    app_id = 'SMGR'
    op_id = 'IP##'
    data = b''
    return cid, token, app_id, op_id, data

def dissect_SMGR_info(data):
    strings = data.split(b'\x00') # splitting strings by null character
    #skipping tag bytes
    hw_product_number = strings[0][1:].decode('ascii') 
    hw_id_number = strings[1][1:].decode('ascii')  
    hw_revision = strings[2][1:].decode('ascii')  
    hw_serial_number = strings[3][1:].decode('ascii')  
    sensor_product_number = strings[4][1:].decode('ascii')  
    sensor_id_number = strings[5][1:].decode('ascii')
    sensor_revision = strings[6][1:].decode('ascii')
    sensor_serial_number = strings[7][1:].decode('ascii')
    software_product_number = strings[8][1:].decode('ascii')
    software_revision = strings[9][1:].decode('ascii')
    firmware_revision = strings[10][1:].decode('ascii')
    pld_revision = strings[11][1:].decode('ascii')
    bootstrap_revision = strings[12][1:].decode('ascii')
    switch_software_revision = strings[13][1:].decode('ascii')
    unit_serial = strings[14][1:].decode('ascii')
    production_date = strings[15][1:].decode('ascii')

    start_index = sum(len(s) + 1 for s in strings[:16])  # +1 for each null character

    start_calib_freq = struct.unpack('>d', data[start_index + 1:start_index + 9])[0] # FLOAT64
    end_calib_freq = struct.unpack('>d', data[start_index + 10:start_index + 18])[0] # FLOAT64
    start_temp_calib = struct.unpack('>f', data[start_index + 19:start_index + 23])[0] # FLOAT32
    end_temp_calib = struct.unpack('>f', data[start_index + 24:start_index + 28])[0] # FLOAT32

    return {
        "HW Product Number": hw_product_number,
        "HW ID Number": hw_id_number,
        "HW Revision": hw_revision,
        "HW Serial Number": hw_serial_number,
        "Sensor Product Number": sensor_product_number,
        "Sensor ID Number": sensor_id_number,
        "Sensor Revision": sensor_revision,
        "Sensor Serial Number": sensor_serial_number,
        "Software Product Number": software_product_number,
        "Software Revision": software_revision,
        "Firmware Revision": firmware_revision,
        "PLD Revision": pld_revision,
        "Bootstrap Revision": bootstrap_revision,
        "Switch Software Revision": switch_software_revision,
        "Unit Serial": unit_serial,
        "Production Date": production_date,
        "Start Calibration Frequency (Hz)": start_calib_freq,
        "End Calibration Frequency (Hz) ": end_calib_freq,
        "Start Temperature Calibration (deg C)": start_temp_calib,
        "End Temperature Calibration (deg C)": end_temp_calib
    }

def dissect_SMGR_network_info(data):
    # first 5 parts are strings with null character terminators
    # last part (tcp_port) is a UINT16
    # each part starts with a tag byte that is skipped
    parts = data.split(b'\x00')
    ip_address = parts[0][1:].decode('ascii') 
    subnet_mask = parts[1][1:].decode('ascii')  
    gateway_ip = parts[2][1:].decode('ascii')  
    hostname = parts[3][1:].decode('ascii')  
    mac_address = parts[4][1:].decode('ascii')  
    tcp_port = int.from_bytes(parts[5][1:3], 'big')
    
    return {
        "IP Address": ip_address,
        "Subnet Mask": subnet_mask,
        "Gateway IP": gateway_ip,
        "Hostname": hostname,
        "MAC Address": mac_address,
        "TCP Port": tcp_port
    }

# Add more API call functions here
# different responses need to be handled manually
# e.g. generate plot with matplotlib for sensor data
# and get user input for API set calls


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    s.sendall(login_payload)
    login_response = s.recv(1024)

    login_response_interpreted = dissect_data(login_response)
    handle_login_response(login_response_interpreted)

    while True:
        # do api calls here while connected
        # leaving this loop breaks connection with wistom

        api_request = get_OPM_enable(token)
        api_call_payload = make_api_request(*api_request)

        print(f"API Call Payload: {api_call_payload}")

        s.sendall(api_call_payload)
        response = s.recv(1024) # NOTE: some responses are larger than 1024 bytes
        print(f"Response: {response}") # response is not formatted, output is raw bytes

        api_request = get_SMGR_info(token)
        api_call_payload = make_api_request(*api_request)

        print(f"API Call Payload: {api_call_payload}")
        s.sendall(api_call_payload)
        response = s.recv(1024)
        response_dissected = dissect_data(response)
        # print(f"Response: {response}")
        hw_info = dissect_SMGR_info(response_dissected['payload'])
        debug_print(hw_info) # formatted response

        api_request = get_SMGR_network_info(token)
        api_call_payload = make_api_request(*api_request)

        print(f"API Call Payload: {api_call_payload}")
        s.sendall(api_call_payload)
        response = s.recv(1024)
        response_dissected = dissect_data(response)
        # print(f"Response: {response_dissected}")
        network_info = dissect_SMGR_network_info(response_dissected['payload'])
        debug_print(network_info) # formatted response

        do_it_again = input("do it again? ")
        if do_it_again.lower() != 'yes':
            break
