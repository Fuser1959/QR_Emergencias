# make_qr_images.py  — genera PNGs de QR + código impreso debajo
import os
import re
import qrcode
from PIL import Image, ImageDraw, ImageFont
import mysql.connector
from urllib.parse import urlparse

# ========= CONFIG =========
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "https://web-production-8479c.up.railway.app")
OUT_DIR = "labels"
FONT_PATH = None      # ej: "C:/Windows/Fonts/arial.ttf" (opcional). Si es None, usa fuente por defecto.
TEXT_SIZE = 28        # tamaño del texto bajo el QR
QR_BOX_SIZE = 10      # densidad del QR (más grande = más píxeles)
QR_BORDER = 4         # borde blanco del QR

def parse_mysql_public_url(url: str):
    """mysql://user:pass@host:port/db -> dict para mysql.connector"""
    p = urlparse(url)
    return {
        "host": p.hostname,
        "port": p.port or 3306,
        "user": p.username,
        "password": p.password,
        "database": p.path.lstrip("/"),
    }

def text_wh(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    """
    Medir texto con APIs nuevas de Pillow (>=10): textbbox.
    (Compat: si existiera textsize, caería allí, pero en Pillow 11 ya no está.)
    """
    # bbox = (left, top, right, bottom)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return w, h

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    url = input("MYSQL_PUBLIC_URL: ").strip()
    cfg = parse_mysql_public_url(url)

    print(f"→ Conectando a {cfg['host']}:{cfg['port']} / db={cfg['database']} …")
    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, public_code FROM qr_codes ORDER BY id")
    rows = cur.fetchall()
    cur.close(); conn.close()

    os.makedirs(OUT_DIR, exist_ok=True)

    # Fuente
    if FONT_PATH and os.path.exists(FONT_PATH):
        try:
            font = ImageFont.truetype(FONT_PATH, TEXT_SIZE)
        except Exception:
            font = ImageFont.load_default()
    else:
        # Fuente por defecto (monoespaciada de PIL)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None  # extremadamente raro

    total = 0
    for r in rows:
        code = r["public_code"]
        if not code:
            continue

        url_publica = f"{PUBLIC_BASE}/v/{code}"

        # 1) Generar QR
        qr = qrcode.QRCode(box_size=QR_BOX_SIZE, border=QR_BORDER)
        qr.add_data(url_publica)
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        # 2) Preparar lienzo con texto debajo
        canvas_pad_top = 0
        canvas_pad_bottom = 16
        text_pad_top = 16

        # medir texto
        drawer = ImageDraw.Draw(img_qr)
        w_text, h_text = text_wh(drawer, code, font)

        canvas_w = max(img_qr.width, w_text + 20)
        canvas_h = canvas_pad_top + img_qr.height + text_pad_top + h_text + canvas_pad_bottom
        canvas = Image.new("RGB", (canvas_w, canvas_h), "white")

        # pegar QR centrado arriba
        x_qr = (canvas_w - img_qr.width) // 2
        canvas.paste(img_qr, (x_qr, canvas_pad_top))

        # dibujar texto centrado
        d2 = ImageDraw.Draw(canvas)
        x_text = (canvas_w - w_text) // 2
        y_text = canvas_pad_top + img_qr.height + text_pad_top
        d2.text((x_text, y_text), code, fill="black", font=font)

        # 3) Guardar
        safe_code = re.sub(r"[^A-Za-z0-9_-]", "_", code)
        out_path = os.path.join(OUT_DIR, f"{r['id']:04d}_{safe_code}.png")
        canvas.save(out_path, "PNG")
        total += 1

    print(f"Listo ✅  —  {total} etiquetas generadas en ./{OUT_DIR}/")

if __name__ == "__main__":
    main()
