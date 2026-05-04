# make_qr_sheet_two_col.py
# PDF A4 con 2 columnas: [QR] [Código + URL]
# - Lee los códigos desde tu MySQL en Railway usando MYSQL_PUBLIC_URL
# - Genera los QR al vuelo y compone un PDF A4 en grilla por filas
#
# Requisitos:
#   pip install qrcode[pil] pillow mysql-connector-python
#
# Ejecución:
#   (venv) python make_qr_sheet_two_col.py
#
# Ajustes rápidos (medidas en mm) al inicio del archivo.

import io
import math
import os
import sys
from urllib.parse import urlparse
import getpass

import mysql.connector
from PIL import Image, ImageDraw, ImageFont
import qrcode

# =========================
#  CONFIGURACIÓN (mm / px)
# =========================

DPI = 300                    # resolución del PDF
A4_W_MM, A4_H_MM = 210, 297  # A4 vertical

MARGIN_MM   = 10             # margen exterior hoja
ROW_GAP_MM  = 4              # separación vertical entre filas
QR_SIZE_MM  = 45             # tamaño del QR (ancho = alto)
RIGHT_PAD_MM = 6             # padding interno en la celda de texto

# Tipografías (intentaremos en este orden)
FONT_LARGE_CANDIDATES = [
    "arialbd.ttf",                 # Arial Bold (Windows)
    "SegoeUI-Bold.ttf",            # Segoe UI Bold
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_LABEL_CANDIDATES = [
    "arial.ttf",
    "SegoeUI.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
FONT_SIZE_CODE_PT = 36      # tamaño para el código
FONT_SIZE_URL_PT  = 16      # tamaño para la URL

# Si querés acotar qué códigos incluir, podés filtrar por IDs:
ID_FROM = None  # ej: 1
ID_TO   = None  # ej: 200


# =========================
#  UTILIDADES
# =========================

def mm_to_px(mm: float) -> int:
    return int(mm / 25.4 * DPI)

A4_W_PX = mm_to_px(A4_W_MM)
A4_H_PX = mm_to_px(A4_H_MM)
MARGIN  = mm_to_px(MARGIN_MM)
ROW_GAP = mm_to_px(ROW_GAP_MM)
QR_SIZE = mm_to_px(QR_SIZE_MM)
RIGHT_PAD = mm_to_px(RIGHT_PAD_MM)

def load_font(candidates, size_pt):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size_pt)
        except Exception:
            continue
    # Fallback
    return ImageFont.load_default()

def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    # Usamos textbbox (Pillow moderno) para medir
    bbox = draw.textbbox((0,0), text, font=font)
    w = bbox[2]-bbox[0]
    h = bbox[3]-bbox[1]
    return w, h

def parse_mysql_public_url(mysql_public_url: str):
    # Formato típico:
    # mysql://root:PASSWORD@shortline.proxy.rlwy.net:40635/railway
    u = urlparse(mysql_public_url)
    if u.scheme != "mysql":
        raise ValueError("La URL no parece ser mysql://…")
    host = u.hostname
    port = u.port or 3306
    user = u.username or "root"
    pwd  = u.password or ""
    db   = (u.path or "/").lstrip("/") or "railway"
    return host, port, user, pwd, db

def connect_mysql_from_public_url(mysql_public_url: str):
    host, port, user, pwd, db = parse_mysql_public_url(mysql_public_url)
    print(f"→ Conectando a {host}:{port} / db={db} user={user} …")
    return mysql.connector.connect(
        host=host, port=port, user=user, password=pwd, database=db
    )

def fetch_codes(conn):
    cur = conn.cursor(dictionary=True)
    sql = "SELECT id, public_code FROM qr_codes WHERE public_code IS NOT NULL"
    params = []
    if ID_FROM is not None:
        sql += " AND id >= %s"
        params.append(ID_FROM)
    if ID_TO is not None:
        sql += " AND id <= %s"
        params.append(ID_TO)
    sql += " ORDER BY id ASC"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows

def build_qr_image(data: str, size_px: int) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        box_size=10,
        border=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    # redimensionamos al tamaño exacto
    img = img.resize((size_px, size_px), Image.LANCZOS)
    return img


# =========================
#  GENERACIÓN DEL PDF
# =========================

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    mysql_public_url = input("MYSQL_PUBLIC_URL: ").strip()

    # URL base pública para armar el link del QR
    # Podés pegar tu dominio aquí (se usa de default el Railway actual).
    default_base = "https://web-production-8479c.up.railway.app"
    base_url = input(f"BASE_PUBLIC_URL [{default_base}]: ").strip() or default_base

    # Archivo de salida
    out_pdf = input("Archivo de salida [qr_two_col_A4.pdf]: ").strip() or "qr_two_col_A4.pdf"

    # Conectar DB y traer códigos
    conn = connect_mysql_from_public_url(mysql_public_url)
    rows = fetch_codes(conn)
    conn.close()

    if not rows:
        print("No hay códigos con public_code asignado.")
        return

    # Página en blanco A4
    pages = []
    page = Image.new("RGB", (A4_W_PX, A4_H_PX), "white")
    draw = ImageDraw.Draw(page)

    # Tipografías
    font_code = load_font(FONT_LARGE_CANDIDATES, FONT_SIZE_CODE_PT)
    font_url  = load_font(FONT_LABEL_CANDIDATES, FONT_SIZE_URL_PT)

    # Layout por fila
    usable_w = A4_W_PX - 2*MARGIN
    usable_h = A4_H_PX - 2*MARGIN

    # Alto de la fila = max(QR_SIZE, alto del bloque texto)
    # Bloque texto: 2 líneas (código grande + URL). Tomamos una estimación con "ABC".
    _, code_h = text_size(draw, "ABCDEF123456", font_code)
    _, url_h  = text_size(draw, "https://x/y", font_url)
    text_block_h = code_h + url_h + mm_to_px(2)  # 2 mm de separación interna

    row_h = max(QR_SIZE, text_block_h)
    # ¿cuántas filas entran?
    rows_per_page = (usable_h + ROW_GAP) // (row_h + ROW_GAP)
    rows_per_page = max(1, rows_per_page)

    x_qr_left = MARGIN
    x_text_left = MARGIN + QR_SIZE + mm_to_px(8)  # 8mm de separación entre QR y texto
    text_col_w = A4_W_PX - x_text_left - MARGIN

    # Generar filas
    y = MARGIN
    count = 0
    for r in rows:
        code = r["public_code"]
        url = f"{base_url}/v/{code}"

        # Salto de página si no entra
        if count > 0 and (y + row_h > A4_H_PX - MARGIN + 1):
            pages.append(page)
            page = Image.new("RGB", (A4_W_PX, A4_H_PX), "white")
            draw = ImageDraw.Draw(page)
            y = MARGIN
            count = 0

        # 1) QR
        qr_img = build_qr_image(url, QR_SIZE)
        page.paste(qr_img, (x_qr_left, y))

        # 2) Texto (código grande + URL)
        # Código centrado verticalmente dentro del bloque de texto
        code_w, code_h = text_size(draw, code, font_code)
        url_w, url_h = text_size(draw, url, font_url)

        # Posiciones
        text_y_top = y + (row_h - (code_h + url_h + mm_to_px(2))) // 2
        code_x = x_text_left + RIGHT_PAD
        code_y = text_y_top
        url_x  = x_text_left + RIGHT_PAD
        url_y  = code_y + code_h + mm_to_px(2)

        draw.text((code_x, code_y), code, fill=(0,0,0), font=font_code)
        draw.text((url_x,  url_y),  url,  fill=(0,0,0), font=font_url)

        # Línea divisoria (opcional)
        line_y = y + row_h + ROW_GAP//2
        draw.line((MARGIN, line_y, A4_W_PX - MARGIN, line_y), fill=(230,230,230), width=1)

        y += row_h + ROW_GAP
        count += 1

    # Agregar última página
    pages.append(page)

    # Guardar PDF multipágina
    first, rest = pages[0], pages[1:]
    first.save(out_pdf, "PDF", resolution=DPI, save_all=True, append_images=rest)
    print(f"Listo ✅ — PDF generado: {out_pdf}")
    print("Tip: al imprimir, usá 'Tamaño real / 100%' y desactiva 'ajustar al papel'.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
