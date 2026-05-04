# Plan de Implementación — VidaQR Fase 1

## Visión General

Implementación incremental sobre el código Flask existente. Cada tarea construye sobre la anterior y termina con todos los componentes integrados. El lenguaje de implementación es **Python** (Flask + Jinja2 + smtplib + Hypothesis para PBT).

## Tareas

- [x] 1. Refactorizar módulo de email: función `_send_email` genérica y funciones puras de construcción
  - Renombrar / reemplazar `_send_reset_email` por una función genérica `_send_email(to_email, subject, text_body, html_body) -> bool` en `app.py`
  - Extraer `_build_reset_email(reset_url: str) -> tuple[str, str]` como función pura (sin efectos secundarios) que retorna `(text_body, html_body)` con la marca VidaQR, advertencia de 1 hora y aclaración de ignorar si no se solicitó
  - Extraer `_build_welcome_email(nombre: str | None, base_url: str) -> tuple[str, str]` como función pura que retorna `(text_body, html_body)` con nombre del producto, saludo personalizado, enlace a `/panel` y mención a etiquetas físicas
  - Actualizar la ruta `/forgot` para usar `_send_email` + `_build_reset_email`
  - Si `MAIL_SERVER` o `MAIL_USERNAME` están vacíos, imprimir el contenido del email en los logs (modo dev) en lugar de intentar enviar
  - Agregar advertencia `[WARN] FLASK_SECRET usa valor por defecto` en los logs al arrancar si `FLASK_SECRET` no está definida en el entorno
  - _Requisitos: 2.3, 2.4, 2.5, 2.6, 2.7, 3.3, 3.4, 5.1, 5.3_

  - [ ]* 1.1 Escribir tests de propiedad para `_build_welcome_email`
    - **Propiedad 2: El email de bienvenida contiene todos los elementos requeridos**
    - Para cualquier combinación de `nombre` (None o texto) y `base_url` válida, verificar que ambas versiones (texto y HTML) contienen "VidaQR", el enlace `/panel`, el nombre del usuario si fue proporcionado, y la palabra "etiqueta"
    - **Valida: Requisitos 2.2, 2.3, 6.4**

  - [ ]* 1.2 Escribir tests de propiedad para `_build_reset_email`
    - **Propiedad 3: El email de reset contiene todos los elementos requeridos y el token correcto**
    - Para cualquier `reset_url` válida, verificar que ambas versiones contienen "VidaQR", la URL completa de reset, la advertencia de 1 hora y la aclaración de ignorar
    - **Valida: Requisitos 3.2, 3.3, 3.4**

  - [ ]* 1.3 Escribir tests de propiedad para la dirección remitente y la URL base
    - **Propiedad 1: El email usa la dirección remitente configurada**
    - Para cualquier `MAIL_FROM` configurado, verificar que el header `From` de todos los emails usa esa dirección
    - **Propiedad 7: La URL base configurable se refleja en todos los enlaces de email**
    - Para cualquier `APP_BASE_URL` válida, verificar que todos los enlaces generados (reset y panel) comienzan con esa URL base
    - **Valida: Requisitos 2.6, 5.2**

- [x] 2. Integrar email de bienvenida en el flujo de registro
  - En la ruta `/register`, después del INSERT exitoso y antes del redirect, llamar a `_send_email` con el contenido construido por `_build_welcome_email(nombre, APP_BASE_URL)`
  - El envío debe ocurrir en un bloque `try/except`; si falla, registrar `[ERROR] send_welcome_email: ...` y continuar el flujo sin mostrar error al usuario
  - _Requisitos: 2.1, 2.2, 2.4, 6.4_

- [ ] 3. Checkpoint — Verificar módulo de email
  - Asegurarse de que todos los tests del módulo de email pasan. Consultar al usuario si surge alguna duda.

- [x] 4. Migración de base de datos: columna `status` en `qr_codes`
  - Crear la función `_ensure_qr_status_column()` en `app.py` que ejecuta `ALTER TABLE qr_codes ADD COLUMN status ENUM('unclaimed','active','inactive') NOT NULL DEFAULT 'unclaimed'` si la columna no existe
  - Después de agregar la columna, ejecutar un UPDATE para sincronizar el estado inicial: `UPDATE qr_codes SET status='active' WHERE user_id IS NOT NULL` y `UPDATE qr_codes SET status='unclaimed' WHERE user_id IS NULL`
  - Llamar a `_ensure_qr_status_column()` dentro del bloque `with app.app_context()` al arrancar, junto a `_ensure_profile_columns()`
  - Actualizar la ruta `/claim/<code>` para que el UPDATE de claim también establezca `status='active'` en la misma sentencia SQL
  - _Requisitos: 6.1_

  - [ ]* 4.1 Escribir tests de propiedad para la invariante status/user_id
    - **Propiedad 9: La invariante status/user_id se mantiene tras el claim**
    - Para cualquier `user_id` y `public_code` válidos, verificar que después del claim el UPDATE incluye `status='active'` y que el `user_id` queda asignado correctamente (usar mock de DB)
    - **Valida: Requisito 6.1**

- [x] 5. Página de inicio pública (`/`)
  - Modificar la ruta `/` en `app.py`: si `get_current_user()` retorna un usuario, redirigir a `/panel`; si no, renderizar `templates/index.html`
  - Crear `templates/index.html` con las siguientes secciones:
    - **Hero**: nombre "VidaQR", tagline sobre emergencias médicas, botón CTA principal que apunte a `/register`
    - **Cómo funciona**: 3 pasos (Comprá tu etiqueta → Completá tu ficha médica → Pegala donde importa)
    - **Casos de uso**: individuos, ciclistas, motociclistas, deportistas, adultos mayores
    - **Cómo obtener tu etiqueta** (preview Fase 2): descripción del proceso de compra futuro sin precios definitivos
    - **Navegación**: enlace a `/login` para usuarios existentes
    - **Meta Open Graph**: `og:title`, `og:description`, `og:image` en el `<head>`
  - El template debe ser responsive (funcional desde 375px de ancho) usando CSS inline o un `<style>` en el propio template, sin dependencias de JS bloqueantes
  - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 6.2, 6.3_

  - [ ]* 5.1 Escribir tests de ejemplo para la landing page
    - `GET /` sin sesión → HTTP 200 y renderiza `index.html`
    - La respuesta contiene un enlace a `/register` (CTA)
    - La respuesta contiene un enlace a `/login`
    - La respuesta contiene las meta tags `og:title`, `og:description`, `og:image`
    - La respuesta contiene la sección de casos de uso (ciclistas, motociclistas, etc.)
    - La respuesta contiene la sección "cómo obtener" o "próximamente"
    - **Valida: Requisitos 4.1, 4.3, 4.6, 4.7, 4.9, 4.10**

  - [ ]* 5.2 Escribir test de propiedad para el redirect de usuarios autenticados
    - **Propiedad 8: La ruta / redirige a /panel para usuarios autenticados**
    - Para cualquier sesión de usuario válida, `GET /` debe resultar en redirect a `/panel`
    - **Valida: Requisito 4.8**

- [ ] 6. Checkpoint — Verificar landing page y migración de DB
  - Asegurarse de que todos los tests de la landing page y de la migración de DB pasan. Consultar al usuario si surge alguna duda.

- [x] 7. Documentación de variables de entorno y archivo `.env.example`
  - Crear el archivo `.env.example` en la raíz del repositorio con todas las variables requeridas documentadas, con descripción de cada una y un valor de ejemplo no sensible:
    - `FLASK_SECRET`, `APP_BASE_URL`, `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`
    - `MYSQLHOST`, `MYSQLPORT`, `MYSQLDATABASE`, `MYSQLUSER`, `MYSQLPASSWORD`
  - Verificar que `.env` ya está en `.gitignore` (ya existe la entrada; solo confirmar)
  - _Requisitos: 5.2, 5.4, 5.5_

  - [ ]* 7.1 Escribir test de smoke para `.env.example` y `.gitignore`
    - Verificar que el archivo `.env.example` existe en la raíz del repositorio
    - Verificar que `.env` está listado en `.gitignore`
    - **Valida: Requisitos 5.4, 5.5**

- [ ] 8. Tests de propiedades restantes y tests de ejemplo de infraestructura
  - [ ]* 8.1 Escribir tests de propiedad para tokens de reset
    - **Propiedad 4: Los tokens de reset son únicos y suficientemente largos**
    - Generar N tokens con `secrets.token_urlsafe(32)` y verificar que todos son distintos entre sí y que su longitud decodificada es ≥ 32 bytes
    - **Valida: Requisito 3.1**

  - [ ]* 8.2 Escribir test de propiedad para invalidación del token tras uso
    - **Propiedad 5: El token de reset se invalida tras el uso exitoso**
    - Simular el flujo de reset exitoso con mock de DB y verificar que el UPDATE establece `reset_token=NULL` y `reset_expires=NULL`
    - **Valida: Requisito 3.7**

  - [ ]* 8.3 Escribir test de propiedad para respuesta idéntica en `/forgot`
    - **Propiedad 6: La respuesta de /forgot es idéntica para emails registrados y no registrados**
    - Para cualquier dirección de email (registrada o no), verificar que el código HTTP y el contenido de la respuesta son idénticos
    - **Valida: Requisito 3.8**

  - [ ]* 8.4 Escribir tests de ejemplo para health checks
    - `GET /health` → HTTP 200 + `{"status": "ok"}`
    - `GET /__ping__` → HTTP 200 + `"pong"`
    - **Valida: Requisitos 1.4, 1.5**

- [x] 9. Integración final — Conectar todos los componentes
  - Verificar que `_ensure_qr_status_column()` se llama correctamente al arrancar junto a `_ensure_profile_columns()`
  - Verificar que la ruta `/` usa la nueva lógica (landing vs. redirect a panel)
  - Verificar que la ruta `/register` llama a `_send_welcome_email` después del registro exitoso
  - Verificar que la ruta `/forgot` usa `_send_email` + `_build_reset_email`
  - Verificar que la ruta `/claim/<code>` actualiza `status='active'` en el mismo UPDATE
  - Verificar que la advertencia de `FLASK_SECRET` por defecto aparece en los logs al arrancar sin la variable definida
  - _Requisitos: 1.4, 1.5, 1.6, 2.1, 3.1, 3.7, 4.1, 4.8, 5.1, 5.3, 6.1_

- [x] 10. Checkpoint final — Asegurarse de que todos los tests pasan
  - Ejecutar la suite completa de tests. Asegurarse de que todos los tests pasan. Consultar al usuario si surge alguna duda.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia los requisitos específicos para trazabilidad
- Los tests de propiedades usan **Hypothesis** (`hypothesis>=6.0`, `pytest>=8.0`, `pytest-flask>=1.0`) — agregar solo a dependencias de desarrollo/testing, no a `requirements.txt` de producción
- Los tests de propiedades se ubican en `tests/test_properties.py` y los tests de ejemplo en `tests/test_examples.py`
- Las funciones puras `_build_welcome_email` y `_build_reset_email` permiten testear el contenido del email sin mocks de SMTP
- La columna `status` en `qr_codes` es la única modificación de esquema de Fase 1; el resto de cambios son en código Python y templates Jinja2
