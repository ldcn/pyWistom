"""Application settings — singleton configuration store.

Ports the Java ``Settings`` class.  Settings are persisted as YAML
(clean break from Java XML).
"""

from __future__ import annotations

import logging
import os
from enum import Enum, auto
from pathlib import Path
from typing import Optional

import yaml

from pyWNMS.project.project import Project
from pyWNMS.util.email_client import EmailClient

logger = logging.getLogger(__name__)

# ---- Defaults -----------------------------------------------------------

_SETTINGS_DIR = str(Path(__file__).resolve().parent.parent.parent)
_SETTINGS_FILE = "settings.yaml"
_ACCOUNTS_FILE = "accounts"

DEFAULT_SESSION_TIMEOUT = 20.0          # seconds
DEFAULT_CONNECT_TIMEOUT = 5.0           # seconds
DEFAULT_VALIDATE_CONNECTION_TIMER = 60.0  # seconds
DEFAULT_TRIG_EMAIL_HOLDOFF = 5.0        # seconds
DEFAULT_TRIG_SPECTRUM_HOLDOFF = 5.0     # seconds
DEFAULT_TRIG_TPWR_HOLDOFF = 5.0        # seconds
DEFAULT_LOGGER_SIZE = 100

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT_DETAILED = "%Y-%m-%d %H:%M:%S.%f"
NUMBER_FORMAT = "##0.#####E0"


class SettingsState(Enum):
    """Application lifecycle state."""
    PASSIVE = auto()
    IDLE = auto()
    CLOSING_RESOURCES = auto()
    PROJECT_CLOSED = auto()
    PROJECT_NEW = auto()
    PROJECT_OPEN = auto()


class Settings:
    """Singleton-like application settings.

    Manages timers, paths, the current project, and provides helper
    methods for project open/close lifecycle.
    """

    _instance: Optional[Settings] = None

    def __init__(self) -> None:
        self.state = SettingsState.PASSIVE
        self.evaluation_mode = False

        # Timer configuration
        self.session_timeout = DEFAULT_SESSION_TIMEOUT
        self.connect_timeout = DEFAULT_CONNECT_TIMEOUT
        self.validate_connection_timer = DEFAULT_VALIDATE_CONNECTION_TIMER
        self.trig_email_holdoff = DEFAULT_TRIG_EMAIL_HOLDOFF
        self.trig_spectrum_holdoff = DEFAULT_TRIG_SPECTRUM_HOLDOFF
        self.trig_tpwr_holdoff = DEFAULT_TRIG_TPWR_HOLDOFF
        self.logger_size = DEFAULT_LOGGER_SIZE

        # Current project
        self.project: Optional[Project] = None
        self.last_project_path: str = ""

        # Settings directory
        self.settings_dir = _SETTINGS_DIR

        # Log file date format (for rotating data logs)
        self.log_file_date_format = "%Y-%m"

        # Email client
        self.email_client = EmailClient()

    @classmethod
    def get_instance(cls) -> Settings:
        """Return the singleton instance (create on first call)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    # ---- Initialization -------------------------------------------------

    def init(self) -> None:
        """Load settings from disk and transition to Idle."""
        os.makedirs(self.settings_dir, exist_ok=True)
        self._load_settings()
        self.state = SettingsState.IDLE
        logger.info("Settings initialized (dir=%s)", self.settings_dir)

    def terminate(self) -> None:
        """Save settings and close the current project."""
        self._save_settings()
        if self.project:
            self.close_project()
        self.state = SettingsState.PASSIVE

    # ---- Project lifecycle ----------------------------------------------

    def new_project(self, project: Project) -> None:
        """Create and activate a new project."""
        if self.project:
            self.close_project()
        self.project = project
        project.create_directories()
        project.save()
        self.last_project_path = project.path
        self.state = SettingsState.PROJECT_NEW
        self._save_settings()
        self._start_triggered_units()
        logger.info("New project: %s", project.name)

    def open_project(self, project: Project) -> None:
        """Open an existing project."""
        if self.project:
            self.close_project()
        self.project = project
        self.last_project_path = project.path
        self.state = SettingsState.PROJECT_OPEN

        # Set log paths on groups
        for group in project.group_db:
            group.set_project_log_path(project.log_path)

        self._save_settings()
        self._start_triggered_units()
        logger.info("Opened project: %s", project.name)

    def close_project(self) -> None:
        """Save and close the current project, disabling all units."""
        if not self.project:
            return
        self.state = SettingsState.CLOSING_RESOURCES

        # Save project
        try:
            self.project.save()
        except Exception:
            logger.exception("Failed to save project on close")

        # Disable all units
        for unit in self.project.unit_db:
            try:
                unit.set_enabled(False)
            except Exception:
                logger.exception("Failed to disable unit '%s'", unit.name)

        # Release monitor group resources
        for group in self.project.group_db:
            try:
                group.release_resources()
            except Exception:
                logger.exception(
                    "Failed to release group '%s'", group.name)

        self.project = None
        self.state = SettingsState.PROJECT_CLOSED

    def _start_triggered_units(self) -> None:
        """Enable all units that were 'triggered' (auto-connect)."""
        if not self.project:
            return
        for unit in self.project.unit_db:
            if unit.triggered:
                unit.set_enabled(True)

    # ---- Persistence (YAML) ---------------------------------------------

    def _settings_filepath(self) -> str:
        return os.path.join(self.settings_dir, _SETTINGS_FILE)

    def _save_settings(self) -> None:
        data = {
            "session_timeout": self.session_timeout,
            "connect_timeout": self.connect_timeout,
            "validate_connection_timer": self.validate_connection_timer,
            "trig_email_holdoff": self.trig_email_holdoff,
            "trig_spectrum_holdoff": self.trig_spectrum_holdoff,
            "trig_tpwr_holdoff": self.trig_tpwr_holdoff,
            "logger_size": self.logger_size,
            "last_project_path": self.last_project_path,
            "log_file_date_format": self.log_file_date_format,
            "email": self.email_client.to_dict(),
        }
        try:
            filepath = self._settings_filepath()
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False)
        except Exception:
            logger.exception("Failed to save settings")

    def _load_settings(self) -> None:
        filepath = self._settings_filepath()
        if not os.path.isfile(filepath):
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.session_timeout = data.get(
                "session_timeout", DEFAULT_SESSION_TIMEOUT)
            self.connect_timeout = data.get(
                "connect_timeout", DEFAULT_CONNECT_TIMEOUT)
            self.validate_connection_timer = data.get(
                "validate_connection_timer",
                DEFAULT_VALIDATE_CONNECTION_TIMER)
            self.trig_email_holdoff = data.get(
                "trig_email_holdoff", DEFAULT_TRIG_EMAIL_HOLDOFF)
            self.trig_spectrum_holdoff = data.get(
                "trig_spectrum_holdoff", DEFAULT_TRIG_SPECTRUM_HOLDOFF)
            self.trig_tpwr_holdoff = data.get(
                "trig_tpwr_holdoff", DEFAULT_TRIG_TPWR_HOLDOFF)
            self.logger_size = data.get(
                "logger_size", DEFAULT_LOGGER_SIZE)
            self.last_project_path = data.get(
                "last_project_path", "")
            self.log_file_date_format = data.get(
                "log_file_date_format", "%Y-%m")
            email_data = data.get("email", {})
            if email_data:
                self.email_client = EmailClient.from_dict(email_data)
        except Exception:
            logger.exception("Failed to load settings")
