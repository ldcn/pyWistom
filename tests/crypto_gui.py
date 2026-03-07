#!/usr/bin/env python3
"""Tkinter GUI for WNMS Classic encrypt/decrypt tool."""

import tkinter as tk
from tkinter import ttk, messagebox


class CryptographyWnmsClassic:

    ALLOWED_LETTERS = 'U6cefhm1nuLTp8rsxCyzAjatBwEiF5GKklIJgMNOPvQRHSWoVqX2YZ03Dd47b9!"£$%^&_*()<>?#-'
    CRYPT_LETTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-#?<>()*&^%$_£"!'

    def encrypt(self, clear_text: str) -> str:
        seed = 123456 % len(self.CRYPT_LETTERS)
        epassword = "="
        epassword += self.CRYPT_LETTERS[seed]
        epassword += self.CRYPT_LETTERS[(len(clear_text) + seed) %
                                        len(self.CRYPT_LETTERS)]

        for ch in clear_text:
            epassword += self.CRYPT_LETTERS[(
                self.ALLOWED_LETTERS.index(ch) + seed) % len(self.CRYPT_LETTERS)]

        if seed > len(self.CRYPT_LETTERS) // 2:
            epassword += self.CRYPT_LETTERS[seed]

        if seed > len(self.CRYPT_LETTERS) // 3:
            epassword += self.CRYPT_LETTERS[len(clear_text)]

        return epassword

    def decrypt(self, encrypted_text: str) -> str:
        if len(encrypted_text) == 0:
            return encrypted_text

        if encrypted_text[0] == '=':
            seed = self.CRYPT_LETTERS.index(encrypted_text[1])
            length = (self.CRYPT_LETTERS.index(
                encrypted_text[2]) + (len(self.CRYPT_LETTERS) - seed)) % len(self.CRYPT_LETTERS)

            password = ""
            for i in range(length):
                password += self.ALLOWED_LETTERS[
                    (self.CRYPT_LETTERS.index(
                        encrypted_text[i + 3]) + (len(self.CRYPT_LETTERS) - seed)) % len(self.ALLOWED_LETTERS)
                ]
            return password

        return encrypted_text


class CryptoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WNMS Password Tool")
        self.root.resizable(False, False)
        self.crypto = CryptographyWnmsClassic()

        self.hex_mode = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # Input
        ttk.Label(self.root, text="Input:").grid(
            row=0, column=0, sticky="w", **pad)
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(
            self.root, textvariable=self.input_var, width=50)
        self.input_entry.grid(
            row=0, column=1, columnspan=2, sticky="ew", **pad)

        # Hex mode checkbox
        ttk.Checkbutton(self.root, text="Hex encoding (encrypted passwords as hex)",
                        variable=self.hex_mode).grid(row=1, column=0, columnspan=3, sticky="w", **pad)

        # Buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(row=2, column=0, columnspan=3, **pad)

        ttk.Button(btn_frame, text="Encrypt",
                   command=self._encrypt).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Decrypt",
                   command=self._decrypt).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Clear", command=self._clear).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="Copy Result",
                   command=self._copy_result).pack(side="left", padx=4)

        # Output
        ttk.Label(self.root, text="Result:").grid(
            row=3, column=0, sticky="w", **pad)
        self.output_var = tk.StringVar()
        self.output_entry = ttk.Entry(self.root, textvariable=self.output_var, width=50,
                                      state="readonly")
        self.output_entry.grid(
            row=3, column=1, columnspan=2, sticky="ew", **pad)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w").grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=(4, 8))

        self.input_entry.focus()
        self.root.bind("<Return>", lambda e: self._encrypt())

    def _encrypt(self):
        text = self.input_var.get()
        if not text:
            self.status_var.set("Error: input is empty")
            return
        try:
            encrypted = self.crypto.encrypt(text)
            if self.hex_mode.get():
                encrypted = encrypted.encode("ascii").hex()
            self.output_var.set(encrypted)
            self.status_var.set("Encrypted successfully")
        except Exception as e:
            self.output_var.set("")
            self.status_var.set(f"Error: {e}")

    def _decrypt(self):
        text = self.input_var.get()
        if not text:
            self.status_var.set("Error: input is empty")
            return
        try:
            if self.hex_mode.get():
                text = bytes.fromhex(text).decode("ascii")
            decrypted = self.crypto.decrypt(text)
            self.output_var.set(decrypted)
            self.status_var.set("Decrypted successfully")
        except ValueError:
            self.output_var.set("")
            self.status_var.set("Error: invalid hex string")
        except Exception as e:
            self.output_var.set("")
            self.status_var.set(f"Error: {e}")

    def _clear(self):
        self.input_var.set("")
        self.output_var.set("")
        self.status_var.set("Ready")

    def _copy_result(self):
        result = self.output_var.get()
        if result:
            self.root.clipboard_clear()
            self.root.clipboard_append(result)
            self.status_var.set("Copied to clipboard")
        else:
            self.status_var.set("Nothing to copy")


def main():
    root = tk.Tk()
    CryptoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
