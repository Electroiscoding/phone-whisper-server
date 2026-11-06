# End-to-End Test Infrastructure & Verification Specification

`TEST_INFRA.md` documents the architectural scope, test harness design, environment configurations, execution methods, and full 88-test verification inventory for the Cloud Phone NTA project (`cool-bohr`).

---

## 1. Architectural Scope & Network Topology

The Cloud Phone NTA system is an asynchronous, multi-tiered infrastructure spanning physical ARM hardware, local network gateways, Cloudflare tunnels, and global edge proxies:

```
[ Host Test Runner (Linux / Python 3.14.4 / Pytest 9.1.1) ]
         |                                 |
         | (Local Subnet / ADB)            | (HTTPS / Edge Proxy)
         v                                 v
[ Xiaomi Redmi 9i Phone Node ]    [ Cloudflare Pages Edge ]
  - ADB: 192.168.29.2:5555          - https://phone-whisper-server.pages.dev
  - Termux Gateway: :8080           - functions/_proxy.js dynamic routing
  - Loopback ADB: 127.0.0.1:5555    - functions/register_tunnel.js
  - APK: com.netuark.app (v4.18)           |
  - AI Organs (Sherpa-ONNX, BGE)           v
         ^                         [ Cloudflare Quick Tunnel ]
         |                         - *.trycloudflare.com
         +---------------------------------+
```

### Operational Layers Under Test
1. **Physical & ADB Hardware Layer**:
   - Device: Xiaomi Redmi 9i (`M2006C3LII`, `dandelion_in`, MediaTek Helio G25, Android 10 / API 29, `armeabi-v7a`).
   - Host ADB connection at `192.168.29.2:5555`.
   - Termux internal loopback ADB at `127.0.0.1:5555` authorized via UID 2000 synced keys.
   - Sideload target artifact `/tmp/nta-4.18-release.apk` (283,302,571 bytes, SHA-256 `9db8ff8f1941b2c15d999782e2e2c7ec865c8963ccfe598f740d2f3d79a57ff9`).
2. **Gateway Lifecycle & Input Layer**:
   - Multi-threaded Python server (`ThreadedHTTPServer`) on port 8080 (`mobile/gateway.py` and `gateway.py`).
   - `GET /v1/screen/app`: Dynamic package inspection via `dumpsys package` returning `status`, `installed`, `package`, `app_name`, `version_name`, `version_code`, `running`, `main_activity`.
   - `POST /v1/screen/app`: Deterministic lifecycle actions (`launch`, `stop`, `restart`, `status`) using `am start -n` and `am force-stop` under UID 2000 ADB shell.
   - `POST /v1/screen/touch` & `POST /v1/screen/key`: Remote touch tap/swipe and hardware navigation with sanitized `LD_LIBRARY_PATH` environment.
   - `GET /v1/screen/frame`: Live screen capture via `adb exec-out screencap` downscaled to 360x800 RGB JPEG (quality=60).
3. **Frontend Presentation & Zero-Hardcoding Layer**:
   - `index.html`: Completely dynamic NTA / App Deck dashboard with zero hardcoded versions (`v4.2.0 Build 21`), static package names (`com.netuark`), or rigid status badges.
   - Reactive UI bound to `/v1/screen/app` with dynamic DOM elements, tab-visibility-aware background polling, and dynamic action buttons.
4. **Edge Proxy & Worldwide Routing Layer**:
   - Cloudflare Pages edge worker (`functions/_proxy.js`) routing `/v1/*` to the phone's live quick tunnel origin (`*.trycloudflare.com`).
   - Dynamic tunnel registration endpoint (`functions/register_tunnel.js`) authenticated via secret `mobile_ai_nuclear_key`.
   - Conforming dynamic mock fallbacks when upstream origin is unreachable.
5. **AI Coexistence & Thermal Safety Layer**:
   - Resource isolation ensuring Sherpa-ONNX Piper Neural TTS (`/v1/audio/speech`), BGE Vector Embeddings (`/v1/embeddings`), BGE Document Reranker (`/v1/rerank`), and 24/7 Currents Autonomous Wire bot (`/v1/currents/status`) execute without interference under the `dynamic_elastic_jit` governor (75s eviction timeout) and ACC thermal guard (40°C threshold).

---

## 2. Environment Specifications & Empirical Benchmarks

### A. Host Test Runner Environment
- **Operating System**: Linux 7.0.0-34-generic (x86_64) Ubuntu/Debian
- **Python Runtime**: Python 3.14.4 (Virtual Environment: `/home/soham/.global_venv/bin/python3`)
- **Key Test Packages**:
  - `pytest 9.1.1` (Core test runner and discovery engine)
  - `requests 2.34.2` (HTTP client with connection pooling)
  - `urllib3 2.7.0` (Underlying transport client)
  - `pillow 12.2.0` (Image verification and header parsing for screen frame JPEG validation)
  - `httpx 0.28.1` & `aiohttp 3.14.1` (Async HTTP testing capability)

### B. Physical Device & ADB Node
- **Device Model**: Xiaomi Redmi 9i (`M2006C3LII`, product `dandelion_in`, device `dandelion`)
- **Android Version**: Android 10 (API Level 29)
- **CPU Architecture**: ARM64 kernel with `armeabi-v7a` 32-bit userland (MediaTek Helio G25, 8x Cortex-A53)
- **Memory**: 3.79 GB LPDDR4X (Nominal ~2.2 GB available)
- **Host ADB Path**: `/usr/bin/adb` (Version 1.0.41, 34.0.5-debian)
- **Device Connection**: `192.168.29.2:5555` (State: `device`, UID 2000 execution capable)
- **APK Target**: `/tmp/nta-4.18-release.apk` (Size: 283,302,571 bytes, SHA-256: `9db8ff8f1941b2c15d999782e2e2c7ec865c8963ccfe598f740d2f3d79a57ff9`)

### C. Measured Network Latencies & Timeout Recommendations
Direct empirical measurements conducted across all network hops:

| Target Endpoint | Network Hop | Measured Latency | Recommended Test Timeout |
|---|---|---|---|
| Direct Gateway Telemetry (`/telemetry`) | Host -> LAN -> Phone Port 8080 | 95.3 ms | 5.0 s |
| Direct Gateway Screen Frame (`/v1/screen/frame`) | Host -> LAN -> Phone Port 8080 | 120 - 180 ms | 10.0 s |
| Edge Pages Telemetry (`/telemetry`) | Host -> Cloudflare Edge -> Tunnel -> Phone | 616.6 ms | 20.0 s |
| Edge Pages Screen Frame (`/v1/screen/frame`) | Host -> Cloudflare Edge -> Tunnel -> Phone | 640 - 750 ms | 25.0 s |
| Edge Quick Tunnel Direct | Host -> trycloudflare.com -> Phone | 634.1 ms | 20.0 s |
| BGE Embeddings (`/v1/embeddings`) | Warm inference in L1/L2 cache | 150 ms | 10.0 s |
| Piper TTS (`/v1/audio/speech`) | Cold start & Sherpa-ONNX model loading | 12.48 s | 45.0 s |

> **Critical Rule**: AI inference endpoints (`/v1/audio/speech`, `/v1/chat/completions`) trigger JIT model loading on the physical phone if evicted by the 75-second governor. Tests exercising these endpoints **must** use a minimum timeout of **45.0 seconds** to avoid spurious test failures.

---

## 3. Directory Layout & Isolation Contract

Legacy test scripts at the repository root (`test_god_grade_datacenter.py`, `test_recsys_integration.py`, `test_two_tower_studio.py`) execute code upon module import and target obsolete localhost ports, causing crashes if collected indiscriminately.

To guarantee complete isolation, the project adopts the following standardized layout:

```
cool-bohr/
├── pytest.ini                    # Test runner configuration strictly targeting tests/e2e/
├── run_e2e_tests.sh              # Unified bash wrapper with colorized CLI output
├── TEST_INFRA.md                 # Test harness and infrastructure documentation (this file)
└── tests/
    ├── __init__.py
    └── e2e/
        ├── __init__.py
        ├── conftest.py           # Shared fixtures, ADB client, requests sessions, timeouts
        ├── runner.py             # Custom orchestrated CLI test runner with JSON export
        ├── test_tier1_features.py     # Tier 1: 10 Features x 5 tests = 50 tests (Feature Coverage)
        ├── test_tier2_boundaries.py   # Tier 2: 5 Boundary Domains x 5 tests = 25 tests (Boundaries)
        ├── test_tier3_combinations.py # Tier 3: 7 Pairwise Interaction & Concurrency Tests
        └── test_tier4_scenarios.py    # Tier 4: 6 Real-World End-to-End Workflow Scenarios
```

---

## 4. 4-Tier Test Suite Inventory (88 Tests Total)

### Tier 1: Feature Coverage (50 Tests, Features F1 - F10)
Validates core functionality with exactly 5 test cases per feature:

- **Feature F1: APK Sideloading & Installation Verification**
  1. `test_f1_apk_file_hash_integrity`: Verifies downloaded APK `/tmp/nta-4.18-release.apk` exists, size is 283,302,571 bytes, and SHA-256 matches release checksum `9db8ff...`.
  2. `test_f1_apk_badging_metadata`: Inspects APK binary manifest verifying package `com.netuark.app`, versionCode 37, versionName 4.18, MainActivity, and `armeabi-v7a`.
  3. `test_f1_adb_push_apk_remote_tmp`: Verifies ADB push capability and remote APK artifact presence in `/data/local/tmp`.
  4. `test_f1_pm_install_sideload_success`: Verifies `pm install -r -d` execution or validates installed package state via Android Package Manager.
  5. `test_f1_package_manager_presence_verification`: Validates `pm list packages` and `dumpsys package` reporting package presence and metadata.

- **Feature F2: Gateway App Inspection API (`GET /v1/screen/app`)**
  6. `test_f2_gateway_app_inspection_default_get`: Calls `GET /v1/screen/app` verifying dynamic discovery and metadata response contract.
  7. `test_f2_gateway_app_inspection_explicit_package_query`: Calls `GET /v1/screen/app?package=com.netuark.app` verifying explicit package lookup.
  8. `test_f2_gateway_app_inspection_post_action_status`: Calls `POST /v1/screen/app` with `{"action": "status", "package": "com.netuark.app"}`.
  9. `test_f2_gateway_app_inspection_uninstalled_package`: Queries an uninstalled dummy package (`com.fake.nonexistent.app`) verifying `installed: false` negative response.
  10. `test_f2_gateway_app_inspection_live_running_state_correlation`: Verifies `running` reflects live process presence.

- **Feature F3: Gateway Lifecycle Execution (`POST /v1/screen/app`)**
  11. `test_f3_gateway_lifecycle_launch_action`: Calls `POST /v1/screen/app` with `action="launch"` verifying app startup.
  12. `test_f3_gateway_lifecycle_stop_action`: Calls `POST /v1/screen/app` with `action="stop"` verifying clean termination.
  13. `test_f3_gateway_lifecycle_restart_action`: Calls `POST /v1/screen/app` with `action="restart"` verifying process restart.
  14. `test_f3_gateway_lifecycle_zero_monkey_execution`: Verifies launching uses `am start -n` under UID 2000 ADB shell without monkey errors (252/253).
  15. `test_f3_gateway_lifecycle_full_cycle_state_transitions`: Deterministic state machine verification: `stop` -> `launch` -> `restart` -> `stop`.

- **Feature F4: Touch Control Environment Sanitization (`/v1/screen/touch`, `/v1/screen/key`)**
  16. `test_f4_screen_touch_center_tap_sanitized_env`: Verifies center tap `x=0.5, y=0.5` maps to `target_pixel=[360, 800]` without dynamic linker aborts.
  17. `test_f4_screen_touch_boundary_tap_sanitized_env`: Verifies boundary tap `x=0.05, y=0.05` maps to `target_pixel=[36, 80]`.
  18. `test_f4_screen_touch_swipe_gesture_sanitized_env`: Tests swipe gesture `[360, 1280]` to `[360, 320]` with `duration_ms=300`.
  19. `test_f4_screen_key_hardware_navigation_events`: Tests navigation keys: `HOME` (3), `BACK` (4), `RECENTS` (187), `UNLOCK`.
  20. `test_f4_screen_touch_env_ld_library_path_isolation`: Validates `mobile/gateway.py` `_run_shell_cmd` environment isolation.

- **Feature F5: Frontend Zero Hardcoding Removal (`index.html`)**
  21. `test_f5_frontend_zero_hardcode_version_audit`: Audits `index.html` ensuring obsolete version string `v4.2.0` is removed from active markup.
  22. `test_f5_frontend_zero_hardcode_build_number_audit`: Audits `index.html` ensuring static string `Build 21` is removed from active markup.
  23. `test_f5_frontend_zero_hardcode_static_package_markup_audit`: Audits app deck markup ensuring static package names are not hardcoded.
  24. `test_f5_frontend_zero_hardcode_badge_strings_audit`: Audits static badges (`NETUARK ACTIVE`, `APK Installed`) ensuring removal from static HTML.
  25. `test_f5_frontend_zero_hardcode_button_labels_audit`: Audits rigid button labels (`Launch NeTuArk`) ensuring replacement with dynamic controls.

- **Feature F6: Frontend Reactive State Engine (`index.html`)**
  26. `test_f6_frontend_dom_container_ids_presence`: Verifies dynamic container element IDs in `index.html`.
  27. `test_f6_frontend_reactive_query_function_present`: Verifies definition of `refreshPhoneAppStatus()` or equivalent dynamic function.
  28. `test_f6_frontend_polling_tab_visibility_awareness`: Verifies polling loop checks `document.hidden` or `visibilitychange`.
  29. `test_f6_frontend_dynamic_button_binding`: Verifies client functions support dynamic actions `launch`, `stop`, `restart`.
  30. `test_f6_frontend_mock_dom_state_renderer`: Simulates UI rendering with mock payload verifying formatted title and badge.

- **Feature F7: Edge Proxy Fallback & Routing (`functions/_proxy.js`, `functions/register_tunnel.js`)**
  31. `test_f7_edge_proxy_register_tunnel_endpoint`: Queries `GET /register_tunnel` on Cloudflare Pages verifying active origin resolution.
  32. `test_f7_edge_proxy_health_upstream_passthrough`: Verifies `/health` proxied through Cloudflare Pages matches upstream phone telemetry.
  33. `test_f7_edge_proxy_screen_app_routing`: Validates `/v1/screen/app` forwarded through Cloudflare Pages edge proxy returns live app state.
  34. `test_f7_edge_proxy_fallback_schema_conformance`: Validates fallback response in `functions/_proxy.js` matches zero-hardcoding schema.
  35. `test_f7_edge_proxy_live_tunnel_secret_authentication`: Verifies tunnel registration endpoint enforces secret key authentication.

- **Feature F8: Cloud Streaming & Touch Edge Verification**
  36. `test_f8_screen_frame_direct_jpeg_delivery`: Requests `/v1/screen/frame` directly from phone gateway verifying valid 360x800 JPEG bytes.
  37. `test_f8_screen_frame_edge_proxy_delivery`: Requests `/v1/screen/frame` through Cloudflare Pages verifying frame delivery.
  38. `test_f8_screen_frame_streaming_latency_budget`: Measures round-trip time across 5 consecutive frame captures through edge proxy (median < 750ms).
  39. `test_f8_screen_touch_edge_proxy_passthrough`: Injects touch tap through Cloudflare Pages edge proxy.
  40. `test_f8_screen_frame_cache_control_headers`: Validates edge proxy frame response headers prevent intermediate CDN caching.

- **Feature F9: Core AI Organs & Currents Wire Health**
  41. `test_f9_core_ai_piper_tts_synthesis`: Calls Piper Neural TTS `/v1/audio/speech?input=Hello+World` verifying 22050Hz WAV audio.
  42. `test_f9_core_ai_bge_embeddings_generation`: Calls BGE Embeddings `/v1/embeddings` verifying 384-dimensional vector.
  43. `test_f9_core_ai_bge_reranker_scoring`: Calls BGE Reranker `/v1/rerank` verifying semantic ranking.
  44. `test_f9_core_ai_currents_news_bot_wire`: Queries `/v1/currents/status` verifying 2-hour autonomous news cycle daemon.
  45. `test_f9_core_ai_telemetry_governor_health`: Checks `/telemetry` verifying battery temp < 42°C, available memory > 500 MB, and `dynamic_elastic_jit` governor.

- **Feature F10: End-to-End Test Suite Meta-Verification**
  46. `test_f10_e2e_suite_pytest_discovery`: Verifies pytest discovers all tests in `tests/e2e/` without collection errors.
  47. `test_f10_e2e_suite_exit_code_zero`: Verifies main test runner script exists, is executable, and conforms to exit code contracts.
  48. `test_f10_e2e_suite_json_report_generation`: Verifies structured JSON report format and metric fields.
  49. `test_f10_e2e_suite_tier_isolation_markers`: Verifies pytest markers `@pytest.mark.tier1` and `@pytest.mark.tier2` allow isolated execution.
  50. `test_f10_e2e_suite_execution_budget`: Verifies Tier 1 execution completes within established execution budgets.

---

### Tier 2: Boundary & Corner Cases (25 Tests across 5 Boundary Domains)
Validates resilience against atypical inputs and extreme system conditions:

- **Boundary Domain 1: Package Name Boundaries & Injection Defense**
  51. `test_b1_package_empty_string`: Sends `POST /v1/screen/app` with empty package name `{"package": "", "action": "launch"}`.
  52. `test_b1_package_whitespace_only`: Sends `POST /v1/screen/app` with whitespace package name `{"package": "   \t\n   "}`.
  53. `test_b1_package_shell_injection`: Attempts command injection via package name: `com.netuark.app; touch /tmp/pwned`.
  54. `test_b1_package_excessively_long_name`: Sends a 5,000-character package name verifying buffer safety and regex limits.
  55. `test_b1_package_special_regex_characters`: Queries package name containing regex metacharacters `com.netuark.*[$^?]+`.

- **Boundary Domain 2: Coordinate & Input Injection Boundaries**
  56. `test_b2_coords_negative_values`: Sends negative relative coordinates `{"x": -1.5, "y": -0.5, "action": "tap"}`.
  57. `test_b2_coords_exceeding_unity`: Sends coordinates exceeding 1.0: `{"x": 2.5, "y": 10.0, "action": "tap"}`.
  58. `test_b2_coords_nan_and_infinity`: Sends `{"x": "NaN", "y": "Infinity", "action": "tap"}`.
  59. `test_b2_coords_non_numeric_strings`: Sends string values `{"x": "left", "y": "bottom", "action": "tap"}`.
  60. `test_b2_touch_missing_coordinates`: Sends payload with missing coordinate keys `{}` or `{"action": "tap"}`.

- **Boundary Domain 3: Concurrency & Race Condition Boundaries**
  61. `test_b3_concurrent_status_inspections`: Dispatches 10 simultaneous asynchronous `GET /v1/screen/app` requests.
  62. `test_b3_concurrent_touch_stream`: Dispatches a rapid burst of 20 consecutive `POST /v1/screen/touch` requests within 500ms.
  63. `test_b3_concurrent_frame_capture_and_touch`: Executes 5 screen frame captures concurrently with 5 touch event posts.
  64. `test_b3_interleaved_lifecycle_race`: Sends rapid interleaved `launch` -> `stop` -> `launch` commands within 150ms.
  65. `test_b3_concurrent_ai_inference_and_screen_stream`: Dispatches Piper TTS synthesis while requesting 3 screen frames.

- **Boundary Domain 4: Power State & Display Transition Boundaries**
  66. `test_b4_display_sleep_detection`: Queries Android display power state via ADB verifying detection of ON vs OFF.
  67. `test_b4_wake_and_unlock_key_command`: Dispatches `POST /v1/screen/key` with `{"key": "UNLOCK"}` waking and unlocking device.
  68. `test_b4_touch_while_display_off`: Sends touch tap while display backlight is powered off (`state=OFF`).
  69. `test_b4_stayon_power_persistence`: Configures `svc power stayon true` and validates persistence in `dumpsys power`.
  70. `test_b4_frame_capture_under_display_off`: Requests `/v1/screen/frame` when display state is OFF without pipe errors.

- **Boundary Domain 5: Malformed Payloads, Protocol & HTTP Method Violations**
  71. `test_b5_malformed_json_syntax`: Sends syntactically broken JSON body to `POST /v1/screen/app`.
  72. `test_b5_empty_post_body`: Sends empty byte body `b""` with `Content-Length: 0` to `POST /v1/screen/app`.
  73. `test_b5_unsupported_http_methods`: Sends unsupported HTTP methods: `DELETE /v1/screen/app`, `PUT /v1/screen/touch`.
  74. `test_b5_invalid_content_type`: Sends POST request with `Content-Type: text/plain` containing JSON string.
  75. `test_b5_unknown_lifecycle_action`: Sends unknown action `{"action": "self_destruct"}` to `POST /v1/screen/app`.

---

### Tier 3: Cross-Feature Combinations (7 Tests)
Validates system behavior under simultaneous operational demands:

76. `test_t3_touch_during_active_screen_streaming`: Continuous 10-second screen streaming while 8 touch events (taps and swipes) are concurrently injected.
77. `test_t3_app_lifecycle_during_speech_synthesis`: App launch and stop actions executed concurrently with multi-core Piper TTS ONNX inference.
78. `test_t3_rapid_lifecycle_restart_stress`: Rapid 6-step lifecycle sequence (`launch` -> `restart` -> `status` -> `stop` -> `status` -> `launch`) testing process stability.
79. `test_t3_gateway_queries_during_currents_cycle`: App inspection and telemetry queries executed while the 24/7 Currents News Bot cycle runs.
80. `test_t3_edge_proxy_vs_direct_concurrency`: Simultaneous WAN requests via Cloudflare Pages and direct LAN requests via port 8080.
81. `test_t3_streaming_during_embedding_rerank`: Continuous screen frame captures during concurrent BGE Embeddings and Reranker batch computation.
82. `test_t3_key_navigation_during_app_active`: Hardware navigation (`HOME`, `BACK`, `RECENTS`) while sideloaded app is active, verifying process persistence.

---

### Tier 4: Real-World Application Scenarios (6 Tests)
Validates complete user journey workflows and recovery mechanics:

83. `test_t4_scenario1_golden_path_interactive_session`: 9-phase complete interactive session: Wake -> Status check -> Launch NTA -> Stream frames -> Touch tap -> Touch swipe -> Post-touch frame -> Stop app -> AI organ coexistence.
84. `test_t4_scenario2_zero_hardcoding_and_frontend_dynamic_load`: 5-phase zero-hardcoding audit and reactive state rendering verification.
85. `test_t4_scenario3_cold_start_and_system_recovery`: Gateway process crash simulation, watchdog detection, restart, and tunnel re-registration within 15 seconds.
86. `test_t4_scenario4_concurrent_multiclient_session`: 4 concurrent clients exercising streaming, dashboard monitoring, touch control, and AI synthesis simultaneously.
87. `test_t4_scenario5_edge_fallback_and_dynamic_switch`: Edge proxy fallback verification on tunnel outage and automatic resumption upon tunnel reconnect.
88. `test_t4_scenario6_thermal_governance_and_currents_coexistence`: Sustained streaming and touch session concurrent with news cycle verifying temperature <= 38.5°C and available memory >= 1500 MB.

---

## 5. Configuration & Environment Overrides

Every test component is configurable via environment variables or CLI flags:

| Variable | Default Value | CLI Flag | Description |
|---|---|---|---|
| `GATEWAY_URL` | `http://192.168.29.2:8080` | `--gateway-url` | Direct Termux gateway base URL |
| `PAGES_URL` | `https://phone-whisper-server.pages.dev` | `--pages-url` | Cloudflare Pages edge proxy URL |
| `ADB_DEVICE` | `192.168.29.2:5555` | `--adb-device` | Target ADB device identifier |
| `APK_PATH` | `/tmp/nta-4.18-release.apk` | `--apk-path` | Local filesystem path to NTA APK |
| `GATEWAY_TIMEOUT` | `10.0` | N/A | Timeout (seconds) for direct gateway calls |
| `PAGES_TIMEOUT` | `25.0` | N/A | Timeout (seconds) for Cloudflare Pages edge calls |
| `AI_TIMEOUT` | `45.0` | N/A | Timeout (seconds) for cold-start AI model inferences |
| `SKIP_HARDWARE_TESTS` | `0` | `--skip-hardware` | Set to 1 to skip physical ADB hardware tests |
| `SKIP_EDGE_TESTS` | `0` | `--skip-edge` | Set to 1 to skip Cloudflare Pages edge tests |

---

## 6. Execution Instructions

### A. Quick Start via Bash Wrapper
```bash
# Run all test tiers (Tier 1 to 4)
./run_e2e_tests.sh

# Run a specific tier
./run_e2e_tests.sh --tier 1
./run_e2e_tests.sh --tier 2
./run_e2e_tests.sh --tier 3
./run_e2e_tests.sh --tier 4

# Run hardware-specific tests only
./run_e2e_tests.sh -m hardware

# Run with custom device override
ADB_DEVICE=127.0.0.1:5555 ./run_e2e_tests.sh
```

### B. Execution via Python Orchestrated Runner
```bash
# Run all tests and generate structured JSON report
python3 tests/e2e/runner.py --tier all --report-file test_reports/e2e_summary.json

# Run Tier 1 with verbose output and early exit on first failure
python3 tests/e2e/runner.py --tier 1 -v -x
```

### C. Direct Pytest Execution
```bash
# Execute pytest strictly on tests/e2e/
pytest tests/e2e/ -v

# Filter by marker
pytest tests/e2e/ -m "tier1 and hardware"
```

---

## 7. Reporting & Acceptance Criteria Contract

### Exit Code Convention
- **`0`**: 100% of executed test cases passed. Acceptance criteria satisfied.
- **`1`**: One or more test cases failed or encountered an unexpected exception.
- **`2`**: Pytest execution was interrupted by user or CLI configuration error.

### Structured JSON Report Schema (`test_reports/e2e_summary.json`)
```json
{
  "timestamp": "2026-11-05T01:30:00.000000Z",
  "exit_code": 0,
  "duration_seconds": 22.45,
  "configuration": {
    "gateway_url": "http://192.168.29.2:8080",
    "pages_url": "https://phone-whisper-server.pages.dev",
    "adb_device": "192.168.29.2:5555",
    "tier": "all"
  },
  "stats": {
    "total": 88,
    "passed": 88,
    "failed": 0,
    "skipped": 0
  },
  "tests": [
    {
      "nodeid": "tests/e2e/test_tier1_features.py::test_f1_apk_file_hash_integrity",
      "name": "test_f1_apk_file_hash_integrity",
      "tier": "tier1",
      "outcome": "passed",
      "duration": 0.045,
      "error": ""
    }
  ]
}
```

---

## 8. Diagnostic & Troubleshooting Runbook

### 1. ADB Unauthorized or Connection Refused
- **Symptom**: `adb -s 192.168.29.2:5555 get-state` returns `unauthorized` or `connection refused`.
- **Resolution**:
  ```bash
  adb disconnect 192.168.29.2:5555
  adb connect 192.168.29.2:5555
  adb -s 192.168.29.2:5555 wait-for-device
  ```
  Ensure the host public key in `~/.android/adbkey.pub` matches the phone's authorized keys.

### 2. Touch Injection Linker Error (`returncode: 1`)
- **Symptom**: `POST /v1/screen/touch` returns `{"status": "ok", "returncode": 1}`.
- **Root Cause**: Bionic dynamic linker failure on `app_process` due to inherited `LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib`.
- **Resolution**: Ensure `env.pop("LD_LIBRARY_PATH", None)` is executed prior to invoking `/system/bin/sh` or `/system/bin/input` in `mobile/gateway.py`.

### 3. Screen Frame Capture Timeout on Asleep Device
- **Symptom**: Frame capture or touch event times out when display power is `state=OFF`.
- **Resolution**: Invoke wake and unlock fixture:
  ```bash
  adb -s 192.168.29.2:5555 shell "input keyevent 224 && input swipe 360 1200 360 300 200"
  ```

### 4. Cloudflare Quick Tunnel Expiration
- **Symptom**: `https://phone-whisper-server.pages.dev` returns HTTP 502 or stale upstream.
- **Resolution**: Query `/register_tunnel` to obtain active origin:
  ```bash
  curl -s https://phone-whisper-server.pages.dev/register_tunnel | jq .active_origin
  ```
  If origin is expired or disconnected, restart cloudflared on phone or run `mobile/start_ai.sh`.
