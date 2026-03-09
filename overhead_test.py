import time
from pyWistom import WistomClient
from pyWistom import COMMAND_ID
from wistomconfig import HOST, PORT, USER_ID, PASSWORD

iterations = 100

# Test without SSH
with WistomClient(HOST, PORT, USER_ID, PASSWORD, use_ssh=False) as client:
    client.custom_api_request(
        COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')  # Warmup
    start = time.time()
    for _ in range(iterations):
        client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')
    no_ssh_time = time.time() - start

# Test with SSH
with WistomClient(HOST, PORT, USER_ID, PASSWORD, use_ssh=True) as client:
    client.custom_api_request(
        COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')  # Warmup
    start = time.time()
    for _ in range(iterations):
        client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')
    ssh_time = time.time() - start

print(
    f"Without SSH: {no_ssh_time:.3f}s "
    f"({no_ssh_time/iterations*1000:.1f}ms per request)")
print(
    f"With SSH: {ssh_time:.3f}s "
    f"({ssh_time/iterations*1000:.1f}ms per request)")
print(f"Overhead: {((ssh_time/no_ssh_time - 1) * 100):.1f}%")

print("\n--- Test without context manager ---")

# Test without SSH - manual connect/disconnect
client_no_ssh = WistomClient(HOST, PORT, USER_ID, PASSWORD, use_ssh=False)
client_no_ssh.connection.connect()
client_no_ssh.login()
client_no_ssh.custom_api_request(
    COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')  # Warmup
start = time.time()
for _ in range(iterations):
    client_no_ssh.custom_api_request(
        COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')
no_ssh_time_manual = time.time() - start
client_no_ssh.connection.disconnect()

# Test with SSH - manual connect/disconnect
client_ssh = WistomClient(HOST, PORT, USER_ID, PASSWORD, use_ssh=True)
client_ssh.connection.connect()
client_ssh.login()
client_ssh.custom_api_request(
    COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')  # Warmup
start = time.time()
for _ in range(iterations):
    client_ssh.custom_api_request(
        COMMAND_ID['GET'], b'WSNS', b'DATA', b'\x0a\x01')
ssh_time_manual = time.time() - start
client_ssh.connection.disconnect()

print(
    f"Without SSH (manual): {no_ssh_time_manual:.3f}s "
    f"({no_ssh_time_manual/iterations*1000:.1f}ms per request)")
print(
    f"With SSH (manual): {ssh_time_manual:.3f}s "
    f"({ssh_time_manual/iterations*1000:.1f}ms per request)")
print(
    f"Overhead (manual): "
    f"{((ssh_time_manual/no_ssh_time_manual - 1) * 100):.1f}%")
