"""
conftest.py - Pytest Fixtures and Environment Configuration for Cloud Phone E2E Tests
Path: tests/e2e/conftest.py
"""

import io
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import pytest
import requests
from PIL import Image


@dataclass
class E2EConfig:
    """Central configuration for End-to-End test suite with environment variable overrides."""
    gateway_url: str
    pages_url: str
    adb_device: str
    apk_path: Path
    project_root: Path
    gateway_timeout: float
    pages_timeout: float
    ai_timeout: float
    skip_hardware: bool
    skip_edge: bool


class ADBExecutor:
    """Robust ADB client wrapper supporting host-to-phone commands with error capturing."""

    def __init__(self, device: str):
        self.device = device
        self._adb_bin = self._find_adb()

    @staticmethod
    def _find_adb() -> str:
        for path in ["/usr/bin/adb", "/usr/local/bin/adb"]:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return "adb"

    def run(self, args: List[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
        cmd = [self._adb_bin, "-s", self.device] + args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
        except subprocess.TimeoutExpired as e:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=-1,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"ADB command timed out after {timeout}s: {e}"
            )

    def shell(self, shell_cmd: str, timeout: float = 20.0) -> subprocess.CompletedProcess:
        return self.run(["shell", shell_cmd], timeout=timeout)

    def get_state(self) -> str:
        res = self.run(["get-state"], timeout=5.0)
        return res.stdout.strip() if res.returncode == 0 else "unknown"

    def is_package_installed(self, package_name: str) -> bool:
        res = self.shell(f"pm list packages | grep -E '^package:{package_name}$'")
        return res.returncode == 0 and package_name in res.stdout

    def get_package_version_info(self, package_name: str) -> Dict[str, Any]:
        res = self.shell(f"dumpsys package {package_name}")
        info: Dict[str, Any] = {"installed": False, "version_name": None, "version_code": None}
        if res.returncode != 0:
            return info

        for line in res.stdout.splitlines():
            line = line.strip()
            if "versionName=" in line:
                m = re.search(r"versionName=([^\s]+)", line)
                if m:
                    info["version_name"] = m.group(1)
            if "versionCode=" in line:
                m = re.search(r"versionCode=([0-9]+)", line)
                if m:
                    info["version_code"] = int(m.group(1))

        info["installed"] = (info["version_name"] is not None)
        return info

    def wake_and_unlock(self) -> bool:
        """Ensure phone screen is on and unlocked for interactive touch input."""
        res = self.shell("dumpsys power | grep 'Display Power: state='")
        if "state=OFF" in res.stdout:
            self.shell("input keyevent 224")  # KEYCODE_WAKEUP
            time.sleep(0.3)
        # Unlock gesture (swipe up from bottom)
        self.shell("input swipe 360 1200 360 300 200")
        return True


def pytest_addoption(parser):
    """Add CLI flags for dynamic test configuration."""
    group = parser.getgroup("e2e", "Cloud Phone E2E Test Suite Options")
    group.addoption(
        "--gateway-url",
        action="store",
        default=os.environ.get("GATEWAY_URL", "http://192.168.29.2:8080"),
        help="Base URL of the phone gateway (Termux port 8080)"
    )
    group.addoption(
        "--pages-url",
        action="store",
        default=os.environ.get("PAGES_URL", "https://phone-whisper-server.pages.dev"),
        help="Base URL of Cloudflare Pages edge proxy"
    )
    group.addoption(
        "--adb-device",
        action="store",
        default=os.environ.get("ADB_DEVICE", "192.168.29.2:5555"),
        help="ADB device identifier (e.g. 192.168.29.2:5555)"
    )
    group.addoption(
        "--apk-path",
        action="store",
        default=os.environ.get("APK_PATH", "/tmp/nta-4.18-release.apk"),
        help="Path to local APK artifact"
    )
    group.addoption(
        "--skip-hardware",
        action="store_true",
        default=os.environ.get("SKIP_HARDWARE_TESTS", "0").lower() in ("1", "true", "yes"),
        help="Skip tests requiring physical ADB connection"
    )
    group.addoption(
        "--skip-edge",
        action="store_true",
        default=os.environ.get("SKIP_EDGE_TESTS", "0").lower() in ("1", "true", "yes"),
        help="Skip tests requiring Cloudflare Pages edge routing"
    )


@pytest.fixture(scope="session")
def e2e_config(request) -> E2EConfig:
    """Session-scoped configuration object resolving CLI options and environment variables."""
    gateway_url = request.config.getoption("--gateway-url").rstrip("/")
    pages_url = request.config.getoption("--pages-url").rstrip("/")
    adb_device = request.config.getoption("--adb-device")
    apk_path = Path(request.config.getoption("--apk-path"))
    project_root = Path(__file__).resolve().parent.parent.parent

    # Measured empirical timeouts
    gateway_timeout = float(os.environ.get("GATEWAY_TIMEOUT", "10.0"))
    pages_timeout = float(os.environ.get("PAGES_TIMEOUT", "25.0"))
    ai_timeout = float(os.environ.get("AI_TIMEOUT", "45.0"))

    skip_hardware = request.config.getoption("--skip-hardware")
    skip_edge = request.config.getoption("--skip-edge")

    return E2EConfig(
        gateway_url=gateway_url,
        pages_url=pages_url,
        adb_device=adb_device,
        apk_path=apk_path,
        project_root=project_root,
        gateway_timeout=gateway_timeout,
        pages_timeout=pages_timeout,
        ai_timeout=ai_timeout,
        skip_hardware=skip_hardware,
        skip_edge=skip_edge
    )


@pytest.fixture(scope="session")
def adb(e2e_config: E2EConfig) -> ADBExecutor:
    """Session-scoped ADB executor instance."""
    return ADBExecutor(device=e2e_config.adb_device)


@pytest.fixture(scope="session")
def gateway_session(e2e_config: E2EConfig) -> Generator[requests.Session, None, None]:
    """Configured HTTP requests session for phone gateway with connection pooling."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 CloudPhone-E2E/1.0",
        "Accept": "application/json, image/jpeg, */*"
    })
    yield session
    session.close()


@pytest.fixture(scope="session")
def pages_session(e2e_config: E2EConfig) -> Generator[requests.Session, None, None]:
    """Configured HTTP requests session for Cloudflare Pages edge proxy with browser User-Agent."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, image/jpeg, */*"
    })
    yield session
    session.close()


@pytest.fixture(scope="function")
def wake_screen(adb: ADBExecutor, e2e_config: E2EConfig):
    """Function-scoped fixture ensuring phone screen is active before UI/touch tests."""
    if not e2e_config.skip_hardware:
        adb.wake_and_unlock()


@pytest.fixture(scope="function")
def cleanup_app_state(e2e_config: E2EConfig, gateway_session: requests.Session):
    """Teardown fixture ensuring com.netuark.app is stopped after test execution."""
    yield
    try:
        gateway_session.post(
            f"{e2e_config.gateway_url}/v1/screen/app",
            json={"package": "com.netuark.app", "action": "stop"},
            timeout=5.0
        )
    except Exception:
        pass


@pytest.fixture
def validate_jpeg_frame():
    """Helper fixture validating image bytes represent a valid JPEG of expected dimensions."""
    def _validate(content: bytes, expected_dims: Optional[Tuple[int, int]] = (360, 800), min_bytes: int = 1000) -> Image.Image:
        assert len(content) >= min_bytes, f"Frame byte length {len(content)} is less than minimum {min_bytes}"
        assert content.startswith(b"\xff\xd8"), f"Frame header does not match JPEG SOI marker (0xFFD8): starts with {content[:4]!r}"
        assert content.endswith(b"\xff\xd9"), f"Frame footer does not match JPEG EOI marker (0xFFD9): ends with {content[-4:]!r}"
        img = Image.open(io.BytesIO(content))
        assert img.format == "JPEG", f"Expected image format JPEG, got {img.format}"
        if expected_dims:
            assert img.size == expected_dims, f"Expected image dimensions {expected_dims}, got {img.size}"
        return img
    return _validate
