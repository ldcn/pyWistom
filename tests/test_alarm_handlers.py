#!/usr/bin/env python3
"""Live alarm handler tests for pyWistom.

Tests alarm subscription, unsubscription, polling, threaded alarm
reception, and the parse_alarm_message static method.

Run: python tests/test_alarm_handlers.py

Requires live device configured in settings.yaml.
"""

import os
import sys
import struct
import threading
import time
import traceback

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from pyWistom import HOST, PORT, USER_ID, PASSWORD, WistomClient
from wistomconstants import ALARM_TYPE, ALARM_ID, ALARM_ELEMENT_SIZE

# ── ANSI helpers ─────────────────────────────────────────────────────────

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"
CYAN = "\033[96m"
YELLOW = "\033[93m"

results = []


def test(name, func, *args, **kwargs):
    """Run a single test, record result."""
    try:
        result = func(*args, **kwargs)
        print(f"  [{PASS}] {name}")
        results.append((name, True))
        return result
    except Exception as e:
        print(f"  [{FAIL}] {name}: {e}")
        traceback.print_exc()
        results.append((name, False))
        return None


# ── Tests ────────────────────────────────────────────────────────────────

def test_subscribe_single(client):
    """Subscribe to Temperature alarm (30), verify SETACK."""
    resp = client.subscribe_alarm(30)
    print(f"        response: {resp}")
    assert "SET Acknowledged" in str(resp), f"Expected SETACK, got {resp}"
    assert 30 in client._alarm_subscriptions, "Token not stored"
    return resp


def test_unsubscribe_single(client):
    """Unsubscribe from Temperature alarm (30), verify SETACK."""
    resp = client.unsubscribe_alarm(30)
    print(f"        response: {resp}")
    assert "SET Acknowledged" in str(resp), f"Expected SETACK, got {resp}"
    assert 30 not in client._alarm_subscriptions, "Token not removed"
    return resp


def test_unsubscribe_not_subscribed(client):
    """Unsubscribe from alarm we never subscribed to — should return error."""
    resp = client.unsubscribe_alarm(999)
    print(f"        response: {resp}")
    assert "error" in str(resp).lower() or "Not subscribed" in str(resp), \
        f"Expected error for unsubscribed alarm, got {resp}"
    return resp


def test_subscribe_all(client):
    """Subscribe to all 7 alarm types."""
    results_map = client.subscribe_all_alarms()
    print(f"        subscribed to {len(results_map)} alarm types")
    for alarm_id, resp in results_map.items():
        name = ALARM_TYPE.get(alarm_id, f"Unknown({alarm_id})")
        ack = "SET Acknowledged" in str(resp)
        status = "ACK" if ack else "NACK"
        print(f"          alarm {alarm_id:>3} ({name:>20}): {status}")
    assert len(results_map) == len(ALARM_TYPE), \
        f"Expected {len(ALARM_TYPE)} subscriptions, got {len(results_map)}"
    assert len(client._alarm_subscriptions) == len(ALARM_TYPE), \
        f"Expected {len(ALARM_TYPE)} stored tokens"
    return results_map


def test_unsubscribe_all(client):
    """Unsubscribe from all alarm types."""
    before = len(client._alarm_subscriptions)
    client.unsubscribe_all_alarms()
    after = len(client._alarm_subscriptions)
    print(f"        before: {before} subscriptions, after: {after}")
    assert after == 0, f"Expected 0 subscriptions after unsubscribe_all, got {after}"


def test_get_alarms_all_types(client):
    """Poll get_alarms() for every alarm type."""
    for alarm_id, name in sorted(ALARM_TYPE.items()):
        resp = client.get_alarms(alarm_id)
        if "error" in str(resp).lower():
            print(f"        alarm {alarm_id:>3} ({name:>20}): ERROR - {resp}")
        else:
            alarms = resp.get("response", resp).get("alarms", [])
            print(f"        alarm {alarm_id:>3} ({name:>20}): "
                  f"{len(alarms)} active alarm(s)")
            for a in alarms[:3]:  # Show first 3
                print(f"            sub_id={a.get('alarm_sub_id')}, "
                      f"status=0x{a.get('status', 0):08X}, "
                      f"type={a.get('alarm_type')}")


def test_subscribe_idempotent(client):
    """Subscribing to same alarm twice should both return SETACK."""
    r1 = client.subscribe_alarm(30)
    r2 = client.subscribe_alarm(30)
    print(f"        first:  {r1}")
    print(f"        second: {r2}")
    # Both should succeed (device allows re-subscribe with new token)
    assert "SET Acknowledged" in str(r1)
    assert "SET Acknowledged" in str(r2)
    # Clean up
    client.unsubscribe_alarm(30)


def test_parse_alarm_message_no_time():
    """Test parse_alarm_message with a synthetic NO_TIME alarm."""
    # Build a fake alarm message: cmd_id(2) + token(2) + data_size(4) + elements
    cmd_id = ALARM_ID["NO_TIME"]  # b'\x01\x05'
    token = struct.pack('>H', 42)
    # One element: alarm_id=20(OPM), sub_id=5, status=0x00400110
    element = struct.pack('>HHI', 20, 5, 0x00400110)
    data_size = struct.pack('>I', len(element))
    raw = cmd_id + token + data_size + element

    parsed = WistomClient.parse_alarm_message(raw)
    print(f"        parsed: {parsed}")
    assert parsed["cmd_id"] == cmd_id.hex()
    assert parsed["token"] == 42
    assert len(parsed["elements"]) == 1
    elem = parsed["elements"][0]
    assert elem["alarm_id"] == 20
    assert elem["alarm_sub_id"] == 5
    assert elem["status"] == 0x00400110
    assert elem["alarm_type"] == "OPM"
    assert "timestamp" not in elem


def test_parse_alarm_message_epoch():
    """Test parse_alarm_message with a synthetic EPOCH alarm."""
    cmd_id = ALARM_ID["EPOCH"]  # b'\x21\x05'
    token = struct.pack('>H', 100)
    # Two elements: Temperature alarm
    elem1 = struct.pack('>HHII', 30, 0, 0x01, 1709700000)
    elem2 = struct.pack('>HHII', 30, 1, 0x02, 1709700001)
    data_size = struct.pack('>I', len(elem1) + len(elem2))
    raw = cmd_id + token + data_size + elem1 + elem2

    parsed = WistomClient.parse_alarm_message(raw)
    print(f"        parsed: {parsed}")
    assert len(parsed["elements"]) == 2
    assert parsed["elements"][0]["timestamp"] == 1709700000
    assert parsed["elements"][1]["alarm_sub_id"] == 1
    assert parsed["elements"][1]["alarm_type"] == "Temperature"


def test_parse_alarm_message_epoch_ms():
    """Test parse_alarm_message with EPOCH_MS (14-byte elements)."""
    cmd_id = ALARM_ID["EPOCH_MS"]  # b'\x41\x05'
    token = struct.pack('>H', 200)
    # One element with extended_info
    element = struct.pack('>HHIIH', 91, 2, 0x01, 1709700000, 500)
    data_size = struct.pack('>I', len(element))
    raw = cmd_id + token + data_size + element

    parsed = WistomClient.parse_alarm_message(raw)
    print(f"        parsed: {parsed}")
    assert len(parsed["elements"]) == 1
    elem = parsed["elements"][0]
    assert elem["alarm_id"] == 91
    assert elem["alarm_type"] == "ModuleStatus"
    assert elem["timestamp"] == 1709700000
    assert elem["extended_info"] == 500


def test_parse_alarm_message_multi_element():
    """Test parse_alarm_message with multiple elements in one message."""
    cmd_id = ALARM_ID["UPTIME_MS"]  # b'\x31\x05', 12-byte elements
    token = struct.pack('>H', 0)
    elements = b''
    for i in range(5):
        elements += struct.pack('>HHII', 20, i, 0x40 << 16, 1000 * i)
    data_size = struct.pack('>I', len(elements))
    raw = cmd_id + token + data_size + elements

    parsed = WistomClient.parse_alarm_message(raw)
    print(f"        parsed {len(parsed['elements'])} elements")
    assert len(parsed["elements"]) == 5
    for i, elem in enumerate(parsed["elements"]):
        assert elem["alarm_sub_id"] == i
        assert elem["alarm_type"] == "OPM"


def test_parse_alarm_unknown_type():
    """parse_alarm_message with unknown alarm_id → 'Unknown(N)' type."""
    cmd_id = ALARM_ID["NO_TIME"]
    token = struct.pack('>H', 0)
    element = struct.pack('>HHI', 999, 0, 0x01)
    data_size = struct.pack('>I', len(element))
    raw = cmd_id + token + data_size + element

    parsed = WistomClient.parse_alarm_message(raw)
    print(f"        alarm_type: {parsed['elements'][0]['alarm_type']}")
    assert "Unknown" in parsed["elements"][0]["alarm_type"]


def test_threaded_alarm_listener(client):
    """Subscribe in threaded mode and listen for alarms for a few seconds."""
    received = []
    event = threading.Event()

    def on_alarm(raw_msg):
        parsed = WistomClient.parse_alarm_message(raw_msg)
        received.append(parsed)
        event.set()

    client.connection.add_alarm_listener(on_alarm)
    try:
        # Subscribe to all alarms
        client.subscribe_all_alarms()
        print(f"        subscribed to {len(client._alarm_subscriptions)} types, "
              f"waiting up to 10s for alarms...")

        # Wait for an alarm or timeout
        got_alarm = event.wait(timeout=10.0)
        if got_alarm:
            print(f"        received {len(received)} alarm message(s):")
            for msg in received[:5]:
                for elem in msg["elements"]:
                    print(f"            type={elem['alarm_type']}, "
                          f"sub_id={elem['alarm_sub_id']}, "
                          f"status=0x{elem['status']:08X}")
        else:
            print(f"        no alarms received in 10s (device may be quiet)")
            # This is OK — no alarms may be active

    finally:
        client.unsubscribe_all_alarms()
        client.connection.remove_alarm_listener(on_alarm)

    print(f"        total received: {len(received)}")


def test_alarm_listener_add_remove(client):
    """Test add/remove alarm listener registration."""
    calls = []

    def listener(msg):
        calls.append(msg)

    client.connection.add_alarm_listener(listener)
    # Adding same listener again should not duplicate
    client.connection.add_alarm_listener(listener)
    with client.connection._alarm_lock:
        count = client.connection._alarm_listeners.count(listener)
    print(f"        listener registered {count} time(s)")
    assert count == 1, f"Expected 1 registration, got {count}"

    client.connection.remove_alarm_listener(listener)
    with client.connection._alarm_lock:
        count = client.connection._alarm_listeners.count(listener)
    assert count == 0, "Listener not removed"

    # Remove again should not raise
    client.connection.remove_alarm_listener(listener)
    print(f"        add/remove/double-remove all OK")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}═══ Alarm Handler Tests ═══{RESET}")
    print(f"  Device: {HOST}:{PORT}\n")

    # ── Offline tests (no device needed) ─────────────────────────────
    print(f"{CYAN}── parse_alarm_message (synthetic) ──{RESET}")
    test("parse NO_TIME alarm", test_parse_alarm_message_no_time)
    test("parse EPOCH alarm", test_parse_alarm_message_epoch)
    test("parse EPOCH_MS alarm", test_parse_alarm_message_epoch_ms)
    test("parse multi-element alarm", test_parse_alarm_message_multi_element)
    test("parse unknown alarm type", test_parse_alarm_unknown_type)

    # ── Live tests (require device) ──────────────────────────────────
    # Use threaded mode throughout — alarm subscriptions trigger async
    # push messages that corrupt synchronous recv.
    print(f"\n{CYAN}── live alarm subscribe/unsubscribe ──{RESET}")
    with WistomClient(HOST, PORT, USER_ID, PASSWORD, use_ssh=False,
                      threaded=True) as client:
        client.login()
        print(f"  Logged in (threaded mode).\n")

        test("subscribe single (Temperature)", test_subscribe_single, client)
        test("unsubscribe single (Temperature)", test_unsubscribe_single, client)
        test("unsubscribe not-subscribed", test_unsubscribe_not_subscribed, client)
        test("subscribe idempotent", test_subscribe_idempotent, client)
        test("subscribe all alarm types", test_subscribe_all, client)
        test("unsubscribe all alarm types", test_unsubscribe_all, client)

        print(f"\n{CYAN}── get_alarms (poll) ──{RESET}")
        test("get_alarms all types", test_get_alarms_all_types, client)

        print(f"\n{CYAN}── threaded alarm listener ──{RESET}")
        test("alarm listener add/remove", test_alarm_listener_add_remove, client)
        test("threaded alarm reception", test_threaded_alarm_listener, client)

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{BOLD}═══ Summary ═══{RESET}")
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    total = len(results)
    print(f"  {passed}/{total} passed, {failed} failed")
    for name, ok in results:
        status = PASS if ok else FAIL
        print(f"    [{status}] {name}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
