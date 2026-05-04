# fix_orphan_qrs.py
# Limpia QR "huérfanos": aquellos con user_id que ya no existe en users.
# Diseñado para ejecutarse desde tu PC usando MYSQL_PUBLIC_URL de Railway.

import os
import re
import sys
import mysql.connector
from urllib.parse import urlparse

def parse_mysql_public_url(url: str):
    """
    Espera algo como:
      mysql://root:PASSWORD@shortline.proxy.rlwy.net:40635/railway
    Devuelve (host, port, user, password, db)
    """
    p = urlparse(url)
    if p.scheme != "mysql":
        raise ValueError("La URL debe comenzar con mysql://")
    host = p.hostname
    port = p.port or 3306
    user = p.username
    pwd  = p.password or ""
    db   = p.path.lstrip("/") or "railway"
    return host, port, user, pwd, db

def get_conn():
    # 1) Preferimos MYSQL_PUBLIC_URL (ideal para correr local)
    url = os.environ.get("MYSQL_PUBLIC_URL")
    if not url:
        url = input("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):\nMYSQL_PUBLIC_URL: ").strip()

    try:
        host, port, user, pwd, db = parse_mysql_public_url(url)
        print(f"→ Conectando a {host}:{port} / db={db} user={user} …")
        return mysql.connector.connect(
            host=host, port=port, user=user, password=pwd, database=db, autocommit=True
        )
    except Exception as e:
        print(f"ERROR parseando/conectando con MYSQL_PUBLIC_URL: {e}")
        sys.exit(1)

def main():
    cnx = get_conn()
    cur = cnx.cursor()

    # --- 1) Mostrar algunos datos previos ---
    print("\nAntes de limpiar:")
    cur.execute("""
        SELECT COUNT(*) 
        FROM qr_codes q 
        LEFT JOIN users u ON u.id=q.user_id
        WHERE q.user_id IS NOT NULL AND u.id IS NULL
    """)
    (huérfanos,) = cur.fetchone()
    print(f"  QR con user_id sin usuario (huérfanos): {huérfanos}")

    # --- 2) Limpiar huérfanos: dejar user_id en NULL y claimed_at en NULL ---
    print("\n→ Limpiando huérfanos (dejando user_id=NULL, claimed_at=NULL)…")
    cur.execute("""
        UPDATE qr_codes q
        LEFT JOIN users u ON u.id=q.user_id
        SET q.user_id = NULL,
            q.claimed_at = NULL
        WHERE q.user_id IS NOT NULL
          AND u.id IS NULL
    """)
    print(f"  Filas afectadas: {cur.rowcount}")

    # --- 3) Verificación rápida ---
    cur.execute("""
        SELECT COUNT(*) 
        FROM qr_codes q 
        LEFT JOIN users u ON u.id=q.user_id
        WHERE q.user_id IS NOT NULL AND u.id IS NULL
    """)
    (huérfanos_post,) = cur.fetchone()
    print(f"\nDespués de limpiar: huérfanos restantes = {huérfanos_post}")

    # --- 4) Muestra corta para control visual ---
    cur.execute("""
        SELECT id, public_code, user_id, claimed_at
        FROM qr_codes
        ORDER BY id
        LIMIT 5
    """)
    rows = cur.fetchall()
    print("\nMuestra:")
    for r in rows:
        print(f"  id={r[0]}  public_code={r[1]}  user_id={r[2]}  claimed_at={r[3]}")

    cur.close()
    cnx.close()
    print("\nListo ✅")

if __name__ == "__main__":
    main()
