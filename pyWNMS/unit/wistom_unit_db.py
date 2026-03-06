"""WistomUnitDb — validated collection of Wistom units.

Ports the Java ``WistomUnitDb`` class with name/host+port uniqueness
validation.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from pyWNMS.unit.wistom_unit import WistomUnit

logger = logging.getLogger(__name__)

# Hostnames that map to loopback for uniqueness checks
_LOOPBACK_NAMES = {"localhost", "127.0.0.1"}


class WistomUnitDb:
    """Validated, ordered collection of :class:`WistomUnit` objects.

    Enforces:
    - Non-empty name, hostname, username, password
    - TCP port in range 1024–65535
    - Unique name and unique (hostname, port) pair
    """

    def __init__(self) -> None:
        self._db: List[WistomUnit] = []
        self._listeners: List[Callable] = []

    # ---- Access ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self._db)

    def __iter__(self):
        return iter(self._db)

    def __contains__(self, name: str) -> bool:
        return any(u.name == name for u in self._db)

    def get(self, name: str) -> Optional[WistomUnit]:
        for u in self._db:
            if u.name == name:
                return u
        return None

    def get_all(self) -> List[WistomUnit]:
        return list(self._db)

    # ---- Mutation -------------------------------------------------------

    def add(self, unit: WistomUnit) -> None:
        """Add a unit after validation.

        :raises ValueError: If validation fails.
        """
        self.validate(None, unit)
        self._db.append(unit)
        self._db.sort()

    def remove(self, name: str) -> Optional[WistomUnit]:
        """Remove a unit by name, returning it or *None*."""
        for i, u in enumerate(self._db):
            if u.name == name:
                return self._db.pop(i)
        return None

    def update(self, old_name: str, unit: WistomUnit) -> None:
        """Replace / rename a unit.

        :raises ValueError: If validation fails against the remaining units.
        """
        self.validate(old_name, unit)
        for i, u in enumerate(self._db):
            if u.name == old_name:
                self._db[i] = unit
                self._db.sort()
                return
        raise ValueError(f"Unit '{old_name}' not found")

    # ---- Validation -----------------------------------------------------

    def validate(self, exclude_name: Optional[str],
                 unit: WistomUnit) -> None:
        """Validate a unit against the database rules.

        :param exclude_name: Name of an existing entry to ignore when
            checking uniqueness (used during updates).
        :raises ValueError: If any rule is violated.
        """
        if not unit.name.strip():
            raise ValueError("Unit name must not be empty")
        if not unit.hostname.strip():
            raise ValueError("Hostname must not be empty")
        if not unit.username.strip():
            raise ValueError("Username must not be empty")
        if not unit.password:
            raise ValueError("Password must not be empty")
        if not (1024 <= unit.tcp_port <= 65535):
            raise ValueError(
                f"TCP port must be 1024–65535, got {unit.tcp_port}")

        norm_host = _normalize_host(unit.hostname)
        for existing in self._db:
            if exclude_name and existing.name == exclude_name:
                continue
            if existing.name == unit.name:
                raise ValueError(
                    f"Unit name '{unit.name}' already exists")
            ex_host = _normalize_host(existing.hostname)
            if ex_host == norm_host and existing.tcp_port == unit.tcp_port:
                raise ValueError(
                    f"Host {unit.hostname}:{unit.tcp_port} already in use "
                    f"by unit '{existing.name}'")

    # ---- Serialization --------------------------------------------------

    def to_list(self) -> List[dict]:
        return [u.to_dict() for u in self._db]

    @classmethod
    def from_list(cls, items: List[dict]) -> WistomUnitDb:
        db = cls()
        for d in items:
            db._db.append(WistomUnit.from_dict(d))
        db._db.sort()
        return db


def _normalize_host(host: str) -> str:
    """Normalize loopback addresses for uniqueness comparison."""
    h = host.strip().lower()
    if h in _LOOPBACK_NAMES:
        return "127.0.0.1"
    return h
