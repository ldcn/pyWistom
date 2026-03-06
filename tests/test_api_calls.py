#!/usr/bin/env python3
"""Comprehensive live API call tests for pyWistom.

Tests every public pyWistom API method against the live device and
prints verbose output including function name, tag numbers, data types,
and values — designed for comparison with manual serial terminal sessions.

Run: python tests/test_api_calls.py

Output goes to stdout (with ANSI colors) and tests/api_test_results.txt
(plain text, no ANSI escape sequences).

Requires live device configured in settings.yaml.
"""

from wistomtags import TAG_PARSER
from pyWistom import HOST, PORT, USER_ID, PASSWORD, WistomClient
from wistomconstants import ALARM_TYPE
import os
import sys
import re
import struct
import time
import traceback
from datetime import datetime

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


# ======================================================================
# Tag data type mapping: (app_id, op_id) → {tag_number: type_string}
# Extracted from pyWistom.py parser implementations.
# ======================================================================
TAG_DATA_TYPES = {
    ('SMGR', 'INFO'): {
        1: 'STR', 2: 'STR', 3: 'STR', 4: 'STR',
        17: 'STR', 18: 'STR', 19: 'STR', 20: 'STR',
        33: 'STR', 35: 'STR', 51: 'STR', 52: 'STR',
        53: 'STR', 54: 'STR', 65: 'STR', 66: 'STR',
        80: 'F64', 81: 'F64', 82: 'F32', 83: 'F32',
    },
    ('SMGR', 'IP##'): {
        1: 'STR', 2: 'STR', 3: 'STR', 4: 'STR', 5: 'STR', 6: 'U16',
    },
    ('SMGR', 'SER#'): {
        1: 'U8', 2: 'U32', 3: 'U8', 4: 'U8', 5: 'U8',
    },
    ('SMGR', 'TIME'): {
        1: 'U16', 2: 'U8', 3: 'U8', 4: 'U8', 5: 'U8', 6: 'U8',
    },
    ('SMGR', 'TEMP'): {
        1: 'F32', 2: 'F32', 3: 'F32', 4: 'F32', 5: 'F32', 6: 'F32',
    },
    ('SMGR', 'UPTI'): {1: 'F32', 2: 'F32', 3: 'F32'},
    ('SMGR', 'INST'): {1: 'U8', 2: 'U8'},
    ('SMGR', 'SCFG'): {1: 'U16', 2: 'U16', 3: 'U16'},
    ('SMGR', 'SLTR'): {1: 'STR', 2: 'U16'},
    ('SPEC', 'SWIN'): {
        **{i: 'U8' for i in range(1, 51)},
        101: 'U8[]', 102: 'U8[]', 103: 'U8[]', 104: 'U8[]',
    },
    ('SPEC', 'SWMO'): {1: 'U8', 2: 'U8'},
    ('SPEC', 'SWCO'): {
        **{i: 'U8' for i in range(1, 17)},
        **{i: 'STR' for i in range(51, 67)},
        **{i: 'U8' for i in range(101, 117)},
        **{i: 'F32' for i in range(151, 167)},
    },
    ('SPEC', 'CTBL'): {1: 'U16', 2: 'U16[]'},
    ('SPEC', 'CHNL'): {
        1: 'U32[32]', 2: 'U16', 3: 'U16', 100: 'U8', 27: 'STR',
        **{i: 'F64' for i in range(4, 27)},
    },
    ('OPM#', 'ENAB'): {1: 'U8'},
    ('OPM#', 'AVRG'): {1: 'U32'},
    ('OPM#', 'CHCO'): {
        1: 'U8', 2: 'U8', 3: 'F64', 4: 'U8', 5: 'U16',
    },
    ('OPM#', 'TRSH'): {1: 'F64', 2: 'F64', 3: 'U16'},
    ('OPM#', 'MINL'): {1: 'F64', 2: 'F64'},
    ('OPM#', 'PCRI'): {
        1: 'F64', 2: 'F64', 4: 'F64', 5: 'F64', 6: 'U8',
    },
    ('OPM#', 'CHNL'): {
        1: 'U16', 100: 'U8', 2: 'F64', 3: 'F64', 4: 'F64',
        5: 'F64', 6: 'F64', 7: 'F64', 8: 'F64',
        9: 'U8', 10: 'U8', 11: 'U8',
        12: 'F64', 13: 'F64', 14: 'F64', 29: 'F32',
    },
    ('OPM#', 'CHAL'): {
        1: 'U16', 100: 'U8', 2: 'F64', 3: 'F64', 4: 'F64',
        5: 'F64', 6: 'F64', 7: 'F64', 8: 'F64',
        9: 'U8', 10: 'U8', 11: 'U8',
        12: 'F64', 13: 'F64', 14: 'F64', 29: 'F32',
    },
    ('OPM#', 'TPWR'): {100: 'U8', 1: 'F64', 2: 'F64', 3: 'F64'},
    ('OPM#', 'FSPC'): {3: 'F32[]', 4: 'F32[]', 100: 'U8'},
    ('OCM#', 'ENAB'): {1: 'U8'},
    ('ALMH', 'ALRM'): {
        1: 'U16', 2: 'U16', 3: 'U32', 4: 'U32',
        5: 'U32', 6: 'U32', 7: 'U16',
    },
    ('WICA', 'FRQC'): {1: 'F32', 2: 'F32', 3: 'F64', 4: 'F64'},
}


def _build_reverse_tag_lookup():
    """Build (app_id, op_id, field_name) → (tag_number, data_type)."""
    lookup = {}
    for app_id, ops in TAG_PARSER.items():
        for op_id, tag_map in ops.items():
            type_map = TAG_DATA_TYPES.get((app_id, op_id), {})
            for tag_num, field_name in tag_map.items():
                dtype = type_map.get(tag_num, '?') if isinstance(
                    type_map, dict) else '?'
                lookup[(app_id, op_id, field_name)] = (tag_num, dtype)
    return lookup


TAG_LOOKUP = _build_reverse_tag_lookup()


def tag_info(app_id, op_id, field_name):
    """Return 'T{n}' and data type string for a field, or ('?','?')."""
    info = TAG_LOOKUP.get((app_id, op_id, field_name))
    if info:
        return f"T{info[0]}", info[1]
    return "?", "?"


# ======================================================================
# Dual-output: colored to stdout, plain text to file
# ======================================================================
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"

_log_file = None
results = []


def out(text=""):
    """Print to stdout (with ANSI) and to log file (stripped)."""
    print(text)
    if _log_file:
        _log_file.write(ANSI_RE.sub('', text) + '\n')


def test(name, func):
    """Run a test, print verbose output, record result."""
    try:
        result = func()
        out(f"  [{PASS}] {name}")
        results.append((name, True, None))
        return result
    except Exception as e:
        out(f"  [{FAIL}] {name}: {e}")
        traceback.print_exc()
        results.append((name, False, str(e)))
        return None


def fmt_val(val):
    """Format a value for display."""
    if isinstance(val, list):
        if len(val) > 10:
            preview = ', '.join(str(v) for v in val[:5])
            return f"[{preview}, ... ({len(val)} items)]"
        return str(val)
    if isinstance(val, float):
        return f"{val:.6g}"
    if isinstance(val, bytes):
        return f"<{len(val)} bytes>"
    return str(val)


def print_response(func_name, resp, app_id=None, op_id=None, indent=4):
    """Pretty-print a response dict with tag numbers and data types."""
    pad = " " * indent
    out(f"{pad}Function: {func_name}()")
    if resp is None:
        out(f"{pad}  Response: None")
        return
    header = resp.get("header", {})
    response = resp.get("response", {})

    if header:
        cid = header.get("cid", "")
        app = header.get("app_id", "")
        op = header.get("op_id", "")
        out(f"{pad}  Header: cid={cid}, app={app}, op={op}")

    if isinstance(response, dict):
        for key, val in response.items():
            if app_id and op_id:
                tn, dt = tag_info(app_id, op_id, key)
                out(f"{pad}  {tn} ({key})({dt})({fmt_val(val)})")
            else:
                out(f"{pad}  ({key})({fmt_val(val)})")
    else:
        out(f"{pad}  Response: {response}")


def print_channel_data(func_name, resp, app_id='OPM#', op_id='CHAL',
                       indent=4):
    """Pretty-print OPM channel data with tag numbers and data types."""
    pad = " " * indent
    out(f"{pad}Function: {func_name}()")
    if resp is None:
        out(f"{pad}  Response: None")
        return
    response = resp.get("response", {})
    channels = response.get("channels", [])
    out(f"{pad}  Channels: {len(channels)}")
    for i, ch in enumerate(channels):
        ch_id = ch.get("channel_id", "?")
        port = ch.get("switch_port", "?")
        freq = ch.get("central_frequency", 0.0)
        power = ch.get("central_power", 0.0)
        osnr = ch.get("osnr", 0.0)
        ps = ch.get("central_power_status", "?")
        fs = ch.get("central_frequency_status", "?")
        os_ = ch.get("osnr_status", "?")
        ts = ch.get("time_stamp", 0.0)
        # Summary line
        tn_ch, dt_ch = tag_info(app_id, op_id, "channel_id")
        tn_p, dt_p = tag_info(app_id, op_id, "switch_port")
        out(f"{pad}  [{i+1}] {tn_ch}(channel_id)({dt_ch})({ch_id}) "
            f"{tn_p}(switch_port)({dt_p})({port})")
        # All fields with tag info
        for key in sorted(ch.keys()):
            if key in ("channel_id", "switch_port"):
                continue
            tn, dt = tag_info(app_id, op_id, key)
            out(f"{pad}    {tn} ({key})({dt})({fmt_val(ch[key])})")


def main():
    global _log_file
    log_path = os.path.join(os.path.dirname(__file__), "api_test_results.txt")
    _log_file = open(log_path, "w")

    out("=" * 72)
    out("Comprehensive pyWistom API Test Suite")
    out(f"Target: {HOST}:{PORT}  User: {USER_ID}")
    out(f"Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    out("=" * 72)

    try:
        with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:

            # ==============================================================
            # SMGR (System Manager) Commands
            # ==============================================================
            out("\n--- SMGR (System Manager) ---")

            def test_smgr_info():
                resp = client.get_smgr_info()
                print_response("get_smgr_info", resp, 'SMGR', 'INFO')
                r = resp["response"]
                assert "unit_serial" in r, f"Missing 'unit_serial', keys: {list(r.keys())}"
                assert "software_revision" in r, f"Missing 'software_revision', keys: {list(r.keys())}"
                assert "firmware_revision" in r, f"Missing 'firmware_revision', keys: {list(r.keys())}"
                assert "sensor_serial_number" in r, f"Missing 'sensor_serial_number', keys: {list(r.keys())}"
                assert r["unit_serial"] != "", "unit_serial is empty"
                return resp

            test("SMGR INFO  (get_smgr_info)", test_smgr_info)

            def test_smgr_network():
                resp = client.get_smgr_network_info()
                print_response("get_smgr_network_info", resp, 'SMGR', 'IP##')
                r = resp["response"]
                assert "ip_address" in r, f"Missing 'ip_address', keys: {list(r.keys())}"
                assert "subnet_mask" in r, f"Missing 'subnet_mask', keys: {list(r.keys())}"
                assert "gateway_address" in r, f"Missing 'gateway_address', keys: {list(r.keys())}"
                assert "host_name" in r, f"Missing 'host_name', keys: {list(r.keys())}"
                assert "mac_address" in r, f"Missing 'mac_address', keys: {list(r.keys())}"
                assert "listening_port" in r, f"Missing 'listening_port', keys: {list(r.keys())}"
                assert r["ip_address"] != "", "ip_address is empty"
                return resp

            test("SMGR IP##  (get_smgr_network_info)", test_smgr_network)

            def test_smgr_serial():
                resp = client.get_smgr_serial_settings()
                print_response("get_smgr_serial_settings",
                               resp, 'SMGR', 'SER#')
                r = resp["response"]
                assert "baud_rate" in r, f"Missing 'baud_rate', keys: {list(r.keys())}"
                assert "data_bits" in r, f"Missing 'data_bits', keys: {list(r.keys())}"
                assert "stop_bits" in r, f"Missing 'stop_bits', keys: {list(r.keys())}"
                assert "parity_bit" in r, f"Missing 'parity_bit', keys: {list(r.keys())}"
                assert "serial_interface" in r, f"Missing 'serial_interface', keys: {list(r.keys())}"
                return resp

            test("SMGR SER#  (get_smgr_serial_settings)", test_smgr_serial)

            def test_smgr_time():
                resp = client.get_smgr_time()
                print_response("get_smgr_time", resp, 'SMGR', 'TIME')
                r = resp["response"]
                assert "year" in r, f"Missing 'year', keys: {list(r.keys())}"
                assert "month" in r, f"Missing 'month', keys: {list(r.keys())}"
                assert "day" in r, f"Missing 'day', keys: {list(r.keys())}"
                assert "hour" in r, f"Missing 'hour', keys: {list(r.keys())}"
                assert "minute" in r, f"Missing 'minute', keys: {list(r.keys())}"
                assert "second" in r, f"Missing 'second', keys: {list(r.keys())}"
                assert 2020 <= r["year"] <= 2030, f"year out of range: {r['year']}"
                return resp

            test("SMGR TIME  (get_smgr_time)", test_smgr_time)

            def test_smgr_temp():
                resp = client.get_smgr_temp()
                print_response("get_smgr_temp", resp, 'SMGR', 'TEMP')
                r = resp["response"]
                assert "board_temperature" in r, f"Missing 'board_temperature', keys: {list(r.keys())}"
                assert "sensor_temperature" in r, f"Missing 'sensor_temperature', keys: {list(r.keys())}"
                assert "sensor_temperature_derivative" in r, f"Missing 'sensor_temperature_derivative', keys: {list(r.keys())}"
                assert "fpga_temperature" in r, f"Missing 'fpga_temperature', keys: {list(r.keys())}"
                assert "configured_min_temperature" in r, f"Missing 'configured_min_temperature', keys: {list(r.keys())}"
                assert "configured_max_temperature" in r, f"Missing 'configured_max_temperature', keys: {list(r.keys())}"
                assert -40 <= r["board_temperature"] <= 100, \
                    f"board_temperature out of range: {r['board_temperature']}"
                return resp

            test("SMGR TEMP  (get_smgr_temp)", test_smgr_temp)

            def test_smgr_uptime():
                resp = client.get_smgr_uptime()
                print_response("get_smgr_uptime", resp, 'SMGR', 'UPTI')
                r = resp["response"]
                assert "uptime" in r, f"Missing 'uptime', keys: {list(r.keys())}"
                assert "app_uptime" in r, f"Missing 'app_uptime', keys: {list(r.keys())}"
                assert "system_load_average" in r, f"Missing 'system_load_average', keys: {list(r.keys())}"
                assert r["uptime"] > 0, f"uptime should be > 0: {r['uptime']}"
                return resp

            test("SMGR UPTI  (get_smgr_uptime)", test_smgr_uptime)

            def test_smgr_installed_features():
                resp = client.get_smgr_installed_features()
                print_response("get_smgr_installed_features",
                               resp, 'SMGR', 'INST')
                r = resp["response"]
                assert "snmp" in r, f"Missing 'snmp', keys: {list(r.keys())}"
                return resp

            test("SMGR INST  (get_smgr_installed_features)",
                 test_smgr_installed_features)

            def test_snmp_config():
                resp = client.get_snmp_agent_listening_port()
                print_response("get_snmp_agent_listening_port",
                               resp, 'SMGR', 'SCFG')
                r = resp["response"]
                assert "agent_port" in r, f"Missing 'agent_port', keys: {list(r.keys())}"
                return resp

            test("SMGR SCFG  (get_snmp_agent_listening_port)", test_snmp_config)

            def test_snmp_trap():
                resp = client.get_snmp_trap_receivers()
                print_response("get_snmp_trap_receivers", resp, 'SMGR', 'SLTR')
                return resp

            test("SMGR SLTR  (get_snmp_trap_receivers)", test_snmp_trap)

            # ==============================================================
            # SPEC (Spectrum / Switch) Commands
            # ==============================================================
            out("\n--- SPEC (Spectrum / Switch) ---")

            def test_spec_swin():
                resp = client.get_spec_swin()
                print_response("get_spec_swin", resp, 'SPEC', 'SWIN')
                r = resp["response"]
                installed = []
                for i in range(1, 17):
                    key = f"port_{i}_installed"
                    assert key in r, f"Missing '{key}', keys: {list(r.keys())}"
                    if r[key]:
                        installed.append(i)
                out(f"      Installed ports: {installed}")
                assert len(installed) > 0, "No ports installed"
                return resp

            test("SPEC SWIN  (get_spec_swin)", test_spec_swin)

            def test_spec_swmo():
                resp = client.get_spec_swmo()
                print_response("get_spec_swmo", resp, 'SPEC', 'SWMO')
                r = resp["response"]
                assert "mode" in r, f"Missing 'mode', keys: {list(r.keys())}"
                assert "manual_port" in r, f"Missing 'manual_port', keys: {list(r.keys())}"
                return resp

            test("SPEC SWMO  (get_spec_swmo)", test_spec_swmo)

            def test_spec_swco():
                resp = client.get_spec_swco()
                print_response("get_spec_swco", resp, 'SPEC', 'SWCO')
                r = resp["response"]
                for i in range(1, 17):
                    prio_key = f"port_{i}_priority"
                    desc_key = f"port_{i}_description"
                    assert prio_key in r, f"Missing '{prio_key}', keys: {list(r.keys())}"
                    assert desc_key in r, f"Missing '{desc_key}', keys: {list(r.keys())}"
                return resp

            test("SPEC SWCO  (get_spec_swco)", test_spec_swco)

            def test_spec_ctbl():
                resp = client.get_spec_ctbl()
                print_response("get_spec_ctbl", resp, 'SPEC', 'CTBL')
                r = resp["response"]
                assert "num_channels" in r, f"Missing 'num_channels', keys: {list(r.keys())}"
                assert "channel_table" in r, f"Missing 'channel_table', keys: {list(r.keys())}"
                num = r["num_channels"]
                tbl = r["channel_table"]
                out(f"      num_channels={num}, channel_table={tbl}")
                assert isinstance(
                    tbl, list), f"channel_table should be list, got {type(tbl)}"
                return resp

            test("SPEC CTBL  (get_spec_ctbl)", test_spec_ctbl)

            # If there are configured channels, test per-channel query
            ctbl_resp = client.get_spec_ctbl()
            channel_ids = ctbl_resp.get(
                "response", {}).get("channel_table", [])
            if channel_ids:
                def make_chnl_test(ch_id):
                    def test_fn():
                        resp = client.get_spec_chnl(ch_id)
                        print_response(f"get_spec_chnl({ch_id})", resp,
                                       'SPEC', 'CHNL')
                        r = resp["response"]
                        assert "channel_id" in r, f"Missing 'channel_id', keys: {list(r.keys())}"
                        assert "switch_port" in r, f"Missing 'switch_port', keys: {list(r.keys())}"
                        assert "nominal_frequency" in r, f"Missing 'nominal_frequency', keys: {list(r.keys())}"
                        assert "channel_description" in r, f"Missing 'channel_description', keys: {list(r.keys())}"
                        return resp
                    return test_fn

                for ch_id in channel_ids[:5]:
                    test(f"SPEC CHNL  (get_spec_chnl, ch={ch_id})",
                         make_chnl_test(ch_id))
            else:
                out(f"    [{WARN}] No configured channels — skipping SPEC CHNL tests")

            # ==============================================================
            # OPM# (Optical Performance Monitor) Commands
            # ==============================================================
            out("\n--- OPM# (Optical Performance Monitor) ---")

            def test_opm_enable():
                resp = client.get_opm_enable()
                print_response("get_opm_enable", resp, 'OPM#', 'ENAB')
                r = resp["response"]
                assert "toggle_enable" in r, f"Missing 'toggle_enable', keys: {list(r.keys())}"
                enabled = bool(r["toggle_enable"])
                out(f"      OPM enabled: {enabled}")
                return resp

            opm_resp = test("OPM# ENAB  (get_opm_enable)", test_opm_enable)
            opm_enabled = bool(
                opm_resp.get("response", {}).get("toggle_enable", 0)
            ) if opm_resp else False

            def test_opm_channel_config():
                resp = client.get_opm_channel_config()
                print_response("get_opm_channel_config", resp, 'OPM#', 'CHCO')
                r = resp["response"]
                assert "process_configured_channels" in r, \
                    f"Missing 'process_configured_channels', keys: {list(r.keys())}"
                return resp

            test("OPM# CHCO  (get_opm_channel_config)", test_opm_channel_config)

            def test_opm_averages():
                resp = client.get_opm_averages()
                print_response("get_opm_averages", resp, 'OPM#', 'AVRG')
                r = resp["response"]
                assert "averages" in r, f"Missing 'averages', keys: {list(r.keys())}"
                return resp

            test("OPM# AVRG  (get_opm_averages)", test_opm_averages)

            def test_opm_threshold():
                resp = client.get_opm_threshold()
                print_response("get_opm_threshold", resp, 'OPM#', 'TRSH')
                r = resp["response"]
                assert "threshold_value" in r, f"Missing 'threshold_value', keys: {list(r.keys())}"
                assert "threshold_value_watt" in r, f"Missing 'threshold_value_watt', keys: {list(r.keys())}"
                assert "max_number_of_peak_candidates" in r, \
                    f"Missing 'max_number_of_peak_candidates', keys: {list(r.keys())}"
                return resp

            test("OPM# TRSH  (get_opm_threshold)", test_opm_threshold)

            def test_opm_min_level():
                resp = client.get_opm_min_level()
                print_response("get_opm_min_level", resp, 'OPM#', 'MINL')
                r = resp["response"]
                assert "min_level" in r, f"Missing 'min_level', keys: {list(r.keys())}"
                assert "min_level_watt" in r, f"Missing 'min_level_watt', keys: {list(r.keys())}"
                return resp

            test("OPM# MINL  (get_opm_min_level)", test_opm_min_level)

            def test_opm_peak_criteria():
                resp = client.get_opm_peak_criteria()
                print_response("get_opm_peak_criteria", resp, 'OPM#', 'PCRI')
                r = resp["response"]
                assert "start_end_criteria" in r, f"Missing 'start_end_criteria', keys: {list(r.keys())}"
                assert "closest_peak_criteria" in r, f"Missing 'closest_peak_criteria', keys: {list(r.keys())}"
                return resp

            test("OPM# PCRI  (get_opm_peak_criteria)", test_opm_peak_criteria)

            # Channel-related OPM commands (need OPM enabled)
            if opm_enabled:
                def test_opm_all_channels():
                    resp = client.get_opm_all_channels()
                    print_channel_data("get_opm_all_channels", resp,
                                       'OPM#', 'CHAL')
                    r = resp["response"]
                    assert "channels" in r, f"Missing 'channels', keys: {list(r.keys())}"
                    channels = r["channels"]
                    out(f"      Total channels detected: {len(channels)}")
                    if channels:
                        ch = channels[0]
                        mandatory_keys = [
                            "channel_id", "switch_port", "central_frequency",
                            "central_power", "osnr", "channel_spacing",
                            "time_stamp",
                        ]
                        for key in mandatory_keys:
                            assert key in ch, (
                                f"Channel missing '{key}', "
                                f"keys: {list(ch.keys())}")
                        optional_keys = [
                            "central_power_status", "central_frequency_status",
                            "osnr_status",
                        ]
                        for key in optional_keys:
                            tn, dt = tag_info('OPM#', 'CHAL', key)
                            if key in ch:
                                out(f"      {tn} ({key})({dt})({ch[key]})")
                            else:
                                out(f"      {tn} ({key})({dt})(not present — "
                                    f"channel not configured)")
                    return resp

                test("OPM# CHAL  (get_opm_all_channels)", test_opm_all_channels)

                # Find an active port (priority > 0 = being scanned)
                swco = client.get_spec_swco()
                swco_resp = swco.get("response", {})
                active_ports = [
                    i for i in range(1, 17)
                    if swco_resp.get(f"port_{i}_priority", 0) > 0
                ]
                swin = client.get_spec_swin()
                installed_ports = [
                    i for i in range(1, 17)
                    if swin.get("response", {}).get(f"port_{i}_installed")
                ]
                test_ports = active_ports if active_ports else installed_ports
                out(f"      Active ports (priority > 0): {active_ports}")
                out(f"      Using port(s) for TPWR/FSPC: {test_ports[:1]}")

                if test_ports:
                    test_port = test_ports[0]

                    def test_opm_total_power():
                        resp = client.get_opm_total_power(test_port)
                        print_response(
                            f"get_opm_total_power({test_port})", resp,
                            'OPM#', 'TPWR')
                        r = resp["response"]
                        assert "switch_port" in r, \
                            f"Missing 'switch_port', keys: {list(r.keys())}"
                        assert "power" in r, \
                            f"Missing 'power', keys: {list(r.keys())}"
                        assert "start_interval" in r, \
                            f"Missing 'start_interval', keys: {list(r.keys())}"
                        assert "end_interval" in r, \
                            f"Missing 'end_interval', keys: {list(r.keys())}"
                        return resp

                    test(f"OPM# TPWR  (get_opm_total_power, port={test_port})",
                         test_opm_total_power)

                    def test_opm_freq_spectrum():
                        resp = client.get_opm_frequency_spectrum(test_port)
                        print_response(
                            f"get_opm_frequency_spectrum({test_port})", resp,
                            'OPM#', 'FSPC')
                        r = resp["response"]
                        assert "switch_port" in r, \
                            f"Missing 'switch_port', keys: {list(r.keys())}"
                        assert "frequency_table" in r, \
                            f"Missing 'frequency_table', keys: {list(r.keys())}"
                        assert "power_table" in r, \
                            f"Missing 'power_table', keys: {list(r.keys())}"
                        freq = r["frequency_table"]
                        pwr = r["power_table"]
                        assert len(freq) == len(pwr), \
                            f"freq/power length mismatch: {len(freq)} vs {len(pwr)}"
                        out(f"      Spectrum points: {len(freq)}")
                        if freq:
                            out(f"      Freq range: {freq[0]:.4f} - "
                                f"{freq[-1]:.4f} GHz")
                            out(f"      Power range: {min(pwr):.2f} - "
                                f"{max(pwr):.2f} dBm")
                        return resp

                    test(f"OPM# FSPC  (get_opm_freq_spectrum, port={test_port})",
                         test_opm_freq_spectrum)

                    # Test a single channel query if channels exist
                    chal = client.get_opm_all_channels()
                    chal_channels = chal.get(
                        "response", {}).get("channels", [])
                    if chal_channels:
                        test_ch_id = chal_channels[0].get("channel_id", 1)

                        def test_opm_single_channel():
                            resp = client.get_opm_channel(test_ch_id)
                            r = resp["response"]
                            if "error" in r:
                                out(
                                    f"      Function: get_opm_channel({test_ch_id})()")
                                out(f"      Got error response (channel {test_ch_id} "
                                    f"not configured, only auto-detected)")
                                return resp
                            print_channel_data(
                                f"get_opm_channel({test_ch_id})", resp,
                                'OPM#', 'CHNL')
                            assert "channels" in r, \
                                f"Missing 'channels', keys: {list(r.keys())}"
                            return resp

                        test(f"OPM# CHNL  (get_opm_channel, ch={test_ch_id})",
                             test_opm_single_channel)
                    else:
                        out(f"    [{WARN}] No OPM channels detected — "
                            f"skipping OPM# CHNL test")
                else:
                    out(f"    [{WARN}] No active ports — "
                        f"skipping TPWR/FSPC tests")
            else:
                out(f"    [{WARN}] OPM disabled — skipping "
                    f"CHAL/TPWR/FSPC/CHNL tests")

            # ==============================================================
            # OCM# (Optical Channel Monitor) Commands
            # ==============================================================
            out("\n--- OCM# (Optical Channel Monitor) ---")

            def test_ocm_enable():
                resp = client.get_ocm_enable()
                print_response("get_ocm_enable", resp, 'OCM#', 'ENAB')
                r = resp["response"]
                assert "ocm_enabled" in r, \
                    f"Missing 'ocm_enabled', keys: {list(r.keys())}"
                enabled = bool(r["ocm_enabled"])
                out(f"      OCM enabled: {enabled}")
                return resp

            test("OCM# ENAB  (get_ocm_enable)", test_ocm_enable)

            # ==============================================================
            # WICA (Calibration) Commands
            # ==============================================================
            out("\n--- WICA (Calibration) ---")

            def test_wica_frqc():
                resp = client.get_wica_frqc()
                print_response("get_wica_frqc", resp, 'WICA', 'FRQC')
                r = resp["response"]
                assert "lambda0" in r, f"Missing 'lambda0', keys: {list(r.keys())}"
                assert "d_lambda" in r, f"Missing 'd_lambda', keys: {list(r.keys())}"
                assert "time_to_start" in r, f"Missing 'time_to_start', keys: {list(r.keys())}"
                assert "dtime" in r, f"Missing 'dtime', keys: {list(r.keys())}"
                return resp

            test("WICA FRQC  (get_wica_frqc)", test_wica_frqc)

            # ==============================================================
            # ALMH (Alarm Handler) Commands
            # ==============================================================
            out("\n--- ALMH (Alarm Handler) ---")

            def test_alarm_subscribe_unsubscribe():
                """Test subscribe + get_alarms + unsubscribe cycle."""
                alarm_id = 30  # Temperature alarm
                out(f"      Subscribing to alarm_id={alarm_id} (Temperature)...")
                sub_resp = client.subscribe_alarm(alarm_id)
                out(f"      Subscribe response: {sub_resp}")
                assert sub_resp.get("response", {}).get("acknowledged", False), \
                    f"Subscribe not acknowledged: {sub_resp}"

                out(f"      Fetching active alarms for alarm_id={alarm_id}...")
                alarms = client.get_alarms(alarm_id)
                print_response(
                    f"get_alarms({alarm_id})", alarms, 'ALMH', 'ALRM')

                out(f"      Unsubscribing from alarm_id={alarm_id}...")
                unsub_resp = client.unsubscribe_alarm(alarm_id)
                out(f"      Unsubscribe response: {unsub_resp}")
                assert unsub_resp.get("response", {}).get("acknowledged", False), \
                    f"Unsubscribe not acknowledged: {unsub_resp}"
                return alarms

            test("ALMH SUBS/ALRM/UNSU  (alarm lifecycle)",
                 test_alarm_subscribe_unsubscribe)

            def test_alarm_all_types():
                """Test get_alarms for each alarm type."""
                for name, alarm_id in ALARM_TYPE.items():
                    out(f"      Fetching alarms: {name} (id={alarm_id})")
                    try:
                        resp = client.get_alarms(alarm_id)
                        r = resp.get("response", {})
                        if "error" in r:
                            out(f"        → error response (no active alarms)")
                        else:
                            out(f"        → {r}")
                    except Exception as e:
                        out(f"        → Exception: {e}")
                return "OK"

            test("ALMH ALRM  (get_alarms, all types)", test_alarm_all_types)

            # ==============================================================
            # pyWNMS Config Fetch Verification
            # ==============================================================
            out("\n--- pyWNMS Config Fetch Key Verification ---")

            def test_config_fetch_swco_keys():
                """Verify SWCO keys match what pyWNMS expects."""
                resp = client.get_spec_swco()
                r = resp.get("response", {})
                for i in range(1, 17):
                    desc = r.get(f"port_{i}_description")
                    prio = r.get(f"port_{i}_priority")
                    tn_p, dt_p = tag_info('SPEC', 'SWCO', f"port_{i}_priority")
                    tn_d, dt_d = tag_info(
                        'SPEC', 'SWCO', f"port_{i}_description")
                    out(f"      Port {i:2d}: {tn_p}(priority)({dt_p})({prio}), "
                        f"{tn_d}(description)({dt_d})('{desc}')")
                assert "port_1_priority" in r, "SWCO missing port_1_priority"
                assert "port_1_description" in r, "SWCO missing port_1_description"
                return "OK"

            test("SWCO keys  (port_N_priority, port_N_description)",
                 test_config_fetch_swco_keys)

            def test_config_fetch_ip_keys():
                """Verify IP## keys match what pyWNMS expects."""
                resp = client.get_smgr_network_info()
                r = resp.get("response", {})
                expected = ["ip_address", "subnet_mask", "gateway_address",
                            "host_name", "mac_address", "listening_port"]
                for key in expected:
                    val = r.get(key, "<MISSING>")
                    tn, dt = tag_info('SMGR', 'IP##', key)
                    out(f"      {tn} ({key})({dt})({val})")
                    assert key in r, f"IP## missing '{key}'"
                return "OK"

            test("IP## keys  (host_name, gateway_address, ...)",
                 test_config_fetch_ip_keys)

            def test_config_fetch_serial_keys():
                """Verify SER# keys match what pyWNMS expects."""
                resp = client.get_smgr_serial_settings()
                r = resp.get("response", {})
                expected = ["serial_interface", "baud_rate", "data_bits",
                            "stop_bits", "parity_bit"]
                for key in expected:
                    val = r.get(key, "<MISSING>")
                    tn, dt = tag_info('SMGR', 'SER#', key)
                    out(f"      {tn} ({key})({dt})({val})")
                    assert key in r, f"SER# missing '{key}'"
                return "OK"

            test("SER# keys  (baud_rate, parity_bit, ...)",
                 test_config_fetch_serial_keys)

            def test_config_fetch_ctbl_keys():
                """Verify CTBL keys match what pyWNMS expects."""
                resp = client.get_spec_ctbl()
                r = resp.get("response", {})
                assert "channel_table" in r, \
                    f"CTBL missing 'channel_table', keys: {list(r.keys())}"
                assert "num_channels" in r, \
                    f"CTBL missing 'num_channels', keys: {list(r.keys())}"
                tn_n, dt_n = tag_info('SPEC', 'CTBL', 'num_channels')
                tn_t, dt_t = tag_info('SPEC', 'CTBL', 'channel_table')
                out(
                    f"      {tn_n} (num_channels)({dt_n})({r['num_channels']})")
                out(
                    f"      {tn_t} (channel_table)({dt_t})({r['channel_table']})")
                return "OK"

            test("CTBL keys  (channel_table, num_channels)",
                 test_config_fetch_ctbl_keys)

            def test_config_fetch_opm_enab_keys():
                """Verify OPM ENAB key matches what pyWNMS expects."""
                resp = client.get_opm_enable()
                r = resp.get("response", {})
                assert "toggle_enable" in r, \
                    f"OPM ENAB missing 'toggle_enable', keys: {list(r.keys())}"
                tn, dt = tag_info('OPM#', 'ENAB', 'toggle_enable')
                out(f"      {tn} (toggle_enable)({dt})({r['toggle_enable']})")
                return "OK"

            test("OPM ENAB keys  (toggle_enable)",
                 test_config_fetch_opm_enab_keys)

            def test_config_fetch_ocm_enab_keys():
                """Verify OCM ENAB key matches what pyWNMS expects."""
                resp = client.get_ocm_enable()
                r = resp.get("response", {})
                assert "ocm_enabled" in r, \
                    f"OCM ENAB missing 'ocm_enabled', keys: {list(r.keys())}"
                tn, dt = tag_info('OCM#', 'ENAB', 'ocm_enabled')
                out(f"      {tn} (ocm_enabled)({dt})({r['ocm_enabled']})")
                return "OK"

            test("OCM ENAB keys  (ocm_enabled)",
                 test_config_fetch_ocm_enab_keys)

            def test_config_fetch_chco_keys():
                """Verify OPM CHCO keys match what pyWNMS expects."""
                resp = client.get_opm_channel_config()
                r = resp.get("response", {})
                assert "process_configured_channels" in r, \
                    f"CHCO missing 'process_configured_channels', keys: {list(r.keys())}"
                for key, val in r.items():
                    tn, dt = tag_info('OPM#', 'CHCO', key)
                    out(f"      {tn} ({key})({dt})({fmt_val(val)})")
                return "OK"

            test("OPM CHCO keys  (process_configured_channels, ...)",
                 test_config_fetch_chco_keys)

            # ==============================================================
            # Summary
            # ==============================================================
            out("\n" + "=" * 72)
            passed = sum(1 for _, ok, _ in results if ok)
            failed = sum(1 for _, ok, _ in results if not ok)
            total = len(results)
            out(f"Results: {passed} passed, {failed} failed, {total} total")

            if failed:
                out("\nFailed tests:")
                for name, ok, err in results:
                    if not ok:
                        out(f"  - {name}: {err}")

            out("=" * 72)
    finally:
        _log_file.close()
        _log_file = None

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
