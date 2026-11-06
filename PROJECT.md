# Project: Cloud Phone NTA Sideloading, Zero-Hardcoding Dynamic Dashboard & Edge Streaming

## Architecture
The system integrates an ARM smartphone (Xiaomi Redmi 9i, Android 10, armeabi-v7a at `192.168.29.2:5555`) with an edge gateway server (`mobile/gateway.py` and `gateway.py` on Termux), exposed worldwide via Cloudflare Quick Tunnels (`cloudflared`) and Cloudflare Pages (`phone-whisper-server.pages.dev`). The architecture consists of:
1. **Device Layer**: Physical Redmi 9i running Android 10, containing ADB loopback at `127.0.0.1:5555` authorized via synced host keys, with `com.netuark.app` (v4.18) sideloaded via `/data/local/tmp` and `pm install -r -d`.
2. **Gateway Lifecycle & Input Layer (`mobile/gateway.py` / `gateway.py`)**:
   - `GET /v1/screen/app`: Dynamic package inspection via `dumpsys package` returning `versionName`, `versionCode`, `installed`, `running`, and `target_activity`.
   - `POST /v1/screen/app`: Deterministic lifecycle control supporting actions `launch` (`am start -n`), `stop` (`am force-stop`), `restart`, and `status`, eliminating monkey launch errors.
   - `POST /v1/screen/touch` & `/v1/screen/key`: Input injection with sanitized environment (`env.pop("LD_LIBRARY_PATH", None)`) eliminating bionic dynamic linker failure on `/system/bin/input`.
   - `GET /v1/screen/frame`: Live screen capture via `adb exec-out screencap` downscaled to 360x800 JPEG (~5.2 KB) for low-latency streaming.
3. **Frontend Presentation Layer (`index.html`)**:
   - Completely dynamic NTA / App Deck dashboard with zero hardcoded versions (`v4.2.0 Build 21`), package names, or status strings.
   - Reactive UI bound to `/v1/screen/app` with Launch, Stop, and Restart controls, live animated status badges, and tab-visibility-aware background polling.
4. **Edge Proxy Layer (`functions/_proxy.js` & `functions/register_tunnel.js`)**:
   - Cloudflare Pages edge worker dynamically routing `/v1/*` requests to the phone's live tunnel origin, with dynamic mock fallbacks matching the zero-hardcode schema.
5. **AI Coexistence Layer**:
   - Resource isolation ensuring Whisper STT, Piper Neural TTS, Qwen LLM, BGE Embeddings/Reranker, and the 2-hour Currents news bot run unimpeded under the dynamic elastic JIT governor.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | APK Sideloading & Installation | Download `nta-4.18-release.apk` (283 MB, SHA-256 verified), push to `/data/local/tmp/nta-4.18-release.apk`, install via `pm install -r -d`, and verify `package:com.netuark.app` | M1 | Survey Explorer 1 / ORIGINAL_REQUEST §R2 |
| 2 | Gateway App Inspection API | Implement `GET /v1/screen/app` (and POST `action="status"`) in `mobile/gateway.py` and `gateway.py` to query installed packages, versions, and running state dynamically | M1 | Survey Explorer 1, 2 / ORIGINAL_REQUEST §R2 |
| 3 | Gateway Lifecycle Execution | Implement `POST /v1/screen/app` with actions `launch`, `stop`, `restart` using deterministic `am start -n` and `am force-stop` via UID 2000 ADB, replacing monkey calls | M1 | Survey Explorer 1 / ORIGINAL_REQUEST §R2 |
| 4 | Touch Control Environment Sanitization | Clear `LD_LIBRARY_PATH` in `_run_shell_cmd` within `mobile/gateway.py` so Android `/system/bin/input` executes with `returncode: 0` without linker failure | M1 | Survey Explorer 3 / ORIGINAL_REQUEST §R3 |
| 5 | Frontend Zero Hardcoding Removal | Eliminate all hardcoded version numbers (`v4.2.0 Build 21`), package names, static badges, and rigid buttons in `index.html` lines 3691, 3741–3778, 13477–13490 | M2 | Survey Explorer 2 / ORIGINAL_REQUEST §R1 |
| 6 | Frontend Reactive State Engine | Add dynamic DOM IDs and `refreshPhoneAppStatus()` client logic in `index.html` to dynamically query `/v1/screen/app`, render live badges, and support Launch/Stop/Restart | M2 | Survey Explorer 2 / ORIGINAL_REQUEST §R1 |
| 7 | Edge Proxy Fallback & Worldwide Routing | Update `functions/_proxy.js` fallback responses to align with dynamic schema and verify worldwide routing via `phone-whisper-server.pages.dev` | M3 | Survey Explorer 2, 3 / ORIGINAL_REQUEST §R3 |
| 8 | Cloud Streaming & Touch Edge Verification | Verify low-latency screen frame delivery (`/v1/screen/frame`) and interactive touch injection (`/v1/screen/touch`) through Cloudflare Pages edge proxy | M3 | Survey Explorer 3 / ORIGINAL_REQUEST §R3 |
| 9 | Core AI Organs & Currents Wire Health | Verify Whisper STT, Piper TTS, Qwen LLM, BGE Embeddings/Reranker, and 2-hour Currents bot maintain full operational health with zero degradation | M3 | Survey Explorer 3 / ORIGINAL_REQUEST §R3 |
| 10 | End-to-End Test Suite Verification | Pass 100% of requirement-driven E2E test cases across Tiers 1-4, followed by Tier 5 adversarial coverage hardening | M4 | ORIGINAL_REQUEST §Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Phone Sideloading & Gateway App Lifecycle | Sideload `nta-4.18-release.apk` on phone; implement `GET /v1/screen/app` and `POST /v1/screen/app` (launch, stop, restart, status); resolve Termux ADB loopback and monkey launch errors; sanitize `LD_LIBRARY_PATH` for touch control in `mobile/gateway.py` and sync to phone | none | IN_PROGRESS |
| M2 | Dynamic Frontend & Zero Hardcoding in index.html | Refactor `index.html` to eliminate all hardcoded version numbers (`v4.2.0 Build 21`), static package names, and hardcoded state text; implement dynamic DOM elements and client-side reactive polling / lifecycle controls | M1 | PLANNED |
| M3 | Edge Cloud Streaming, Touch Control & AI Liveness | Align `functions/_proxy.js` fallback schema; verify end-to-end screen streaming and touch control through Cloudflare Pages (`phone-whisper-server.pages.dev`); verify 100% health of core AI organs and news bot | M1, M2 | PLANNED |
| M4 | Final Acceptance & Adversarial Hardening | Pass 100% E2E test suite (Tiers 1-4) published by E2E Testing Track; Tier 5 adversarial coverage hardening; comprehensive acceptance gate review & forensic audit | M1, M2, M3, TEST_READY.md | PLANNED |

## Interface Contracts

### 1. Gateway `/v1/screen/app` Interface Contract (`mobile/gateway.py` & Frontend)
- **Endpoint**: `/v1/screen/app`
- **Methods**: `GET`, `POST`
- **GET Request**:
  - Optional Query Params: `?package=<pkg>` (defaults to auto-detecting installed NTA package, e.g. `com.netuark.app`)
  - Response (200 OK):
    ```json
    {
      "status": "ok",
      "installed": true,
      "package": "com.netuark.app",
      "app_name": "NeTuArk",
      "version_name": "4.18",
      "version_code": 37,
      "running": true,
      "main_activity": "com.netuark.app.MainActivity"
    }
    ```
- **POST Request**:
  - Request Body:
    ```json
    {
      "package": "com.netuark.app",
      "action": "launch" | "stop" | "restart" | "status"
    }
    ```
  - Response (200 OK):
    ```json
    {
      "status": "ok",
      "action": "launch",
      "package": "com.netuark.app",
      "running": true,
      "returncode": 0,
      "message": "App launched into foreground"
    }
    ```

### 2. Remote Touch & Key Control (`/v1/screen/touch`, `/v1/screen/key`)
- **Environment**: Must pop `LD_LIBRARY_PATH` before invoking `/system/bin/sh` or `/system/bin/input` to prevent bionic dynamic linker failure on `app_process`.
- **Response**: `{"status": "ok", "action": "tap", "target_pixel": [x, y], "returncode": 0}`

### 3. Edge Proxy Contract (`functions/_proxy.js`)
- Fallback schema for `/v1/screen/app` must match the dynamic contract:
  ```json
  {
    "status": "ok",
    "installed": false,
    "package": "",
    "app_name": "",
    "version_name": "",
    "version_code": 0,
    "running": false,
    "message": "Connecting to device gateway..."
  }
  ```

## Code Layout
- `mobile/gateway.py`: Primary mobile gateway running on phone (Termux port 8080) handling `/v1/screen/*`, `/v1/audio/*`, `/v1/chat/*`, `/v1/embeddings`, `/v1/rerank`, `/v1/currents/*`.
- `gateway.py`: Root gateway file synchronized with `mobile/gateway.py`.
- `index.html`: Web dashboard accessible locally and globally via Cloudflare Pages.
- `functions/_proxy.js`: Cloudflare Pages edge router and fallback handler.
- `functions/register_tunnel.js`: Dynamic tunnel registration endpoint for Cloudflare Pages.
- `mobile/start_ai.sh`: Daemon launcher on phone managing cloudflared tunnel, gateway, and AI models.
