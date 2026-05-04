"""
Tests de ejemplo para VidaQR Fase 1.
Usan pytest. No requieren DB ni SMTP real.

Tests cubiertos:
  - Tarea 7.1: Smoke test para .env.example y .gitignore (Valida: Requisitos 5.4, 5.5)
"""

import os
import pytest


# ---------------------------------------------------------------------------
# Tarea 7.1 — Smoke test para .env.example y .gitignore
# Valida: Requisitos 5.4, 5.5
# ---------------------------------------------------------------------------

# Raíz del repositorio: dos niveles arriba de este archivo (tests/)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_env_example_exists():
    """
    Verifica que el archivo .env.example existe en la raíz del repositorio.
    Valida: Requisito 5.4
    """
    env_example_path = os.path.join(REPO_ROOT, ".env.example")
    assert os.path.isfile(env_example_path), (
        f".env.example no encontrado en {REPO_ROOT}. "
        "Debe existir para documentar las variables de entorno requeridas."
    )


def test_env_in_gitignore():
    """
    Verifica que .env está listado en .gitignore para evitar subir secretos al repo.
    Valida: Requisito 5.5
    """
    gitignore_path = os.path.join(REPO_ROOT, ".gitignore")
    assert os.path.isfile(gitignore_path), ".gitignore no encontrado en la raíz del repositorio."

    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verificar que .env aparece como entrada (línea propia, no como parte de otra palabra)
    lines = [line.strip() for line in content.splitlines()]
    assert ".env" in lines, (
        ".env debe estar listado en .gitignore para evitar subir credenciales al repositorio."
    )


def test_env_example_not_in_gitignore():
    """
    Verifica que .env.example NO está en .gitignore (debe poder subirse al repo).
    Valida: Requisito 5.4
    """
    gitignore_path = os.path.join(REPO_ROOT, ".gitignore")
    assert os.path.isfile(gitignore_path), ".gitignore no encontrado en la raíz del repositorio."

    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = [line.strip() for line in content.splitlines()]
    assert ".env.example" not in lines, (
        ".env.example NO debe estar en .gitignore; debe poder subirse al repositorio "
        "para que otros desarrolladores puedan usarlo como referencia."
    )


def test_env_example_contains_required_variables():
    """
    Verifica que .env.example documenta todas las variables de entorno requeridas.
    Valida: Requisito 5.4
    """
    env_example_path = os.path.join(REPO_ROOT, ".env.example")
    with open(env_example_path, "r", encoding="utf-8") as f:
        content = f.read()

    required_vars = [
        "FLASK_SECRET",
        "APP_BASE_URL",
        "MAIL_SERVER",
        "MAIL_PORT",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_FROM",
        "MYSQLHOST",
        "MYSQLPORT",
        "MYSQLDATABASE",
        "MYSQLUSER",
        "MYSQLPASSWORD",
    ]

    for var in required_vars:
        assert var in content, (
            f"La variable '{var}' debe estar documentada en .env.example."
        )
