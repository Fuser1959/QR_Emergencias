# migrate_auth_reset.py
import mysql.connector
import urllib.parse as up

DDL_COLUMNS = [
    ("reset_token",   "VARCHAR(64) NULL"),
    ("reset_expires", "DATETIME NULL"),
]

def col_exists(cur, table, column):
    cur.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (table, column))
    return cur.fetchone()[0] > 0

def index_exists(cur, table, index_name):
    cur.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s
    """, (table, index_name))
    return cur.fetchone()[0] > 0

def main():
    url = input("MYSQL_PUBLIC_URL: ").strip()
    if not url:
        print("Cancelado.")
        return

    p = up.urlsplit(url)
    host = p.hostname
    port = p.port or 3306
    user = up.unquote(p.username or "")
    pwd  = up.unquote(p.password or "")
    db   = (p.path or "/").strip("/")

    print(f"→ Conectando a {host}:{port} / db={db} …")
    cnx = mysql.connector.connect(host=host, port=port, user=user, password=pwd, database=db)
    cur = cnx.cursor()

    # agregar columnas si faltan
    for col, ddl in DDL_COLUMNS:
        if not col_exists(cur, "users", col):
            print(f"→ Agregando columna users.{col} …")
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

    # índice para reset_token
    if not index_exists(cur, "users", "idx_reset_token"):
        print("→ Creando índice idx_reset_token en users.reset_token …")
        cur.execute("CREATE INDEX idx_reset_token ON users(reset_token)")

    cnx.commit()
    cur.close()
    cnx.close()
    print("Listo ✅ — Migración aplicada.")

if __name__ == "__main__":
    main()
