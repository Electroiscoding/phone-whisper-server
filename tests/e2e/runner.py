"""
runner.py - Orchestrated E2E Test Suite Runner for Cloud Phone NTA Project
Path: tests/e2e/runner.py
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cloud Phone NTA End-to-End Test Suite Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="all",
        choices=["1", "2", "3", "4", "5", "all"],
        help="Test tier to execute (1-4, 5, or 'all')"
    )
    parser.add_argument(
        "-m", "--marker",
        type=str,
        default=None,
        help="Custom pytest marker expression (e.g. 'tier1 or tier2')"
    )
    parser.add_argument(
        "-k", "--keyword",
        type=str,
        default=None,
        help="Pytest keyword expression filter"
    )
    parser.add_argument(
        "--gateway-url",
        type=str,
        default=os.environ.get("GATEWAY_URL", "http://192.168.29.2:8080"),
        help="Direct phone gateway URL"
    )
    parser.add_argument(
        "--pages-url",
        type=str,
        default=os.environ.get("PAGES_URL", "https://phone-whisper-server.pages.dev"),
        help="Cloudflare Pages edge proxy URL"
    )
    parser.add_argument(
        "--adb-device",
        type=str,
        default=os.environ.get("ADB_DEVICE", "192.168.29.2:5555"),
        help="ADB target device ID"
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=os.environ.get("REPORT_FILE", "test_reports/e2e_summary.json"),
        help="Path to generate structured JSON summary report"
    )
    parser.add_argument(
        "--report-json",
        type=str,
        default=None,
        help="Alias for --report-file"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable extra verbose pytest output"
    )
    parser.add_argument(
        "-x", "--exitfirst",
        action="store_true",
        help="Exit immediately on first test failure"
    )
    return parser.parse_args()


class ResultCollectorPlugin:
    """Pytest plugin collecting per-test outcomes and timing for structured reporting."""

    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def pytest_sessionstart(self, session):
        self.start_time = time.time()

    def pytest_sessionfinish(self, session, exitstatus):
        self.end_time = time.time()

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.failed):
            tier = "unknown"
            for marker in report.keywords:
                if marker in ["tier1", "tier2", "tier3", "tier4", "tier5"]:
                    tier = marker
                    break

            error_msg = ""
            if report.failed and report.longrepr:
                error_msg = str(report.longrepr)

            self.results.append({
                "nodeid": report.nodeid,
                "name": report.location[2] if report.location else report.nodeid,
                "tier": tier,
                "outcome": report.outcome,
                "duration": round(report.duration, 3),
                "error": error_msg
            })


def print_banner(args: argparse.Namespace):
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 78}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}   CLOUD PHONE NTA END-TO-END VERIFICATION TEST RUNNER{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 78}{Colors.END}")
    print(f"  Target Gateway : {Colors.YELLOW}{args.gateway_url}{Colors.END}")
    print(f"  Edge Pages     : {Colors.YELLOW}{args.pages_url}{Colors.END}")
    print(f"  ADB Device     : {Colors.YELLOW}{args.adb_device}{Colors.END}")
    print(f"  Target Tier    : {Colors.BOLD}{args.tier.upper()}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'-' * 78}{Colors.END}\n")


def print_summary_table(collector: ResultCollectorPlugin, total_duration: float):
    total = len(collector.results)
    passed = sum(1 for r in collector.results if r["outcome"] == "passed")
    failed = sum(1 for r in collector.results if r["outcome"] == "failed")
    skipped = sum(1 for r in collector.results if r["outcome"] == "skipped")

    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 78}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}   E2E TEST EXECUTION SUMMARY MATRIX{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 78}{Colors.END}")

    # Per-tier breakdown
    tiers = ["tier1", "tier2", "tier3", "tier4", "tier5", "unknown"]
    tier_labels = {
        "tier1": "Tier 1: Feature Coverage (50 Tests)",
        "tier2": "Tier 2: Boundary & Corner Cases (25 Tests)",
        "tier3": "Tier 3: Pairwise Combinations (7 Tests)",
        "tier4": "Tier 4: Real-World Scenarios (6 Tests)",
        "tier5": "Tier 5: Adversarial Stress & Security",
        "unknown": "General / Uncategorized"
    }

    for t in tiers:
        tier_tests = [r for r in collector.results if r["tier"] == t]
        if not tier_tests:
            continue
        t_passed = sum(1 for r in tier_tests if r["outcome"] == "passed")
        t_failed = sum(1 for r in tier_tests if r["outcome"] == "failed")
        t_skipped = sum(1 for r in tier_tests if r["outcome"] == "skipped")
        t_total = len(tier_tests)

        status_color = Colors.GREEN if t_failed == 0 else Colors.RED
        status_text = "PASS" if t_failed == 0 else f"{t_failed} FAIL"

        label = tier_labels.get(t, t).ljust(44)
        print(f"  {label} | Total: {t_total:2d} | Passed: {Colors.GREEN}{t_passed:2d}{Colors.END} | Failed: {status_color}{t_failed:2d}{Colors.END} | Skipped: {Colors.YELLOW}{t_skipped:2d}{Colors.END} | [{status_color}{status_text}{Colors.END}]")

    print(f"{Colors.BOLD}{Colors.CYAN}{'-' * 78}{Colors.END}")
    overall_color = Colors.GREEN if failed == 0 and total > 0 else Colors.RED
    print(f"  TOTAL TESTS: {total:3d} | PASSED: {Colors.GREEN}{passed:3d}{Colors.END} | FAILED: {Colors.RED}{failed:3d}{Colors.END} | SKIPPED: {Colors.YELLOW}{skipped:3d}{Colors.END}")
    print(f"  TOTAL DURATION: {total_duration:.2f}s")

    if failed == 0 and total > 0:
        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ [ACCEPTANCE CRITERIA MET]: All E2E test suites passed successfully!{Colors.END}\n")
    elif total == 0:
        print(f"\n{Colors.BOLD}{Colors.YELLOW}! [NO TESTS COLLECTED]: Verify marker expressions and test files.{Colors.END}\n")
    else:
        print(f"\n{Colors.BOLD}{Colors.RED}✗ [FAILURES DETECTED]: {failed} test(s) failed.{Colors.END}\n")


def write_json_report(report_path_str: str, args: argparse.Namespace, collector: ResultCollectorPlugin, total_duration: float, exit_code: int):
    report_path = Path(report_path_str)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exit_code": exit_code,
        "duration_seconds": round(total_duration, 3),
        "configuration": {
            "gateway_url": args.gateway_url,
            "pages_url": args.pages_url,
            "adb_device": args.adb_device,
            "tier": args.tier
        },
        "stats": {
            "total": len(collector.results),
            "passed": sum(1 for r in collector.results if r["outcome"] == "passed"),
            "failed": sum(1 for r in collector.results if r["outcome"] == "failed"),
            "skipped": sum(1 for r in collector.results if r["outcome"] == "skipped")
        },
        "tests": collector.results
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"  Structured report written to: {Colors.CYAN}{report_path.resolve()}{Colors.END}")


def main() -> int:
    args = parse_args()
    print_banner(args)

    report_file = args.report_json if args.report_json else args.report_file

    # Resolve test directory
    project_root = Path(__file__).resolve().parent.parent.parent
    test_dir = project_root / "tests" / "e2e"

    pytest_args = [
        str(test_dir),
        "-v" if args.verbose else "--tb=short",
        f"--gateway-url={args.gateway_url}",
        f"--pages-url={args.pages_url}",
        f"--adb-device={args.adb_device}",
    ]

    if args.exitfirst:
        pytest_args.append("-x")

    # Marker configuration
    if args.marker:
        pytest_args.extend(["-m", args.marker])
    elif args.tier != "all":
        pytest_args.extend(["-m", f"tier{args.tier}"])

    if args.keyword:
        pytest_args.extend(["-k", args.keyword])

    collector = ResultCollectorPlugin()
    start_time = time.time()
    ret_code = pytest.main(pytest_args, plugins=[collector])
    total_duration = time.time() - start_time

    print_summary_table(collector, total_duration)
    write_json_report(report_file, args, collector, total_duration, int(ret_code))

    return int(ret_code)


if __name__ == "__main__":
    sys.exit(main())
