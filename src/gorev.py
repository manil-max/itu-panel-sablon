"""
Zamanlanmış görevin tek komutu: veriyi toplar (topla.py) ve özet için gereken
"yeni ne var" bilgisini yazdırır. Görev başka komut çalıştırmasın, izin sormasın diye.

    python gorev.py            # topla + özet
    python gorev.py --ozet     # sadece özet (toplamadan)
    python gorev.py --ozet --dosya   # özeti ekrana değil veri/adaylar.md dosyasına yaz (Gemini okur)
    python gorev.py --panel    # değerlendirmeden sonra paneli yeniden üret, adayları işaretle

Çıkış kodu 2 = İTÜ girişi başarısız (tekrar deneme, hesap kilitlenebilir).
"""
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
VERI = KOK / "veri"
ONCEKI = VERI / "gorev_onceki.json"
AYLAR = {a: i for i, a in enumerate(["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz",
                                      "ağustos", "eylül", "ekim", "kasım", "aralık"], 1)}


def tr_tarih(s):
    """'30 Eylül 2026 22:57' -> datetime"""
    m = re.match(r"(\d{1,2}) (\w+) (\d{4})(?: (\d{1,2}):(\d{2}))?", s or "")
    if not m or m.group(2).lower() not in AYLAR:
        return None
    return dt.datetime(int(m.group(3)), AYLAR[m.group(2).lower()], int(m.group(1)),
                       int(m.group(4) or 0), int(m.group(5) or 0))


def iso(s):
    try:
        return dt.datetime.fromisoformat((s or "")[:16])
    except ValueError:
        return None


def topla():
    p = subprocess.run([sys.executable, str(HERE / "topla.py")], cwd=HERE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    cikti = (p.stdout or "") + (p.stderr or "")
    if p.returncode == 2 or "GIRIS_HATASI" in cikti or "GirisHatasi" in cikti or "giriş başarısız" in cikti.lower():
        print("GIRIS_HATASI: İTÜ girişi yapılamadı. Tekrar deneme.")
        print("\n".join(cikti.strip().splitlines()[-5:]))
        sys.exit(2)
    if p.returncode != 0:
        print("TOPLA_HATASI (kod", p.returncode, ")")
        print("\n".join(cikti.strip().splitlines()[-15:]))
        sys.exit(1)
    uyarilar = [s for s in cikti.splitlines() if "alınamadı" in s or "Hata" in s]
    print("topla.py tamam." + (" Uyarılar: " + " | ".join(uyarilar[:5]) if uyarilar else ""))


def ozet():
    d = json.loads((VERI / "panel.json").read_text(encoding="utf-8"))
    onceki = json.loads(ONCEKI.read_text(encoding="utf-8")) if ONCEKI.exists() else {}
    simdi = dt.datetime.now()
    son = iso(onceki.get("zaman")) or simdi - dt.timedelta(days=1)
    n, o = d.get("ninova") or {}, d.get("obs") or {}
    out = {"guncellendi": d.get("guncellendi"), "oncekiCalisma": son.isoformat(timespec="minutes")}
    out["derslerim"] = [f'{x["kod"]} {x.get("ad") or ""}'.strip() for x in o.get("dersler", [])]

    out["yeniNinovaDuyuru"] = [f'{x["ders"]}: {x["baslik"]} ({x["tarih"]})' for x in n.get("duyurular", [])
                               if (tr_tarih(x.get("tarih")) or dt.datetime.min) > son]
    out["odevler"] = [(f'{x.get("ders")}: {x.get("baslik") or x.get("ad")} — teslim {x.get("teslim") or x.get("bitis")}'
                       if x.get("ders") else " · ".join(map(str, x.get("alanlar") or []))[:260])
                      for x in n.get("odevler", [])]
    out["yeniDosya"] = [f'{s["ders"]}: {f["ad"]} ({f["tarih"]})' for s in n.get("siniflar", [])
                        for f in s.get("dosyalar", []) if (tr_tarih(f.get("tarih")) or dt.datetime.min) > son]
    out["yeniMesajPanosu"] = [f'{s["ders"]}: {(m.get("baslik") or m.get("metin") or "")[:80]}'
                              for s in n.get("siniflar", []) for m in s.get("mesajPanosu", [])
                              if (tr_tarih(m.get("tarih")) or dt.datetime.min) > son]

    notlar = {f'{x.get("dersKodu") or x.get("ders")}|{x.get("ad") or x.get("harfNot") or x.get("not")}':
              x for x in (o.get("harfNotlari") or []) + (o.get("donemIciNotlar") or [])}
    out["yeniNot"] = [k for k in notlar if k not in set(onceki.get("notlar", []))]

    ufuk = simdi + dt.timedelta(days=7)
    yakin = []
    for x in (d.get("izlenceSinavlari") or n.get("izlenceSinavlari") or []):
        b = iso(x.get("bas"))
        if b and simdi - dt.timedelta(days=5) <= b <= ufuk:
            yakin.append(f'{x["ders"]} {x["tur"]} ({x.get("konu", "")}) haftası {x["bas"]}–{x.get("bit")}')
    for x in n.get("sinavTarihleri", []) + (o.get("finalTakvimim") or []):
        b = iso(x.get("tarih") or x.get("bas"))
        if b and simdi <= b <= ufuk:
            yakin.append(f'{x.get("ders")}: {x.get("tur") or x.get("baslik") or "sınav"} {b:%d.%m %H:%M}')
    gizle = json.loads((HERE / "ayarlar.json").read_text(encoding="utf-8")).get("takvimGizle", [])
    for x in d.get("akademikTakvim", []) + d.get("onemliTarihler", []):
        if "Lisans / Önlisans" not in x.get("tablo", "Lisans / Önlisans") or x.get("tur") == "idari"                 or any(g in x.get("olay", "") for g in gizle):
            continue
        for alan in ("bas", "bit"):
            t = iso(x.get(alan))
            if t and simdi <= t <= ufuk:
                yakin.append(f'{x["olay"]} — {"başlıyor" if alan == "bas" else "bitiyor"} {t:%d.%m}')
                break
    out["onumuzdeki7Gun"] = yakin

    db = VERI / "whatsapp" / "mesajlar.db"
    if db.exists():
        c = sqlite3.connect(db)
        out["whatsappYeni"] = {g: k for g, k in c.execute(
            "SELECT grup_adi, COUNT(*) FROM mesajlar WHERE zaman > ? GROUP BY grup_adi ORDER BY 2 DESC",
            (int(son.timestamp()),))}
        c.close()
        durum = VERI / "whatsapp" / "durum.json"
        if durum.exists():
            out["whatsappKopru"] = json.loads(durum.read_text(encoding="utf-8"))

    print(json.dumps(out, ensure_ascii=False, indent=1))
    bosluklar(d)
    whatsapp_adaylari()
    eposta_adaylari()
    ONCEKI.write_text(json.dumps({"zaman": simdi.isoformat(timespec="minutes"), "notlar": list(notlar)},
                                 ensure_ascii=False), encoding="utf-8")


def bosluklar(d):
    """Panelde eksik kalanlar: ajan bunları gruplardan / e-postadan / Ninova'dan doldurmaya çalışır."""
    yol = VERI / "whatsapp" / "notlar.json"
    notlar = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
    ek, detay = notlar.get("dersler", {}), d.get("dersDetay") or {}
    satir = []
    for ders in (d.get("obs") or {}).get("dersler", []):
        kod, x = ders["kod"], detay.get(ders["kod"], {})
        online = "Sanal" in str(x.get("yontem") or "")
        if not online and not any(s.get("sinif") or s.get("mekan") for s in ders.get("saatler", [])) \
                and not ek.get(kod, {}).get("yer"):
            satir.append(f"- {kod}: OBS'de derslik yok (bina: {', '.join({s.get('bina') or '?' for s in ders.get('saatler', [])})})"
                         " -> dersler[kod].yer")
        if not x.get("hoca") and not ek.get(kod, {}).get("hoca"):
            satir.append(f"- {kod}: hoca adı yok -> dersler[kod].hoca (Ninova duyurusu / izlence / grup)")
    simdi = dt.datetime.now()
    for o in notlar.get("olaylar", []):
        b = iso(o.get("bas"))
        if b and b >= simdi and o.get("ders") and not o.get("yer") and o.get("olayTuru", "sınav") != "başvuru":
            satir.append(f"- olay {o['ders']} {o['tur']} {o['bas']}: yer yok -> olaylar[].yer")
    for n in notlar.get("notlar", []):
        t = iso(n.get("tarih"))
        if n.get("teyit") == "yok" and (n.get("onem") or 3) <= 2 and t and (simdi - t).days >= 2:
            satir.append(f"- teyit bekleyen not '{n['id']}': {n['baslik'][:80]} -> Ninova/e-postada doğrulandı mı?")
    print(f"\n=== PANEL_BOSLUKLARI: {len(satir)} ===")
    print("\n".join(satir) if satir else "(yok)")


def whatsapp_adaylari(sinir=400):
    """Değerlendirilmemiş aday mesajları yazdırır; rowid'leri bekleyen.json'a koyar (--panel işaretler)."""
    db = VERI / "whatsapp" / "mesajlar.db"
    if not db.exists():
        return
    sys.path.insert(0, str(HERE))
    import whatsapp_ozet as wo
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    satirlar = c.execute("SELECT rowid, * FROM mesajlar WHERE degerlendirildi=0 AND benden=0 ORDER BY grup_adi, zaman").fetchall()
    c.close()
    tum_adaylar = [r for r in satirlar if wo.aday_mi(r)]
    adaylar = tum_adaylar[:sinir]                      # fazlası bir sonraki çalışmaya kalır
    kalan = {r["rowid"] for r in tum_adaylar[sinir:]}
    (VERI / "whatsapp" / "bekleyen.json").write_text(
        json.dumps([r["rowid"] for r in satirlar if r["rowid"] not in kalan]), encoding="utf-8")
    print(f"\n=== WHATSAPP_ADAYLARI: {len(satirlar)} yeni mesaj, {len(adaylar)} aday"
          + (f", {len(kalan)} aday sonraki çalışmaya kaldı" if kalan else "") + " ===")
    grup = None
    for r in adaylar:
        if r["grup_adi"] != grup:
            grup = r["grup_adi"]
            print(f"## {grup}")
        metin = re.sub(r"\s+", " ", (r["metin"] or "").strip())[:400]
        ek = f" [{r['tur']}: {r['dosya_adi'] or ''} -> {r['dosya'] or 'inmedi'}]" if r["tur"] in ("belge", "foto", "video") else ""
        alinti = f" (yanıt: «{re.sub(chr(10), ' ', r['alinti'])[:80]}»)" if r["alinti"] else ""
        print(f"{dt.datetime.fromtimestamp(r['zaman']):%d.%m %H:%M}|{metin}{ek}{alinti}")


GURULTU_EPOSTA = re.compile(r"^\[Vefat\]|BAŞSAĞLIĞI|İTÜ'de Bu Hafta|E-Bülteni|Kuvaterner|AYBE Semineri", re.I)


def eposta_adaylari():
    """Değerlendirilmemiş İTÜ e-postalarını yazdırır (başsağlığı/bülten gibi gürültü elenir)."""
    db = VERI / "eposta" / "epostalar.db"
    if not db.exists():
        return
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    satirlar = c.execute("SELECT rowid, * FROM epostalar WHERE degerlendirildi=0 ORDER BY tarih").fetchall()
    c.close()
    adaylar = [r for r in satirlar if not GURULTU_EPOSTA.search(r["konu"] or "")]
    (VERI / "eposta" / "bekleyen.json").write_text(json.dumps([r["rowid"] for r in satirlar]), encoding="utf-8")
    print(f"\n=== EPOSTA_ADAYLARI: {len(satirlar)} yeni e-posta, {len(adaylar)} aday ===")
    for r in adaylar:
        metin = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r["metin"] or "")).strip()[:900]
        print(f"- {r['tarih'][:16]} | {r['kimden'][:70]} | {r['konu']}\n  {metin}"
              + (f"\n  EKLER: {r['ekler']}" if r["ekler"] else ""))


def panel_yenile():
    """Önce paneli üret; yalnız başarılı üretimden sonra adayları tüket."""
    sys.path.insert(0, str(HERE))
    import kurulum
    if not kurulum.notlar_kontrol():                 # bozuk notlar.json ile panel üretme, adayları tüketme
        sys.exit(1)
    import topla
    topla.panel_uret()
    bek = VERI / "whatsapp" / "bekleyen.json"
    if bek.exists():
        ids = json.loads(bek.read_text(encoding="utf-8"))
        c = sqlite3.connect(VERI / "whatsapp" / "mesajlar.db")
        c.executemany("UPDATE mesajlar SET degerlendirildi=1 WHERE rowid=?", [(i,) for i in ids])
        c.commit()
        c.close()
        bek.unlink()
        print(len(ids), "WhatsApp mesajı değerlendirildi olarak işaretlendi")
    bek = VERI / "eposta" / "bekleyen.json"
    if bek.exists():
        ids = json.loads(bek.read_text(encoding="utf-8"))
        c = sqlite3.connect(VERI / "eposta" / "epostalar.db")
        c.executemany("UPDATE epostalar SET degerlendirildi=1 WHERE rowid=?", [(i,) for i in ids])
        c.commit()
        c.close()
        bek.unlink()
        print(len(ids), "e-posta değerlendirildi olarak işaretlendi")
    try:                                             # yeni önemli notlar telefona (ntfy)
        import bildirim
        bildirim.yeni_notlar()
    except Exception as e:
        print("bildirim gönderilemedi:", e.__class__.__name__)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if (VERI / "otomasyon_kapali").exists():
        print("OTOMASYON_KAPALI: otomasyon.bat ile kapatılmış, bu çalışma atlandı.")
        sys.exit(0)
    if "--panel" in sys.argv:
        panel_yenile()
        sys.exit(0)
    if "--ozet" not in sys.argv:
        topla()
    if "--dosya" in sys.argv:
        VERI.mkdir(exist_ok=True)
        hedef = VERI / "adaylar.md"
        with open(hedef, "w", encoding="utf-8") as f:
            eski, sys.stdout = sys.stdout, f
            try:
                ozet()
            finally:
                sys.stdout = eski
        print(f"ADAYLAR_HAZIR: {hedef} ({hedef.stat().st_size // 1024} KB)")
    else:
        ozet()
