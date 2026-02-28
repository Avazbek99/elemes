# -*- coding: utf-8 -*-
"""SQLite baza integritetini tekshirish va zaxira/tiklash."""
import os
import shutil
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'instance', 'eduspace.db')
INSTANCE = os.path.join(BASE, 'instance')
RECOVERED_PATH = os.path.join(BASE, 'instance', 'eduspace_recovered.db')


def check():
    """PRAGMA integrity_check."""
    if not os.path.isfile(DB_PATH):
        print('Baza fayli topilmadi:', DB_PATH)
        return
    print('Baza:', DB_PATH)
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute('PRAGMA integrity_check;')
        result = cur.fetchone()[0]
        conn.close()
        if result == 'ok':
            print('Natija: OK — baza to\'g\'ri.')
        else:
            print('Natija:', result)
            print('Baza shikastlangan bo\'lishi mumkin. Zaxira oling va tiklashga harakat qiling.')
    except Exception as e:
        print('Xato:', e)


def backup():
    """Bazani zaxira nusxasiga olish."""
    if not os.path.isfile(DB_PATH):
        print('Baza fayli topilmadi:', DB_PATH)
        return
    os.makedirs(INSTANCE, exist_ok=True)
    name = 'eduspace.db.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(INSTANCE, name)
    shutil.copy2(DB_PATH, dest)
    print('Zaxira saqlandi:', dest)


def recover():
    """Zaxira olib, bazani tiklashga urinish (VACUUM INTO yoki jadvalma-jadval nusxalash)."""
    if not os.path.isfile(DB_PATH):
        print('Baza fayli topilmadi:', DB_PATH)
        return False
    os.makedirs(INSTANCE, exist_ok=True)
    # 1. Zaxira
    backup_name = 'eduspace.db.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(INSTANCE, backup_name)
    shutil.copy2(DB_PATH, backup_path)
    print('Zaxira saqlandi:', backup_path)

    recovered_ok = False
    # 2. VACUUM INTO (SQLite 3.27+) — toza nusxa
    if os.path.isfile(RECOVERED_PATH):
        try:
            os.remove(RECOVERED_PATH)
        except OSError:
            pass
    try:
        conn = sqlite3.connect(DB_PATH)
        path_escaped = RECOVERED_PATH.replace("'", "''").replace("\\", "/")
        conn.execute("VACUUM INTO '" + path_escaped + "'")
        conn.close()
        recovered_ok = os.path.isfile(RECOVERED_PATH)
        if recovered_ok:
            print('VACUUM INTO muvaffaqiyatli. Tiklangan fayl:', RECOVERED_PATH)
    except sqlite3.OperationalError as e:
        if 'VACUUM INTO' in str(e) or 'syntax' in str(e).lower():
            pass  # Eski SQLite — keyingi usulga o'tamiz
        else:
            print('VACUUM INTO xato:', e)
    except Exception as e:
        print('VACUUM INTO xato:', e)

    # 3. Agar VACUUM ishlamasa — jadvalma-jadval nusxalash
    if not recovered_ok:
        try:
            src = sqlite3.connect(DB_PATH)
            src.row_factory = sqlite3.Row
            if os.path.isfile(RECOVERED_PATH):
                os.remove(RECOVERED_PATH)
            dst = sqlite3.connect(RECOVERED_PATH)
            cur = src.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = list(cur.fetchall())
            for name, sql in tables:
                if not sql:
                    continue
                try:
                    dst.execute(sql)
                    rows = src.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
                    if rows:
                        cols = len(rows[0])
                        placeholders = ','.join(['?'] * cols)
                        dst.executemany(
                            'INSERT OR REPLACE INTO "' + name.replace('"', '""') + '" VALUES (' + placeholders + ')',
                            rows,
                        )
                    dst.commit()
                except Exception as e:
                    print('  Jadval "%s" nusxalashda xato: %s' % (name, e))
                    dst.rollback()
            # Indekslar va view lar
            cur = src.execute(
                "SELECT sql FROM sqlite_master WHERE type IN ('index','view') AND sql IS NOT NULL"
            )
            for (sql,) in cur.fetchall():
                try:
                    if sql:
                        dst.execute(sql)
                except Exception:
                    pass
            dst.commit()
            src.close()
            dst.close()
            recovered_ok = os.path.isfile(RECOVERED_PATH)
            if recovered_ok:
                print('Jadvalma-jadval nusxalash muvaffaqiyatli. Tiklangan fayl:', RECOVERED_PATH)
        except Exception as e:
            print('Tiklash xato:', e)

    if not recovered_ok:
        print('Bazani tiklash amalga oshmadi. Zaxira:', backup_path)
        return False

    # 4. Asl bazani tiklanganni bilan almashtirish (server to'xtaganda)
    try:
        os.remove(DB_PATH)
        shutil.move(RECOVERED_PATH, DB_PATH)
        print('Baza almashtirildi. Hozirgi baza:', DB_PATH)
        return True
    except OSError as e:
        if getattr(e, 'winerror', None) == 32 or 'being used' in str(e).lower():  # Windows: file in use
            print('Asl baza boshqa dastur tomonidan ochiq. Serverni to\'xtating, keyin: python check_db.py replace')
        else:
            print('Almashtirish xato:', e)
        return False
    except Exception as e:
        print('Almashtirish xato:', e)
        return False


def replace_with_recovered():
    """Tiklangan bazani asl o'rniga qo'yish (serverni to'xtatgach ishlating)."""
    if not os.path.isfile(RECOVERED_PATH):
        print('Tiklangan fayl topilmadi. Avval: python check_db.py recover')
        return
    try:
        if os.path.isfile(DB_PATH):
            os.remove(DB_PATH)
        shutil.move(RECOVERED_PATH, DB_PATH)
        print('Baza almashtirildi:', DB_PATH)
    except OSError as e:
        if getattr(e, 'winerror', None) == 32 or 'being used' in str(e).lower():
            print('Baza ochiq. Ilova/web-serverni to\'xtating va qayta urinib ko\'ring.')
        else:
            print('Xato:', e)
    except Exception as e:
        print('Xato:', e)


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'backup':
        backup()
    elif len(sys.argv) > 1 and sys.argv[1] == 'recover':
        recover()
    elif len(sys.argv) > 1 and sys.argv[1] == 'replace':
        replace_with_recovered()
    else:
        check()


if __name__ == '__main__':
    main()
