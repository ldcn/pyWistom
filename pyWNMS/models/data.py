"""Core data model classes for WNMS measurement data.

Ports the Java ``data/`` package: ``WnmsData``, ``WistomData``,
``OpmChannelData``, ``OpmChannelDataCollection``, ``OpmSpectrumData``,
and ``OpmTpwrData``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional


@dataclass
class WnmsData:
    """Base data object with a timestamp and a generic caller reference.

    :param date: Timestamp when the data was created.
    :param reference: Opaque caller reference (used to route data back).
    """

    date: datetime = field(default_factory=datetime.now)
    reference: Any = None

    def clone(self) -> WnmsData:
        return copy.deepcopy(self)


@dataclass
class WistomData(WnmsData):
    """Data associated with a specific Wistom device.

    :param source: Name (or reference) of the originating WistomUnit.
    :param valid: Whether the data passed validation.
    :param empty: Whether the data payload is empty/placeholder.
    """

    source: Optional[str] = None
    valid: bool = True
    empty: bool = False

    def clone(self) -> WistomData:
        return copy.deepcopy(self)


@dataclass
class OpmChannelData(WistomData):
    """OPM channel measurement data for a single channel.

    Contains central frequency, power, OSNR, status flags, and deltas
    exactly as returned by the ``OPM# CHAL`` command (one element per
    channel).
    """

    channel_id: int = 0
    port_id: int = 0
    central_frequency: float = 0.0
    fwhm: float = 0.0
    amplitude: float = 0.0
    central_power: float = 0.0
    osnr: float = 0.0
    channel_spacing: float = 0.0
    status_power: int = 0
    status_frequency: int = 0
    status_osnr: int = 0
    delta_power: float = 0.0
    delta_frequency: float = 0.0
    osnr_margin: float = 0.0
    timestamp: float = 0.0

    def clone(self) -> OpmChannelData:
        return copy.deepcopy(self)


@dataclass
class OpmChannelDataCollection(WnmsData):
    """Collection of :class:`OpmChannelData` from a single ``CHAL`` fetch.

    :param channels: Per-channel measurement records.
    """

    channels: List[OpmChannelData] = field(default_factory=list)

    def clone(self) -> OpmChannelDataCollection:
        return copy.deepcopy(self)


@dataclass
class OpmSpectrumData(WistomData):
    """Frequency spectrum for a single port (``OPM# FSPC``).

    :param port_id: Optical switch port number.
    :param power: Array of power values (dBm).
    :param frequency: Array of frequency values (GHz).
    """

    port_id: int = 0
    power: List[float] = field(default_factory=list)
    frequency: List[float] = field(default_factory=list)

    def validate_port_id(self, port_id: int) -> None:
        """Mark data as valid only if *port_id* matches."""
        self.valid = (self.port_id == port_id)

    def clone(self) -> OpmSpectrumData:
        return copy.deepcopy(self)


@dataclass
class OpmTpwrData(WistomData):
    """Total power measurement for a single port (``OPM# TPWR``).

    :param port_id: Optical switch port number.
    :param power: Total optical power (dBm).
    :param start_interval: Start frequency of measurement interval (GHz).
    :param end_interval: End frequency of measurement interval (GHz).
    """

    port_id: int = 0
    power: float = 0.0
    start_interval: float = 0.0
    end_interval: float = 0.0

    def validate_port_id(self, port_id: int) -> None:
        """Mark data as valid only if *port_id* matches."""
        self.valid = (self.port_id == port_id)

    def clone(self) -> OpmTpwrData:
        return copy.deepcopy(self)
