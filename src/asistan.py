"""
"İTÜ Asistan" bilgi metni: yapay zekânın (Gemini uygulamasında Drive'dan eklenen dosya, ya da paneldeki
Sor kutusundan) sorulara cevap verebilmesi için panel verisinin düz metin özeti.

    python asistan.py      # veri/asistan.md (ana belge, ~25 bin karakter) + ham kayıtlar belgesi

Ana belge sırası: EKSİK → bu hafta + gelecek hafta → ders kartları → yaklaşan olaylar (75 gün) →
son 10 duyuru → teyitsiz söylentiler. Ham WhatsApp mesajları ve e-posta dökümü ayrı belgede:
Drive'ım/İTÜ/İTÜ Asistan - ham kayıtlar.md (ana belge linkini verir). Diğer öğrencilerin mesajları
panele girmez; panel_uret() mesajsız sürümü gömer.
"""
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERI = HERE.parent / "veri"
GUN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
KISA = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
AZAMI = 25000
HAM_AD = "İTÜ Asistan - ham kayıtlar.md"
# kullanıcının derslerinin konuşulduğu gruplar (sosyal gruplar Drive'a gitmez)
def _ders_grubu_deseni():
    """ayarlar.json -> whatsapp.dersGrubuDeseni: grup adında bunlardan biri geçerse ders grubu sayılır."""
    try:
        d = json.loads((Path(__file__).resolve().parent / "ayarlar.json").read_text(encoding="utf-8"))
        return (d.get("whatsapp") or {}).get("dersGrubuDeseni") or "FIZ|MAT|KIM|EHB|ELE|EEF|BLG|BBF|EKO|havuz"
    except (OSError, ValueError):
        return "FIZ|MAT|KIM|EHB|ELE|EEF|BLG|BBF|EKO|havuz"


DERS_GRUPLARI = re.compile(_ders_grubu_deseni(), re.I)
ILGISIZ = re.compile(r"lisansüstü|yüksek lisans|doktora|tezsiz|enstitü|yatay geçiş|dikey geçiş|çift anadal|çap\b|"
                     r"yandal|intibak|uolp|kktc|konservatuar|önlisans|masterbee|mikrokredi|bitirme|mezuniyet|"
                     r"azami süre|son sınıf|2\. öğretim|yabancı uyruklu", re.I)
SINAV = re.compile(r"quiz|vize|midterm|final|sınav|exam|deney", re.I)
AY = {a: i + 1 for i, a in enumerate(["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
                                       "Eylül", "Ekim", "Kasım", "Aralık"])}


def _ss(dk):
    return f"{dk // 60:02d}:{dk % 60:02d}"


def _t(s):
    try:
        return dt.datetime.fromisoformat(str(s)[:16])
    except ValueError:
        return None


def _tr_tarih(s):
    """'09 Ekim 2026 13:46' -> datetime"""
    m = re.match(r"(\d+) (\w+) (\d{4})(?: (\d\d):(\d\d))?", s or "")
    if not m or m.group(2) not in AY:
        return None
    return dt.datetime(int(m.group(3)), AY[m.group(2)], int(m.group(1)), int(m.group(4) or 0), int(m.group(5) or 0))


def _kisa(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _oku(ad, varsayilan):
    try:
        return json.loads((VERI / ad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return varsayilan


# ------------------------------------------------------------------ Drive linkleri
def _drive():
    """-> (İTÜ klasörü yolu, {göreli yol: id}, kök id) ; Drive for Desktop yoksa boş."""
    try:
        import dosyalar
        import drive_yerel
        kok = dosyalar.drive_kok()
        kid, idler = drive_yerel.klasor_idleri("İTÜ")
        return kok, idler, kid
    except Exception:
        return None, {}, None


def _link(yol, drive, klasor=False):
    import drive_yerel
    kok, idler, _ = drive
    if not yol:
        return None
    p = Path(yol)
    try:
        rel = p.relative_to(kok).as_posix() if kok else None
    except ValueError:
        rel = None
    did = idler.get(rel + ("/" if klasor else "")) if rel else None
    return drive_yerel.link(did, klasor=klasor) if did else drive_yerel.link(ad=p.name)


def ders_dosyalari():
    """Paneldeki ders penceresi için: {kod: {klasor, dosyalar: [{ad, kategori, tarih, link, ninova, basliklar}], linkler: [{ad, url}]}}"""
    drive, dk = _drive(), _oku("dosyalar.json", {})
    out = {}
    for v in (dk.get("dosyalar") or {}).values():
        if not v.get("ders") or not v.get("yol"):
            continue
        d = out.setdefault(v["ders"], {"klasor": None, "dosyalar": [], "linkler": []})
        if not d["klasor"]:
            k = Path(v["yol"])
            while k.parent.name != "Dersler" and k.parent != k:
                k = k.parent
            d["klasor"] = _link(k, drive, klasor=True)
        d["dosyalar"].append({"ad": v["ad"], "kategori": v.get("kategori") or "Diğer", "tarih": v.get("tarih") or "",
                              "link": _link(v["yol"], drive), "ninova": v.get("ninovaUrl") or v.get("url"),
                              "basliklar": (v.get("basliklar") or [])[:8]})
    for v in (dk.get("linkler") or {}).values():          # Ninova'daki video/site bağlantıları
        if v.get("ders") and v.get("url"):
            out.setdefault(v["ders"], {"klasor": None, "dosyalar": [], "linkler": []})["linkler"].append(
                {"ad": v["ad"], "url": v["url"], "yol": v.get("ninovaYolu") or ""})
    return out


# ------------------------------------------------------------------ olaylar
def olaylar(veri, wa, gun_ileri=75, geri=1):
    """Tüm kaynaklardan tarihli olaylar -> [(datetime, ders, metin, tür)] (sıralı, tekrarsız)."""
    o, n = veri.get("obs") or {}, veri.get("ninova") or {}
    ad = o.get("akademikDurum") or {}
    simdi = dt.datetime.now()
    bas, ufuk = simdi - dt.timedelta(days=geri), simdi + dt.timedelta(days=gun_ileri)
    out = []
    for x in wa.get("olaylar", []):
        t = _t(x.get("bas"))
        if t and bas <= t <= ufuk:
            yer = f" · {x['yer']}" if x.get("yer") else ""
            teyit = "" if x.get("teyit") != "yok" else " (teyit yok)"
            out.append((t, x.get("ders") or "", f"{x['tur']}{yer} — {_kisa(x.get('konu'), 160)}{teyit}",
                        x.get("olayTuru") or ("sınav" if SINAV.search(x["tur"]) else "")))
    for x in (veri.get("izlenceler") or []) + (n.get("izlenceSinavlari") or []):
        t = _t(x.get("bas"))
        if t and simdi - dt.timedelta(days=6) <= t <= ufuk:
            if x.get("bit") and x["bit"] != x["bas"]:
                out.append((t, x["ders"], f"{x['tur']} haftası ({x['bas'][5:]}–{str(x.get('bit', ''))[5:]}) — "
                                          f"{x.get('konu', '')} (izlence; dersin o haftaki gününde)", "sınav"))
            else:
                konu = f" — {x['konu']}" if x.get("konu") else ""
                out.append((t, x["ders"], f"{x['tur']} ({x['bas'][5:]}, ders saatinde){konu} (izlence)", "sınav"))
    for x in (o.get("finalTakvimim") or []):
        t = _t(x.get("tarih") or x.get("bas"))
        if t and simdi <= t <= ufuk:
            out.append((t, x.get("dersKodu") or x.get("ders", ""), "FİNAL", "sınav"))
    gizle = json.loads((HERE / "ayarlar.json").read_text(encoding="utf-8")).get("takvimGizle", [])
    for x in (veri.get("akademikTakvim") or []) + (veri.get("onemliTarihler") or []):
        if "Lisans / Önlisans" not in x.get("tablo", "Lisans / Önlisans") or x.get("tur") == "idari" \
                or ILGISIZ.search(x.get("olay", "")) or any(g in x.get("olay", "") for g in gizle):
            continue
        m = re.search(r"(\d)\.\s*sınıf", x.get("olay", ""), re.I)
        if m and m.group(1) != re.sub(r"\D", "", ad.get("sinifSeviye", "1"))[:1]:
            continue
        b, s = _t(x.get("bas")), _t(x.get("bit"))
        if b and (simdi <= b <= ufuk or (s and b <= simdi <= s)):
            out.append((b, "", f"{x['olay']} ({x.get('tarihMetni') or ''})", x.get("tur", "")))
    gorulen, son = set(), []
    for z in sorted(out, key=lambda z: z[0]):
        a = (z[0].date(), z[1], z[2][:40])
        if a not in gorulen:
            gorulen.add(a)
            son.append(z)
    return son


def _olay_satiri(z):
    t, ders, m, _ = z
    saat = "" if (t.hour, t.minute) == (0, 0) else f" {t:%H:%M}"
    return f"- {t:%d.%m} {KISA[t.weekday()]}{saat} · {ders + ' ' if ders else ''}{m}"


# ------------------------------------------------------------------ eksik kontrolü
def eksikler(veri, wa, dk, olay):
    """Önümüzdeki 7 gündeki her sınav: kapsam dosyası Drive'da mı, alt konular yazılı mı, salon/sıra belli mi?"""
    simdi = dt.datetime.now()
    dersler = wa.get("dersler") or {}
    oturma = dk.get("oturma") or {}
    out = []
    for t, ders, m, tur in olay:
        if not (simdi - dt.timedelta(hours=3) <= t <= simdi + dt.timedelta(days=7)) or tur != "sınav" or not ders:
            continue
        if "lab" in ders.lower() or ders.endswith("EL"):
            continue                          # lab: föy + Ninova deney videosu, ayrı kontrol
        s = next((x for x in dersler.get(ders, {}).get("sinavlar", [])
                  if _t(x.get("tarih")) and abs((_t(x["tarih"]) - t).days) <= 6), None)
        ad = (s or {}).get("ad") or m.split(" — ")[0]
        eksik = []
        if not s or not s.get("kapsam"):
            eksik.append("kapsam dosyası belirlenmedi")
        else:
            yok = [k for k in s["kapsam"] if not any(k.lower() in (v.get("ad") or "").lower()
                                                       for v in dk.get("dosyalar", {}).values())]
            if yok:
                eksik.append("Drive'da yok: " + ", ".join(yok))
        if not s or not s.get("konular"):
            eksik.append("alt konular yazılmadı")
        cevrimici = re.search(r"moodle|pearson|çevrimiçi|online|teams", m + " " + str((s or {}).get("salon", "")), re.I)
        if not cevrimici:
            ot = [v for v in oturma.values() if v.get("ders") == ders and _tr_tarih(v.get("dosyaTarihi") or "")
                  and _tr_tarih(v["dosyaTarihi"]) >= t - dt.timedelta(days=21)]
            if not (s and s.get("salon")) and not ot:
                eksik.append("salon/sıra belli değil")
        if eksik:
            out.append(f"EKSİK: {t:%d.%m %H:%M} {ders} {ad} — " + "; ".join(eksik))
    return out


# ------------------------------------------------------------------ ders kartları
def ders_karti(d, veri, wa, dk, drive, olay):
    kod = d["kod"]
    det = (veri.get("dersDetay") or {}).get(kod, {})
    ek = (wa.get("dersler") or {}).get(kod, {})
    y = [f"\n### {kod} — {d.get('ad', '')} (CRN {d['crn']})"]
    hoca = ek.get("hoca") or det.get("hoca")
    satir = []
    if hoca:
        satir.append(f"Hoca: {hoca}" + (f" ({ek['eposta']})" if ek.get("eposta") else ""))
    if ek.get("asistan"):
        satir.append(f"Asistan: {ek['asistan']}")
    if satir:
        y.append(" · ".join(satir))
    saat = [f"{GUN[s['gun']]} {_ss(s['bas'])}–{_ss(s['bit'] + 1)} {s.get('yerMetni') or s.get('mekan') or ''}".strip()
            for s in d.get("saatler", [])]
    if ek.get("yer"):
        saat.append(f"(yer notu: {ek['yer']})")
    y.append("Ders: " + "; ".join(saat) if saat else "Ders: saat yok")
    izb = (veri.get("izlenceBilgi") or {}).get(kod) or {}
    y.append("Not dağılımı: " + (ek.get("degerlendirme")
                                  or ("izlenceden: " + "; ".join(izb["agirliklar"]) if izb.get("agirliklar") else None)
                                  or "BİLİNMİYOR — syllabus okunmadı"))
    # sınavlar: ajanın yazdığı konu listeleri + olaylar
    sinavlar = ek.get("sinavlar") or []
    simdi = dt.datetime.now()
    for s in sinavlar:
        t = _t(s.get("tarih"))
        if t and t < simdi - dt.timedelta(days=2):
            continue
        y.append(f"- {s.get('ad')}: {t:%d.%m %a %H:%M}".replace(t.strftime('%a'), KISA[t.weekday()]) if t
                 else f"- {s.get('ad')}: tarih belli değil")
        if s.get("salon"):
            y[-1] += f" · {s['salon']}" + (f", {s['sira']}" if s.get("sira") else "")
        if s.get("konular"):
            y.append("  Konular: " + "; ".join(s["konular"]))
        if s.get("kapsam"):
            y.append("  Kapsam dosyaları: " + ", ".join(s["kapsam"]))
    diger = [_olay_satiri(z) for z in olay if z[1] == kod and z[0] >= simdi - dt.timedelta(hours=3)
             and not any(_t(s.get("tarih")) and _t(s["tarih"]).date() == z[0].date() for s in sinavlar)][:6]
    if diger:
        y.append("Tarihler:")
        y += ["  " + x[2:] for x in diger]
    for v in (dk.get("oturma") or {}).values():
        if v.get("ders") == kod:
            y.append(f"Oturma planı ({v['dosya']}): salon {v['salon']}, kürsüden {v['sira']}. sıra, "
                     f"soldan {v['sutun']}. sütun ({v['sutunSayisi']} sütun) — {_link(v['yol'], drive)}")
    for o in (dk.get("odevler") or {}).values():
        if o.get("ders") == kod:
            bit = _tr_tarih(o.get("teslimBitis") or "")
            if bit and bit < simdi - dt.timedelta(days=14):
                continue
            y.append(f"Ödev: {o['baslik']} — son {o.get('teslimBitis')}; "
                     + (f"YÜKLENDİ {o['yuklendi']} (dosya adı Ninova'da görünmüyor)" if o.get("yuklendi") else "YÜKLENMEDİ"))
    # dersin WhatsApp grubu (Ninova mesaj panosunda paylaşılan davet linki)
    for s in (veri.get("ninova") or {}).get("siniflar", []):
        if s["ders"].split(" - ")[0] == kod:
            wl = next((u for m in s.get("mesajPanosu", []) for u in m.get("linkler", []) if "chat.whatsapp.com/" in u), None)
            if wl:
                y.append(f"WhatsApp grubu (Ninova mesaj panosu): {wl}")
            break
    # Drive klasörü + önemli dosyalar
    dosya = [v for v in (dk.get("dosyalar") or {}).values() if v.get("ders") == kod and v.get("yol")]
    if dosya:
        klasor = Path(dosya[0]["yol"])
        while klasor.parent.name != "Dersler" and klasor.parent != klasor:
            klasor = klasor.parent
        y.append(f"Drive klasörü: {_link(klasor, drive, klasor=True)}")
        onemli = []
        for kat, n in (("Syllabus", 2), ("Slaytlar", 2), ("Recitation-Problem Session", 1),
                       ("Sınavlar (çıkmış + oturma planları)", 2)):
            secim = sorted([v for v in dosya if v.get("kategori") == kat],
                           key=lambda v: _tr_tarih(v.get("tarih") or "") or dt.datetime.min, reverse=True)[:n]
            onemli += [f"{v['ad']} ({kat.split(' ')[0]}, {(v.get('tarih') or '').rsplit(' ', 1)[0] if ':' in (v.get('tarih') or '') else (v.get('tarih') or '?')}) {_link(v['yol'], drive)}"
                       for v in secim]
        if onemli:
            y.append("Dosyalar: " + " | ".join(onemli))
    # devam
    for s in (veri.get("ninova") or {}).get("siniflar", []):
        if s["ders"].split(" - ")[0] == kod and (s.get("yoklama") or {}).get("katildi"):   # 0 = Ninova'ya işlenmemiş
            yk = s["yoklama"]
            y.append(f"Devam (Ninova yoklaması): {yk['katildi']} saat katılım işlenmiş (dönem tablosunda {yk['toplam']} saat; "
                     "henüz işlenmemiş haftalar da sayıda)")
            break
    if ek.get("notu"):
        y.append("Not: " + _kisa(ek["notu"], 220))
    return y


# ------------------------------------------------------------------ belgeler
def metin(veri=None, mesajlar=True, gun_ileri=75, **_):
    veri = veri or json.loads((VERI / "panel.json").read_text(encoding="utf-8"))
    o, n = veri.get("obs") or {}, veri.get("ninova") or {}
    wa = veri.get("whatsapp") or {}
    if not wa.get("dersler"):
        wa = {**_oku("whatsapp/notlar.json", {}), **{k: v for k, v in wa.items() if v}}
    dk = _oku("dosyalar.json", {})
    drive = _drive() if mesajlar else (None, {}, None)
    simdi = dt.datetime.now()
    ad = o.get("akademikDurum") or {}
    og = o.get("ogrenci") or {}
    olay = olaylar(veri, wa, gun_ileri)

    y = ["# İTÜ Asistan — kişisel bilgi dosyası"]
    y += eksikler(veri, wa, dk, olay)
    y.append(f"Güncellendi: {simdi:%d.%m.%Y %H:%M} ({GUN[simdi.weekday()]}). 'Yarın', 'bu hafta' gibi ifadeleri "
             "bu tarihe göre hesapla. Kullanıcının kendi İTÜ verisi (OBS, Ninova, Moodle, takvim, ders grupları, "
             "e-posta). 'teyit yok' = öğrenci söylentisi, öyle belirt. Dosya linkleri kullanıcının Drive'ında; "
             "dosya içeriği gerekirse Drive'dan aç.")
    if mesajlar and drive[0]:
        ham = drive[0] / HAM_AD
        y.append(f"Ham WhatsApp mesajları ve e-posta dökümü ayrı belgede: {_link(ham, drive)}")
    y.append(f"Öğrenci: {og.get('program', '')} · {ad.get('sinifSeviye', '')}")

    # a) bu hafta + gelecek hafta
    pzt = (simdi - dt.timedelta(days=simdi.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    y.append(f"\n## Bu hafta ve gelecek hafta ({pzt:%d.%m}–{pzt + dt.timedelta(days=13):%d.%m})")
    for z in olay:
        if simdi - dt.timedelta(hours=6) <= z[0] < pzt + dt.timedelta(days=14):
            y.append(_olay_satiri(z))
    onem1 = [x for x in wa.get("notlar", []) if x.get("onem") == 1 and not x.get("ders")
             and _t(x.get("tarih")) and _t(x["tarih"]) > simdi - dt.timedelta(days=5)]
    for x in onem1[:4]:
        y.append(f"- Gündem: {x['baslik']} — {_kisa(x['metin'], 180)}")
    y.append("Haftalık program: " + "; ".join(
        f"{KISA[g]} " + ", ".join(f"{_ss(s['bas'])} {d['kod']}" for d in o.get("dersler", [])
                                    for s in d.get("saatler", []) if s["gun"] == g)
        for g in range(7) if any(s["gun"] == g for d in o.get("dersler", []) for s in d.get("saatler", []))))

    # b) ders kartları
    y.append("\n## Ders kartları")
    for d in o.get("dersler", []):
        y += ders_karti(d, veri, wa, dk, drive, olay)
        notlar = [x for x in wa.get("notlar", []) if x.get("ders") == d["kod"] and x.get("teyit") != "yok"
                  and _t(x.get("tarih")) and _t(x["tarih"]) > simdi - dt.timedelta(days=21)]
        for x in sorted(notlar, key=lambda z: (z.get("onem", 3), str(z.get("tarih"))))[:2]:
            y.append(f"Bilgi: {x['baslik']} — {_kisa(x['metin'], 150)}")
    y.append(f"\nAGNO: {ad.get('genelNotOrtalamasi')} · dönem içi ortalama: {o.get('donemIciOrtalama')}")
    for x in (o.get("donemIciNotlar") or [])[:12]:
        y.append("- " + ", ".join(f"{k}: {v}" for k, v in x.items() if v not in (None, "") and len(str(v)) < 50))

    # c) yaklaşan olaylar
    y.append(f"\n## Yaklaşan olaylar (75 gün, gelecek haftadan sonrası)")
    for z in olay:
        if z[0] >= pzt + dt.timedelta(days=14):
            y.append(_olay_satiri(z))

    # d) son 10 duyuru
    y.append("\n## Son Ninova/Moodle duyuruları (son 10)")
    for x in n.get("duyurular", [])[:10]:
        y.append(f"- {x.get('tarih', '')[:12].strip()} · {(x.get('ders') or '').split(' - ')[0]} · {x['baslik']}: "
                 f"{_kisa(x.get('tamMetin') or x.get('ozet'), 160)}")

    # genel notlar (burs, gündem, fırsat) + e) söylentiler
    genel = [x for x in wa.get("notlar", []) if not x.get("ders") and x.get("teyit") != "yok"
             and _t(x.get("tarih")) and _t(x["tarih"]) > simdi - dt.timedelta(days=21)]
    gy = []
    # başvurular (panelde takip ettiklerin; rutin db'den veri/basvurular.json'a yansıtır) + açık fırsat önerileri
    bas = [b for b in _oku("basvurular.json", []) if b.get("asama", "ilgi") in ("ilgi", "hazirlik", "basvurdum", "surec")]
    if bas:
        gy.append("\n## Takip ettiğim başvurular (Fırsatlar sekmesi)")
        for b in sorted(bas, key=lambda z: str(z.get("sonBasvuru") or "9")):
            gy.append(f"- {b.get('ad')} ({b.get('tur', '')}, {b.get('kurum', '')}) · aşama: {b.get('asama', 'ilgi')}"
                      + (f" · son başvuru {b['sonBasvuru']}" if b.get("sonBasvuru") else "")
                      + (f" · mülakat/test {b['mulakat']}" if b.get("mulakat") else ""))
    acik = [f for f in wa.get("firsatlar", []) if not f.get("sonBasvuru") or str(f["sonBasvuru"]) >= f"{simdi:%Y-%m-%d}"]
    if acik:
        gy.append("\n## Açık fırsat önerileri (bana uygun bulunanlar)")
        for f in acik[:8]:
            gy.append(f"- {f.get('ad')} ({f.get('tur', '')}, {f.get('kurum', '')})"
                      + (f" · son başvuru {f['sonBasvuru']}" if f.get("sonBasvuru") else "") + f" · {f.get('url', '')}")
    korunan = len(gy)                                  # başvurular ve fırsatlar kısaltmada silinmez
    if genel:
        gy.append("\n## Genel (burs, gündem, fırsat — teyitli)")
        for x in sorted(genel, key=lambda z: (z.get("onem", 3), str(z.get("tarih"))))[:8]:
            gy.append(f"- {x['baslik']}: {_kisa(x['metin'], 160)}")
    sy = []
    soylenti = [x for x in wa.get("notlar", []) if x.get("teyit") in ("yok", "celiski")]
    if soylenti:
        sy.append("\n## Teyitsiz söylentiler")
        for x in soylenti[:10]:
            sy.append(f"- {x.get('ders') or 'genel'}: {x['baslik']} — {_kisa(x['metin'], 140)}")
    uzun = lambda *p: len("\n".join(sum(p, []))) + 1
    while len(gy) > max(korunan, 1) and uzun(y, gy, sy) > AZAMI:   # sınır aşılırsa önce genel notlar, sonra 75 günlük liste kısalır
        gy.pop()
    kes = "(25 bin karakter sınırı yüzünden kısaltıldı; tamamı ham kayıtlar belgesinde.)"
    while uzun(y, gy, sy) > AZAMI - len(kes) - 1 and len(y) > 50:
        y.pop(next(i for i in range(len(y) - 1, 0, -1) if y[i].startswith(("- ", "Bilgi:"))))
    if uzun(y, gy, sy) + len(kes) > AZAMI - 200:
        y.append(kes)
    return "\n".join(y + gy + sy) + "\n"


def ham_metin(veri=None, mesaj_gun=14, azami_mesaj=400):
    """Ayrı belge: tüm notlar (tam metin), ders gruplarındaki mesajlar, e-postalar, dosya listesi."""
    veri = veri or json.loads((VERI / "panel.json").read_text(encoding="utf-8"))
    wa = _oku("whatsapp/notlar.json", {})
    dk = _oku("dosyalar.json", {})
    simdi = dt.datetime.now()
    y = ["# İTÜ Asistan — ham kayıtlar", f"Güncellendi: {simdi:%d.%m.%Y %H:%M}. Ana belge: Drive'da "
         "'İTÜ Asistan (güncel)'. Burası arama için: tam notlar, grup mesajları, e-postalar, dosya listesi."]
    y.append("\n## Tüm notlar (tam metin)")
    for x in sorted(wa.get("notlar", []), key=lambda z: str(z.get("tarih")), reverse=True):
        y.append(f"- {str(x.get('tarih'))[:16]} [{x.get('teyit')}] {x.get('ders') or ''} {x['baslik']}: {x['metin']}"
                 + (f" ({x['teyitNot']})" if x.get("teyitNot") else "") + (f" {x['link']}" if x.get("link") else ""))
    y.append("\n## İndirilen ders dosyaları")
    for v in sorted((dk.get("dosyalar") or {}).values(), key=lambda v: (v.get("ders") or "", v.get("kategori") or "")):
        y.append(f"- {v.get('ders')} · {v.get('kategori')} · {v.get('ninovaYolu') or v.get('ad')} · {v.get('tarih') or ''}"
                 + (f" · başlıklar: {'; '.join(v['basliklar'][:15])}" if v.get("basliklar") else ""))
    for v in (dk.get("linkler") or {}).values():
        y.append(f"- {v.get('ders')} · bağlantı · {v.get('ad')}: {v.get('url')}")
    for v in (dk.get("buyuk") or {}).values():
        y.append(f"- {v.get('ders')} · 100 MB üstü, indirilmedi · {v.get('ad')} ({v.get('boyut')}): {v.get('url')}")
    edb = VERI / "eposta" / "epostalar.db"
    if edb.exists():
        c = sqlite3.connect(edb)
        sinir = (simdi - dt.timedelta(days=30)).isoformat(timespec="minutes")
        gurultu = re.compile(r"^\[Vefat\]|BAŞSAĞLIĞI|İTÜ'de Bu Hafta|E-Bülteni", re.I)
        satir = [r for r in c.execute("SELECT tarih, kimden, konu, metin FROM epostalar WHERE tarih > ? "
                                      "ORDER BY tarih DESC", (sinir,)) if not gurultu.search(r[2] or "")]
        c.close()
        y.append("\n## İTÜ e-postası (son 30 gün)")
        for t, kim, konu, govde in satir[:80]:
            kim = re.sub(r"\s*<[^>]+>", "", kim or "").strip('" ') or kim
            y.append(f"- {t[:16]} · {kim[:40]} · {konu}: {_kisa(re.sub(r'<[^>]+>', ' ', govde or ''), 400)}")
    db = VERI / "whatsapp" / "mesajlar.db"
    if db.exists():
        import whatsapp_ozet
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        sinir = int((simdi - dt.timedelta(days=mesaj_gun)).timestamp())
        satirlar = [r for r in c.execute("SELECT rowid, * FROM mesajlar WHERE zaman > ? AND benden=0 "
                                         "ORDER BY grup_adi, zaman", (sinir,))
                    if DERS_GRUPLARI.search((r["grup_adi"] or "") + " " + (r["topluluk"] or "")) and whatsapp_ozet.aday_mi(r)]
        c.close()
        satirlar = sorted(sorted(satirlar, key=lambda r: r["zaman"])[-azami_mesaj:],
                          key=lambda r: (r["grup_adi"], r["zaman"]))
        y.append(f"\n## Ders gruplarındaki mesajlar (son {mesaj_gun} gün, isimsiz, sohbet elendi)")
        y.append("Öğrencilerin yazdıkları — doğru olmayabilir.")
        grup = None
        for r in satirlar:
            if r["grup_adi"] != grup:
                grup = r["grup_adi"]
                y.append(f"\n### {grup}")
            m = re.sub(r"@\d{6,}", "@…", _kisa(r["metin"], 300))
            ek = f" [dosya: {r['dosya_adi'] or r['tur']}]" if r["tur"] in ("belge",) else ""
            y.append(f"- {dt.datetime.fromtimestamp(r['zaman']):%d.%m %H:%M} {m}{ek}")
    return "\n".join(y) + "\n"


def yaz(veri=None):
    t = metin(veri, mesajlar=True)
    (VERI / "asistan.md").write_text(t, encoding="utf-8")
    h = ham_metin(veri)
    (VERI / "asistan_ham.md").write_text(h, encoding="utf-8")
    try:
        import dosyalar
        kok = dosyalar.drive_kok()
        if kok:
            kok.mkdir(parents=True, exist_ok=True)
            (kok / HAM_AD).write_text(h, encoding="utf-8")
            (kok / "İTÜ Asistan.txt").write_text(t, encoding="utf-8")   # telefonda Gemini'ye eklenen dosya
    except OSError:
        pass
    return t, h


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    t, h = yaz()
    print(f"veri/asistan.md yazıldı ({len(t)} karakter); ham kayıtlar {len(h)} karakter")
