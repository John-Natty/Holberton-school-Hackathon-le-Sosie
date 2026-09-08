"""Test/demo-only switches to disable a verify_expenses operation live.

Disabled by default: ENABLE_TEST_CONTROLS=1 must be explicitly set for these
endpoints and checks to do anything. State is an in-memory set for the
running process only - it resets on restart and is not shared across
multiple workers. That is acceptable for a single-process demo and must
not be relied on in production.
"""
import os

from app.calculation_request import OPERATIONS

_disabled_operations: set[str] = set()


def is_test_mode_enabled() -> bool:
    # Read live (not cached at import time) so it can be toggled per test
    # and so a running process reflects an updated .env after a restart.
    return os.environ.get("ENABLE_TEST_CONTROLS") == "1"


def get_operation_states() -> dict[str, bool]:
    """Every known operation mapped to whether it is currently enabled."""
    disabled = _disabled_operations if is_test_mode_enabled() else set()
    return {operation: operation not in disabled for operation in sorted(OPERATIONS)}


def is_operation_enabled(operation: str) -> bool:
    if not is_test_mode_enabled():
        return True
    return operation not in _disabled_operations


def set_operation_enabled(operation: str, enabled: bool) -> None:
    if operation not in OPERATIONS:
        raise ValueError(f"operation inconnue : {operation!r}")
    if enabled:
        _disabled_operations.discard(operation)
    else:
        _disabled_operations.add(operation)
