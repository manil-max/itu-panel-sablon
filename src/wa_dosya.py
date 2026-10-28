"""
WhatsApp grup dosyalarını düzenler (köprü yine 'İTÜ WhatsApp Dosyaları/<grup>/' altına indirir, bu betik taşır):

- Ders grubu dosyası -> Drive'ım/İTÜ/Dersler/<DERS KODU>/Diğer/ ; dersle eşleşmeyen -> İTÜ/Genel/<grup>/
- Aynı içerik (SHA-256) zaten varsa (Ninova'dan inen dahil) ikinci kopya 'İTÜ/_kopyalar (silinebilir)'e gider,
  mesaj kaydı mevcut kopyayı gösterir. Hiçbir dosya silinmez.
- Adı anlamsız resimler: --adsiz listeler (değerlendiren ajan resme bakıp ad verir),
  --adlandir <yol> <yeni ad> yeniden adlandırır, --ele <yol> sohbet/mizah resmini 'İTÜ/_elenen'e taşır.

    python wa_dosya.py              # düzenle
    python wa_dosya.py --adsiz
    python wa_dosya.py --adlandir "G:/My Drive/İTÜ/Dersler/FIZ 101E/Diğer/2026-10-14_AC63.jpg" "2026-10-14_FIZ101_lab-tablosu.jpg"
    python wa_dosya.py --ele "G:/My Drive/İTÜ/Genel/Genel/2026-10-14_3F2A.jpg"
"""
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

import dosyalar

HERE = Path(__file__).resolve().parent
VERI = HERE.parent / "veri"
DB = VERI / "whatsapp" / "mesajlar.db"
ESKI_KLASOR = "İTÜ WhatsApp Dosyaları"
ANLAMSIZ = re.compile(r"^\d{4}-\d{2}-\d{2}_(?:[0-9A-F]{8,}|IMG[-_]|WhatsApp Image|image|photo|[0-9a-f]{12})", re.I)
RESIM = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def ders_bul(grup, ad, kodlar):
    """Grup adı + dosya adından ders kodu (yoksa None)."""
    metin = f"{grup} {ad}".upper().replace(" ", "")
    for k in sorted(kodlar, key=len, reverse=True):
        if k.replace(" ", "") in metin:
            return k
    g = grup.upper()
    if "FIZ" in g:
        return "FIZ 101EL" if re.search(r"lab|deney|exp|föy|foy|projectile|pendulum|inertia|harmonic|centripetal|"
                                         r"constant acceleration", ad, re.I) and "FIZ 101EL" in kodlar else "FIZ 101E"
    for k in kodlar:                                  # grup adında kod gövdesi: MAT103-yedek -> MAT 103E
        if k.replace(" ", "")[:6] in grup.upper().replace(" ", ""):
            return k
    return None


def _sha(yol):
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for p in iter(lambda: f.read(1 << 16), b""):
            h.update(p)
    return h.hexdigest()


def _guncelle_db(c, eski, yeni):
    c.execute("UPDATE mesajlar SET dosya=? WHERE dosya=? OR replace(dosya,'\\','/')=?",
              (str(yeni), str(eski), str(eski).replace("\\", "/")))


def duzenle(log=print):
    kok = dosyalar.drive_kok()
    if not kok or not DB.exists():
        return
    try:
        kodlar = [d["kod"] for d in json.loads((VERI / "panel.json").read_text(encoding="utf-8"))["obs"]["dersler"]]
    except (OSError, ValueError, KeyError):
        kodlar = []
    kayit = dosyalar.kayit_oku()
    ozetler = {v["sha256"]: v["yol"] for v in kayit.get("dosyalar", {}).values()
               if v.get("sha256") and v.get("yol") and Path(v["yol"]).exists()}
    wa_ozet = kayit.setdefault("whatsapp", {})       # taşınan WhatsApp dosyalarının sha256 -> yol
    for o, y in wa_ozet.items():
        if Path(y).exists():
            ozetler.setdefault(o, y)
    c = sqlite3.connect(DB)
    satirlar = c.execute("SELECT DISTINCT dosya, grup_adi, dosya_adi FROM mesajlar WHERE dosya != ''").fetchall()
    tasinan = kopya = 0
    for yol, grup, ad in satirlar:
        p = Path(yol)
        if not p.is_absolute() or ESKI_KLASOR not in p.parts or not p.is_file():
            continue
        ozet = _sha(p)
        if ozet in ozetler and Path(ozetler[ozet]) != p:
            hedef = kok / "_kopyalar (silinebilir)" / p.parent.name / p.name
            hedef.parent.mkdir(parents=True, exist_ok=True)
            if not hedef.exists():
                shutil.move(str(p), str(hedef))
            _guncelle_db(c, p, ozetler[ozet])
            kopya += 1
            continue
        ders = ders_bul(grup or p.parent.name, ad or p.name, kodlar)
        hedef_klasor = kok / "Dersler" / dosyalar.temiz(ders) / "Diğer" if ders else kok / "Genel" / p.parent.name
        hedef_klasor.mkdir(parents=True, exist_ok=True)
        hedef = hedef_klasor / p.name
        if hedef.exists():
            hedef = hedef_klasor / f"{p.stem} ({ozet[:6]}){p.suffix}"
        shutil.move(str(p), str(hedef))
        _guncelle_db(c, p, hedef)
        ozetler[ozet] = wa_ozet[ozet] = str(hedef)
        tasinan += 1
    c.commit()
    c.close()
    dosyalar.kayit_yaz({**dosyalar.kayit_oku(), "whatsapp": wa_ozet})
    if tasinan or kopya:
        log(f"  WhatsApp dosyaları: {tasinan} taşındı, {kopya} kopya ayrıldı")


def adsizlar():
    """Adı anlamsız resimler + mesajın yazısı (ajan resme bakıp ad verir)."""
    if not DB.exists():                              # WhatsApp köprüsü hiç çalışmadıysa boş DB yaratma
        return []
    c = sqlite3.connect(DB)
    out = []
    for yol, grup, metin in c.execute("SELECT dosya, grup_adi, metin FROM mesajlar WHERE dosya != '' AND tur='foto'"):
        p = Path(yol)
        if p.suffix.lower() in RESIM and ANLAMSIZ.match(p.name) and p.exists() and "_elenen" not in p.parts:
            out.append((str(p), grup, (metin or "")[:120]))
    c.close()
    return out


def adlandir(yol, yeni):
    p = Path(yol)
    yeni = dosyalar.temiz(yeni)
    if Path(yeni).suffix.lower() != p.suffix.lower():
        yeni += p.suffix
    hedef = p.with_name(yeni)
    if hedef.exists():
        raise SystemExit(f"zaten var: {hedef}")
    p.rename(hedef)
    c = sqlite3.connect(DB)
    _guncelle_db(c, p, hedef)
    c.commit()
    c.close()
    return hedef


def ele(yol):
    p = Path(yol)
    kok = dosyalar.drive_kok()
    hedef = kok / "_elenen" / p.name
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(hedef))
    c = sqlite3.connect(DB)
    _guncelle_db(c, p, hedef)
    c.commit()
    c.close()
    return hedef


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--adsiz" in sys.argv:
        for y, g, m in adsizlar():
            print(f"{y} | {g} | {m}")
    elif "--adlandir" in sys.argv:
        i = sys.argv.index("--adlandir")
        print(adlandir(sys.argv[i + 1], sys.argv[i + 2]))
    elif "--ele" in sys.argv:
        print(ele(sys.argv[sys.argv.index("--ele") + 1]))
    else:
        duzenle()
