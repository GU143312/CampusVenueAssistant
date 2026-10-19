"""Run in your own terminal. No key arguments, plaintext files or API calls."""
import argparse
import getpass
import os
import warnings

from app.credentials import CredentialError, delete_settings, read_settings, save_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Save/read/delete current-user Windows DPAPI configuration; no network calls.")
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("set", help="Save or replace encrypted API key and model")
    save.add_argument("--from-env", action="store_true", help="Save OPENAI_API_KEY and AGENT_MODEL from this terminal; values are not printed")
    commands.add_parser("status", help="Check decryption of the saved file without showing its values")
    commands.add_parser("delete", help="Delete the saved file; does not revoke the API key or clear environment variables")
    args = parser.parse_args(argv)
    try:
        if args.command == "set":
            if args.from_env:
                key, model = os.environ.get("OPENAI_API_KEY", ""), os.environ.get("AGENT_MODEL", "")
            else:
                with warnings.catch_warnings():
                    # Refuse getpass's echoing fallback on non-interactive terminals.
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    key = getpass.getpass("OpenAI API Key (hidden): ")
                model = input("Model ID (account-accessible model): ").strip()
            save_settings(key, model)
            print("Saved with Windows current-user DPAPI. Model startup will load it automatically. No API request was made.")
        elif args.command == "status":
            saved = read_settings()
            print("Saved configuration: readable; API key and model present." if saved else "No saved configuration.")
            if os.environ.get("OPENAI_API_KEY") or os.environ.get("AGENT_MODEL"):
                print("Environment variables are also present and take precedence at startup.")
            print("This checks local storage only, not API validity, model access or credits.")
        else:
            print("Saved configuration deleted." if delete_settings() else "No saved configuration.")
            print("Existing environment variables are unchanged; the API key was not revoked.")
        return 0
    except (CredentialError, getpass.GetPassWarning) as exc:
        print(str(exc) if isinstance(exc, CredentialError) else "Hidden input unavailable. Run this command in your own interactive terminal.")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Configuration cancelled; no new configuration saved.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
