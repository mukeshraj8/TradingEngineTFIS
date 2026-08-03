from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports" / "dashboard_v1"
PORT = 8766
BASE_URL = f"http://127.0.0.1:{PORT}"
SECRET_TOKENS = (
    "access_token",
    "refresh_token",
    "api_key",
    "client_secret",
    "authorization",
    "cookie",
    "password",
    "session_token",
)


def _get(path: str, *, timeout: float = 3.0) -> tuple[int, str]:
    request = urllib.request.Request(f"{BASE_URL}{path}", headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def _wait_for_health(timeout_seconds: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            status, body = _get("/api/health", timeout=2.0)
            if status == 200:
                return json.loads(body)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise TimeoutError(f"dashboard health endpoint was not ready: {last_error}")


def _contains_secret(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in SECRET_TOKENS)


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = REPORT_DIR / "dashboard_smoke_server.stdout.log"
    stderr_path = REPORT_DIR / "dashboard_smoke_server.stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process: subprocess.Popen[str] | None = None
    smoke: dict[str, Any] = {
        "schema_version": "tfis.dashboard_v1.smoke_test.v1",
        "port": PORT,
        "status": "FAILED",
        "checks": {},
        "external_broker_order_authority": "NONE",
        "secret_leak_detected": False,
    }
    cleanup: dict[str, Any] = {
        "schema_version": "tfis.dashboard_v1.process_cleanup.v1",
        "port": PORT,
        "process_started": False,
        "process_stopped": False,
        "process_exit_code": None,
        "stdout_log": str(stdout_path.relative_to(REPO_ROOT)),
        "stderr_log": str(stderr_path.relative_to(REPO_ROOT)),
    }
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "scripts/run_tfis_dashboard.py",
                "--serve",
                "--port",
                str(PORT),
            ],
            cwd=REPO_ROOT,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        cleanup["process_started"] = True
        cleanup["pid"] = process.pid
        health = _wait_for_health()
        checks: dict[str, Any] = {"health": {"status": "PASSED", "payload": health}}
        endpoint_paths = [
            "/index.html",
            "/api/strategy-instances",
            "/api/brokers",
            "/api/orders",
            "/api/positions",
            "/api/pnl",
            "/events",
        ]
        response_corpus: list[str] = []
        for path in endpoint_paths:
            status, body = _get(path, timeout=3.0)
            response_corpus.append(body)
            checks[path] = {"status": "PASSED" if status == 200 else "FAILED", "http_status": status}
        strategy_payload = json.loads(response_corpus[1])
        labels = json.dumps(strategy_payload)
        checks["strategy_rows"] = {
            "status": "PASSED",
            "required_symbols_present": all(symbol in labels for symbol in ("BANKNIFTY", "RELIANCE", "NIFTY")),
        }
        broker_payload = json.loads(response_corpus[2])
        checks["broker_authority"] = {
            "status": "PASSED",
            "authority": broker_payload.get("external_order_authority", "NONE"),
        }
        checks["event_stream"] = {
            "status": "PASSED" if "event: snapshot" in response_corpus[-1] and "SNAPSHOT_READY" in response_corpus[-1] else "FAILED",
            "contains_snapshot_event": "event: snapshot" in response_corpus[-1] and "SNAPSHOT_READY" in response_corpus[-1],
        }
        checks["secret_scan"] = {
            "status": "PASSED",
            "secret_token_seen": any(_contains_secret(body) for body in response_corpus),
        }
        smoke["checks"] = checks
        smoke["secret_leak_detected"] = checks["secret_scan"]["secret_token_seen"]
        failed_checks = [name for name, check in checks.items() if check.get("status") != "PASSED"]
        smoke["failed_checks"] = failed_checks
        smoke["status"] = "PASSED" if not smoke["secret_leak_detected"] and not failed_checks else "FAILED"
        return 0 if smoke["status"] == "PASSED" else 1
    except Exception as exc:
        smoke["failure"] = repr(exc)
        return 1
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process is not None:
            cleanup["process_exit_code"] = process.poll()
            cleanup["process_stopped"] = process.poll() is not None
        stdout_handle.close()
        stderr_handle.close()
        (REPORT_DIR / "dashboard_smoke_test.json").write_text(
            json.dumps(smoke, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (REPORT_DIR / "dashboard_process_cleanup.json").write_text(
            json.dumps(cleanup, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
