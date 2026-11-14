#!/usr/bin/env python3
"""Arranca el servidor MCP cargando `.env` — y lo crea si le falta configuración.

Visual Studio Code lanza este script como comando del servidor (`.vscode/mcp.json`).
El protocolo MCP viaja por **stdout**, así que aquí nunca se escribe en stdout: los
avisos van a stderr, y en modo interactivo se le preguntan los valores al usuario.

Modos:

    python scripts/start_mcp.py            # carga .env y arranca server.py
    python scripts/start_mcp.py --setup    # pregunta lo que falte, escribe .env y sale
    python scripts/start_mcp.py --http     # lo mismo, con transporte HTTP

Por qué existe en vez de poner las variables en `mcp.json`: la API key no debe
quedar en un archivo versionado, y así el mismo `.env` sirve para VS Code, para
`scripts/live_check.py` y para una terminal.

Diferencia importante entre los dos modos: cuando VS Code arranca el servidor no hay
terminal interactiva, así que si falta configuración el script **no se queda
esperando** — termina con código 2 y un mensaje accionable en el panel de MCP.
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
SERVER = ROOT / "server.py"

REQUIRED = ("ESPO_URL", "ESPO_API_KEY")
URL_PREFIXES = ("http://", "https://")

# Mensaje que ve el usuario cuando el servidor se lanza desde el cliente MCP y no
# hay forma de preguntar: debe decir exactamente qué ejecutar.
SETUP_HINT = (
    "Falta configuración de EspoCRM. Ejecuta una vez en la terminal:\n"
    "    python scripts/start_mcp.py --setup\n"
    "y vuelve a iniciar el servidor desde VS Code."
)


# ---------------------------------------------------------------------------
# Lectura y escritura del `.env`
# ---------------------------------------------------------------------------

def parse_env_file(text: str) -> dict[str, str]:
    """Lee `KEY=valor` ignorando comentarios, líneas vacías y comillas.

    No interpreta variables ni comentarios al final de la línea: prefiere ser
    predecible a ser listo, porque una API key puede contener `#`.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Las variables del archivo, o un diccionario vacío si todavía no existe."""
    if not path.exists():
        return {}
    return parse_env_file(path.read_text(encoding="utf-8"))


def merged_environment(values: dict[str, str]) -> dict[str, str]:
    """Entorno del proceso con `.env` como base; lo que ya está definido gana."""
    environment = dict(os.environ)
    for key, value in values.items():
        environment.setdefault(key, value)
    return environment


def render_env(values: dict[str, str]) -> str:
    """Contenido del `.env`, con las opcionales comentadas como recordatorio."""
    return (
        "# Generado por scripts/start_mcp.py. No se versiona (ver .gitignore).\n"
        "# Vuelve a ejecutar `python scripts/start_mcp.py --setup` para cambiarlo.\n"
        f"ESPO_URL={values['ESPO_URL']}\n"
        f"ESPO_API_KEY={values['ESPO_API_KEY']}\n"
        "\n"
        "# Opcionales: descomenta y ajusta si hacen falta. Ver .env.example.\n"
        "# MCP_ENTITY_ALLOW=Account,Contact,Opportunity\n"
        "# ESPO_AUTO_ASSIGN=1\n"
        "# ESPO_UTC_OFFSET=-5\n"
        "# ESPO_METADATA_MODE=frontend\n"
        "# ESPO_TIMEOUT=30\n"
        "# ESPO_LOG_LEVEL=INFO\n"
    )


def write_env(path: Path, values: dict[str, str]) -> None:
    """Escribe el `.env` con permisos de lectura sólo para el usuario (POSIX)."""
    path.write_text(render_env(values), encoding="utf-8", newline="\n")
    if os.name != "nt":
        path.chmod(0o600)


# ---------------------------------------------------------------------------
# Validación y preguntas
# ---------------------------------------------------------------------------

def validate(values: dict[str, str]) -> list[str]:
    """Problemas que impedirían arrancar, en texto accionable."""
    problems: list[str] = []
    url = (values.get("ESPO_URL") or "").strip()
    if not url:
        problems.append("ESPO_URL no está definida.")
    elif not url.lower().startswith(URL_PREFIXES):
        problems.append(f"ESPO_URL debe empezar por http:// o https:// (valor: {url!r}).")
    if not (values.get("ESPO_API_KEY") or "").strip():
        problems.append("ESPO_API_KEY no está definida.")
    return problems


def _normalise_url(value: str) -> str:
    """`crm.ejemplo.com` → `https://crm.ejemplo.com`, sin barra final.

    Escribir el esquema es lo que más se olvida al configurar esto, y adivinarlo no
    tiene riesgo: el servidor sólo habla HTTP(S).
    """
    url = value.strip().rstrip("/")
    if url and not url.lower().startswith(URL_PREFIXES):
        url = f"https://{url}"
    return url


def prompt_values(
    existing: dict[str, str],
    ask: Callable[[str], str] = input,
    ask_secret: Callable[[str], str] = getpass.getpass,
) -> dict[str, str]:
    """Pregunta las dos variables obligatorias conservando lo ya configurado.

    `ask`/`ask_secret` se inyectan para poder probar el flujo sin teclado.
    """
    values = dict(existing)

    current_url = values.get("ESPO_URL", "").strip()
    label = f"ESPO_URL [{current_url}]: " if current_url else "ESPO_URL (https://…): "
    answer = ask(label).strip()
    values["ESPO_URL"] = _normalise_url(answer or current_url)

    current_key = values.get("ESPO_API_KEY", "").strip()
    if current_key:
        answer = ask_secret("ESPO_API_KEY [ya definida, Enter para conservar]: ").strip()
        values["ESPO_API_KEY"] = answer or current_key
    else:
        values["ESPO_API_KEY"] = ask_secret("ESPO_API_KEY: ").strip()
    return values


def interactive_setup(
    existing: dict[str, str],
    path: Path = ENV_FILE,
    ask: Callable[[str], str] = input,
    ask_secret: Callable[[str], str] = getpass.getpass,
) -> dict[str, str] | None:
    """Pregunta hasta tres veces, escribe el `.env` y devuelve los valores.

    Devuelve None si no se consiguió una configuración válida; el `.env` anterior
    se deja intacto.
    """
    values = dict(existing)
    for _ in range(3):
        values = prompt_values(values, ask, ask_secret)
        problems = validate(values)
        if not problems:
            write_env(path, values)
            print(f"Configuración guardada en {path}", file=sys.stderr)
            return values
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print("Inténtalo de nuevo.", file=sys.stderr)
    print("No se guardó nada: la configuración sigue incompleta.", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

def resolve_python() -> str:
    """El intérprete con las dependencias instaladas.

    VS Code no siempre arranca con el entorno virtual del proyecto, así que se
    prefiere `.venv` cuando existe. `ESPO_PYTHON` permite forzar otro.
    """
    override = os.environ.get("ESPO_PYTHON", "").strip()
    if override:
        return override
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def missing_dependencies(python: str) -> bool:
    """True si ese intérprete no puede importar `mcp` y `httpx`."""
    probe = subprocess.run(
        [python, "-c", "import mcp, httpx"],
        capture_output=True,
        text=True,
    )
    return probe.returncode != 0


def launch(environment: dict[str, str], server_args: Iterable[str] = ()) -> int:
    """Ejecuta `server.py` heredando stdin/stdout, que es el canal MCP."""
    python = resolve_python()
    if missing_dependencies(python):
        print(
            f"Faltan dependencias en {python}.\n"
            "Instálalas con:  uv sync    (o  pip install -e .  en ese intérprete)",
            file=sys.stderr,
        )
        return 1
    command = [python, str(SERVER), *server_args]
    try:
        return subprocess.call(command, env=environment, cwd=str(ROOT))
    except FileNotFoundError:
        print(f"No encuentro el intérprete: {python}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def main(
    argv: list[str] | None = None,
    env_path: Path = ENV_FILE,
    launcher: Callable[[dict[str, str], Iterable[str]], int] = launch,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    setup_only = "--setup" in args
    server_args = [arg for arg in args if arg != "--setup"]

    environment = merged_environment(load_env(env_path))
    problems = validate(environment)
    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())

    if setup_only or (problems and interactive):
        configured = interactive_setup(
            {key: environment.get(key, "") for key in REQUIRED},
            env_path,
        )
        if configured is None:
            return 2
        environment = merged_environment(configured)
        # Lo que se acaba de escribir manda: un `ESPO_URL` vacío en el entorno del
        # proceso no debe ganarle al valor que el usuario tecleó.
        environment.update({key: configured[key] for key in REQUIRED if configured.get(key)})
        problems = validate(environment)
        if setup_only:
            return 0

    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(SETUP_HINT, file=sys.stderr)
        return 2

    return launcher(environment, server_args)


if __name__ == "__main__":
    raise SystemExit(main())
