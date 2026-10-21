"""Bakım kontrolü: kimlik bilgisi ve mesaj metni yazdırmaz, veri değiştirmez."""
import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
VERI = KOK / "veri"


def durum():
    sonuc = {"otomasyonKapali": (VERI / "otomasyon_kapali").exists(),
             "girisEngellendi": (VERI / "giris_hatasi.json").exists()}
    for ad in ("panel.json", "whatsapp/notlar.json", "whatsapp/durum.json"):
        yol = VERI / ad
        try:
            veri = json.loads(yol.read_text(encoding="utf-8"))
            sonuc[ad] = {"gecerli": True, "degisti": dt.datetime.fromtimestamp(yol.stat().st_mtime).isoformat(timespec="seconds")}
            if ad == "panel.json":
                sonuc[ad]["guncellendi"] = veri.get("guncellendi")
                sonuc[ad]["dersSayisi"] = len((veri.get("obs") or {}).get("dersler", []))
                sonuc[ad]["ninovaVar"] = bool(veri.get("ninova"))
            if ad == "whatsapp/durum.json":
                sonuc[ad]["bagli"] = veri.get("bagli")
        except (OSError, ValueError):
            sonuc[ad] = {"gecerli": False}
    for ad, tablo in (("whatsapp/mesajlar.db", "mesajlar"), ("eposta/epostalar.db", "epostalar")):
        yol = VERI / ad
        if not yol.exists():
            sonuc[ad] = {"mevcut": False}
            continue
        try:
            with closing(sqlite3.connect(yol.as_uri() + "?mode=ro", uri=True)) as bag:
                sonuc[ad] = {"bekleyen": bag.execute(f"SELECT COUNT(*) FROM {tablo} WHERE degerlendirildi=0").fetchone()[0]}
        except sqlite3.Error:
            sonuc[ad] = {"hata": "veritabani okunamadi"}
    sonuc["panelMevcut"] = (KOK / "panel.html").exists()
    return sonuc


if __name__ == "__main__":
    print(json.dumps(durum(), ensure_ascii=False, indent=2))
