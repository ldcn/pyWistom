"""MonitorGroupDb — validated collection of monitor groups.

Ports the Java ``MonitorGroupDb`` class.
"""

from __future__ import annotations

from typing import List, Optional

from pyWNMS.monitor.monitor_group import MonitorGroup


class MonitorGroupDb:
    """Validated, ordered collection of :class:`MonitorGroup` objects."""

    def __init__(self) -> None:
        self._db: List[MonitorGroup] = []

    def __len__(self) -> int:
        return len(self._db)

    def __iter__(self):
        return iter(self._db)

    def __contains__(self, name: str) -> bool:
        return any(g.name == name for g in self._db)

    def get(self, name: str) -> Optional[MonitorGroup]:
        for g in self._db:
            if g.name == name:
                return g
        return None

    def find(self, name: str, exact_match: bool = True
             ) -> Optional[MonitorGroup]:
        if exact_match:
            return self.get(name)
        name_lower = name.lower()
        for g in self._db:
            if g.name.lower().startswith(name_lower):
                return g
        return None

    def get_all(self) -> List[MonitorGroup]:
        return list(self._db)

    # ---- Mutation -------------------------------------------------------

    def add(self, group: MonitorGroup) -> None:
        self.validate(None, group)
        self._db.append(group)
        self._db.sort(key=lambda g: g.name.lower())

    def remove(self, name: str) -> Optional[MonitorGroup]:
        for i, g in enumerate(self._db):
            if g.name == name:
                removed = self._db.pop(i)
                removed.release_resources()
                return removed
        return None

    def update(self, old_name: str, group: MonitorGroup) -> None:
        self.validate(old_name, group)
        for i, g in enumerate(self._db):
            if g.name == old_name:
                self._db[i] = group
                self._db.sort(key=lambda g: g.name.lower())
                return
        raise ValueError(f"Group '{old_name}' not found")

    # ---- Validation -----------------------------------------------------

    def validate(self, exclude_name: Optional[str],
                 group: MonitorGroup) -> None:
        if not group.name.strip():
            raise ValueError("Group name must not be empty")
        if not group.log_dir.strip():
            raise ValueError("Log directory must not be empty")

        for ex in self._db:
            if exclude_name and ex.name == exclude_name:
                continue
            if ex.name == group.name:
                raise ValueError(
                    f"Group name '{group.name}' already exists")
            if ex.log_dir == group.log_dir:
                raise ValueError(
                    f"Log directory '{group.log_dir}' already in use "
                    f"by group '{ex.name}'")

    # ---- Serialization --------------------------------------------------

    def to_list(self) -> List[dict]:
        return [g.to_dict() for g in self._db]

    @classmethod
    def from_list(cls, items: List[dict]) -> MonitorGroupDb:
        db = cls()
        for d in items:
            db._db.append(MonitorGroup.from_dict(d))
        db._db.sort(key=lambda g: g.name.lower())
        return db
