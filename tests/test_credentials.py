import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app import credentials as c
from scripts import configure_api

WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
TEST_KEY = "not-a-real-api-key-for-local-tests"
TEST_MODEL = "test-model"


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path, monkeypatch):
    # Never inspect/overwrite the developer's real saved configuration or environment.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)


@WINDOWS
def test_native_dpapi_roundtrip_and_acl():
    import win32api
    import win32con
    import win32security

    c.save_settings(TEST_KEY, TEST_MODEL)
    blob = c.credential_path().read_bytes()
    assert TEST_KEY.encode() not in blob and TEST_MODEL.encode() not in blob
    assert c.read_settings() == c.Settings(TEST_KEY, TEST_MODEL)
    assert TEST_KEY not in repr(c.read_settings())
    sd = win32security.GetFileSecurity(str(c.credential_path()), win32security.DACL_SECURITY_INFORMATION)
    acl = sd.GetSecurityDescriptorDacl()
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    assert acl.GetAceCount() == 1 and acl.GetAce(0)[2] == sid
    c.save_settings(TEST_KEY + "-replacement", TEST_MODEL)
    assert c.read_settings().api_key == TEST_KEY + "-replacement"
    assert c.delete_settings() and not c.delete_settings()
    assert c.read_settings() is None


@WINDOWS
def test_fresh_process_load_without_key_environment():
    c.save_settings(TEST_KEY, TEST_MODEL)
    script = "from app.credentials import resolve_settings; s=resolve_settings(); assert s.api_key=='not-a-real-api-key-for-local-tests'; assert s.model=='test-model'; print('loaded')"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "loaded"
    assert TEST_KEY not in result.stdout + result.stderr


@WINDOWS
def test_tampering_rejected_and_existing_file_survives_failed_save(monkeypatch):
    c.save_settings(TEST_KEY, TEST_MODEL)
    original = c.credential_path().read_bytes()
    monkeypatch.setattr(c, "_restrict_to_current_user", lambda path: (_ for _ in ()).throw(OSError("fake failure")))
    with pytest.raises(c.CredentialError):
        c.save_settings("replacement", TEST_MODEL)
    assert c.credential_path().read_bytes() == original
    assert list(c.credential_path().parent.glob("credentials-*.dpapi")) == []
    altered = bytearray(original)
    altered[-1] ^= 1
    c.credential_path().write_bytes(altered)
    with pytest.raises(c.CredentialError, match="Cannot decrypt"):
        c.read_settings()


@WINDOWS
def test_cli_from_env_status_delete_no_disclosure(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", TEST_KEY)
    monkeypatch.setenv("AGENT_MODEL", TEST_MODEL)
    assert configure_api.main(["set", "--from-env"]) == 0
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("AGENT_MODEL")
    assert configure_api.main(["status"]) == 0
    assert c.resolve_settings().api_key == TEST_KEY
    assert configure_api.main(["delete"]) == 0
    output = capsys.readouterr()
    assert TEST_KEY not in output.out + output.err
    assert TEST_MODEL not in output.out + output.err


def test_environment_precedence_skips_bad_saved_file(monkeypatch):
    monkeypatch.setattr(c, "read_settings", lambda **kw: pytest.fail("Complete env must not read local credentials"))
    assert c.resolve_settings({"OPENAI_API_KEY":TEST_KEY,"AGENT_MODEL":TEST_MODEL}) == c.Settings(TEST_KEY, TEST_MODEL)


@pytest.mark.parametrize("env,expected", [
    ({}, c.Settings(TEST_KEY, TEST_MODEL)),
    ({"OPENAI_API_KEY":"override"}, c.Settings("override",TEST_MODEL)),
    ({"AGENT_MODEL":"other-model"}, c.Settings(TEST_KEY,"other-model")),
])
def test_partial_environment_fallback(monkeypatch, env, expected):
    monkeypatch.setattr(c,"is_windows",lambda:True)
    monkeypatch.setattr(c,"read_settings",lambda **kw:c.Settings(TEST_KEY,TEST_MODEL))
    assert c.resolve_settings(env) == expected


def test_nonwindows_missing_settings_and_encrypted_storage(monkeypatch):
    monkeypatch.setattr(c,"is_windows",lambda:False)
    monkeypatch.setattr(c,"read_settings",lambda **kw:pytest.fail("No DPAPI on Linux"))
    with pytest.raises(c.CredentialError,match="Configure API"):
        c.resolve_settings({})
    with pytest.raises(c.CredentialError,match="requires Windows"):
        c.save_settings(TEST_KEY, TEST_MODEL)


@pytest.mark.parametrize("key,model", [("",TEST_MODEL),(TEST_KEY,""),("secret\nvalue",TEST_MODEL),(TEST_KEY,"bad model"),("x"*8193,TEST_MODEL)], ids=["empty-key","empty-model","newline","space","oversized"])
def test_invalid_input_never_encrypted(monkeypatch,key,model):
    monkeypatch.setattr(c,"is_windows",lambda:True)
    monkeypatch.setattr(c,"_protect",lambda value:pytest.fail("Invalid data must not be encrypted"))
    with pytest.raises(c.CredentialError):
        c.save_settings(key,model)


@pytest.mark.parametrize("data", [b"plaintext-secret",c.MAGIC+b"x"*65537], ids=["bad-header","oversized-file"])
def test_invalid_file_rejected_before_decrypt(monkeypatch,tmp_path,data):
    monkeypatch.setattr(c,"is_windows",lambda:True)
    monkeypatch.setattr(c,"_unprotect",lambda value:pytest.fail("Bad header/size must fail before decrypt"))
    path=tmp_path / "bad.dpapi"
    path.write_bytes(data)
    with pytest.raises(c.CredentialError,match="invalid"):
        c.read_settings(path=path)


def test_bad_payload_redacted(monkeypatch,tmp_path):
    monkeypatch.setattr(c,"is_windows",lambda:True)
    monkeypatch.setattr(c,"_unprotect",lambda value:json.dumps({"api_key":TEST_KEY}).encode())
    path=tmp_path / "bad.dpapi"
    path.write_bytes(c.MAGIC+b"fake-encrypted")
    with pytest.raises(c.CredentialError) as error:
        c.read_settings(path=path)
    assert TEST_KEY not in str(error.value)


def test_hidden_input_fallback_refused(monkeypatch,capsys):
    import warnings
    def fallback(prompt):
        warnings.warn("no echo control",configure_api.getpass.GetPassWarning)
        pytest.fail("Echo fallback must not run")
    monkeypatch.setattr(configure_api.getpass,"getpass",fallback)
    assert configure_api.main(["set"]) == 1
    assert "Hidden input unavailable" in capsys.readouterr().out


def test_agent_startup_uses_resolved_key_without_environment_export(monkeypatch,capsys):
    from agent_layer import read_agent
    observed={}
    class Resource:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    def client(**kw):
        observed["key"]=kw["api_key"]
        return Resource()
    async def run(*args,**kw):
        assert kw["run_config"].tracing_disabled
        return SimpleNamespace(final_output="fake response",new_items=[])
    monkeypatch.setattr(read_agent,"resolve_settings",lambda:c.Settings(TEST_KEY,TEST_MODEL))
    monkeypatch.setattr(read_agent,"AsyncOpenAI",client)
    monkeypatch.setattr(read_agent,"server_connection",Resource)
    monkeypatch.setattr(read_agent,"OpenAIResponsesModel",lambda **kw:observed.update(model=kw["model"]))
    monkeypatch.setattr(read_agent,"make_agent",lambda *args:None)
    monkeypatch.setattr(read_agent.Runner,"run",run)
    asyncio.run(read_agent.main("test"))
    assert observed=={"key":TEST_KEY,"model":TEST_MODEL}
    assert "OPENAI_API_KEY" not in os.environ
    assert TEST_KEY not in capsys.readouterr().out
