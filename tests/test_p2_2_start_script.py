"""P2-2 — arranque desde VS Code y creación del `.env`.

`scripts/start_mcp.py` es el comando que VS Code ejecuta (`.vscode/mcp.json`). Hace
dos cosas que no pueden vivir en el JSON de configuración: sacar la API key de un
archivo no versionado y negarse a quedarse colgado cuando el cliente MCP lo lanza
sin terminal interactiva.

El protocolo MCP viaja por stdout, así que estas pruebas también comprueban que el
script no escribe nada ahí: cualquier `print` normal rompería la sesión.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALID = {"ESPO_URL": "https://crm.test", "ESPO_API_KEY": "clave-de-prueba"}


def _starter():
    path = ROOT / "scripts" / "start_mcp.py"
    spec = importlib.util.spec_from_file_location("start_mcp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture()
def starter():
    return _starter()


# -- .env parsing -----------------------------------------------------------

def test_parse_env_ignores_comments_and_blank_lines(starter):
    text = (
        "# configuración\n"
        "\n"
        "ESPO_URL=https://crm.test\n"
        "export ESPO_API_KEY=\"abc#123\"\n"
        "SIN_IGUAL\n"
    )

    assert starter.parse_env_file(text) == {
        "ESPO_URL": "https://crm.test",
        "ESPO_API_KEY": "abc#123",
    }


def test_parse_env_strips_single_quotes(starter):
    assert starter.parse_env_file("ESPO_URL='https://crm.test'\n") == {
        "ESPO_URL": "https://crm.test"
    }


def test_load_env_missing_file_is_empty(starter, tmp_path):
    assert starter.load_env(tmp_path / "no-existe.env") == {}


# -- validation -------------------------------------------------------------

def test_validate_accepts_a_complete_configuration(starter):
    assert starter.validate(VALID) == []


def test_validate_reports_both_missing_variables(starter):
    problems = starter.validate({})

    assert len(problems) == 2
    assert any("ESPO_URL" in problem for problem in problems)
    assert any("ESPO_API_KEY" in problem for problem in problems)


def test_validate_rejects_a_url_without_scheme(starter):
    problems = starter.validate({**VALID, "ESPO_URL": "crm.test"})

    assert problems == ["ESPO_URL debe empezar por http:// o https:// (valor: 'crm.test')."]


def test_blank_value_counts_as_missing(starter):
    problems = starter.validate({"ESPO_URL": "   ", "ESPO_API_KEY": " "})

    assert len(problems) == 2


def test_url_is_normalised_and_trailing_slash_removed(starter):
    assert starter._normalise_url("crm.test/") == "https://crm.test"
    assert starter._normalise_url("http://host/espocrm/") == "http://host/espocrm"


# -- prompting and writing --------------------------------------------------

def test_prompt_keeps_the_existing_key_on_empty_answer(starter):
    values = starter.prompt_values(
        VALID,
        ask=lambda _: "",
        ask_secret=lambda _: "",
    )

    assert values == VALID


def test_prompt_asks_for_the_key_without_echoing_it(starter):
    asked: list[str] = []

    def ask(_: str) -> str:
        return "crm.test"

    def ask_secret(prompt: str) -> str:
        asked.append(prompt)
        return "nueva-clave"

    values = starter.prompt_values({}, ask, ask_secret)

    assert values == {"ESPO_URL": "https://crm.test", "ESPO_API_KEY": "nueva-clave"}
    assert asked == ["ESPO_API_KEY: "]


def test_setup_writes_a_readable_env_file(starter, tmp_path):
    path = tmp_path / ".env"

    values = starter.interactive_setup(
        {},
        path=path,
        ask=lambda _: "crm.test",
        ask_secret=lambda _: "clave-1",
    )

    assert values == {"ESPO_URL": "https://crm.test", "ESPO_API_KEY": "clave-1"}
    assert starter.parse_env_file(path.read_text(encoding="utf-8")) == values
    assert path.read_text(encoding="utf-8").count("\r") == 0  # LF, no CRLF


def test_setup_gives_up_without_writing_after_three_attempts(starter, tmp_path):
    path = tmp_path / ".env"

    values = starter.interactive_setup(
        {},
        path=path,
        ask=lambda _: "",
        ask_secret=lambda _: "",
    )

    assert values is None
    assert not path.exists()


# -- process environment ----------------------------------------------------

def test_process_environment_wins_over_the_file(starter, monkeypatch):
    monkeypatch.setenv("ESPO_URL", "https://desde-el-entorno.test")
    monkeypatch.delenv("ESPO_API_KEY", raising=False)

    environment = starter.merged_environment({"ESPO_URL": "https://del-archivo.test", "ESPO_API_KEY": "k"})

    assert environment["ESPO_URL"] == "https://desde-el-entorno.test"
    assert environment["ESPO_API_KEY"] == "k"


# -- main() -----------------------------------------------------------------

def _isolate(monkeypatch):
    monkeypatch.delenv("ESPO_URL", raising=False)
    monkeypatch.delenv("ESPO_API_KEY", raising=False)


def test_without_configuration_and_without_terminal_it_fails_fast(starter, monkeypatch, tmp_path, capsys):
    """VS Code no da terminal: quedarse leyendo stdin colgaría el arranque."""
    _isolate(monkeypatch)
    launched: list[object] = []

    code = starter.main(
        [],
        env_path=tmp_path / ".env",
        launcher=lambda environment, args: launched.append(environment) or 0,
    )

    assert code == 2
    assert launched == []
    assert "start_mcp.py --setup" in capsys.readouterr().err


def test_setup_mode_writes_and_does_not_launch(starter, monkeypatch, tmp_path):
    _isolate(monkeypatch)
    path = tmp_path / ".env"
    monkeypatch.setattr(
        starter, "interactive_setup", lambda existing, env_path: {**VALID}
    )
    launched: list[object] = []

    code = starter.main(
        ["--setup"],
        env_path=path,
        launcher=lambda environment, args: launched.append(environment) or 0,
    )

    assert code == 0
    assert launched == []


def test_it_launches_with_the_file_environment(starter, monkeypatch, tmp_path):
    _isolate(monkeypatch)
    path = tmp_path / ".env"
    path.write_text("ESPO_URL=https://del-archivo.test\nESPO_API_KEY=k\n", encoding="utf-8")
    captured: dict[str, object] = {}

    code = starter.main(
        ["--http"],
        env_path=path,
        launcher=lambda environment, args: captured.update(env=environment, args=list(args)) or 7,
    )

    assert code == 7
    assert captured["env"]["ESPO_URL"] == "https://del-archivo.test"
    assert captured["args"] == ["--http"]


def test_just_configured_values_beat_an_empty_environment(starter, monkeypatch, tmp_path):
    _isolate(monkeypatch)
    monkeypatch.setenv("ESPO_URL", "")
    monkeypatch.setattr(sys, "stdin", type("TTY", (), {"isatty": lambda self: True})())
    monkeypatch.setattr(
        starter, "interactive_setup", lambda existing, env_path: {**VALID}
    )
    captured: dict[str, object] = {}

    starter.main(
        [],
        env_path=tmp_path / ".env",
        launcher=lambda environment, args: captured.update(env=environment) or 0,
    )

    assert captured["env"]["ESPO_URL"] == "https://crm.test"


# -- .vscode/mcp.json -------------------------------------------------------

def test_mcp_json_starts_the_launcher_without_secrets():
    config = json.loads((ROOT / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    server = config["servers"]["espocrm"]

    assert server["type"] == "stdio"
    assert server["command"]
    assert any("scripts/start_mcp.py" in arg for arg in server["args"])
    assert "env" not in server, "las credenciales van al .env, no al archivo versionado"
