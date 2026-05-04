# Documento de Requisitos — VidaQR Fase 1

## Introducción

VidaQR es un sistema de etiquetas QR de emergencia médica. El usuario pega una etiqueta física (en su mochila, casco, auto, etc.) y cualquier persona que la escanee en una emergencia accede de inmediato a datos críticos: nombre, grupo sanguíneo, alergias y contactos de emergencia.

La Fase 1 establece la base operativa del producto: infraestructura estable en Railway con dominio propio y SSL, email transaccional funcional mediante Brevo (bienvenida al registrarse + reset de contraseña), y una página de inicio pública que comunique el valor del producto y prepare el terreno para la monetización de la Fase 2.

El código base ya incluye: autenticación (login/register), perfil médico, claim de QR, ficha pública de emergencia, reset de contraseña, protección CSRF y rate limiting.

---

## Glosario

- **VidaQR**: Nombre del producto. Sistema de etiquetas QR de emergencia médica.
- **App**: La aplicación web Flask desplegada en Railway.
- **Usuario**: Persona registrada que posee una o más etiquetas QR.
- **Visitante**: Persona no autenticada que accede a la App (puede ser quien escanea un QR en una emergencia o un potencial cliente).
- **Ficha de Emergencia**: Página pública accesible al escanear un QR, que muestra los datos médicos críticos del Usuario.
- **Etiqueta QR**: Objeto físico (sticker, tarjeta) con un código QR único que apunta a la Ficha de Emergencia.
- **Claim**: Proceso por el cual un Usuario asocia una Etiqueta QR a su cuenta.
- **Railway**: Plataforma de hosting donde se despliega la App.
- **Brevo**: Servicio de email transaccional utilizado para enviar correos de bienvenida y reset de contraseña.
- **SMTP_Relay**: Conexión SMTP configurada hacia Brevo para el envío de emails.
- **Página de Inicio**: Página pública en la ruta `/` que presenta el producto a Visitantes.
- **CTA**: Call to Action — botón o enlace que invita al Visitante a registrarse o adquirir una etiqueta.
- **SSL**: Certificado TLS/SSL que habilita HTTPS en el dominio propio.
- **Dominio**: Nombre de dominio propio (ej. vidaqr.com.ar) apuntando a la App en Railway.
- **Email de Bienvenida**: Correo enviado automáticamente al Usuario tras completar el registro.
- **Email de Reset**: Correo enviado al Usuario con el enlace para restablecer su contraseña.

---

## Requisitos

---

### Requisito 1: Infraestructura — Despliegue en Railway con dominio propio y SSL

**User Story:** Como operador del producto, quiero que la App esté disponible bajo un dominio propio con HTTPS, para que los Visitantes y Usuarios accedan de forma segura y el producto proyecte una imagen profesional.

#### Criterios de Aceptación

1. THE App SHALL responder a solicitudes HTTP en el dominio configurado (ej. `vidaqr.com.ar`) con un redireccionamiento 301 hacia HTTPS.
2. THE App SHALL responder a solicitudes HTTPS en el dominio configurado con un certificado SSL válido y sin advertencias de seguridad en navegadores modernos.
3. WHEN el certificado SSL está próximo a vencer (menos de 30 días), THE Railway SHALL renovarlo automáticamente sin intervención manual.
4. THE App SHALL devolver una respuesta HTTP 200 en la ruta `/health` con el cuerpo `{"status": "ok"}` para verificar que el servicio está activo.
5. WHEN la App recibe una solicitud en la ruta `/__ping__`, THE App SHALL responder con el texto `pong` y código HTTP 200 en menos de 2 segundos.
6. THE App SHALL leer las variables de entorno `MYSQLHOST`, `MYSQLPORT`, `MYSQLDATABASE`, `MYSQLUSER` y `MYSQLPASSWORD` provistas por Railway para establecer la conexión con la base de datos MySQL.
7. IF la conexión a la base de datos falla al iniciar, THEN THE App SHALL registrar el error en los logs de Railway y devolver HTTP 503 en todas las rutas que requieran base de datos.

---

### Requisito 2: Email transaccional — Bienvenida al registrarse

**User Story:** Como Usuario recién registrado, quiero recibir un email de bienvenida, para confirmar que mi cuenta fue creada correctamente y conocer los próximos pasos.

#### Criterios de Aceptación

1. WHEN un Usuario completa el registro exitosamente, THE App SHALL enviar un Email de Bienvenida a la dirección de email proporcionada en el formulario de registro.
2. THE Email de Bienvenida SHALL contener el nombre del producto (VidaQR), un saludo personalizado con el nombre del Usuario si fue proporcionado, y un enlace directo al panel de usuario (`/panel`).
3. THE Email de Bienvenida SHALL incluir una versión en texto plano y una versión HTML para compatibilidad con todos los clientes de correo.
4. IF el envío del Email de Bienvenida falla por error del SMTP_Relay, THEN THE App SHALL registrar el error en los logs y continuar el flujo de registro sin mostrar un error al Usuario.
5. THE SMTP_Relay SHALL autenticarse con Brevo usando las credenciales configuradas en las variables de entorno `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME` y `MAIL_PASSWORD`.
6. THE App SHALL enviar emails desde la dirección configurada en la variable de entorno `MAIL_FROM`.
7. WHEN el SMTP_Relay no está configurado (variables de entorno vacías), THE App SHALL registrar la URL o el contenido del email en los logs del servidor para facilitar el desarrollo local.

---

### Requisito 3: Email transaccional — Reset de contraseña

**User Story:** Como Usuario que olvidó su contraseña, quiero recibir un email con un enlace seguro para restablecerla, para recuperar el acceso a mi cuenta sin intervención del soporte.

#### Criterios de Aceptación

1. WHEN un Usuario solicita el reset de contraseña en `/forgot`, THE App SHALL generar un token criptográficamente seguro de al menos 32 bytes y almacenarlo en la base de datos junto con una fecha de expiración de 1 hora.
2. WHEN el token de reset es generado, THE App SHALL enviar un Email de Reset al Usuario con un enlace que incluya el token en la URL (`/reset/<token>`).
3. THE Email de Reset SHALL contener el nombre del producto (VidaQR), una advertencia de que el enlace expira en 1 hora, y una aclaración de que si el Usuario no solicitó el reset puede ignorar el mensaje.
4. THE Email de Reset SHALL incluir una versión en texto plano y una versión HTML.
5. WHEN un Usuario accede a `/reset/<token>` con un token válido y no expirado, THE App SHALL mostrar el formulario para ingresar una nueva contraseña.
6. IF el token de reset no existe o está expirado, THEN THE App SHALL mostrar un mensaje de error indicando que el enlace es inválido o expiró, sin revelar si el email existe en la base de datos.
7. WHEN el Usuario completa el reset de contraseña exitosamente, THE App SHALL invalidar el token (establecerlo en NULL en la base de datos) e iniciar sesión automáticamente o redirigir al login con un mensaje de confirmación.
8. IF un Visitante solicita reset para un email no registrado, THEN THE App SHALL mostrar el mismo mensaje de confirmación que para un email registrado, para no revelar qué emails existen en el sistema.

---

### Requisito 4: Página de Inicio pública

**User Story:** Como Visitante que llega al sitio, quiero entender qué es VidaQR y cómo funciona, para decidir si quiero registrarme o adquirir una etiqueta.

#### Criterios de Aceptación

1. WHEN un Visitante accede a la ruta `/`, THE App SHALL mostrar la Página de Inicio en lugar de redirigir al login.
2. THE Página de Inicio SHALL mostrar el nombre del producto (VidaQR), una descripción del problema que resuelve (emergencias médicas sin información disponible) y cómo funciona el producto en 3 pasos o menos.
3. THE Página de Inicio SHALL incluir al menos un CTA visible que dirija al Visitante a `/register`.
4. THE Página de Inicio SHALL ser completamente funcional y legible en dispositivos móviles con pantallas de 375px de ancho o más (diseño responsive).
5. THE Página de Inicio SHALL cargar en menos de 3 segundos en una conexión de 4G estándar, sin dependencias de JavaScript bloqueantes.
6. THE Página de Inicio SHALL incluir una sección que mencione los casos de uso principales: individuos, ciclistas, motociclistas, deportistas, adultos mayores.
7. THE Página de Inicio SHALL incluir un enlace de navegación hacia `/login` para Usuarios que ya tienen cuenta.
8. WHERE el Usuario ya tiene sesión iniciada, THE App SHALL redirigir la ruta `/` hacia `/panel` en lugar de mostrar la Página de Inicio.
9. THE Página de Inicio SHALL incluir una sección de "próximamente" o "cómo obtener tu etiqueta" que prepare al Visitante para el modelo de pago de la Fase 2, sin comprometer funcionalidad ni mostrar precios definitivos.
10. THE Página de Inicio SHALL incluir metaetiquetas Open Graph (`og:title`, `og:description`, `og:image`) para que los enlaces compartidos en redes sociales muestren una vista previa correcta del producto.

---

### Requisito 5: Seguridad y configuración de variables de entorno

**User Story:** Como operador del producto, quiero que todas las credenciales y configuraciones sensibles se gestionen mediante variables de entorno, para que no queden expuestas en el repositorio de código.

#### Criterios de Aceptación

1. THE App SHALL leer la clave secreta de Flask desde la variable de entorno `FLASK_SECRET` y no usar un valor hardcodeado en producción.
2. THE App SHALL leer la URL base desde la variable de entorno `APP_BASE_URL` para construir los enlaces en los emails (ej. el enlace de reset de contraseña).
3. IF la variable de entorno `FLASK_SECRET` no está definida, THEN THE App SHALL usar un valor de fallback únicamente en entorno de desarrollo local, y registrar una advertencia en los logs indicando que se está usando el valor por defecto.
4. THE App SHALL documentar todas las variables de entorno requeridas en un archivo `README.md` o `.env.example` en el repositorio, con descripción de cada variable y un valor de ejemplo no sensible.
5. THE App SHALL excluir el archivo `.env` del control de versiones mediante la entrada correspondiente en `.gitignore`.

---

### Requisito 6: Preparación para Fase 2 — Modelo de negocio

**User Story:** Como operador del producto, quiero que el diseño de la Fase 1 no bloquee la implementación futura de pagos y suscripciones, para poder agregar monetización en la Fase 2 sin refactorizaciones mayores.

#### Criterios de Aceptación

1. THE App SHALL mantener en la tabla `qr_codes` una columna `status` (o equivalente) que permita representar los estados `unclaimed` (sin dueño), `active` (activo) y `inactive` (inactivo/suscripción vencida) para uso futuro en Fase 2.
2. THE Página de Inicio SHALL incluir una sección de "cómo obtener tu etiqueta" que describa el proceso de compra futuro sin implementar el flujo de pago, para que el contenido sea coherente con el modelo de negocio de Fase 2.
3. THE App SHALL estructurar las rutas de forma que `/comprar` o `/pricing` puedan agregarse en Fase 2 sin conflictos con las rutas existentes.
4. THE Email de Bienvenida SHALL incluir una mención al proceso de obtención de etiquetas físicas, preparando al Usuario para el modelo de negocio de Fase 2.
