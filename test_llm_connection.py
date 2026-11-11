"""Safely test the configured LLM provider from the project directory.

Run on Windows CMD with the virtual environment active:
    .venv\\Scripts\\python.exe test_llm_connection.py
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

secrets_file = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
if secrets_file.exists():
    try:
        secrets = tomllib.loads(secrets_file.read_text(encoding="utf-8"))
        for name, value in secrets.items():
            os.environ.setdefault(name, str(value))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"Could not read .streamlit/secrets.toml: {type(exc).__name__}") from exc

from processor import get_llm_settings, llm_health_check  # noqa: E402

settings = get_llm_settings()
if settings is None:
    print("RESULT: NO KEY FOUND. Configure GROQ_API_KEY or OPENAI_API_KEY in .streamlit/secrets.toml")
else:
    print(f"Provider: {settings['provider']}   Model: {settings['model']}   API key: found (hidden)")
    ok, message = llm_health_check()
    print("RESULT:", "API CALL SUCCEEDED" if ok else "API CALL FAILED")
    print(message)
