from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from tfis.broker.authentication.models import (
    BrokerAuthenticationFailure,
    BrokerAuthenticationRequest,
    BrokerAuthenticationResult,
    BrokerCredentialReference,
    BrokerSessionIdentity,
    BrokerSessionStatus,
    ValidatedBrokerSession,
    canonical_hash,
    fingerprint,
)
from tfis.brokers.fyers_token import (
    FyersPreparedEnvironment,
    FyersTokenRefreshError,
    default_token_paths,
    prepare_fyers_env_from_tfis,
)


class FyersAuthenticationAdapter:
    """Reusable FYERS authentication/session boundary around the canonical token flow."""

    broker = "fyers"

    def __init__(
        self,
        *,
        tfis_root: str | Path | None = None,
        logical_account_ref: str = "default",
        environment: str = "local",
        now_provider: Callable[[], datetime] | None = None,
        session_client_factory: Callable[[str, str], Any] | None = None,
        prepare_environment: Callable[..., FyersPreparedEnvironment] = prepare_fyers_env_from_tfis,
        gitignore_path: str | Path | None = None,
    ) -> None:
        self._paths = default_token_paths(tfis_root)
        self._logical_account_ref = logical_account_ref
        self._environment = environment
        self._now = now_provider or datetime.now
        self._session_client_factory = session_client_factory or _default_fyers_client_factory
        self._prepare_environment = prepare_environment
        self._gitignore_path = Path(gitignore_path) if gitignore_path is not None else self._paths.repo_root / ".gitignore"

    @property
    def credential_reference(self) -> BrokerCredentialReference:
        return BrokerCredentialReference(
            source_type="LOCAL_TOKEN_STORE",
            path=str(self._paths.token_store),
            schema="json.access_token + optional refreshed_at",
            ignored_by_git=_is_ignored_by_git(self._paths.repo_root, self._paths.token_store, self._gitignore_path),
        )

    def build_request(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationRequest:
        return BrokerAuthenticationRequest(
            broker=self.broker,
            logical_account_ref=self._logical_account_ref,
            environment=self._environment,
            credential_reference=self.credential_reference,
            authentication_method="canonical_tfis_fyers_token_store",
            validate_session=validate_session,
            allow_refresh=allow_refresh,
        )

    def authenticate(self, *, allow_refresh: bool = False, validate_session: bool = True) -> BrokerAuthenticationResult:
        observed_at = self._now()
        credential_ref = self.credential_reference
        preflight_status = self._preflight_status(allow_refresh=allow_refresh)
        if preflight_status is not None:
            return self._failure(preflight_status[0], preflight_status[1], preflight_status[2], observed_at, credential_ref)
        try:
            prepared = self._prepare_environment(
                tfis_root=self._paths.repo_root,
                skip_refresh=not allow_refresh,
            )
        except FyersTokenRefreshError as exc:
            status = _classify_refresh_error(str(exc))
            action = (
                "Run .\\.venv\\Scripts\\python.exe scripts\\fyers_token_refresh.py --prepare from the TFIS repository."
                if status in {BrokerSessionStatus.TOKEN_MISSING, BrokerSessionStatus.TOKEN_EXPIRED, BrokerSessionStatus.TOKEN_REJECTED}
                else "Review FYERS .env configuration and token-store JSON."
            )
            return self._failure(status, str(exc), action, observed_at, credential_ref)
        except Exception as exc:
            return self._failure(
                BrokerSessionStatus.SESSION_VALIDATION_FAILED,
                str(exc),
                "Review FYERS authentication setup.",
                observed_at,
                credential_ref,
            )

        access_token = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
        if not access_token:
            return self._failure(
                BrokerSessionStatus.TOKEN_MISSING,
                "Canonical token preparation did not provide FYERS_ACCESS_TOKEN.",
                "Run the canonical FYERS token refresh command.",
                observed_at,
                credential_ref,
            )
        try:
            client = self._session_client_factory(prepared.app_id, access_token)
        except Exception as exc:
            return self._failure(
                BrokerSessionStatus.SESSION_VALIDATION_FAILED,
                str(exc),
                "Install/use the existing FYERS environment before live read-only diagnostics.",
                observed_at,
                credential_ref,
            )

        validation_payload: Mapping[str, Any] = {}
        if validate_session:
            try:
                validation_payload = client.get_profile()
            except Exception as exc:
                return self._failure(_classify_exception(str(exc)), str(exc), "Retry when network/broker is available.", observed_at, credential_ref)
            validation_status = _classify_profile_payload(validation_payload)
            if validation_status != BrokerSessionStatus.AUTHENTICATED:
                return self._failure(
                    validation_status,
                    str(validation_payload.get("message") or validation_payload.get("errmsg") or validation_status.value),
                    "Run the canonical FYERS token refresh command.",
                    observed_at,
                    credential_ref,
                )

        identity = BrokerSessionIdentity(
            broker=self.broker,
            logical_account_ref=self._logical_account_ref,
            environment=self._environment,
            app_id_prefix=prepared.app_id.split("-")[0] if prepared.app_id else None,
            client_id_fingerprint=fingerprint(prepared.client_id),
            credential_reference=credential_ref,
            authenticated_at=observed_at,
            expires_at=None,
            identity_hash=canonical_hash(
                {
                    "broker": self.broker,
                    "logical_account_ref": self._logical_account_ref,
                    "environment": self._environment,
                    "app_id_prefix": prepared.app_id.split("-")[0] if prepared.app_id else None,
                    "client_id_fingerprint": fingerprint(prepared.client_id),
                    "token_store": str(prepared.token_store),
                }
            ),
        )
        session = ValidatedBrokerSession(identity=identity, client=client, validation_payload=validation_payload)
        return BrokerAuthenticationResult(
            broker=self.broker,
            logical_account_ref=self._logical_account_ref,
            environment=self._environment,
            observed_at=observed_at,
            status=BrokerSessionStatus.AUTHENTICATED,
            credential_reference=credential_ref,
            session_identity=identity,
            session=session,
            refreshed=prepared.refreshed,
        )

    def _preflight_status(self, *, allow_refresh: bool) -> tuple[BrokerSessionStatus, str, str] | None:
        if not self._paths.env_path.exists():
            return (
                BrokerSessionStatus.APP_CONFIGURATION_MISSING,
                f"Missing FYERS .env configuration: {self._paths.env_path}",
                "Create/update the existing TFIS .env FYERS configuration.",
            )
        try:
            payload = json.loads(self._paths.token_store.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if allow_refresh:
                return None
            return (
                BrokerSessionStatus.CREDENTIAL_SOURCE_MISSING,
                f"Missing FYERS token store: {self._paths.token_store}",
                "Run .\\.venv\\Scripts\\python.exe scripts\\fyers_token_refresh.py --prepare.",
            )
        except json.JSONDecodeError:
            return (
                BrokerSessionStatus.TOKEN_SCHEMA_INVALID,
                f"Invalid FYERS token-store JSON: {self._paths.token_store}",
                "Repair or regenerate the canonical FYERS token store.",
            )
        if not isinstance(payload, Mapping):
            return (
                BrokerSessionStatus.TOKEN_SCHEMA_INVALID,
                f"FYERS token store must be a JSON object: {self._paths.token_store}",
                "Regenerate the canonical FYERS token store.",
            )
        if not str(payload.get("access_token") or "").strip():
            if allow_refresh:
                return None
            return (
                BrokerSessionStatus.TOKEN_MISSING,
                f"Missing access_token in FYERS token store: {self._paths.token_store}",
                "Run .\\.venv\\Scripts\\python.exe scripts\\fyers_token_refresh.py --prepare.",
            )
        return None

    def _failure(
        self,
        status: BrokerSessionStatus,
        message: str,
        operator_action_required: str,
        observed_at: datetime,
        credential_ref: BrokerCredentialReference,
    ) -> BrokerAuthenticationResult:
        failure = BrokerAuthenticationFailure(
            status=status,
            message=message,
            operator_action_required=operator_action_required,
            evidence={
                "token_store": str(self._paths.token_store),
                "env_path": str(self._paths.env_path),
                "canonical_refresh_script": "scripts/fyers_token_refresh.py",
            },
        )
        return BrokerAuthenticationResult(
            broker=self.broker,
            logical_account_ref=self._logical_account_ref,
            environment=self._environment,
            observed_at=observed_at,
            status=status,
            credential_reference=credential_ref,
            failure=failure,
        )


def _default_fyers_client_factory(app_id: str, access_token: str) -> Any:
    from fyers_apiv3 import fyersModel

    return fyersModel.FyersModel(client_id=app_id, token=access_token, log_path="")


def _classify_refresh_error(message: str) -> BrokerSessionStatus:
    lowered = message.lower()
    if "missing tfis .env" in lowered or "missing required environment variable" in lowered:
        return BrokerSessionStatus.APP_CONFIGURATION_MISSING
    if "invalid tfis token store json" in lowered:
        return BrokerSessionStatus.TOKEN_SCHEMA_INVALID
    if "missing access_token" in lowered:
        return BrokerSessionStatus.TOKEN_MISSING
    if "profile check returned" in lowered or "profile rejected" in lowered:
        return BrokerSessionStatus.TOKEN_REJECTED
    if "timeout" in lowered or "connection" in lowered:
        return BrokerSessionStatus.NETWORK_UNAVAILABLE
    if "rate" in lowered or "429" in lowered:
        return BrokerSessionStatus.RATE_LIMITED
    if "totp" in lowered or "pin" in lowered or "auth_code" in lowered or "login" in lowered:
        return BrokerSessionStatus.INTERACTIVE_LOGIN_REQUIRED
    return BrokerSessionStatus.SESSION_VALIDATION_FAILED


def _classify_exception(message: str) -> BrokerSessionStatus:
    lowered = message.lower()
    if "timeout" in lowered or "connection" in lowered or "network" in lowered:
        return BrokerSessionStatus.NETWORK_UNAVAILABLE
    if "rate" in lowered or "429" in lowered:
        return BrokerSessionStatus.RATE_LIMITED
    return BrokerSessionStatus.SESSION_VALIDATION_FAILED


def _classify_profile_payload(payload: Mapping[str, Any]) -> BrokerSessionStatus:
    status = str(payload.get("s") or payload.get("status") or "").lower()
    code = str(payload.get("code") or "").lower()
    message = str(payload.get("message") or payload.get("errmsg") or "").lower()
    if status == "ok" or status == "success":
        return BrokerSessionStatus.AUTHENTICATED
    if code in {"-16", "401"} or "unauthorized" in message:
        return BrokerSessionStatus.TOKEN_REJECTED
    if "expired" in message:
        return BrokerSessionStatus.TOKEN_EXPIRED
    if "rate" in message or code == "429":
        return BrokerSessionStatus.RATE_LIMITED
    if not payload:
        return BrokerSessionStatus.MALFORMED_RESPONSE
    return BrokerSessionStatus.SESSION_VALIDATION_FAILED


def _is_ignored_by_git(repo_root: Path, token_store: Path, gitignore_path: Path) -> bool | None:
    try:
        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    rel = token_store.relative_to(repo_root).as_posix()
    return any(line.strip().rstrip("/") in {rel, rel.split("/")[0]} for line in lines if line.strip() and not line.strip().startswith("#"))


__all__ = ["FyersAuthenticationAdapter"]
