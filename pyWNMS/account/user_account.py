"""User account model — authentication and role-based access.

Ports the Java ``UserAccount``, ``Administrator``, ``Operator``,
``DefaultAdministrator``, and ``UserAccountModel`` classes.

Passwords are stored encrypted on disk using the configured
:class:`Cryptography` backend.
"""

from __future__ import annotations

import logging
import os
from enum import Enum, auto
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class AccountType(Enum):
    """User role."""
    ADMINISTRATOR = "Administrator"
    OPERATOR = "Operator"


class UserAccount:
    """A user account with encrypted password.

    :param account_type: Role of the user.
    :param username: Login name.
    :param password: Plaintext password (will be encrypted for storage).
    :param removable: Whether the account can be deleted.
    """

    def __init__(
        self,
        account_type: AccountType,
        username: str,
        password: str = "",
        removable: bool = True,
    ) -> None:
        self.account_type = account_type
        self.username = username
        self._password_encrypted: str = ""
        self.removable = removable
        if password:
            self.set_password_encrypt(password)

    def set_password_encrypt(self, plaintext: str) -> None:
        """Encrypt and store a password."""
        from pyWNMS.util.crypto import CryptographyWnmsClassic
        crypto = CryptographyWnmsClassic()
        self._password_encrypted = crypto.encrypt(plaintext)

    def get_password_decrypt(self) -> str:
        """Decrypt and return the stored password."""
        from pyWNMS.util.crypto import CryptographyWnmsClassic
        crypto = CryptographyWnmsClassic()
        return crypto.decrypt(self._password_encrypted)

    @property
    def password_encrypted(self) -> str:
        """Raw encrypted password string (for serialization)."""
        return self._password_encrypted

    @password_encrypted.setter
    def password_encrypted(self, value: str) -> None:
        self._password_encrypted = value

    def validate_password(self, plaintext: str) -> bool:
        """Check if a plaintext password matches the stored one."""
        from pyWNMS.util.crypto import CryptographyWnmsClassic
        crypto = CryptographyWnmsClassic()
        return crypto.encrypt(plaintext) == self._password_encrypted

    def __repr__(self) -> str:
        return (f"<{type(self).__name__} '{self.username}' "
                f"type={self.account_type.value}>")


class Administrator(UserAccount):
    """Administrator account (removable)."""

    def __init__(self, username: str, password: str = "") -> None:
        super().__init__(AccountType.ADMINISTRATOR, username, password)


class DefaultAdministrator(UserAccount):
    """Built-in default admin account (non-removable).

    Username ``admin``, default password ``admin``.
    """

    USERNAME = "admin"
    DEFAULT_PASSWORD = "admin"

    def __init__(self) -> None:
        super().__init__(
            AccountType.ADMINISTRATOR,
            self.USERNAME,
            self.DEFAULT_PASSWORD,
            removable=False,
        )


class Operator(UserAccount):
    """Operator account (removable, lower privilege)."""

    def __init__(self, username: str, password: str = "") -> None:
        super().__init__(AccountType.OPERATOR, username, password)


class UserAccountModel:
    """Manages the set of user accounts.

    Accounts are persisted as a hex-encoded file.  The first entry is
    always the default admin password (possibly changed from the
    default).

    :param accounts_filepath: Full path to the accounts file on disk.
    """

    def __init__(self, accounts_filepath: str = "") -> None:
        self._db: List[UserAccount] = [DefaultAdministrator()]
        self._logged_in_user: Optional[UserAccount] = None
        self._filepath = accounts_filepath

        # Login/logout event callbacks
        self._login_listeners: List[Callable[[
            Optional[UserAccount]], None]] = []

    # ---- Query ----------------------------------------------------------

    @property
    def logged_in_user(self) -> Optional[UserAccount]:
        return self._logged_in_user

    def get_accounts(self) -> List[UserAccount]:
        return list(self._db)

    def exists(self, username: str) -> bool:
        return any(a.username == username for a in self._db)

    # ---- Login / logout -------------------------------------------------

    def login(self, username: str, password: str) -> bool:
        """Authenticate a user.

        :returns: *True* if login succeeded.
        """
        for acc in self._db:
            if acc.username == username:
                if acc.validate_password(password):
                    self._logged_in_user = acc
                    self._fire_login(acc)
                    return True
                return False
        return False

    def logout(self) -> None:
        self._logged_in_user = None
        self._fire_login(None)

    # ---- Mutation (admin-only) ------------------------------------------

    def add(self, account: UserAccount) -> None:
        """Add a new account (requires an admin to be logged in).

        :raises PermissionError: If no admin is logged in.
        :raises ValueError: If username already exists or is empty.
        """
        self._require_admin()
        if not account.username.strip():
            raise ValueError("Username must not be empty")
        if self.exists(account.username):
            raise ValueError(
                f"Account '{account.username}' already exists")
        self._db.append(account)

    def remove(self, account: UserAccount) -> None:
        """Remove an account (admin-only, non-removable accounts blocked).

        :raises PermissionError: If no admin is logged in.
        :raises ValueError: If account is non-removable.
        """
        self._require_admin()
        if not account.removable:
            raise ValueError(
                f"Account '{account.username}' cannot be removed")
        self._db = [a for a in self._db if a.username != account.username]

    def reset(self) -> None:
        """Reset to default (delete accounts file, recreate default admin)."""
        if self._filepath and os.path.isfile(self._filepath):
            os.remove(self._filepath)
        self._db = [DefaultAdministrator()]
        self._logged_in_user = None

    # ---- Persistence (hex-encoded file) ---------------------------------

    def save(self) -> None:
        """Save all accounts to the configured file."""
        if not self._filepath:
            return
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        lines: List[str] = []
        for acc in self._db:
            # Line 1: hex(encrypted "type|username")
            type_user = f"{acc.account_type.value}|{acc.username}"
            lines.append(_bytes_to_hex(type_user.encode("utf-8")))
            # Line 2: hex(encrypted password)
            lines.append(_bytes_to_hex(
                acc.password_encrypted.encode("utf-8")))
        with open(self._filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def load(self) -> None:
        """Load accounts from the configured file."""
        if not self._filepath or not os.path.isfile(self._filepath):
            return
        with open(self._filepath, "r", encoding="utf-8") as f:
            raw_lines = [ln.strip() for ln in f if ln.strip()]

        if len(raw_lines) < 2:
            return

        accounts: List[UserAccount] = []
        i = 0
        while i + 1 < len(raw_lines):
            type_user_str = _hex_to_bytes(raw_lines[i]).decode("utf-8")
            password_enc = _hex_to_bytes(raw_lines[i + 1]).decode("utf-8")
            i += 2

            parts = type_user_str.split("|", 1)
            if len(parts) != 2:
                continue
            type_str, username = parts
            if type_str == AccountType.ADMINISTRATOR.value:
                if username == DefaultAdministrator.USERNAME:
                    acc = DefaultAdministrator()
                else:
                    acc = Administrator(username)
            else:
                acc = Operator(username)
            acc.password_encrypted = password_enc
            accounts.append(acc)

        if accounts:
            self._db = accounts

    # ---- Listener management --------------------------------------------

    def add_login_listener(
            self, callback: Callable[[Optional[UserAccount]], None]) -> None:
        if callback not in self._login_listeners:
            self._login_listeners.append(callback)

    def _fire_login(self, user: Optional[UserAccount]) -> None:
        for cb in list(self._login_listeners):
            try:
                cb(user)
            except Exception:
                logger.exception("Login listener error")

    # ---- Internal helpers -----------------------------------------------

    def _require_admin(self) -> None:
        if (self._logged_in_user is None
                or self._logged_in_user.account_type
                != AccountType.ADMINISTRATOR):
            raise PermissionError("Administrator login required")


# ---- Hex encoding helpers -----------------------------------------------

def _bytes_to_hex(data: bytes) -> str:
    return data.hex()


def _hex_to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str)
