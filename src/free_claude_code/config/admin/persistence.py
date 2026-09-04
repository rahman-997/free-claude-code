"""Sparse managed-config validation, preview, and atomic persistence."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from free_claude_code.config.env_files import (
    FCC_CONFIG_SCHEMA_ENV,
    dotenv_values_from_text,
)
from free_claude_code.config.env_migrations import (
    CONFIG_SCHEMA_VERSION,
    atomic_write_managed_config,
    recognized_env_keys,
    render_managed_config,
)
from free_claude_code.config.paths import config_lock_path, managed_env_path
from free_claude_code.config.provider_proxies import invalid_provider_proxy_keys
from free_claude_code.config.settings import Settings
from free_claude_code.core.interprocess_lock import InterprocessFileLock
from free_claude_code.core.json_types import JsonObject

from .manifest import FIELD_BY_KEY
from .state import ConfigInputValue
from .validation import settings_from_values
from .values import MASKED_SECRET, is_locked_source, load_value_state, normalize_for_env

_CONFIG_WRITE_CONFLICT_MESSAGE = (
    "Managed configuration changed in another FCC process. Reload Admin and retry."
)
_PROVIDER_PROXY_ERROR = (
    "must be a proxy URL with a supported scheme and host "
    "(for example http://127.0.0.1:8080 or socks5://127.0.0.1:1080)"
)


class ConfigWriteConflict(RuntimeError):
    """A prepared Admin snapshot is stale and must not overwrite newer state."""


@dataclass(frozen=True, slots=True)
class PreparedAdminUpdate:
    """Validated Admin update ready for an atomic managed-file commit."""

    target_values: dict[str, str]
    settings: Settings | None
    errors: tuple[str, ...]
    pending_fields: tuple[str, ...]
    path: Path
    base_digest: str | None

    @property
    def valid(self) -> bool:
        return self.settings is not None and not self.errors

    def validation_response(self) -> JsonObject:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "env_preview": render_managed_config(
                self.target_values,
                mask_secrets=True,
            ),
        }

    def applied_response(self) -> JsonObject:
        if not self.valid:
            return self.validation_response() | {
                "applied": False,
                "pending_fields": [],
            }
        return {
            "applied": True,
            "valid": True,
            "errors": [],
            "env_preview": render_managed_config(
                self.target_values,
                mask_secrets=True,
            ),
            "path": str(self.path),
            "pending_fields": list(self.pending_fields),
        }

    def conflict_response(self) -> JsonObject:
        """Return a retryable, secret-safe response for a stale Admin snapshot."""

        return {
            "applied": False,
            "valid": True,
            "errors": [_CONFIG_WRITE_CONFLICT_MESSAGE],
            "env_preview": render_managed_config(
                self.target_values,
                mask_secrets=True,
            ),
            "pending_fields": [],
            "conflict": True,
        }


def target_values_with_updates(
    updates: Mapping[str, ConfigInputValue],
) -> dict[str, str]:
    """Return sparse managed state after applying valid partial-update semantics."""

    values, _ = _target_values_with_updates_and_digest(updates)
    return values


def _target_values_with_updates_and_digest(
    updates: Mapping[str, ConfigInputValue],
) -> tuple[dict[str, str], str | None]:
    """Build an update from one managed-config snapshot and its revision token."""

    # Loading value state may consolidate/migrate the managed config. Capture the
    # revision only after that process-owned mutation, and derive target values
    # from the exact same bytes so the commit guard cannot reject our own migration
    # or accept a target assembled from an older file revision.
    state = load_value_state()
    path = managed_env_path()
    values, base_digest = _managed_config_snapshot(path)
    known = recognized_env_keys()
    for key in tuple(values):
        if key in known and key != FCC_CONFIG_SCHEMA_ENV and not values[key].strip():
            values.pop(key)

    for key, submitted in updates.items():
        field = FIELD_BY_KEY.get(key)
        if field is None or is_locked_source(state[key].source):
            continue
        if field.secret and (
            submitted == MASKED_SECRET
            or (isinstance(submitted, str) and not submitted.strip())
        ):
            continue
        value = normalize_for_env(submitted)
        if value is None or (field.nullable and not value):
            values.pop(key, None)
        else:
            values[key] = value

    values[FCC_CONFIG_SCHEMA_ENV] = CONFIG_SCHEMA_VERSION
    return values, base_digest


def changed_pending_fields(
    updates: Mapping[str, ConfigInputValue],
    *,
    settings: Settings,
) -> list[str]:
    """Return changed fields that require manual runtime action."""

    state = load_value_state()
    pending: list[str] = []
    for key, submitted in updates.items():
        field = FIELD_BY_KEY.get(key)
        if field is None or is_locked_source(state[key].source):
            continue
        if field.secret and (
            submitted == MASKED_SECRET
            or (isinstance(submitted, str) and not submitted.strip())
        ):
            continue
        requires_restart = field.restart_required or field.session_sensitive
        if not requires_restart:
            requires_restart = _active_voice_credential(settings) == key
        if not requires_restart:
            continue
        if normalize_for_env(submitted) == state[key].value:
            continue
        pending.append(key)
    return pending


def prepare_admin_update(
    updates: Mapping[str, ConfigInputValue],
) -> PreparedAdminUpdate:
    """Validate an update and construct its prospective Settings snapshot."""

    path = managed_env_path()
    update_errors = _update_protocol_errors(updates)
    target_values, base_digest = _target_values_with_updates_and_digest(updates)
    settings, settings_errors = settings_from_values(target_values)
    errors = (
        *update_errors,
        *settings_errors,
        *_provider_proxy_errors(target_values),
    )
    pending_fields = (
        tuple(changed_pending_fields(updates, settings=settings))
        if settings is not None and not errors
        else ()
    )
    return PreparedAdminUpdate(
        target_values=target_values,
        settings=settings,
        errors=errors,
        pending_fields=pending_fields,
        path=path,
        base_digest=base_digest,
    )


def commit_prepared_admin_update(prepared: PreparedAdminUpdate) -> JsonObject:
    """Atomically persist a previously validated Admin update."""

    if not prepared.valid:
        raise ValueError("Cannot commit an invalid Admin update")

    lock = InterprocessFileLock(config_lock_path())
    if not lock.acquire(wait=True, timeout=10.0):
        raise TimeoutError(
            f"Could not acquire managed-config lock: {config_lock_path()}"
        )
    try:
        if _managed_config_digest(prepared.path) != prepared.base_digest:
            raise ConfigWriteConflict(_CONFIG_WRITE_CONFLICT_MESSAGE)
        atomic_write_managed_config(prepared.target_values, path=prepared.path)
        return prepared.applied_response()
    finally:
        lock.release()


def _managed_config_snapshot(path: Path) -> tuple[dict[str, str], str | None]:
    """Read one managed config exactly once and return values plus revision."""

    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return {}, None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Could not parse configuration file {path}: not UTF-8") from exc
    try:
        values = dotenv_values_from_text(text)
    except ValueError as exc:
        raise ValueError(f"Could not parse configuration file {path}: {exc}") from exc
    return values, hashlib.sha256(content).hexdigest()


def _managed_config_digest(path: Path) -> str | None:
    """Return a secret-free revision token for one managed config snapshot."""

    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return None
    return hashlib.sha256(content).hexdigest()


def _update_protocol_errors(
    updates: Mapping[str, ConfigInputValue],
) -> tuple[str, ...]:
    errors: list[str] = []
    for key, submitted in updates.items():
        field = FIELD_BY_KEY.get(key)
        if field is None or (field.secret and submitted == MASKED_SECRET):
            continue
        if submitted is None and not field.nullable:
            errors.append(f"{key}: this setting cannot be removed")
            continue
        if (
            not field.secret
            and isinstance(submitted, str)
            and not submitted.strip()
            and not field.nullable
        ):
            errors.append(f"{key}: this setting cannot be blank")
    return tuple(errors)


def _provider_proxy_errors(values: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        f"{key}: {_PROVIDER_PROXY_ERROR}" for key in invalid_provider_proxy_keys(values)
    )


def _active_voice_credential(settings: Settings) -> str | None:
    if not settings.voice_note_enabled:
        return None
    if settings.whisper_device == "nvidia_nim":
        return "NVIDIA_NIM_API_KEY"
    return "HUGGINGFACE_API_KEY"
