#!/usr/bin/env python3
"""Phase 1 verification: test pyWNMS core backend classes.

Split into two sections:
  A. Offline unit tests (no device needed)
  B. Live integration tests (requires device at 10.44.40.218:7734)

Run: python tests/test_phase1.py [--live]
"""

import os
import sys
import shutil
import tempfile
import time
import traceback
from datetime import datetime

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results = []


def test(name, func):
    """Run a test and record the result."""
    try:
        result = func()
        print(f"  [{PASS}] {name}")
        results.append((name, True, result))
        return result
    except Exception as e:
        print(f"  [{FAIL}] {name}: {e}")
        traceback.print_exc()
        results.append((name, False, str(e)))
        return None


# =========================================================================
# A.  OFFLINE UNIT TESTS
# =========================================================================

def test_models_data():
    """Test data model construction, clone, field access."""
    from pyWNMS.models.data import (
        OpmChannelData, OpmChannelDataCollection,
        OpmSpectrumData, OpmTpwrData, WistomData,
    )

    ch = OpmChannelData(
        channel_id=1, port_id=3, central_frequency=193.1,
        fwhm=50.0, amplitude=1.2, central_power=-10.5,
        osnr=35.0, channel_spacing=100.0,
        status_power=0x01, status_frequency=0x01, status_osnr=0x01,
        delta_power=0.1, delta_frequency=0.2, osnr_margin=5.0,
    )
    assert ch.channel_id == 1
    assert ch.port_id == 3
    assert ch.central_frequency == 193.1
    clone = ch.clone()
    assert clone.channel_id == ch.channel_id
    assert clone is not ch

    coll = OpmChannelDataCollection(channels=[ch, clone])
    assert len(coll.channels) == 2

    spec = OpmSpectrumData(
        port_id=2, power=[1.0, 2.0], frequency=[191.0, 192.0])
    spec.validate_port_id(2)
    assert spec.valid is True
    spec.validate_port_id(3)
    assert spec.valid is False

    tpwr = OpmTpwrData(port_id=5, power=-15.3,
                       start_interval=191.0, end_interval=196.0)
    tpwr.validate_port_id(5)
    assert tpwr.valid is True
    return "OK"


def test_models_configuration():
    """Test configuration dataclasses."""
    from pyWNMS.models.configuration import (
        WistomUnitConfiguration, PortInfo, ChannelInfo, ChannelType,
    )

    cfg = WistomUnitConfiguration()
    pi = PortInfo(port=1, description="Port 1", priority=0)
    cfg.ports[1] = pi
    assert cfg.get_port_info(1) is pi
    assert cfg.get_port_info(99) is None

    ci = ChannelInfo(port=1, channel=0, channel_type=ChannelType.OPM,
                     description="Ch0")
    cfg.channels[0] = ci
    assert cfg.get_channel_info(0) is ci
    return "OK"


def test_events_base():
    """Test WnmsEvent hash, acknowledge, clearable."""
    from pyWNMS.events.base import WnmsEvent, Severity

    ev = WnmsEvent(id=20, sub_id=5, status_code=0x40)
    assert ev.hash_id == WnmsEvent.create_hash_id(20, 5)
    assert ev.is_acknowledged() is False
    assert ev.is_clearable() is False

    ev.set_acknowledged("admin")
    assert ev.is_acknowledged() is True
    # Default severity is NA, so acknowledged + NA → clearable
    assert ev.is_clearable() is True

    # Re-occur resets acknowledged state
    ev.set_last_occurrence()
    assert ev.is_acknowledged() is False
    return "OK"


def test_events_factory():
    """Test WistomEvent.instance_of factory method."""
    from pyWNMS.events.base import WnmsEvent, Severity
    from pyWNMS.events.wistom_event import WistomEvent
    from pyWNMS.events.opm import (
        OpmChannelStatusPowerEvent,
        OpmChannelStatusFreqEvent,
        OpmChannelStatusOsnrEvent,
        OpmNewChannelCountEvent,
    )
    from pyWNMS.events.system import (
        TemperatureStatusEvent, WistomSystemEvent,
        WistomModuleStatus, UnknownWistomEvent,
    )

    # OPM alarm (id=20) → three sub-events
    events = WistomEvent.instance_of(20, 5, 0x00400110, 1000)
    assert len(events) == 3
    assert isinstance(events[0], OpmChannelStatusPowerEvent)
    assert isinstance(events[1], OpmChannelStatusFreqEvent)
    assert isinstance(events[2], OpmChannelStatusOsnrEvent)
    # Power status = (0x00400110 >> 16) & 0xFF = 0x40
    assert events[0].status_code == 0x40
    assert events[0].get_severity() == Severity.ALARM
    # Freq status = (0x00400110 >> 8) & 0xFF = 0x01
    assert events[1].status_code == 0x01
    assert events[1].get_severity() == Severity.OK
    # OSNR status = 0x10
    assert events[2].status_code == 0x10
    assert events[2].get_severity() == Severity.WARNING

    # New channel count (id=21)
    events = WistomEvent.instance_of(21, 0, 5, 2000)
    assert len(events) == 1
    assert isinstance(events[0], OpmNewChannelCountEvent)

    # Temperature (id=30)
    events = WistomEvent.instance_of(30, 0, 0x01, 3000)
    assert len(events) == 1
    assert isinstance(events[0], TemperatureStatusEvent)

    # System event (id=90) → stateless
    events = WistomEvent.instance_of(90, 1, 0x02, 4000)
    assert len(events) == 1
    assert isinstance(events[0], WistomSystemEvent)
    assert events[0].is_stateless() is True

    # Module status (id=91)
    events = WistomEvent.instance_of(91, 2, 0x01, 5000)
    assert len(events) == 1
    assert isinstance(events[0], WistomModuleStatus)

    # Unknown alarm
    events = WistomEvent.instance_of(999, 0, 0x01, 6000)
    assert len(events) == 1
    assert isinstance(events[0], UnknownWistomEvent)
    return "OK"


def test_event_model_add_dedup():
    """Test MonitorEventModel add, dedup, and counters."""
    from pyWNMS.events.base import WnmsEvent, Severity
    from pyWNMS.events.opm import OpmChannelStatusPowerEvent
    from pyWNMS.events.wistom_event import S_ALARM_HIGH, S_OK, S_MISSING
    from pyWNMS.monitor.monitor_event_model import MonitorEventModel, Counter

    model = MonitorEventModel()

    # Add alarm event → should be stored
    ev = OpmChannelStatusPowerEvent(sub_id=1, status_code=S_ALARM_HIGH,
                                    timestamp=100)
    model.add(ev)
    assert len(model) == 1
    assert model.total_alarms == 1

    # Duplicate with same hash_id → update, not add new
    ev2 = OpmChannelStatusPowerEvent(sub_id=1, status_code=S_ALARM_HIGH,
                                     timestamp=200)
    model.add(ev2)
    assert len(model) == 1  # Still one event

    # OK event for same sub_id → update existing status
    ev_ok = OpmChannelStatusPowerEvent(sub_id=1, status_code=S_OK,
                                       timestamp=300)
    model.add(ev_ok)
    assert len(model) == 1  # Still one event (updated in place)
    stored = model.get_events()[0]
    assert stored.status_code == S_OK

    # New OK event for a new sub_id → should NOT be added
    ev_new_ok = OpmChannelStatusPowerEvent(sub_id=99, status_code=S_OK,
                                           timestamp=400)
    model.add(ev_new_ok)
    assert len(model) == 1  # Not added because severity=OK

    return "OK"


def test_event_model_acknowledge():
    """Test acknowledge and clear workflows."""
    from pyWNMS.events.opm import OpmChannelStatusPowerEvent
    from pyWNMS.events.wistom_event import S_ALARM_HIGH
    from pyWNMS.monitor.monitor_event_model import MonitorEventModel, Counter

    model = MonitorEventModel()
    ev = OpmChannelStatusPowerEvent(sub_id=1, status_code=S_ALARM_HIGH,
                                    timestamp=100)
    model.add(ev)
    assert model.total_alarms == 1
    assert model.total_acknowledged == 0

    model.acknowledge(ev, "admin")
    assert model.total_acknowledged == 1
    assert model.total_alarms == 0  # Moved from alarms to acknowledged

    # Clearable only if severity is OK/NA and acknowledged
    # This event still has ALARM_HIGH severity so not clearable
    model.clear_passed()
    assert len(model) == 1  # Not cleared — still alarm severity

    return "OK"


def test_event_model_opm_missing():
    """OPM Power S_MISSING should remove companion freq/osnr events."""
    from pyWNMS.events.base import WnmsEvent
    from pyWNMS.events.opm import (
        OpmChannelStatusPowerEvent,
        OpmChannelStatusFreqEvent,
        OpmChannelStatusOsnrEvent,
    )
    from pyWNMS.events.wistom_event import S_ALARM_HIGH, S_MISSING
    from pyWNMS.monitor.monitor_event_model import MonitorEventModel

    model = MonitorEventModel()

    # Add freq and osnr alarms for sub_id=5
    freq = OpmChannelStatusFreqEvent(sub_id=5, status_code=S_ALARM_HIGH,
                                     timestamp=100)
    osnr = OpmChannelStatusOsnrEvent(sub_id=5, status_code=S_ALARM_HIGH,
                                     timestamp=100)
    model.add(freq)
    model.add(osnr)
    # Freq and OSNR have distinct IDs so both should be stored
    assert len(
        model) == 2, f"Expected 2 events, got {len(model)}: {model.get_events()}"

    # Power MISSING for same sub_id → removes freq + osnr
    power_miss = OpmChannelStatusPowerEvent(
        sub_id=5, status_code=S_MISSING, timestamp=200)
    model.add(power_miss)
    # After this, freq and osnr should be removed; power MISSING added
    assert len(model) == 1
    remaining = model.get_events()[0]
    assert isinstance(remaining, OpmChannelStatusPowerEvent)
    return "OK"


def test_event_model_freq_osnr_missing_filtered():
    """Freq/OSNR events with S_MISSING should be silently dropped."""
    from pyWNMS.events.opm import (
        OpmChannelStatusFreqEvent, OpmChannelStatusOsnrEvent,
    )
    from pyWNMS.events.wistom_event import S_MISSING
    from pyWNMS.monitor.monitor_event_model import MonitorEventModel

    model = MonitorEventModel()
    model.add(OpmChannelStatusFreqEvent(sub_id=1, status_code=S_MISSING,
                                        timestamp=100))
    model.add(OpmChannelStatusOsnrEvent(sub_id=2, status_code=S_MISSING,
                                        timestamp=100))
    assert len(model) == 0
    return "OK"


def test_unit_db_validation():
    """Test WistomUnitDb add/validation logic."""
    from pyWNMS.unit.wistom_unit import WistomUnit
    from pyWNMS.unit.wistom_unit_db import WistomUnitDb

    db = WistomUnitDb()
    u1 = WistomUnit(name="Unit1", hostname="10.0.0.1", tcp_port=7734,
                    username="admin", password="pass")
    db.add(u1)
    assert len(db) == 1
    assert "Unit1" in db

    # Duplicate name → ValueError
    u2 = WistomUnit(name="Unit1", hostname="10.0.0.2", tcp_port=7734,
                    username="admin", password="pass")
    try:
        db.add(u2)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # Duplicate host:port → ValueError
    u3 = WistomUnit(name="Unit3", hostname="10.0.0.1", tcp_port=7734,
                    username="admin", password="pass")
    try:
        db.add(u3)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # Empty name → ValueError
    u4 = WistomUnit(name="", hostname="10.0.0.3", tcp_port=7734,
                    username="admin", password="pass")
    try:
        db.add(u4)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # Port out of range
    u5 = WistomUnit(name="Unit5", hostname="10.0.0.5", tcp_port=80,
                    username="admin", password="pass")
    try:
        db.add(u5)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # Loopback normalization
    u6 = WistomUnit(name="UnitA", hostname="localhost", tcp_port=7734,
                    username="admin", password="pass")
    db.add(u6)
    u7 = WistomUnit(name="UnitB", hostname="127.0.0.1", tcp_port=7734,
                    username="admin", password="pass")
    try:
        db.add(u7)
        assert False, "Should have raised ValueError (loopback dup)"
    except ValueError:
        pass

    return "OK"


def test_unit_db_serialization():
    """Test WistomUnitDb round-trip to_list / from_list."""
    from pyWNMS.unit.wistom_unit import WistomUnit
    from pyWNMS.unit.wistom_unit_db import WistomUnitDb

    db = WistomUnitDb()
    db.add(WistomUnit(name="A", hostname="1.1.1.1", tcp_port=7734,
                      username="u", password="p"))
    db.add(WistomUnit(name="B", hostname="2.2.2.2", tcp_port=8000,
                      username="u2", password="p2"))
    data = db.to_list()
    assert len(data) == 2

    db2 = WistomUnitDb.from_list(data)
    assert len(db2) == 2
    assert db2.get("A") is not None
    assert db2.get("A").hostname == "1.1.1.1"
    assert db2.get("B").tcp_port == 8000
    return "OK"


def test_monitor_group_db():
    """Test MonitorGroupDb validation."""
    from pyWNMS.monitor.monitor_group import MonitorGroup
    from pyWNMS.monitor.monitor_group_db import MonitorGroupDb

    gdb = MonitorGroupDb()
    g1 = MonitorGroup(name="Group1", log_dir="g1")
    gdb.add(g1)
    assert len(gdb) == 1

    # Duplicate name
    try:
        gdb.add(MonitorGroup(name="Group1", log_dir="g1b"))
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # Duplicate log_dir
    try:
        gdb.add(MonitorGroup(name="Group2", log_dir="g1"))
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    return "OK"


def test_monitor_group_settings_propagation():
    """Test that MonitorGroup propagates alarm/log flags to children."""
    from pyWNMS.monitor.monitor_group import MonitorGroup
    from pyWNMS.monitor.monitor_unit import MonitorUnit
    from pyWNMS.unit.wistom_unit import WistomUnit, OptionalEvent

    u = WistomUnit(name="U1", hostname="1.1.1.1", tcp_port=7734,
                   username="u", password="p")
    mu = MonitorUnit(name="U1", log_dir="u1", unit=u)
    g = MonitorGroup(name="G1", log_dir="g1")
    g.add(mu)

    # Initially all False
    assert mu._monitored_events[OptionalEvent.OPM] is False

    # Turn on OPM alarm for the group → should propagate to child
    g.set_mon_opm_alarm(True)
    assert mu._monitored_events[OptionalEvent.OPM] is True

    g.set_mon_temp_alarm(True)
    assert mu._monitored_events[OptionalEvent.TEMPERATURE] is True

    return "OK"


def test_monitor_object_tree():
    """Test MonitorObject parent/child tree, add, remove, contains."""
    from pyWNMS.monitor.monitor_object import MonitorObject

    root = MonitorObject(name="root", log_dir="root")
    child1 = MonitorObject(name="c1", log_dir="c1")
    child2 = MonitorObject(name="c2", log_dir="c2")
    root.add(child1)
    root.add(child2)
    assert root.get_number_of_objects() == 2
    assert root.contains("c1")

    removed = root.remove("c1")
    assert removed is not None
    assert removed.name == "c1"
    assert root.get_number_of_objects() == 1

    # Duplicate name should fail
    root.add(MonitorObject(name="c3", log_dir="c3"))
    try:
        root.add(MonitorObject(name="c3", log_dir="c3b"))
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    return "OK"


def test_crypto_classic_roundtrip():
    """Test CryptographyWnmsClassic encrypt/decrypt roundtrip."""
    from pyWNMS.util.crypto import CryptographyWnmsClassic

    crypto = CryptographyWnmsClassic()
    for plaintext in ["hello", "W!stom#123", "", "a", "admin",
                      "short", "A much longer password with spaces!"]:
        encrypted = crypto.encrypt(plaintext)
        if plaintext:
            assert encrypted != plaintext, f"Should be encrypted: {plaintext}"
            assert encrypted.startswith("="), "Should start with ="
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == plaintext, \
            f"Roundtrip failed: '{plaintext}' → '{encrypted}' → '{decrypted}'"
    return "OK"


def test_crypto_des_roundtrip():
    """Test DES Cryptography encrypt/decrypt roundtrip."""
    from pyWNMS.util.crypto import Cryptography, _HAS_CRYPTO_LIB

    if not _HAS_CRYPTO_LIB:
        print("    (cryptography lib not installed — skipping DES test)")
        return "SKIP"

    crypto = Cryptography()
    for plaintext in ["hello", "admin", "W!stom_p@ss"]:
        encrypted = crypto.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == plaintext, \
            f"DES roundtrip failed: '{plaintext}' → '{decrypted}'"
    return "OK"


def test_user_account_model():
    """Test UserAccountModel: create, login, add, remove, save/load."""
    from pyWNMS.account.user_account import (
        UserAccountModel, Administrator, Operator,
        DefaultAdministrator, AccountType,
    )

    tmpdir = tempfile.mkdtemp()
    try:
        filepath = os.path.join(tmpdir, "accounts.dat")
        model = UserAccountModel(filepath)

        # Default admin exists
        assert model.exists("admin")
        assert len(model.get_accounts()) == 1

        # Login with default credentials
        assert model.login("admin", "admin") is True
        assert model.logged_in_user is not None
        assert model.logged_in_user.username == "admin"

        # Add an operator
        op = Operator("operator1", "op_pass")
        model.add(op)
        assert model.exists("operator1")
        assert len(model.get_accounts()) == 2

        # Cannot add duplicate username
        try:
            model.add(Operator("operator1", "x"))
            assert False, "Should have raised ValueError for dup"
        except ValueError:
            pass

        # Add another operator for removal test
        op2 = Operator("operator2", "op2_pass")
        model.add(op2)
        assert model.exists("operator2")

        # Save and reload
        model.save()
        assert os.path.isfile(filepath)

        model2 = UserAccountModel(filepath)
        model2.load()
        assert model2.exists("admin")
        assert model2.exists("operator1")
        assert model2.exists("operator2")

        # Login with the loaded data
        assert model2.login("operator1", "op_pass") is True

        # Non-admin cannot add
        try:
            model2.add(Operator("op3", "x"))
            assert False, "Should have raised PermissionError"
        except PermissionError:
            pass

        # Remove operator (requires admin)
        assert model2.login("admin", "admin") is True
        # Find op1 account in loaded model
        op1_loaded = [a for a in model2.get_accounts()
                      if a.username == "operator1"][0]
        model2.remove(op1_loaded)
        assert not model2.exists("operator1")

        # Cannot remove default admin
        default_admin = [a for a in model2.get_accounts()
                         if a.username == "admin"][0]
        try:
            model2.remove(default_admin)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return "OK"


def test_project_save_load():
    """Test Project create, save, load roundtrip."""
    from pyWNMS.project.project import Project
    from pyWNMS.unit.wistom_unit import WistomUnit
    from pyWNMS.monitor.monitor_group import MonitorGroup
    from pyWNMS.monitor.monitor_unit import MonitorUnit

    tmpdir = tempfile.mkdtemp()
    try:
        proj = Project(name="TestProject", path=tmpdir)

        u1 = WistomUnit(name="DevA", hostname="10.0.0.1", tcp_port=7734,
                        username="admin", password="pass")
        u2 = WistomUnit(name="DevB", hostname="10.0.0.2", tcp_port=7734,
                        username="admin", password="pass")
        proj.unit_db.add(u1)
        proj.unit_db.add(u2)

        g = MonitorGroup(name="MainGroup", log_dir="main")
        g.set_mon_opm_alarm(True)
        g.log_opm_chan_data = True
        proj.group_db.add(g)

        proj.save()
        assert Project.file_exists(tmpdir)

        # Reload
        proj2 = Project.load(tmpdir)
        assert proj2.name == "TestProject"
        assert len(proj2.unit_db) == 2
        assert proj2.unit_db.get("DevA") is not None
        assert proj2.unit_db.get("DevA").hostname == "10.0.0.1"
        assert len(proj2.group_db) == 1
        loaded_g = proj2.group_db.get("MainGroup")
        assert loaded_g is not None
        assert loaded_g.mon_opm_alarm is True
        assert loaded_g.log_opm_chan_data is True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return "OK"


def test_datalog_channel_data():
    """Test OpmChannelDataLogger writes TSV."""
    from pyWNMS.datalog.writers import OpmChannelDataLogger
    from pyWNMS.models.data import OpmChannelData

    tmpdir = tempfile.mkdtemp()
    try:
        logger = OpmChannelDataLogger(tmpdir)
        ch = OpmChannelData(
            channel_id=1, port_id=3, central_frequency=193.1,
            fwhm=50.0, amplitude=1.2, central_power=-10.5,
            osnr=35.0, channel_spacing=100.0,
            status_power=1, status_frequency=1, status_osnr=1,
            delta_power=0.1, delta_frequency=0.2, osnr_margin=5.0,
        )
        logger.write(ch)
        logger.write(ch)  # Second write, same file

        # Check file exists
        log_dir = os.path.join(tmpdir, "opmchanneldata")
        assert os.path.isdir(log_dir)
        files = os.listdir(log_dir)
        assert len(files) == 1
        assert files[0].startswith("opmchanneldata_")
        assert files[0].endswith(".log")

        # Check content: header + 2 data lines
        with open(os.path.join(log_dir, files[0])) as f:
            lines = f.readlines()
        assert len(lines) == 3  # header + 2 data rows
        assert "Timestamp\tChannelId\t" in lines[0]
        assert "193.1" in lines[1]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return "OK"


def test_datalog_tpwr():
    """Test OpmTpwrDataLogger writes TSV."""
    from pyWNMS.datalog.writers import OpmTpwrDataLogger
    from pyWNMS.models.data import OpmTpwrData

    tmpdir = tempfile.mkdtemp()
    try:
        logger = OpmTpwrDataLogger(tmpdir)
        data = OpmTpwrData(port_id=2, power=-15.3,
                           start_interval=191.0, end_interval=196.0)
        logger.write(data)

        log_dir = os.path.join(tmpdir, "totalpower")
        files = os.listdir(log_dir)
        assert len(files) == 1
        assert "totalpower" in files[0]

        with open(os.path.join(log_dir, files[0])) as f:
            lines = f.readlines()
        assert len(lines) == 2  # header + 1 data row
        assert "-15.3" in lines[1]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return "OK"


def test_datalog_spectrum():
    """Test OpmSpectrumDataLogger writes TSV."""
    from pyWNMS.datalog.writers import OpmSpectrumDataLogger
    from pyWNMS.models.data import OpmSpectrumData

    tmpdir = tempfile.mkdtemp()
    try:
        logger = OpmSpectrumDataLogger(tmpdir)
        data = OpmSpectrumData(
            port_id=1,
            power=[-20.0, -15.5, -10.3],
            frequency=[191.0, 191.5, 192.0],
        )
        logger.write(data)
        logger.write(data)  # Second write → different index

        port_dir = os.path.join(tmpdir, "spectrum", "1")
        assert os.path.isdir(port_dir)
        files = sorted(os.listdir(port_dir))
        assert len(files) == 2
        assert "_0.log" in files[0]
        assert "_1.log" in files[1]

        with open(os.path.join(port_dir, files[0])) as f:
            lines = f.readlines()
        assert len(lines) == 4  # header + 3 data rows
        assert "191.0" in lines[1]
        assert "-20.0" in lines[1]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return "OK"


def test_datalog_events():
    """Test EventLogger writes TSV."""
    from pyWNMS.datalog.writers import EventLogger
    from pyWNMS.events.opm import OpmChannelStatusPowerEvent
    from pyWNMS.events.wistom_event import S_ALARM_HIGH

    tmpdir = tempfile.mkdtemp()
    try:
        logger = EventLogger(tmpdir)
        ev = OpmChannelStatusPowerEvent(sub_id=1, status_code=S_ALARM_HIGH,
                                        timestamp=100)
        logger.write(ev, "Raised")
        logger.write(ev, "Cleared")

        events_dir = os.path.join(tmpdir, "events")
        files = os.listdir(events_dir)
        assert len(files) == 1

        with open(os.path.join(events_dir, files[0])) as f:
            lines = f.readlines()
        assert len(lines) == 3  # header + 2 entries
        assert "Raised" in lines[1]
        assert "Cleared" in lines[2]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return "OK"


def test_event_counter_propagation():
    """Test counter propagation from child event model to parent."""
    from pyWNMS.monitor.monitor_object import MonitorObject
    from pyWNMS.monitor.monitor_event_model import Counter
    from pyWNMS.events.opm import OpmChannelStatusPowerEvent
    from pyWNMS.events.wistom_event import S_ALARM_HIGH, S_WARNING_LOW

    parent = MonitorObject(name="parent", log_dir="parent")
    child1 = MonitorObject(name="c1", log_dir="c1")
    child2 = MonitorObject(name="c2", log_dir="c2")
    parent.add(child1)
    parent.add(child2)

    # Add alarm event to child1
    ev1 = OpmChannelStatusPowerEvent(sub_id=1, status_code=S_ALARM_HIGH,
                                     timestamp=100)
    child1.event_model.add(ev1)
    assert child1.event_model.total_alarms == 1

    # Add warning to child2
    ev2 = OpmChannelStatusPowerEvent(sub_id=2, status_code=S_WARNING_LOW,
                                     timestamp=200)
    child2.event_model.add(ev2)
    assert child2.event_model.total_warnings == 1

    # Parent should reflect children's totals
    # (parent counters include base = sum of children + own events)
    # The counter listener mechanism triggers refresh
    assert parent.event_model.total_alarms >= 1
    assert parent.event_model.total_warnings >= 1
    return "OK"


def test_holdoff_timer():
    """Test trigger HoldOffTimer."""
    from pyWNMS.monitor.trigger import HoldOffTimer

    timer = HoldOffTimer()
    assert timer.is_active(1) is False

    timer.start(1, 0.2)  # 200ms hold-off
    assert timer.is_active(1) is True
    time.sleep(0.3)
    assert timer.is_active(1) is False
    return "OK"


def test_email_client_serialization():
    """Test EmailClient to_dict / from_dict."""
    from pyWNMS.util.email_client import EmailClient

    client = EmailClient(
        server="smtp.example.com", port=587,
        sender="test@example.com",
        recipients=["a@example.com", "b@example.com"],
    )

    d = client.to_dict()
    assert d["server"] == "smtp.example.com"
    assert d["port"] == 587

    client2 = EmailClient.from_dict(d)
    assert client2.server == "smtp.example.com"
    assert client2.recipients == ["a@example.com", "b@example.com"]
    return "OK"


def test_wistom_unit_serialization():
    """Test WistomUnit to_dict / from_dict roundtrip."""
    from pyWNMS.unit.wistom_unit import WistomUnit

    u = WistomUnit(name="Test", hostname="192.168.1.1", tcp_port=8080,
                   username="root", password="secret")
    u.triggered = True
    d = u.to_dict()
    assert d["name"] == "Test"
    assert d["triggered"] is True

    u2 = WistomUnit.from_dict(d)
    assert u2.name == "Test"
    assert u2.hostname == "192.168.1.1"
    assert u2.tcp_port == 8080
    assert u2.triggered is True
    return "OK"


def test_monitor_group_serialization():
    """Test MonitorGroup to_dict / from_dict roundtrip."""
    from pyWNMS.monitor.monitor_group import MonitorGroup

    g = MonitorGroup(name="G1", log_dir="g1dir")
    g.mon_opm_alarm = True
    g.mon_temp_alarm = True
    g.log_event_to_disk = True
    g.log_opm_chan_data_interval = 3600

    d = g.to_dict()
    assert d["mon_opm_alarm"] is True
    assert d["log_opm_chan_data_interval"] == 3600

    g2 = MonitorGroup.from_dict(d)
    assert g2.name == "G1"
    assert g2.mon_opm_alarm is True
    assert g2.mon_temp_alarm is True
    assert g2.log_event_to_disk is True
    assert g2.log_opm_chan_data_interval == 3600
    return "OK"


# =========================================================================
# B.  LIVE INTEGRATION TESTS (require device)
# =========================================================================

def run_live_tests():
    """Run tests that require a live Wistom device."""
    from pyWistom import HOST, PORT, USER_ID, PASSWORD
    from pyWNMS.unit.wistom_unit import (
        WistomUnit, UnitState,
        WistomUnitListener, WistomUnitCommListener,
    )
    from pyWNMS.events.base import WnmsEvent

    print("\n--- Live Integration Tests ---")
    print(f"  Device: {HOST}:{PORT}")

    # -- Listener to capture state changes --------------------------------
    class TestListener(WistomUnitListener, WistomUnitCommListener):
        def __init__(self):
            self.states = []
            self.config_changed = False
            self.events: list = []

        def wistom_unit_state_changed(self, unit, cause=""):
            self.states.append(unit.state)
            cause_str = f" ({cause})" if cause else ""
            print(f"    [STATE] {unit.name}: → {unit.state.name}{cause_str}")

        def wistom_unit_configuration_changed(self, unit):
            self.config_changed = True
            cfg = unit.configuration
            print(f"    [CONFIG] Configuration updated:")
            print(f"             Serial: {cfg.unit_info.unit_serial}")
            print(f"             Sensor: {cfg.unit_info.web_serial}")
            print(f"             SW: {cfg.unit_info.sw_revision}  "
                  f"FW: {cfg.unit_info.fw_revision}  "
                  f"PLD: {cfg.unit_info.pld_revision}")
            print(f"             Ports: {len(cfg.ports)}  "
                  f"Channels: {len(cfg.channels)}")
            print(f"             OPM: {'enabled' if cfg.opm_enabled else 'disabled'}  "
                  f"OCM: {'enabled' if cfg.ocm_enabled else 'disabled'}")
            if cfg.ports:
                port_nums = sorted(cfg.ports.keys())
                print(f"             Port list: {port_nums}")

        def wistom_unit_comm_event_received(self, unit, event):
            self.events.append(event)
            sev = event.get_severity().name
            status = event.get_status() if hasattr(event, 'get_status') else ''
            print(f"    [EVENT] {type(event).__name__}: "
                  f"id={event.id}, severity={sev}"
                  f"{f', status={status}' if status else ''}")

        def wistom_unit_comm_data_received(self, unit, data):
            print(f"    [DATA]  {type(data).__name__} received")

    # -- Test: WistomUnit connects, fetches config, reaches CONNECTED -----

    def test_live_connect_and_config():
        unit = WistomUnit(
            name="LiveTest",
            hostname=HOST,
            tcp_port=PORT,
            username=USER_ID,
            password=PASSWORD,
        )
        listener = TestListener()
        unit.add_unit_listener(listener)
        unit.add_comm_listener(listener)

        try:
            print(f"    Enabling unit '{unit.name}' → {HOST}:{PORT} ...")
            unit.set_enabled(True)
            # Wait for connection (up to 30 seconds)
            print(f"    Waiting for CONNECTED state (timeout 30s) ...")
            deadline = time.monotonic() + 30
            last_state = None
            while unit.state != UnitState.CONNECTED:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Unit did not reach CONNECTED within 30s, "
                        f"state={unit.state.name}")
                if unit.state != last_state:
                    last_state = unit.state
                time.sleep(0.5)
            elapsed = 30 - (deadline - time.monotonic())
            print(f"    Reached CONNECTED in {elapsed:.1f}s")

            # Verify state reached CONNECTED (may skip CONNECTING
            # notification since internal state advances before listener fires)
            assert unit.state == UnitState.CONNECTED
            assert UnitState.CONNECTED in listener.states

            # Verify configuration was fetched
            cfg = unit.configuration
            assert cfg.unit_info is not None
            assert cfg.unit_info.unit_serial != ""
            assert len(cfg.ports) > 0

            # Print connection events summary
            if listener.events:
                print(f"    Events received: {len(listener.events)}")
                for ev in listener.events:
                    sev = ev.get_severity().name
                    status = ev.get_status() if hasattr(ev, 'get_status') else ''
                    print(f"      - {type(ev).__name__} "
                          f"(id={ev.id}, sev={sev}"
                          f"{f', status={status}' if status else ''}")

            return {
                "serial": cfg.unit_info.unit_serial,
                "sw": cfg.unit_info.sw_revision,
                "ports": len(cfg.ports),
                "channels": len(cfg.channels),
            }
        finally:
            unit.set_enabled(False)
            time.sleep(2)  # Allow cleanup

    test("WistomUnit connect + config fetch", test_live_connect_and_config)

    # -- Test: WistomUnit keepalive works ----------------------------------

    def test_live_keepalive():
        """Connect, wait a bit, verify still connected."""
        unit = WistomUnit(
            name="KATest",
            hostname=HOST,
            tcp_port=PORT,
            username=USER_ID,
            password=PASSWORD,
        )
        listener = TestListener()
        unit.add_unit_listener(listener)
        unit.add_comm_listener(listener)

        try:
            print(f"    Enabling unit '{unit.name}' → {HOST}:{PORT} ...")
            unit.set_enabled(True)
            deadline = time.monotonic() + 30
            while unit.state != UnitState.CONNECTED:
                if time.monotonic() > deadline:
                    raise TimeoutError("Did not reach CONNECTED")
                time.sleep(0.5)
            elapsed = 30 - (deadline - time.monotonic())
            print(f"    Reached CONNECTED in {elapsed:.1f}s")

            # Stay connected for a few seconds
            print(f"    Holding connection for 5s (keepalive test) ...")
            time.sleep(5)
            assert unit.state == UnitState.CONNECTED, \
                f"Expected CONNECTED, got {unit.state.name}"
            print(f"    Still CONNECTED after 5s hold — keepalive OK")
            return "OK"
        finally:
            unit.set_enabled(False)
            time.sleep(1)

    test("WistomUnit keepalive", test_live_keepalive)


# =========================================================================
# Main
# =========================================================================

def main():
    live = "--live" in sys.argv

    print("=" * 60)
    print("Phase 1 Tests: pyWNMS Core Backend")
    print("=" * 60)

    print("\n--- Offline Unit Tests ---")

    test("Data models (construction, clone)", test_models_data)
    test("Configuration dataclasses", test_models_configuration)
    test("WnmsEvent (hash, ack, clearable)", test_events_base)
    test("WistomEvent.instance_of factory", test_events_factory)
    test("MonitorEventModel add/dedup", test_event_model_add_dedup)
    test("MonitorEventModel acknowledge", test_event_model_acknowledge)
    test("MonitorEventModel OPM MISSING", test_event_model_opm_missing)
    test("MonitorEventModel Freq/OSNR MISSING filter",
         test_event_model_freq_osnr_missing_filtered)
    test("WistomUnitDb validation", test_unit_db_validation)
    test("WistomUnitDb serialization", test_unit_db_serialization)
    test("MonitorGroupDb validation", test_monitor_group_db)
    test("MonitorGroup settings propagation",
         test_monitor_group_settings_propagation)
    test("MonitorObject tree management", test_monitor_object_tree)
    test("CryptographyWnmsClassic roundtrip", test_crypto_classic_roundtrip)
    test("Cryptography DES roundtrip", test_crypto_des_roundtrip)
    test("UserAccountModel lifecycle", test_user_account_model)
    test("Project save/load YAML", test_project_save_load)
    test("EventLogger TSV", test_datalog_events)
    test("OpmChannelDataLogger TSV", test_datalog_channel_data)
    test("OpmTpwrDataLogger TSV", test_datalog_tpwr)
    test("OpmSpectrumDataLogger TSV", test_datalog_spectrum)
    test("Counter propagation", test_event_counter_propagation)
    test("HoldOffTimer", test_holdoff_timer)
    test("EmailClient serialization", test_email_client_serialization)
    test("WistomUnit serialization", test_wistom_unit_serialization)
    test("MonitorGroup serialization", test_monitor_group_serialization)

    if live:
        run_live_tests()
    else:
        print("\n  (Skipping live tests — use --live to enable)")

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"Results: {passed} passed, {failed} failed, "
          f"{len(results)} total")
    if failed:
        print("\nFailed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
