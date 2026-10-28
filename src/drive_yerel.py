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
RCLONE = os.environ.get("ITU_RCLONE", "gdrive:")      # Pi: rclone'daki Drive remote'u


def drive_ana():
    """Drive'ın 'Drive'ım' kökü: ITU_DRIVE ortam değişkeni (Pi'de rclone mount), yoksa Windows'ta
    Google Drive for Desktop'un harfi (G: ...), yoksa ~/gdrive. Hiçbiri yoksa None."""
    try:                                              # şablon: ayarlar.json -> driveKlasoru (elle)
        import json
        elle = json.loads((Path(__file__).resolve().parent / "ayarlar.json").read_text(encoding="utf-8")).get("driveKlasoru")
        if elle and Path(elle).is_dir():
            return Path(elle)
    except (OSError, ValueError):
        pass
    if os.environ.get("ITU_DRIVE"):
        k = Path(os.environ["ITU_DRIVE"])
        return k if k.is_dir() else None
    if os.name == "nt":
        for harf in "GHIJKLMNOPQRSTUVWXYZDEF":
            for ad in ("My Drive", "Drive'ım", "Drive’ım"):
                k = Path(f"{harf}:/") / ad
                if k.is_dir():
                    return k
        return None
    k = Path.home() / "gdrive"
    return k if k.is_dir() and any(k.iterdir()) else None      # boş = mount edilmemiş


def _rclone_idleri(kok):
    """Drive for Desktop yoksa (Pi) aynı bilgiyi rclone'dan alır: -> (klasör_id, {yol: id}) ya da (None, {})."""
    import json
    import subprocess
    if not shutil.which("rclone"):
        return None, {}
    try:
        ust = json.loads(subprocess.run(["rclone", "lsjson", "--dirs-only", RCLONE], capture_output=True,
                                        text=True, encoding="utf-8", timeout=120).stdout or "[]")
        kid = next((x.get("ID") for x in ust if x.get("Name") == kok), None)
        if not kid:
            return None, {}
        l = json.loads(subprocess.run(["rclone", "lsjson", "-R", RCLONE + kok], capture_output=True,
                                      text=True, encoding="utf-8", timeout=300).stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, {}
    return kid, {x["Path"] + ("/" if x.get("IsDir") else ""): x.get("ID") for x in l if x.get("ID")}


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
    return _rclone_idleri(kok)


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
