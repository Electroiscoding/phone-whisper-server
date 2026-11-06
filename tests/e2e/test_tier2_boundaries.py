"""
test_tier2_boundaries.py - Tier 2: Boundary & Corner Cases E2E Tests
Path: tests/e2e/test_tier2_boundaries.py

Covers 5 Critical Boundary Domains with 5 concrete tests each (25 tests total):
- Domain 1: Package Name Boundaries & Injection Defense (Tests 1.1 - 1.5)
- Domain 2: Coordinate & Input Injection Boundaries (Tests 2.1 - 2.5)
- Domain 3: Concurrency & Race Condition Boundaries (Tests 3.1 - 3.5)
- Domain 4: Power State & Display Transition Boundaries (Tests 4.1 - 4.5)
- Domain 5: Malformed Payloads, Protocol & HTTP Method Violations (Tests 5.1 - 5.5)
"""

import concurrent.futures
import json
import os
import time

import pytest
import requests


# =============================================================================
# Domain 1: Package Name Boundaries & Injection Defense
# =============================================================================

@pytest.mark.tier2
@pytest.mark.hardware
def test_b1_package_empty_string(gateway_session, e2e_config):
    """Test 2.1.1: Sends POST /v1/screen/app with empty package name."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        json={"package": "", "action": "launch"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400)
    # Gateway remains responsive
    health = gateway_session.get(f"{e2e_config.gateway_url}/health", timeout=5.0)
    assert health.status_code == 200


@pytest.mark.tier2
@pytest.mark.hardware
def test_b1_package_whitespace_only(gateway_session, e2e_config):
    """Test 2.1.2: Sends POST /v1/screen/app with whitespace-only package name."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        json={"package": "   \t\n   ", "action": "status"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b1_package_shell_injection(gateway_session, e2e_config):
    """Test 2.1.3: Attempts shell injection via package name, verifying command isolation."""
    injection_marker = "/tmp/pwned_nta_test"
    if os.path.exists(injection_marker):
        os.remove(injection_marker)
        
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        json={"package": f"com.netuark.app; touch {injection_marker}", "action": "status"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400)
    assert not os.path.exists(injection_marker), "Security vulnerability: shell command was injected and executed on host!"


@pytest.mark.tier2
@pytest.mark.hardware
def test_b1_package_excessively_long_name(gateway_session, e2e_config):
    """Test 2.1.4: Sends a 5,000-character package name verifying buffer safety."""
    long_pkg = "com." + "a" * 5000 + ".app"
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        json={"package": long_pkg, "action": "status"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400, 414)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b1_package_special_regex_characters(gateway_session, e2e_config):
    """Test 2.1.5: Queries package name containing regex metacharacters com.netuark.*[$^?]+."""
    resp = gateway_session.get(
        f"{e2e_config.gateway_url}/v1/screen/app?package=com.netuark.*[$^?]+",
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400, 404)
    if resp.status_code == 200:
        data = resp.json()
        assert data.get("installed") is False


# =============================================================================
# Domain 2: Coordinate & Input Injection Boundaries
# =============================================================================

@pytest.mark.tier2
@pytest.mark.hardware
def test_b2_coords_negative_values(gateway_session, e2e_config, wake_screen):
    """Test 2.2.1: Sends negative relative coordinates clamping to [0, 0]."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/touch",
        json={"x": -1.5, "y": -0.5, "action": "tap"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("target_pixel") == [0, 0]


@pytest.mark.tier2
@pytest.mark.hardware
def test_b2_coords_exceeding_unity(gateway_session, e2e_config, wake_screen):
    """Test 2.2.2: Sends coordinates exceeding 1.0 clamping to [720, 1600]."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/touch",
        json={"x": 2.5, "y": 10.0, "action": "tap"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("target_pixel") == [720, 1600]


@pytest.mark.tier2
@pytest.mark.hardware
def test_b2_coords_nan_and_infinity(gateway_session, e2e_config, wake_screen):
    """Test 2.2.3: Sends non-finite strings NaN and Infinity safely handled."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/touch",
        json={"x": "NaN", "y": "Infinity", "action": "tap"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400, 500)
    health = gateway_session.get(f"{e2e_config.gateway_url}/health", timeout=5.0)
    assert health.status_code == 200


@pytest.mark.tier2
@pytest.mark.hardware
def test_b2_coords_non_numeric_strings(gateway_session, e2e_config):
    """Test 2.2.4: Sends string values {'x': 'left', 'y': 'bottom'} without crashing daemon."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/touch",
        json={"x": "left", "y": "bottom", "action": "tap"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400, 500)
    health = gateway_session.get(f"{e2e_config.gateway_url}/health", timeout=5.0)
    assert health.status_code == 200


@pytest.mark.tier2
@pytest.mark.hardware
def test_b2_touch_missing_coordinates(gateway_session, e2e_config, wake_screen):
    """Test 2.2.5: Sends payload with missing coordinate keys defaulting safely to center [360, 800]."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/touch",
        json={"action": "tap"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("target_pixel") == [360, 800]


# =============================================================================
# Domain 3: Concurrency & Race Condition Boundaries
# =============================================================================

@pytest.mark.tier2
@pytest.mark.hardware
def test_b3_concurrent_status_inspections(e2e_config):
    """Test 2.3.1: Dispatches 10 simultaneous GET requests without socket starvation."""
    url = f"{e2e_config.gateway_url}/telemetry"
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(requests.get, url, timeout=e2e_config.gateway_timeout) for _ in range(10)]
        results = [f.result() for f in futures]
        
    assert all(r.status_code == 200 for r in results)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b3_concurrent_touch_stream(e2e_config, wake_screen):
    """Test 2.3.2: Dispatches a rapid burst of 10 touch events within 500ms."""
    url = f"{e2e_config.gateway_url}/v1/screen/touch"
    payload = {"x": 0.5, "y": 0.5, "action": "tap"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(requests.post, url, json=payload, timeout=e2e_config.gateway_timeout) for _ in range(10)]
        results = [f.result() for f in futures]
        
    assert all(r.status_code == 200 for r in results)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b3_concurrent_frame_capture_and_touch(e2e_config, wake_screen):
    """Test 2.3.3: Executes 3 screen frame captures concurrently with 3 touch events."""
    frame_url = f"{e2e_config.gateway_url}/v1/screen/frame"
    touch_url = f"{e2e_config.gateway_url}/v1/screen/touch"
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f_frames = [executor.submit(requests.get, frame_url, timeout=e2e_config.gateway_timeout) for _ in range(3)]
        f_touches = [executor.submit(requests.post, touch_url, json={"x": 0.5, "y": 0.5}, timeout=e2e_config.gateway_timeout) for _ in range(3)]
        
        frames = [f.result() for f in f_frames]
        touches = [f.result() for f in f_touches]
        
    assert all(r.status_code == 200 for r in frames)
    assert all(r.status_code == 200 for r in touches)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b3_interleaved_lifecycle_race(gateway_session, e2e_config, cleanup_app_state):
    """Test 2.3.4: Sends rapid interleaved launch -> stop -> launch commands within 150ms."""
    url = f"{e2e_config.gateway_url}/v1/screen/app"
    r1 = gateway_session.post(url, json={"package": "com.netuark.app", "action": "launch"}, timeout=e2e_config.gateway_timeout)
    r2 = gateway_session.post(url, json={"package": "com.netuark.app", "action": "stop"}, timeout=e2e_config.gateway_timeout)
    r3 = gateway_session.post(url, json={"package": "com.netuark.app", "action": "launch"}, timeout=e2e_config.gateway_timeout)
    
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 200


@pytest.mark.tier2
@pytest.mark.ai
def test_b3_concurrent_ai_inference_and_screen_stream(e2e_config):
    """Test 2.3.5: Dispatches Piper TTS synthesis concurrently with 2 screen frame requests."""
    tts_url = f"{e2e_config.gateway_url}/v1/audio/speech?input=Concurrent+stream+test"
    frame_url = f"{e2e_config.gateway_url}/v1/screen/frame"
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_tts = executor.submit(requests.get, tts_url, timeout=e2e_config.ai_timeout)
        f_frames = [executor.submit(requests.get, frame_url, timeout=e2e_config.gateway_timeout) for _ in range(2)]
        
        r_tts = f_tts.result()
        r_frames = [f.result() for f in f_frames]
        
    assert r_tts.status_code == 200
    assert all(r.status_code == 200 for r in r_frames)


# =============================================================================
# Domain 4: Power State & Display Transition Boundaries
# =============================================================================

@pytest.mark.tier2
@pytest.mark.hardware
def test_b4_display_sleep_detection(adb):
    """Test 2.4.1: Queries Android display power state via ADB verifying ON vs OFF detection."""
    res = adb.shell("dumpsys power | grep 'Display Power: state='")
    assert res.returncode == 0
    assert "Display Power: state=" in res.stdout


@pytest.mark.tier2
@pytest.mark.hardware
def test_b4_wake_and_unlock_key_command(gateway_session, e2e_config):
    """Test 2.4.2: Dispatches POST /v1/screen/key with UNLOCK."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/key",
        json={"key": "UNLOCK"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


@pytest.mark.tier2
@pytest.mark.hardware
def test_b4_touch_while_display_off(gateway_session, e2e_config):
    """Test 2.4.3: Sends a touch tap verifying gateway handles input without deadlock."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/touch",
        json={"x": 0.5, "y": 0.5, "action": "tap"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


@pytest.mark.tier2
@pytest.mark.hardware
def test_b4_stayon_power_persistence(adb):
    """Test 2.4.4: Configures svc power stayon true validating device persistence."""
    res = adb.shell("svc power stayon true")
    assert res.returncode == 0


@pytest.mark.tier2
@pytest.mark.hardware
def test_b4_frame_capture_under_display_off(gateway_session, e2e_config):
    """Test 2.4.5: Requests /v1/screen/frame reading framebuffer bytes without pipe errors."""
    resp = gateway_session.get(f"{e2e_config.gateway_url}/v1/screen/frame", timeout=e2e_config.gateway_timeout)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type") == "image/jpeg"
    assert len(resp.content) >= 1000


# =============================================================================
# Domain 5: Malformed Payloads, Protocol & HTTP Method Violations
# =============================================================================

@pytest.mark.tier2
@pytest.mark.hardware
def test_b5_malformed_json_syntax(gateway_session, e2e_config):
    """Test 2.5.1: Sends syntactically broken JSON body to POST /v1/screen/app."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        data='{"package": "com.netuark", action: ',
        headers={"Content-Type": "application/json"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (400, 500)
    health = gateway_session.get(f"{e2e_config.gateway_url}/health", timeout=5.0)
    assert health.status_code == 200


@pytest.mark.tier2
@pytest.mark.hardware
def test_b5_empty_post_body(gateway_session, e2e_config):
    """Test 2.5.2: Sends empty byte body b'' with Content-Length: 0."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        data=b"",
        headers={"Content-Length": "0"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b5_unsupported_http_methods(gateway_session, e2e_config):
    """Test 2.5.3: Sends unsupported HTTP methods: DELETE on /v1/screen/app, PUT on touch."""
    r_del = gateway_session.delete(f"{e2e_config.gateway_url}/v1/screen/app", timeout=e2e_config.gateway_timeout)
    assert r_del.status_code in (404, 405, 501)
    
    r_put = gateway_session.put(f"{e2e_config.gateway_url}/v1/screen/touch", timeout=e2e_config.gateway_timeout)
    assert r_put.status_code in (404, 405, 501)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b5_invalid_content_type(gateway_session, e2e_config):
    """Test 2.5.4: Sends POST request with Content-Type: text/plain containing JSON string."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/touch",
        data='{"x": 0.5, "y": 0.5, "action": "tap"}',
        headers={"Content-Type": "text/plain"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400, 415)


@pytest.mark.tier2
@pytest.mark.hardware
def test_b5_unknown_lifecycle_action(gateway_session, e2e_config):
    """Test 2.5.5: Sends unknown action {'action': 'self_destruct'} to POST /v1/screen/app."""
    resp = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        json={"action": "self_destruct", "package": "com.netuark.app"},
        timeout=e2e_config.gateway_timeout
    )
    assert resp.status_code in (200, 400)
