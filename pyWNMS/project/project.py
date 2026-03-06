"""Project management — create, open, save, load projects.

Projects are saved as YAML files (clean break from the Java XML format).
Directory structure::

    <project_path>/
        .project/
            project.yaml
        log/
            <group_log_dir>/
                <unit_log_dir>/
                    events/
                    opmchanneldata/
                    spectrum/
                    totalpower/
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import yaml

from pyWNMS.monitor.monitor_group import MonitorGroup
from pyWNMS.monitor.monitor_group_db import MonitorGroupDb
from pyWNMS.monitor.monitor_unit import MonitorUnit
from pyWNMS.unit.wistom_unit import WistomUnit
from pyWNMS.unit.wistom_unit_db import WistomUnitDb

logger = logging.getLogger(__name__)

_PROJ_DIR = ".project"
_PROJ_FILE = "project.yaml"
_LOG_DIR = "log"


class Project:
    """WNMS project — container for units and monitor groups.

    :param name: Human-readable project name.
    :param path: Root directory for this project on disk.
    """

    def __init__(self, name: str = "", path: str = "") -> None:
        self.name = name
        self._path = ""
        self._proj_path = ""
        self._log_path = ""
        if path:
            self.set_path(path)

        self.unit_db = WistomUnitDb()
        self.group_db = MonitorGroupDb()

    # ---- Path management ------------------------------------------------

    @property
    def path(self) -> str:
        return self._path

    @property
    def proj_path(self) -> str:
        return self._proj_path

    @property
    def log_path(self) -> str:
        return self._log_path

    def set_path(self, path: str) -> None:
        self._path = os.path.abspath(path)
        self._proj_path = os.path.join(self._path, _PROJ_DIR)
        self._log_path = os.path.join(self._path, _LOG_DIR)

    # ---- Directory creation ---------------------------------------------

    def create_directories(self) -> None:
        """Create the project, log, and metadata directories."""
        os.makedirs(self._path, exist_ok=True)
        os.makedirs(self._proj_path, exist_ok=True)
        os.makedirs(self._log_path, exist_ok=True)

    # ---- Save / Load (YAML) ---------------------------------------------

    def save(self) -> None:
        """Write the project to ``<proj_path>/project.yaml``."""
        self.create_directories()
        data = {
            "name": self.name,
            "units": self.unit_db.to_list(),
            "groups": self.group_db.to_list(),
        }
        filepath = os.path.join(self._proj_path, _PROJ_FILE)
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logger.info("Project saved to %s", filepath)

    @classmethod
    def load(cls, path: str) -> Project:
        """Load a project from the given root directory.

        :param path: Root directory containing ``.project/project.yaml``.
        :returns: Loaded :class:`Project` instance.
        :raises FileNotFoundError: If project file does not exist.
        """
        proj_dir = os.path.join(os.path.abspath(path), _PROJ_DIR)
        filepath = os.path.join(proj_dir, _PROJ_FILE)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Project file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        proj = cls(name=data.get("name", ""), path=path)
        proj.unit_db = WistomUnitDb.from_list(data.get("units", []))
        proj.group_db = MonitorGroupDb.from_list(data.get("groups", []))

        # Re-link MonitorUnits to WistomUnits and set project log path
        for group in proj.group_db:
            group.set_project_log_path(proj.log_path)
            for child in group.children:
                if isinstance(child, MonitorUnit):
                    unit_name = child.to_dict().get("unit_name", "")
                    unit = proj.unit_db.get(unit_name)
                    if unit:
                        child.unit = unit
                        child.set_parent_group(group)

        logger.info("Project loaded from %s", filepath)
        return proj

    @staticmethod
    def file_exists(path: str) -> bool:
        """Check whether a project file exists at the given path."""
        filepath = os.path.join(
            os.path.abspath(path), _PROJ_DIR, _PROJ_FILE)
        return os.path.isfile(filepath)

    # ---- Display --------------------------------------------------------

    def __repr__(self) -> str:
        return (f"<Project '{self.name}' path='{self._path}' "
                f"units={len(self.unit_db)} groups={len(self.group_db)}>")
