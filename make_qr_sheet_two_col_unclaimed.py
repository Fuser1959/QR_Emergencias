# make_qr_sheet_two_col_unclaimed.py
# PDF A4 con 2 columnas: [QR] [Código + URL] SOLO para etiquetas no reclamadas (user_id IS NULL).
import os
from urllib.parse import urlparse
import mysql.connector
from PIL import Image, ImageDraw, ImageFont
import qrcode

# ===== CONFIG HOJA =====
DPI = 300
A4_W_MM, A4_H_MM = 210, 297
MARGIN_MM   = 10
ROW_GAP_MM  = 4
QR_SIZE_MM  = 45
RIGHT_PAD_MM = 6
MAX_COUNT = 50   # máximo de etiquetas a incluir

# Tipos de letra (candidatos)
FONT_LARGE_CANDIDATES = [
    "arialbd.ttf", "SegoeUI-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_LABEL_CANDIDATES = [
    "arial.ttf", "SegoeUI.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
FONT_SIZE_CODE_PT = 36
FONT_SIZE_URL_PT  = 16

def mm_to_px(mm): return int(mm / 25.4 * DPI)
A4_W_PX, A4_H_PX = mm_to_px(A4_W_MM), mm_to_px(A4_H_MM)
MARGIN, ROW_GAP, QR_SIZE, RIGHT_PAD = map(mm_to_px, (MARGIN_MM, ROW_GAP_MM, QR_SIZE_MM, RIGHT_PAD_MM))

def load_font(cands, size_pt):
    for p in cands:
        try:
            return ImageFont.truetype(p, size_pt)
        except Exception:
            continue
    return ImageFont.load_default()

def text_wh(draw, text, font):
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

def parse_mysql_public_url(url: str):
    u = urlparse(url)
    if u.scheme != "mysql": raise ValueError("URL inválida (mysql://)")
    return u.hostname, (u.port or 3306), (u.username or "root"), (u.password or ""), (u.path or "/").lstrip("/") or "railway"

def build_qr(data: str, size_px: int):
    qr = qrcode.QRCode(version=None, box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((size_px, size_px), Image.LANCZOS)

def fetch_unclaimed(conn, limit=MAX_COUNT):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
      SELECT id, public_code FROM qr_codes
      WHERE user_id IS NULL AND public_code IS NOT NULL
      ORDER BY id DESC
      LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    return rows

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    mysql_public_url = input("MYSQL_PUBLIC_URL: ").strip()
    default_base = "https://web-production-8479c.up.railway.app"
    base_url = input(f"BASE_PUBLIC_URL [{default_base}]: ").strip() or default_base
    out_pdf = input("Archivo de salida [qr_unclaimed_two_col_A4.pdf]: ").strip() or "qr_unclaimed_two_col_A4.pdf"

    host, port, user, pwd, db = parse_mysql_public_url(mysql_public_url)
    print(f"→ Conectando a {host}:{port} / db={db} user={user} …")
    conn = mysql.connector.connect(host=host, port=port, user=user, password=pwd, database=db)

    rows = fetch_unclaimed(conn, MAX_COUNT)
    conn.close()
    if not rows:
        print("No hay etiquetas sin reclamar.")
        return

    # Página A4
    pages = []
    page = Image.new("RGB", (A4_W_PX, A4_H_PX), "white")
    draw = ImageDraw.Draw(page)

    font_code = load_font(FONT_LARGE_CANDIDATES, FONT_SIZE_CODE_PT)
    font_url  = load_font(FONT_LABEL_CANDIDATES,  FONT_SIZE_URL_PT)

    usable_w = A4_W_PX - 2*MARGIN
    usable_h = A4_H_PX - 2*MARGIN

    # Altura de fila (código grande + URL)
    _, code_h = text_wh(draw, "ABCDEFGH123456", font_code)
    _, url_h  = text_wh(draw, "https://x/y",    font_url)
    text_block_h = code_h + url_h + mm_to_px(2)
    row_h = max(QR_SIZE, text_block_h)
    rows_per_page = max(1, (usable_h + ROW_GAP) // (row_h + ROW_GAP))

    x_qr_left   = MARGIN
    x_text_left = MARGIN + QR_SIZE + mm_to_px(8)
    y = MARGIN
    count = 0

    for r in rows:
        code = r["public_code"]
        url  = f"{base_url}/v/{code}"

        if count > 0 and (y + row_h > A4_H_PX - MARGIN + 1):
            pages.append(page)
            page = Image.new("RGB", (A4_W_PX, A4_H_PX), "white")
            draw = ImageDraw.Draw(page)
            y = MARGIN
            count = 0

        qr_img = build_qr(url, QR_SIZE)
        page.paste(qr_img, (x_qr_left, y))

        code_w, code_h2 = text_wh(draw, code, font_code)
        url_w,  url_h2  = text_wh(draw, url,  font_url)
        text_y_top = y + (row_h - (code_h2 + url_h2 + mm_to_px(2))) // 2

        draw.text((x_text_left + RIGHT_PAD, text_y_top), code, fill=(0,0,0), font=font_code)
        draw.text((x_text_left + RIGHT_PAD, text_y_top + code_h2 + mm_to_px(2)), url, fill=(0,0,0), font=font_url)

        draw.line((MARGIN, y + row_h + ROW_GAP//2, A4_W_PX - MARGIN, y + row_h + ROW_GAP//2), fill=(230,230,230), width=1)

        y += row_h + ROW_GAP
        count += 1

    pages.append(page)
    first, rest = pages[0], pages[1:]
    first.save(out_pdf, "PDF", resolution=DPI, save_all=True, append_images=rest)
    print(f"Listo ✅ — PDF generado: {out_pdf}")
    print("Tip: al imprimir, usá 'Tamaño real / 100%' y desactivá 'ajustar al papel'.")

if __name__ == "__main__":
    main()
