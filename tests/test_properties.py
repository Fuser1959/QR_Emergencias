"""
Tests de propiedades para VidaQR Fase 1 — Tarea 1.
Usan Hypothesis + pytest. No requieren DB ni SMTP real.

Propiedades cubiertas:
  - P1: El email usa la dirección remitente configurada (Valida: Requisito 2.6)
  - P2: El email de bienvenida contiene todos los elementos requeridos (Valida: Requisitos 2.2, 2.3, 6.4)
  - P3: El email de reset contiene todos los elementos requeridos (Valida: Requisitos 3.2, 3.3, 3.4)
  - P7: La URL base configurable se refleja en todos los enlaces de email (Valida: Requisito 5.2)
"""

import sys
import os

# Asegurar que el directorio raíz del proyecto esté en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Importar las funciones puras desde app.py
from app import _build_reset_email, _build_welcome_email, _send_email


# ---------------------------------------------------------------------------
# Estrategias de generación
# ---------------------------------------------------------------------------

# URLs de reset válidas: esquema + host + path con token
_reset_url_strategy = st.builds(
    lambda scheme, host, token: f"{scheme}://{host}/reset/{token}",
    scheme=st.sampled_from(["http", "https"]),
    host=st.sampled_from(["localhost:5000", "vidaqr.com.ar", "example.com"]),
    token=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
        min_size=10,
        max_size=64,
    ),
)

# URLs base válidas
_base_url_strategy = st.builds(
    lambda scheme, host: f"{scheme}://{host}",
    scheme=st.sampled_from(["http", "https"]),
    host=st.sampled_from(["localhost:5000", "vidaqr.com.ar", "staging.vidaqr.com.ar"]),
)

# Nombres de usuario: None o texto no vacío
_nombre_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Zs")),
        min_size=1,
        max_size=50,
    ).filter(lambda s: s.strip()),
)

# Direcciones de email válidas (simplificadas para evitar caracteres problemáticos)
_email_strategy = st.builds(
    lambda local, domain: f"{local}@{domain}",
    local=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=1,
        max_size=20,
    ),
    domain=st.sampled_from(["gmail.com", "hotmail.com", "vidaqr.com.ar", "example.com"]),
)


# ---------------------------------------------------------------------------
# Tarea 1.1 — Propiedad 2: _build_welcome_email contiene todos los elementos
# Valida: Requisitos 2.2, 2.3, 6.4
# ---------------------------------------------------------------------------

@given(nombre=_nombre_strategy, base_url=_base_url_strategy)
@settings(max_examples=100)
def test_welcome_email_contains_required_elements(nombre, base_url):
    """
    **Validates: Requirements 2.2, 2.3, 6.4**

    Feature: vidaqr-fase1, Property 2: El email de bienvenida contiene todos los elementos requeridos.

    Para cualquier combinación de nombre (None o texto) y base_url válida,
    ambas versiones (texto y HTML) deben contener:
      - La marca "VidaQR"
      - El enlace al panel ("/panel")
      - El nombre del usuario si fue proporcionado
      - La palabra "etiqueta" (mención a etiquetas físicas)
    """
    text_body, html_body = _build_welcome_email(nombre, base_url)

    # Marca VidaQR presente en ambas versiones
    assert "VidaQR" in text_body, "text_body debe contener 'VidaQR'"
    assert "VidaQR" in html_body, "html_body debe contener 'VidaQR'"

    # Enlace al panel presente en ambas versiones
    assert "/panel" in text_body, "text_body debe contener '/panel'"
    assert "/panel" in html_body, "html_body debe contener '/panel'"

    # Nombre del usuario incluido si fue proporcionado
    if nombre:
        assert nombre in text_body or nombre in html_body, (
            f"El nombre '{nombre}' debe aparecer en text_body o html_body"
        )

    # Mención a etiquetas físicas
    assert "etiqueta" in text_body.lower(), "text_body debe mencionar 'etiqueta'"
    assert "etiqueta" in html_body.lower(), "html_body debe mencionar 'etiqueta'"


@given(nombre=_nombre_strategy, base_url=_base_url_strategy)
@settings(max_examples=100)
def test_welcome_email_panel_url_uses_base_url(nombre, base_url):
    """
    **Validates: Requirements 2.2, 5.2**

    El enlace al panel en el email de bienvenida debe comenzar con base_url.
    """
    text_body, html_body = _build_welcome_email(nombre, base_url)
    panel_url = f"{base_url}/panel"

    assert panel_url in text_body, (
        f"text_body debe contener el panel_url completo '{panel_url}'"
    )
    assert panel_url in html_body, (
        f"html_body debe contener el panel_url completo '{panel_url}'"
    )


# ---------------------------------------------------------------------------
# Tarea 1.2 — Propiedad 3: _build_reset_email contiene todos los elementos
# Valida: Requisitos 3.2, 3.3, 3.4
# ---------------------------------------------------------------------------

@given(reset_url=_reset_url_strategy)
@settings(max_examples=100)
def test_reset_email_contains_required_elements(reset_url):
    """
    **Validates: Requirements 3.2, 3.3, 3.4**

    Feature: vidaqr-fase1, Property 3: El email de reset contiene todos los elementos requeridos.

    Para cualquier reset_url válida, ambas versiones deben contener:
      - La marca "VidaQR"
      - La URL completa de reset
      - Advertencia de expiración en 1 hora
      - Aclaración de que puede ignorarse si no se solicitó
    """
    text_body, html_body = _build_reset_email(reset_url)

    # Marca VidaQR presente en ambas versiones
    assert "VidaQR" in text_body, "text_body debe contener 'VidaQR'"
    assert "VidaQR" in html_body, "html_body debe contener 'VidaQR'"

    # URL completa de reset presente en ambas versiones
    assert reset_url in text_body, f"text_body debe contener la reset_url '{reset_url}'"
    assert reset_url in html_body, f"html_body debe contener la reset_url '{reset_url}'"

    # Advertencia de expiración en 1 hora
    assert "1 hora" in text_body, "text_body debe advertir que el enlace expira en 1 hora"
    assert "1 hora" in html_body, "html_body debe advertir que el enlace expira en 1 hora"

    # Aclaración de que puede ignorarse
    assert "ignorar" in text_body.lower() or "ignorá" in text_body.lower(), (
        "text_body debe aclarar que puede ignorarse si no se solicitó"
    )
    assert "ignorar" in html_body.lower() or "ignorá" in html_body.lower(), (
        "html_body debe aclarar que puede ignorarse si no se solicitó"
    )


# ---------------------------------------------------------------------------
# Tarea 1.3 — Propiedad 1 y 7: dirección remitente y URL base en emails
# Valida: Requisitos 2.6, 5.2
# ---------------------------------------------------------------------------

@given(
    nombre=_nombre_strategy,
    base_url=_base_url_strategy,
    reset_url=_reset_url_strategy,
)
@settings(max_examples=100)
def test_app_base_url_reflected_in_email_links(nombre, base_url, reset_url):
    """
    **Validates: Requirements 5.2**

    Feature: vidaqr-fase1, Property 7: La URL base configurable se refleja en todos los enlaces de email.

    Para cualquier base_url válida, todos los enlaces generados en emails
    (panel en bienvenida) deben comenzar con esa URL base.
    """
    text_body, html_body = _build_welcome_email(nombre, base_url)

    # El enlace al panel debe comenzar con base_url
    assert base_url in text_body, (
        f"text_body del email de bienvenida debe contener base_url '{base_url}'"
    )
    assert base_url in html_body, (
        f"html_body del email de bienvenida debe contener base_url '{base_url}'"
    )


@given(
    mail_from=st.builds(
        lambda local, domain: f"{local}@{domain}",
        local=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz",
            min_size=1,
            max_size=20,
        ),
        domain=st.sampled_from(["vidaqr.com.ar", "example.com", "noreply.com"]),
    ),
    reset_url=_reset_url_strategy,
    nombre=_nombre_strategy,
    base_url=_base_url_strategy,
)
@settings(max_examples=100)
def test_send_email_uses_configured_from_address(mail_from, reset_url, nombre, base_url):
    """
    **Validates: Requirement 2.6**

    Feature: vidaqr-fase1, Property 1: El email usa la dirección remitente configurada.

    Para cualquier MAIL_FROM configurado, el mensaje construido debe usar
    esa dirección como remitente (header From).
    Verificamos que _send_email construye el mensaje con MAIL_FROM correcto
    interceptando smtplib.SMTP antes de que intente conectarse.
    """
    import app as app_module
    from unittest.mock import patch, MagicMock

    # Parchear las variables globales de configuración de email
    original_server = app_module.MAIL_SERVER
    original_username = app_module.MAIL_USERNAME
    original_from = app_module.MAIL_FROM

    try:
        app_module.MAIL_SERVER = "smtp.example.com"
        app_module.MAIL_USERNAME = "user@example.com"
        app_module.MAIL_FROM = mail_from

        captured_messages = []

        mock_smtp_instance = MagicMock()

        def capture_sendmail(from_addr, to_addrs, msg_string):
            captured_messages.append({"from": from_addr, "msg": msg_string})

        mock_smtp_instance.sendmail.side_effect = capture_sendmail
        mock_smtp_instance.__enter__ = lambda s: mock_smtp_instance
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)

        text_body, html_body = _build_reset_email(reset_url)

        with patch("smtplib.SMTP", return_value=mock_smtp_instance):
            result = app_module._send_email(
                "dest@example.com",
                "Test subject",
                text_body,
                html_body,
            )

        assert result is True, "_send_email debe retornar True cuando SMTP está configurado"
        assert len(captured_messages) == 1, "Debe haberse enviado exactamente un mensaje"
        assert captured_messages[0]["from"] == mail_from, (
            f"El remitente debe ser '{mail_from}', got '{captured_messages[0]['from']}'"
        )
        # Verificar que el header From aparece en el mensaje
        assert f"From: {mail_from}" in captured_messages[0]["msg"], (
            f"El header From debe contener '{mail_from}'"
        )
    finally:
        app_module.MAIL_SERVER = original_server
        app_module.MAIL_USERNAME = original_username
        app_module.MAIL_FROM = original_from


@given(reset_url=_reset_url_strategy)
@settings(max_examples=50)
def test_send_email_returns_false_when_not_configured(reset_url):
    """
    **Validates: Requirement 2.7**

    Cuando MAIL_SERVER o MAIL_USERNAME están vacíos, _send_email debe retornar False
    y no intentar conectarse a ningún servidor SMTP.
    """
    import app as app_module
    from unittest.mock import patch

    original_server = app_module.MAIL_SERVER
    original_username = app_module.MAIL_USERNAME

    try:
        app_module.MAIL_SERVER = ""
        app_module.MAIL_USERNAME = ""

        text_body, html_body = _build_reset_email(reset_url)

        with patch("smtplib.SMTP") as mock_smtp:
            result = app_module._send_email(
                "dest@example.com",
                "Test",
                text_body,
                html_body,
            )
            mock_smtp.assert_not_called()

        assert result is False, "_send_email debe retornar False cuando no hay config SMTP"
    finally:
        app_module.MAIL_SERVER = original_server
        app_module.MAIL_USERNAME = original_username
