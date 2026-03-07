encrypted_hex = "3d383c654e3e6a293866"
encrypted_password = bytes.fromhex(encrypted_hex).decode('ascii')
print(f"Encrypted password: {encrypted_password}")
