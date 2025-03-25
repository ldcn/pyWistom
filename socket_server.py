import socket

server_address = ('10.44.42-10', 12345)
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(server_address)
server_socket.listen(1)

print(f"Waiting for connections on {server_address}")
client_socket, client_address = server_socket.accept()

print(f"Connecting from {client_address}")
message = "Hello, clients! Connection established."

client_socket.sendall(message.encode())
client_socket.close()
server_socket.close()