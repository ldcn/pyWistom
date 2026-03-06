"""Wistom unit configuration model.

Ports ``WistomUnitConfiguration`` and its inner classes from the Java
source (``unit/WistomUnitConfiguration.java``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional


# -- Enumerations ---------------------------------------------------------

class PortMode(Enum):
    """Switch port operation mode."""
    MANUAL = "Manual"
    AUTOMATIC = "Automatic"
    CONFIGURED = "Configured"


class ChannelType(Enum):
    """Channel assignment type."""
    NONE = "None"
    OCM = "Ocm"
    OPM = "Opm"


# -- Inner data classes ---------------------------------------------------

@dataclass
class UnitInfo:
    """Hardware and firmware identity strings."""
    unit_serial: str = ""
    web_serial: str = ""
    web_revision: str = ""
    sw_revision: str = ""
    fw_revision: str = ""
    pld_revision: str = ""
    switch_revision: str = ""


@dataclass
class PortInfo:
    """Per-port description and priority."""
    port: int = 0
    description: str = ""
    priority: int = 0


@dataclass
class ChannelInfo:
    """Per-channel configuration."""
    port: int = 0
    channel: int = 0
    channel_type: ChannelType = ChannelType.NONE
    description: str = ""


@dataclass
class IpSettings:
    """Network configuration retrieved via ``SMGR IP##``."""
    hostname: str = ""
    ip_address: str = ""
    subnet_mask: str = ""
    default_gateway: str = ""
    mac_address: str = ""


@dataclass
class Rs232Settings:
    """Serial port settings retrieved via ``SMGR SER#``."""
    baudrate: int = 0
    data_bits: int = 0
    stop_bits: int = 0
    parity: str = ""


@dataclass
class InstalledFeatures:
    """Feature flags from ``SMGR INST``."""
    snmp: bool = False


@dataclass
class TempInfo:
    """Temperature readings from ``SMGR TEMP``."""
    web_temp: float = 0.0
    sensor_temp: float = 0.0
    min_temp_limit: float = 0.0
    max_temp_limit: float = 0.0
    min_cfg_temp_limit: float = 0.0
    max_cfg_temp_limit: float = 0.0


# -- Main configuration class --------------------------------------------

MAX_NO_OF_PORTS = 16
MAX_NO_OF_CHANNELS = 1024


@dataclass
class WistomUnitConfiguration:
    """Complete cached configuration of a Wistom device.

    Populated by the config-fetch sequence after login:
    ``SPEC SWIN → SWMO → SWCO → SMGR INFO → SPEC CTBL → …``
    """

    # Port / switch state
    ports: Dict[int, PortInfo] = field(default_factory=dict)
    port_mode: PortMode = PortMode.AUTOMATIC
    manual_port: int = 0

    # Channel table
    channels: Dict[int, ChannelInfo] = field(default_factory=dict)

    # OPM / OCM feature flags
    ocm_enabled: bool = False
    opm_enabled: bool = False
    opm_mode: Optional[PortMode] = None
    opm_scanning_unconfigured_channels: bool = False

    # Identity / network / hardware
    unit_info: UnitInfo = field(default_factory=UnitInfo)
    installed_features: InstalledFeatures = field(
        default_factory=InstalledFeatures)
    ip_settings: IpSettings = field(default_factory=IpSettings)
    rs232_settings: Rs232Settings = field(default_factory=Rs232Settings)
    temp_info: TempInfo = field(default_factory=TempInfo)

    # Timestamp of last successful update
    last_update: Optional[datetime] = None

    # -- Port helpers -----------------------------------------------------

    def get_port_info(self, port: int) -> Optional[PortInfo]:
        return self.ports.get(port)

    def set_port_info(self, info: PortInfo) -> None:
        info.description = info.description.strip()
        if not info.description:
            info.description = str(info.port)
        self.ports[info.port] = info

    def get_no_of_installed_ports(self) -> int:
        return len(self.ports)

    def is_port_installed(self, port: int) -> bool:
        return port in self.ports

    def is_port_scanned(self, port: int) -> bool:
        info = self.ports.get(port)
        return info is not None and info.priority > 0

    # -- Channel helpers --------------------------------------------------

    def get_channel_info(self, channel: int) -> Optional[ChannelInfo]:
        return self.channels.get(channel)

    def set_channel_info(self, info: ChannelInfo) -> None:
        info.description = info.description.strip()
        if not info.description:
            info.description = str(info.channel)
        self.channels[info.channel] = info

    def get_no_of_configured_channels(self) -> int:
        return len(self.channels)

    def get_no_of_configured_opm_channels(self) -> int:
        return sum(
            1 for c in self.channels.values()
            if c.channel_type == ChannelType.OPM
        )

    def get_no_of_configured_ocm_channels(self) -> int:
        return sum(
            1 for c in self.channels.values()
            if c.channel_type == ChannelType.OCM
        )
