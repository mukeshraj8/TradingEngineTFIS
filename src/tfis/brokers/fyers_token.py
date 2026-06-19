from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
import requests
from dotenv import load_dotenv


VAGATOR_BASE = "https://api-t2.fyers.in/vagator/v2"
API_V3_BASE = "https://api-t1.fyers.in/api/v3"
DEFAULT_REDIRECT_URI = "https://myapi.fyers.in/"
TIMEOUT_SECONDS = 15
MAX_RETRIES = 2

PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


@dataclass(frozen=True, slots=True)
class FyersTokenPaths:
    repo_root: Path
    env_path: Path
    token_store: Path
    log_dir: Path


@dataclass(frozen=True, slots=True)
class FyersPreparedEnvironment:
    app_id: str
    client_id: str | None
    token_store: Path
    refreshed: bool


class FyersTokenRefreshError(RuntimeError):
    pass


def default_tfis_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_token_paths(repo_root: str | Path | None = None) -> FyersTokenPaths:
    root = Path(repo_root) if repo_root is not None else default_tfis_repo_root()
    return FyersTokenPaths(
        repo_root=root,
        env_path=root / ".env",
        token_store=root / "data" / "token_store.json",
        log_dir=root / "logs" / "token_refresh",
    )


def prepare_fyers_env_from_tfis(
    *,
    tfis_root: str | Path | None = None,
    skip_refresh: bool = False,
) -> FyersPreparedEnvironment:
    paths = default_token_paths(tfis_root)
    _require_exists(paths.repo_root, "TFIS root")
    _require_exists(paths.env_path, "TFIS .env")
    clear_proxy_environment()
    load_dotenv(paths.env_path, override=True)

    refreshed = False
    if not skip_refresh:
        refresh_fyers_token(paths=paths)
        refreshed = True

    token_payload = json.loads(paths.token_store.read_text(encoding="utf-8"))
    access_token = str(token_payload.get("access_token") or "").strip()
    app_id = _require_env("FYERS_APP_ID")
    client_id = os.getenv("FYERS_CLIENT_ID", "").strip() or None
    if not access_token:
        raise FyersTokenRefreshError(f"Missing access_token in TFIS token store: {paths.token_store}")

    os.environ["FYERS_APP_ID"] = app_id
    os.environ["FYERS_ACCESS_TOKEN"] = access_token
    if client_id:
        os.environ["FYERS_CLIENT_ID"] = client_id
    return FyersPreparedEnvironment(
        app_id=app_id,
        client_id=client_id,
        token_store=paths.token_store,
        refreshed=refreshed,
    )


def refresh_fyers_token(*, paths: FyersTokenPaths | None = None) -> Path:
    token_paths = paths or default_token_paths()
    _require_exists(token_paths.env_path, "TFIS .env")
    clear_proxy_environment()
    load_dotenv(token_paths.env_path, override=True)

    app_id = _require_env("FYERS_APP_ID")
    app_secret = _require_env("FYERS_APP_SECRET")
    fy_id = _require_env("FYERS_CLIENT_ID")
    pin = _require_env("FYERS_PIN")
    totp_secret = _require_env("FYERS_TOTP_SECRET")
    redirect_uri = os.getenv("FYERS_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()
    app_id_short = app_id.split("-")[0]

    _log(token_paths, "=" * 60)
    _log(token_paths, "  TFIS FYERS TOKEN REFRESH")
    _log(token_paths, "=" * 60)
    _log(token_paths, f"App ID    : {app_id}  (short: {app_id_short})")
    _log(token_paths, f"Client ID : {fy_id}")
    _log(token_paths, f"Token     : {token_paths.token_store}")

    request_key = _step1_initiate(token_paths, fy_id, app_id_short)
    request_key = _step2_verify_totp(token_paths, request_key, totp_secret)
    step3_type, step3_value = _step3_verify_pin(token_paths, request_key, pin)
    auth_code = (
        step3_value
        if step3_type == "auth_code"
        else _step4_request_auth_code(token_paths, step3_value, fy_id, app_id, redirect_uri)
    )
    access_token = _step5_exchange_token(token_paths, auth_code, app_id, app_secret, redirect_uri)
    _write_token(token_paths, access_token)
    _verify_token(token_paths, access_token, app_id)
    _log(token_paths, "=" * 60)
    _log(token_paths, "  TFIS TOKEN REFRESH COMPLETE")
    _log(token_paths, "=" * 60)
    return token_paths.token_store


def clear_proxy_environment() -> None:
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def _require_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise FyersTokenRefreshError(f"Missing {label}: {path}")


def _require_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value or value.startswith("<") or value.startswith("your_"):
        raise FyersTokenRefreshError(f"Missing required environment variable: {key}")
    return value


def _log(paths: FyersTokenPaths, message: str, level: str = "INFO") -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {level:<5} | {message}"
    print(line)
    try:
        paths.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = paths.log_dir / f"token_refresh_{datetime.now().strftime('%Y%m%d')}.log"
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _post(paths: FyersTokenPaths, url: str, payload: dict, step_name: str) -> dict:
    headers = {"Content-Type": "application/json"}
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
            try:
                body = response.json()
            except Exception as exc:
                last_error = f"JSON parse error: {exc}"
                _log(paths, f"{step_name}: HTTP {response.status_code} -- {last_error}", "WARN")
                if attempt <= MAX_RETRIES:
                    time.sleep(3)
                continue
            _log(paths, f"{step_name}: HTTP {response.status_code}  code={body.get('code')}  s={body.get('s')}")
            return body
        except requests.exceptions.Timeout:
            last_error = "timeout"
        except requests.exceptions.ConnectionError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
        if attempt <= MAX_RETRIES:
            _log(paths, f"{step_name}: attempt {attempt} failed ({last_error}) -- retrying in 3s", "WARN")
            time.sleep(3)
    raise FyersTokenRefreshError(f"{step_name}: all attempts failed. Last error: {last_error}")


def _extract_request_key(body: dict, fallback: str) -> str:
    return body.get("request_key") or (body.get("data") or {}).get("request_key") or fallback


def _parse_app_components(app_id: str) -> tuple[str, str]:
    if "-" not in app_id:
        raise FyersTokenRefreshError("FYERS_APP_ID must include the app type suffix, for example TE6J0QHDIX-100.")
    return tuple(app_id.rsplit("-", 1))  # type: ignore[return-value]


def _extract_auth_code_from_url(raw: str) -> str | None:
    if not raw or not raw.startswith("http"):
        return None
    query = parse_qs(urlparse(raw).query)
    return (query.get("auth_code") or [None])[0]


def _classify_step3_value(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    if not value:
        return ("missing", "")
    auth_code = _extract_auth_code_from_url(value)
    if auth_code:
        return ("auth_code", auth_code)
    return ("login_token", value)


def _app_id_hash(app_id: str, app_secret: str) -> str:
    return hashlib.sha256(f"{app_id}:{app_secret}".encode()).hexdigest()


def _step1_initiate(paths: FyersTokenPaths, fy_id: str, app_id_short: str) -> str:
    _log(paths, f"Step 1: Initiating login for Client ID: {fy_id}")
    body = _post(
        paths,
        f"{VAGATOR_BASE}/send_login_otp",
        {"fy_id": fy_id, "app_id": app_id_short},
        "Step 1 (initiate)",
    )
    key = body.get("request_key") or (body.get("data") or {}).get("request_key")
    if not key:
        raise FyersTokenRefreshError(f"Step 1 failed -- no request_key in response: {body}")
    _log(paths, "Step 1: OK -- request_key received")
    return str(key)


def _step2_verify_totp(paths: FyersTokenPaths, request_key: str, totp_secret: str) -> str:
    otp_code = pyotp.TOTP(totp_secret).now()
    remaining = int(30 - time.time() % 30)
    _log(paths, f"Step 2: Submitting TOTP (valid for {remaining}s more)")
    body = _post(
        paths,
        f"{VAGATOR_BASE}/verify_otp",
        {"request_key": request_key, "otp": otp_code},
        "Step 2 (TOTP)",
    )
    if body.get("s") != "ok":
        raise FyersTokenRefreshError(f"Step 2 (TOTP) failed -- {body}")
    key = _extract_request_key(body, request_key)
    _log(paths, "Step 2: OK -- TOTP accepted")
    return key


def _step3_verify_pin(paths: FyersTokenPaths, request_key: str, pin: str) -> tuple[str, str]:
    _log(paths, "Step 3: Verifying PIN")
    pin_b64 = base64.b64encode(pin.encode()).decode()
    body = _post(
        paths,
        f"{VAGATOR_BASE}/verify_pin_v2",
        {"request_key": request_key, "identity_type": "pin", "identifier": pin_b64},
        "Step 3 (PIN)",
    )
    if body.get("s") != "ok":
        raise FyersTokenRefreshError(f"Step 3 (PIN) failed -- {body}")
    raw = (body.get("data") or {}).get("access_token") or ""
    value_type, value = _classify_step3_value(raw)
    if value_type == "missing":
        raise FyersTokenRefreshError(f"Step 3 failed -- no usable token in response: {body}")
    _log(paths, f"Step 3: OK -- PIN verified, {value_type} received (length={len(value)})")
    return value_type, value


def _step4_request_auth_code(
    paths: FyersTokenPaths,
    login_token: str,
    fy_id: str,
    app_id: str,
    redirect_uri: str,
) -> str:
    _log(paths, "Step 4: Requesting auth_code via /api/v3/token")
    app_short, app_type = _parse_app_components(app_id)
    payload = {
        "fyers_id": fy_id,
        "app_id": app_short,
        "redirect_uri": redirect_uri,
        "appType": app_type,
        "code_challenge": "",
        "state": "None",
        "scope": "",
        "nonce": "",
        "response_type": "code",
        "create_cookie": True,
    }
    headers = {"Authorization": f"Bearer {login_token}", "Content-Type": "application/json"}
    try:
        response = requests.post(
            f"{API_V3_BASE}/token",
            json=payload,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        body = response.json()
    except Exception as exc:
        raise FyersTokenRefreshError(f"Step 4 failed -- {exc}") from exc
    _log(paths, f"Step 4 (/token): HTTP {response.status_code}  code={body.get('code')}  s={body.get('s')}")
    auth_code = _extract_auth_code_from_url(body.get("Url") or body.get("url") or "")
    if not auth_code:
        raise FyersTokenRefreshError(f"Step 4 failed -- no auth_code in /token response: {body}")
    _log(paths, f"Step 4: OK -- auth_code received (length={len(auth_code)})")
    return auth_code


def _step5_exchange_token(
    paths: FyersTokenPaths,
    auth_code: str,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
) -> str:
    _log(paths, "Step 5: Exchanging auth_code for access_token via SessionModel")
    try:
        from fyers_apiv3 import fyersModel

        session = fyersModel.SessionModel(
            client_id=app_id,
            secret_key=app_secret,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code",
        )
        session.set_token(auth_code)
        token_data = session.generate_token()
        access_token = token_data.get("access_token")
        if not access_token:
            raise FyersTokenRefreshError(
                "Step 5 failed -- no access_token in response: "
                f"{token_data} | appIdHash_prefix={_app_id_hash(app_id, app_secret)[:12]}"
            )
        _log(paths, f"Step 5: OK -- access_token received (length={len(access_token)})")
        return str(access_token)
    except FyersTokenRefreshError:
        raise
    except Exception as exc:
        raise FyersTokenRefreshError(f"Step 5 failed -- {exc}") from exc


def _write_token(paths: FyersTokenPaths, access_token: str) -> None:
    paths.token_store.parent.mkdir(parents=True, exist_ok=True)
    payload = {"access_token": access_token, "refreshed_at": datetime.now().isoformat()}
    tmp = paths.token_store.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(paths.token_store)
    _log(paths, f"Step 6: OK -- token written to {paths.token_store}")


def _verify_token(paths: FyersTokenPaths, access_token: str, app_id: str) -> None:
    _log(paths, "Step 7: Verifying new token via GET /user/profile")
    try:
        from fyers_apiv3 import fyersModel

        client = fyersModel.FyersModel(client_id=app_id, token=access_token, log_path="")
        response = client.get_profile()
    except Exception as exc:
        raise FyersTokenRefreshError(f"Step 7 failed -- profile check raised {exc}") from exc
    if response and response.get("s") == "ok":
        name = (response.get("data") or {}).get("name") or "unknown"
        _log(paths, f"Step 7: OK -- profile confirmed for '{name}'")
        return
    raise FyersTokenRefreshError(f"Step 7 failed -- profile check returned {response}")


__all__ = [
    "FyersPreparedEnvironment",
    "FyersTokenPaths",
    "FyersTokenRefreshError",
    "clear_proxy_environment",
    "default_tfis_repo_root",
    "default_token_paths",
    "prepare_fyers_env_from_tfis",
    "refresh_fyers_token",
]
