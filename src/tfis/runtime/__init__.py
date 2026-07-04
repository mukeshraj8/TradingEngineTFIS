"""Runtime guardrails for TFIS operational processes."""

from .process_lock import (
    CRITICAL_DUPLICATE_PROCESS_SHUTDOWN,
    STALE_PROCESS_LOCK_RECLAIMED,
    ProcessLockError,
    ProcessLockHandle,
    acquire_process_lock,
)

__all__ = [
    "CRITICAL_DUPLICATE_PROCESS_SHUTDOWN",
    "STALE_PROCESS_LOCK_RECLAIMED",
    "ProcessLockError",
    "ProcessLockHandle",
    "acquire_process_lock",
]
