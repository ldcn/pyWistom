#!/usr/bin/env python3
"""Command-line tool to encrypt/decrypt strings using CryptographyWnmsClassic."""

import argparse
import sys

from CryptographyWnmsClassic import CryptographyWnmsClassic


def main():
    parser = argparse.ArgumentParser(
        description="Encrypt or decrypt strings using WNMS Classic cryptography.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-e", "--encrypt", metavar="TEXT",
                       help="Encrypt the given text")
    group.add_argument("-d", "--decrypt", metavar="TEXT",
                       help="Decrypt the given text")

    args = parser.parse_args()
    crypto = CryptographyWnmsClassic()

    if args.encrypt is not None:
        encrypted = crypto.encrypt(args.encrypt)
        print(encrypted.encode('ascii').hex())
    else:
        decrypted_hex = bytes.fromhex(args.decrypt).decode('ascii')
        print(crypto.decrypt(decrypted_hex))


if __name__ == "__main__":
    main()
