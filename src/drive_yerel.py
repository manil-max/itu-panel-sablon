"""
Google Drive for Desktop'un yerel kaydından (DriveFS metadata_sqlite_db) dosya kimliklerini okur,
böylece PC'deki G:\\My Drive\\... dosyası için telefonda açılan bir Drive linki üretilebilir.
Sadece okur; veritabanının bir kopyası üzerinde çalışır (Drive açıkken kilitli olabilir).

    python drive_yerel.py      # WhatsApp klasöründe kaç dosyanın linki bulundu
"""
import os
import shutil
import sqlite3
import tempfile
import urllib.parse
from pathlib import Path

KLASOR = "İTÜ WhatsApp Dosyaları"


def _kopya(db):
    t = Path(tempfile.gettempdir()) / f"itu_drivefs_{db.parent.name}.db"
    shutil.copy(db, t)
    if Path(str(db) + "-wal").exists():
        shutil.copy(str(db) + "-wal", str(t) + "-wal")
    return t


def klasor_idleri(kok=KLASOR):
    """-> (klasör_id, {"altklasör/dosya.pdf": dosya_id}) ; Drive for Desktop yoksa (None, {})."""
    ana = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "DriveFS"
    for db in ana.glob("*/metadata_sqlite_db"):
        try:
            c = sqlite3.connect(_kopya(db))
            c.text_factory = lambda b: b.decode("utf-8", "replace")
            r = c.execute("SELECT id, stable_id FROM items WHERE local_title=? AND is_folder=1 AND trashed=0",
                          (kok,)).fetchone()
            if not r:
                continue
            sonuc, yigin = {}, [(r[1], "")]
            while yigin:
                sid, yol = yigin.pop()
                for cid, csid, ad, klasor in c.execute(
                        "SELECT i.id, i.stable_id, i.local_title, i.is_folder FROM stable_parents p "
                        "JOIN items i ON i.stable_id=p.item_stable_id WHERE p.parent_stable_id=? AND i.trashed=0",
                        (sid,)):
                    if klasor:
                        sonuc[yol + ad + "/"] = cid
                        yigin.append((csid, yol + ad + "/"))
                    else:
                        sonuc[yol + ad] = cid
            c.close()
            return r[0], sonuc
        except sqlite3.Error:
            continue
    return None, {}


def link(dosya_id=None, ad=None, klasor=False):
    if dosya_id:
        return (f"https://drive.google.com/drive/folders/{dosya_id}" if klasor
                else f"https://drive.google.com/file/d/{dosya_id}/view")
    return "https://drive.google.com/drive/search?q=" + urllib.parse.quote(f'"{ad}"') if ad else None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    k, d = klasor_idleri()
    print("klasör:", k, "·", len(d), "dosya")
