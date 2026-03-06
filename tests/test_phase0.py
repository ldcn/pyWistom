#!/usr/bin/env python3
"""Phase 0 verification: test all new pyWistom commands against a live device.

Tests the 22 WNMS-required commands:
  - SMGR: INFO, IP##, SER#, TEMP, UPTI, INST
  - SPEC: SWIN, SWMO, SWCO, CTBL, CHNL (per channel from CTBL)
  - OPM#: ENAB, CHCO, CHAL, TPWR, FSPC
  - OCM#: ENAB
  - ALMH: ALRM (GET), SUBS/UNSU (SET)
"""

from pyWistom import WistomClient, HOST, PORT, USER_ID, PASSWORD
from wistomconstants import COMMAND_ID, ALARM_TYPE
import sys
import os
import json
import traceback

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


def pp(obj, indent=4):
    """Pretty-print a dict, truncating large lists."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and len(v) > 5:
                print(
                    f"{' ' * indent}{k}: [{v[0]}, {v[1]}, ... ({len(v)} items)]")
            elif isinstance(v, dict):
                print(f"{' ' * indent}{k}:")
                pp(v, indent + 4)
            else:
                print(f"{' ' * indent}{k}: {v}")
    else:
        print(f"{' ' * indent}{obj}")


def main():
    print(f"\n{'='*60}")
    print(f"Phase 0 Verification — pyWistom against {HOST}:{PORT}")
    print(f"{'='*60}\n")

    print(f"Connecting to {HOST}:{PORT} as {USER_ID}...")
    client = WistomClient(HOST, PORT, USER_ID, PASSWORD, use_ssh=False)

    try:
        client.connection.connect()
        print("  Connected.\n")

        # Login
        print("--- LOGIN ---")
        login_result = test("LGIN API2 (login)", lambda: client.login())
        if login_result is None:
            print("Login failed, aborting.")
            return 1
        print()

        # ===============================================================
        # SMGR commands (existing + new INST)
        # ===============================================================
        print("--- SMGR (System Manager) ---")

        info = test("SMGR INFO", lambda: client.get_smgr_info())
        if info:
            pp(info.get("response", {}))

        net = test("SMGR IP##", lambda: client.get_smgr_network_info())
        if net:
            pp(net.get("response", {}))

        ser = test("SMGR SER#", lambda: client.get_smgr_serial_settings())
        if ser:
            pp(ser.get("response", {}))

        temp = test("SMGR TEMP", lambda: client.get_smgr_temp())
        if temp:
            pp(temp.get("response", {}))

        upti = test("SMGR UPTI", lambda: client.get_smgr_uptime())
        if upti:
            pp(upti.get("response", {}))

        inst = test("SMGR INST (new)",
                    lambda: client.get_smgr_installed_features())
        if inst:
            pp(inst.get("response", {}))

        print()

        # ===============================================================
        # SPEC commands (all new)
        # ===============================================================
        print("--- SPEC (Spectrum Parameters) ---")

        swin = test("SPEC SWIN (new)", lambda: client.get_spec_swin())
        if swin:
            resp = swin.get("response", {})
            installed = [k for k, v in resp.items() if v is True]
            print(f"    Installed ports: {installed}")

        swmo = test("SPEC SWMO (new)", lambda: client.get_spec_swmo())
        if swmo:
            pp(swmo.get("response", {}))

        swco = test("SPEC SWCO (new)", lambda: client.get_spec_swco())
        if swco:
            resp = swco.get("response", {})
            # Show first few entries
            shown = dict(list(resp.items())[:6])
            pp(shown)
            if len(resp) > 6:
                print(f"    ... ({len(resp)} total entries)")

        ctbl = test("SPEC CTBL (new)", lambda: client.get_spec_ctbl())
        channel_ids = []
        if ctbl:
            resp = ctbl.get("response", {})
            pp(resp)
            channel_ids = resp.get("channel_table", [])

        # Test SPEC CHNL for first channel (if channels exist)
        if channel_ids:
            ch_id = channel_ids[0]
            chnl = test(f"SPEC CHNL ch={ch_id} (new)",
                        lambda: client.get_spec_chnl(ch_id))
            if chnl:
                resp = chnl.get("response", {})
                # Show key fields
                for k in ["channel_id", "switch_port", "nominal_frequency",
                          "channel_description"]:
                    if k in resp:
                        print(f"    {k}: {resp[k]}")
        else:
            print(f"  [{SKIP}] SPEC CHNL — no channels in table")

        print()

        # ===============================================================
        # OPM# commands (all new)
        # ===============================================================
        print("--- OPM# (Optical Performance Monitor) ---")

        opm_enab = test("OPM# ENAB (new)", lambda: client.get_opm_enable())
        if opm_enab:
            pp(opm_enab.get("response", {}))

        opm_chco = test("OPM# CHCO (new)",
                        lambda: client.get_opm_channel_config())
        if opm_chco:
            pp(opm_chco.get("response", {}))

        opm_chal = test("OPM# CHAL (new)",
                        lambda: client.get_opm_all_channels())
        if opm_chal:
            resp = opm_chal.get("response", {})
            channels = resp.get("channels", [])
            print(f"    Channel count: {len(channels)}")
            if channels:
                print(f"    First channel:")
                pp(channels[0], indent=8)

        # TPWR and FSPC need a port ID — use first installed port
        test_port = None
        if swin:
            resp = swin.get("response", {})
            for k, v in resp.items():
                if v is True:
                    # Extract port number from "port_N_installed"
                    try:
                        test_port = int(k.split("_")[1])
                        break
                    except (IndexError, ValueError):
                        pass

        if test_port:
            tpwr = test(f"OPM# TPWR port={test_port} (new)",
                        lambda: client.get_opm_total_power(test_port))
            if tpwr:
                pp(tpwr.get("response", {}))

            fspc = test(f"OPM# FSPC port={test_port} (new)",
                        lambda: client.get_opm_frequency_spectrum(test_port))
            if fspc:
                resp = fspc.get("response", {})
                freq = resp.get("frequency_table", [])
                power = resp.get("power_table", [])
                print(f"    Frequency points: {len(freq)}")
                print(f"    Power points: {len(power)}")
                if freq:
                    print(f"    Freq range: {freq[0]:.2f} - {freq[-1]:.2f}")
        else:
            print(f"  [{SKIP}] OPM# TPWR/FSPC — no installed ports found")

        print()

        # ===============================================================
        # OCM# commands (new)
        # ===============================================================
        print("--- OCM# (Optical Channel Monitor) ---")

        ocm_enab = test("OCM# ENAB (new)", lambda: client.get_ocm_enable())
        if ocm_enab:
            pp(ocm_enab.get("response", {}))

        print()

        # ===============================================================
        # ALMH commands (all new)
        # ===============================================================
        print("--- ALMH (Alarm Handler) ---")

        # Test GET ALRM for each alarm type
        for alarm_id, alarm_name in ALARM_TYPE.items():
            alrm = test(f"ALMH ALRM id={alarm_id} ({alarm_name}) (new)",
                        lambda aid=alarm_id: client.get_alarms(aid))
            if alrm:
                resp = alrm.get("response", {})
                alarms = resp.get("alarms", [])
                print(f"    Active alarms: {len(alarms)}")
                if alarms:
                    pp(alarms[0], indent=8)

        # Test SUBS/UNSU for one alarm type (OPM=20)
        subs = test("ALMH SUBS alarm=20 (OPM) (new)",
                    lambda: client.subscribe_alarm(20))
        if subs:
            pp(subs.get("header", {}))

        unsub = test("ALMH UNSU alarm=20 (OPM) (new)",
                     lambda: client.unsubscribe_alarm(20))
        if unsub:
            pp(unsub.get("header", {}))

        print()

    except ConnectionRefusedError:
        print(f"\n  [{FAIL}] Connection refused to {HOST}:{PORT}")
        return 1
    except Exception as e:
        print(f"\n  [{FAIL}] Unexpected error: {e}")
        traceback.print_exc()
        return 1
    finally:
        client.connection.disconnect()

    # ===============================================================
    # Summary
    # ===============================================================
    print(f"{'='*60}")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    if failed:
        print(f"\nFailed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
    print(f"{'='*60}\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
