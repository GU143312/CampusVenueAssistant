"""Local, current-user Windows DPAPI storage. Never log settings or plaintext."""
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

MAGIC = b"CVA-DPAPI-1\x00"
ENTROPY = b"CampusVenueAssistant/openai/v1"  # App binding, not a secret.
MAX_BYTES = 65536


class CredentialError(RuntimeError):
    """A safe error message with no input values or underlying exception text."""


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str


def is_windows():
    return sys.platform == "win32"


def _require_windows():
    if not is_windows():
        raise CredentialError("Encrypted storage requires Windows. Use environment variables on other systems.")


def credential_path():
    _require_windows()
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise CredentialError("LOCALAPPDATA is unavailable; encrypted storage cannot be located.")
    return Path(base) / "CampusVenueAssistant" / "credentials.dpapi"


def _validate(api_key, model):
    for name, value, maximum in (("API key", api_key, 8192), ("model ID", model, 256)):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise CredentialError(f"Provide a non-empty, single-line {name}.")
    if any(c.isspace() for c in api_key.strip()) or any(c.isspace() for c in model.strip()):
        raise CredentialError("API key and model ID cannot contain whitespace.")
    return Settings(api_key.strip(), model.strip())


def _protect(plaintext):
    _require_windows()
    try:
        import win32crypt
        # UI_FORBIDDEN=1; deliberately omit LOCAL_MACHINE=4 (current-user scope).
        return win32crypt.CryptProtectData(plaintext, "CampusVenueAssistant", ENTROPY, None, None, 1)
    except Exception:
        raise CredentialError("Windows could not encrypt the configuration.") from None


def _unprotect(ciphertext):
    _require_windows()
    try:
        import win32crypt
        return win32crypt.CryptUnprotectData(ciphertext, ENTROPY, None, None, 1)[1]
    except Exception:
        raise CredentialError("Cannot decrypt saved configuration. Use the original Windows account or save it again.") from None


def _restrict_to_current_user(path):
    import ntsecuritycon
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    acl = win32security.ACL()
    acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)


def save_settings(api_key, model, *, path=None):
    _require_windows()
    settings = _validate(api_key, model)
    payload = json.dumps({"version": 1, "api_key": settings.api_key, "model": settings.model}).encode("utf-8")
    encrypted = MAGIC + _protect(payload)
    target = Path(path) if path is not None else credential_path()
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix="credentials-", suffix=".dpapi", dir=target.parent)
        temporary = Path(filename)
        with os.fdopen(fd, "wb") as stream:
            # The temporary file contains only ciphertext, even before ACL hardening.
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        _restrict_to_current_user(temporary)
        os.replace(temporary, target)
    except OSError:
        raise CredentialError("Could not save encrypted configuration; check local folder permissions.") from None
    except Exception:
        raise CredentialError("Could not secure the encrypted file. Existing configuration was preserved.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_settings(*, path=None):
    _require_windows()
    target = Path(path) if path is not None else credential_path()
    try:
        with target.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError:
        raise CredentialError("Cannot read encrypted configuration; check local folder permissions.") from None
    if len(data) > MAX_BYTES or not data.startswith(MAGIC):
        raise CredentialError("Saved configuration is invalid. Save it again.")
    plaintext = _unprotect(data[len(MAGIC):])
    try:
        payload = json.loads(plaintext)
        if not isinstance(payload, dict) or set(payload) != {"version", "api_key", "model"} or type(payload["version"]) is not int or payload["version"] != 1:
            raise ValueError
        return _validate(payload["api_key"], payload["model"])
    except (ValueError, TypeError, CredentialError):
        raise CredentialError("Decrypted configuration has an unsupported or invalid format. Save it again.") from None


def resolve_settings(environ: Mapping[str, str] | None = None, *, path=None):
    env = os.environ if environ is None else environ
    key, model = env.get("OPENAI_API_KEY", ""), env.get("AGENT_MODEL", "")
    if key and model:
        return _validate(key, model)
    saved = read_settings(path=path) if is_windows() else None
    key = key or (saved.api_key if saved else "")
    model = model or (saved.model if saved else "")
    if not key or not model:
        raise CredentialError("Configure API key and model: python -m scripts.configure_api set (Windows), or set OPENAI_API_KEY and AGENT_MODEL.")
    return _validate(key, model)


def delete_settings(*, path=None):
    _require_windows()
    target = Path(path) if path is not None else credential_path()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise CredentialError("Cannot remove encrypted configuration; check file permissions.") from None
