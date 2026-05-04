# make_qr_sheet.py — compone los PNG de ./labels/ en un PDF A4 para imprimir
import os
from glob import glob
from math import ceil
from PIL import Image

LABELS_DIR = "labels"
OUT_PDF = "labels_sheet_A4.pdf"

# Configuración de hoja A4 a 300 DPI
DPI = 300
A4_W_MM, A4_H_MM = 210, 297
A4_W_PX = int(A4_W_MM / 25.4 * DPI)
A4_H_PX = int(A4_H_MM / 25.4 * DPI)

# Config de grilla (podés ajustar estas 3 líneas a gusto)
COLS = 3            # columnas
ROWS = 8            # filas
MARGIN_MM = 8       # margen exterior
GAP_MM = 5          # separación entre etiquetas

# Convertir mm a píxeles
def mm_to_px(mm): return int(mm / 25.4 * DPI)

MARGIN = mm_to_px(MARGIN_MM)
GAP = mm_to_px(GAP_MM)

def main():
    files = sorted(glob(os.path.join(LABELS_DIR, "*.png")))
    if not files:
        print("No se encontraron PNG en ./labels/")
        return

    # Área útil (sin márgenes)
    usable_w = A4_W_PX - 2 * MARGIN
    usable_h = A4_H_PX - 2 * MARGIN

    # Tamaño de cada celda
    cell_w = (usable_w - (COLS - 1) * GAP) // COLS
    cell_h = (usable_h - (ROWS - 1) * GAP) // ROWS

    pages = []
    per_page = COLS * ROWS
    total_pages = ceil(len(files) / per_page)

    for p in range(total_pages):
        page = Image.new("RGB", (A4_W_PX, A4_H_PX), "white")

        chunk = files[p * per_page: (p + 1) * per_page]
        for i, f in enumerate(chunk):
            img = Image.open(f).convert("RGB")

            # Escalar manteniendo aspecto para que entre en la celda
            scale = min(cell_w / img.width, cell_h / img.height)
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)

            r = i // COLS
            c = i % COLS

            x0 = MARGIN + c * (cell_w + GAP) + (cell_w - new_w) // 2
            y0 = MARGIN + r * (cell_h + GAP) + (cell_h - new_h) // 2
            page.paste(img, (x0, y0))

        pages.append(page)

    # Guardar en PDF multipágina
    first, rest = pages[0], pages[1:]
    first.save(OUT_PDF, "PDF", resolution=DPI, save_all=True, append_images=rest)
    print(f"Listo ✅ — PDF generado: {OUT_PDF}")
    print("Tip: al imprimir, usá 'Tamaño real / 100%' y sin ajuste de márgenes del driver.")

if __name__ == "__main__":
    main()
