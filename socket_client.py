import socket

server_address = ('localhost', 12345)
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect(server_address)
data = client_socket.recv(1024)
print(f"Received from server: {data.decode()}")
client_socket.close()