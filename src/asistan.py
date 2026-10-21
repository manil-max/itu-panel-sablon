"""
"İTÜ Asistan" bilgi metni: yapay zekânın (Gemini uygulamasında Drive'dan eklenen dosya, ya da paneldeki
Sor kutusundan) sorulara cevap verebilmesi için panel verisinin düz metin özeti.

    python asistan.py      # veri/asistan.md yazar (Drive'a yüklenen sürüm: ders grubu mesajları dahil)

panel_uret() aynı metnin mesajsız sürümünü panele gömer (panel linki paylaşılabildiği için
diğer öğrencilerin mesajları panele girmez; sadece kullanıcının kendi Drive'ındaki belgeye girer).
"""
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERI = HERE.parent / "veri"
GUN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
# kullanıcının derslerinin konuşulduğu gruplar (sosyal gruplar Drive'a gitmez)
def _ders_grubu_deseni():
    try:
        d = json.loads((Path(__file__).resolve().parent / "ayarlar.json").read_text(encoding="utf-8"))
        return (d.get("whatsapp") or {}).get("dersGrubuDeseni") or "FIZ|MAT|KIM|EHB|ELE|EEF|BLG|havuz"
    except (OSError, ValueError):
        return "FIZ|MAT|KIM|EHB|ELE|EEF|BLG|havuz"


DERS_GRUPLARI = re.compile(_ders_grubu_deseni(), re.I)
ILGISIZ = re.compile(r"lisansüstü|yüksek lisans|doktora|tezsiz|enstitü|yatay geçiş|dikey geçiş|çift anadal|çap\b|"
                     r"yandal|intibak|uolp|kktc|konservatuar|önlisans|masterbee|mikrokredi|bitirme|mezuniyet|"
                     r"azami süre|son sınıf|2\. öğretim|yabancı uyruklu", re.I)


def _ss(dk):
    return f"{dk // 60:02d}:{dk % 60:02d}"


def _t(s):
    try:
        return dt.datetime.fromisoformat(str(s)[:16])
    except ValueError:
        return None


def metin(veri=None, mesajlar=True, gun_ileri=75, mesaj_gun=14, azami_mesaj=150):
    veri = veri or json.loads((VERI / "panel.json").read_text(encoding="utf-8"))
    o, n = veri.get("obs") or {}, veri.get("ninova") or {}
    dd = veri.get("dersDetay") or {}
    wa = veri.get("whatsapp") or {}
    if not wa and (VERI / "whatsapp" / "notlar.json").exists():
        wa = json.loads((VERI / "whatsapp" / "notlar.json").read_text(encoding="utf-8"))
    simdi = dt.datetime.now()
    ad = o.get("akademikDurum") or {}
    og = o.get("ogrenci") or {}
    y = []
    y.append("# İTÜ Asistan — kişisel bilgi dosyası")
    y.append(f"Güncellendi: {simdi:%d.%m.%Y %H:%M} (panel verisi: {veri.get('guncellendi', '?')}). "
             "Bugünün tarihine göre 'yarın', 'bu hafta' gibi ifadeleri sen hesapla.")
    y.append("Asistan için: Bu dosya kullanıcının kendi İTÜ verisi (OBS, Ninova, akademik takvim, WhatsApp ders "
             "grupları). İTÜ, ders, sınav, takvim sorularını buna göre cevapla. 'teyit yok' işaretli bilgiler "
             "öğrenci söylentisidir, öyle belirt.")
    y.append(f"\nÖğrenci: {og.get('program', '')} · {ad.get('sinifSeviye', '')}. "
             + "Danışman: " + ", ".join(x.get("ad", "") for x in o.get("danisman") or []))

    y.append("\n## Haftalık ders programı (bu dönem)")
    satir = []
    for d in o.get("dersler", []):
        det = dd.get(d["kod"], {})
        for s in d.get("saatler", []):
            satir.append((s["gun"], s["bas"], f"- {GUN[s['gun']]} {_ss(s['bas'])}–{_ss(s['bit'] + 1)} · {d['kod']} "
                          f"{d.get('ad', '')} · {s.get('yerMetni') or s.get('mekan') or 'derslik yok/online'} · "
                          f"CRN {d['crn']}" + (f" · {det['hoca']}" if det.get("hoca") else "")))
    y += [x[2] for x in sorted(satir)]

    y.append(f"\n## Yaklaşan olaylar (önümüzdeki {gun_ileri} gün)")
    ufuk = simdi + dt.timedelta(days=gun_ileri)
    olay = []
    for x in wa.get("olaylar", []):
        t = _t(x.get("bas"))
        if t and simdi - dt.timedelta(days=1) <= t <= ufuk:
            olay.append((t, f"- {t:%d.%m} {GUN[t.weekday()]} {t:%H:%M} · {x['ders']} {x['tur']} — {x.get('konu', '')} "
                            f"({'teyitli' if x.get('teyit') != 'yok' else 'teyit yok'})"))
    for x in (veri.get("izlenceler") or []) + (n.get("izlenceSinavlari") or []):
        t = _t(x.get("bas"))
        if t and simdi - dt.timedelta(days=6) <= t <= ufuk:
            olay.append((t, f"- {x['bas']}–{x.get('bit', '')} haftası · {x['ders']} {x['tur']} — {x.get('konu', '')} "
                            "(izlence; dersin o haftaki gününde)"))
    for x in (n.get("sinavTarihleri") or []) + (o.get("finalTakvimim") or []):
        t = _t(x.get("tarih") or x.get("bas"))
        if t and simdi <= t <= ufuk:
            olay.append((t, f"- {t:%d.%m %H:%M} · {x.get('ders', '')} {x.get('tur') or x.get('baslik') or 'sınav'}"))
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
            olay.append((b, f"- {x.get('tarihMetni') or f'{b:%d.%m.%Y}'} · {x['olay']}"))
    gorulen = set()
    for _, s in sorted(olay, key=lambda z: z[0]):
        if s not in gorulen:
            gorulen.add(s)
            y.append(s)

    y.append("\n## Notlar ve devam")
    y.append(f"AGNO: {ad.get('genelNotOrtalamasi')} · dönem içi ortalama: {o.get('donemIciOrtalama')}")
    for x in (o.get("harfNotlari") or []) + (o.get("donemIciNotlar") or []):
        y.append("- " + ", ".join(f"{k}: {v}" for k, v in x.items() if v not in (None, "") and len(str(v)) < 60))
    for s in n.get("siniflar", []):
        yk = s.get("yoklama") or {}
        gecmis = [h for h in yk.get("haftalar", []) if h.get("katilim") or 0]
        if gecmis:
            y.append(f"- Devam {s['ders'].split(' - ')[0]}: " + ", ".join(
                f"{h['hafta']} {h['katilim']}/{h['ders']}" for h in gecmis))

    y.append("\n## Ninova (son duyurular, ödevler, dosyalar)")
    for x in n.get("duyurular", [])[:12]:
        y.append(f"- {x.get('tarih', '')} · {(x.get('ders') or '').split(' - ')[0]} · {x['baslik']}: "
                 f"{re.sub(r'\s+', ' ', x.get('tamMetin') or x.get('ozet') or '')[:500]}")
    for x in n.get("odevler", []):
        y.append(f"- ÖDEV: {json.dumps(x, ensure_ascii=False)[:300]}")
    for s in n.get("siniflar", []):
        dosya = [f["ad"] for f in s.get("dosyalar", [])][:12]
        if dosya:
            y.append(f"- {s['ders'].split(' - ')[0]} dosyaları: " + ", ".join(dosya))

    if wa.get("notlar"):
        y.append("\n## WhatsApp grupları ve e-postadan notlar (yapay zekâ özeti)")
        for x in sorted(wa["notlar"], key=lambda z: (z.get("onem", 3), str(z.get("tarih")))):
            teyit = {"ninova": "teyitli", "resmi": "resmî"}.get(x.get("teyit"), "teyit yok — öğrenci söylentisi")
            y.append(f"- [{teyit}] {x['baslik']}: {x['metin']}" + (f" ({x['teyitNot']})" if x.get("teyitNot") else ""))

    if wa.get("dosyalar"):
        y.append("\n## Gruplardan inen dosyalar (kullanıcının Google Drive'ında, linkler sadece ona açık)")
        if wa.get("klasorLink"):
            y.append(f"Klasör: {wa['klasorLink']}")
        for x in wa["dosyalar"][:30]:
            y.append(f"- {x['tarih'][:10]} · {x['grup']} · {x['ad']}" + (f" — {x['link']}" if x.get("link") else ""))

    kampus = veri.get("kampus") or {}
    if kampus.get("yemekSaatleri"):
        y.append("\n## Kampüs")
        y.append("Yemek saatleri: " + re.sub(r"\s+", " ", json.dumps(kampus["yemekSaatleri"], ensure_ascii=False))[:400])

    edb = VERI / "eposta" / "epostalar.db"
    if mesajlar and edb.exists():                    # sadece Drive sürümüne (panel linki paylaşılabiliyor)
        c = sqlite3.connect(edb)
        sinir = (simdi - dt.timedelta(days=21)).isoformat(timespec="minutes")
        gurultu = re.compile(r"^\[Vefat\]|BAŞSAĞLIĞI|İTÜ'de Bu Hafta|E-Bülteni", re.I)
        satir = [r for r in c.execute("SELECT tarih, kimden, konu, metin FROM epostalar WHERE tarih > ? "
                                      "ORDER BY tarih DESC", (sinir,)) if not gurultu.search(r[2] or "")]
        c.close()
        y.append("\n## İTÜ e-postası (son 21 gün, en yeni üstte)")
        for t, kim, konu, govde in satir[:40]:
            kim = re.sub(r"\s*<[^>]+>", "", kim or "").strip('" ') or kim
            ozet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", govde or "")).strip()[:220]
            y.append(f"- {t[:10]} · {kim[:40]} · {konu}: {ozet}")

    db = VERI / "whatsapp" / "mesajlar.db"
    if mesajlar and db.exists():
        import whatsapp_ozet
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        sinir = int((simdi - dt.timedelta(days=mesaj_gun)).timestamp())
        satirlar = [r for r in c.execute("SELECT rowid, * FROM mesajlar WHERE zaman > ? AND benden=0 "
                                         "ORDER BY grup_adi, zaman", (sinir,))
                    if DERS_GRUPLARI.search((r["grup_adi"] or "") + " " + (r["topluluk"] or "")) and whatsapp_ozet.aday_mi(r)]
        c.close()
        satirlar = sorted(sorted(satirlar, key=lambda r: r["zaman"])[-azami_mesaj:],
                          key=lambda r: (r["grup_adi"], r["zaman"]))     # en yeni N mesaj
        y.append(f"\n## Ders gruplarındaki mesajlar (son {mesaj_gun} gün, en yeni {azami_mesaj}, isimsiz, sohbet elendi)")
        y.append("Öğrencilerin yazdıkları — doğru olmayabilir. 'Gruba X hakkında bir şey yazılmış mı' sorusu için.")
        grup = None
        for r in satirlar:
            if r["grup_adi"] != grup:
                grup = r["grup_adi"]
                y.append(f"\n### {grup}")
            m = re.sub(r"\s+", " ", r["metin"] or "").strip()[:300]
            m = re.sub(r"@\d{6,}", "@…", m)                      # etiketlenen numaraları sil
            ek = f" [dosya: {r['dosya_adi'] or r['tur']}]" if r["tur"] in ("belge",) else ""
            y.append(f"- {dt.datetime.fromtimestamp(r['zaman']):%d.%m %H:%M} {m}{ek}")
    return "\n".join(y) + "\n"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    t = metin()
    (VERI / "asistan.md").write_text(t, encoding="utf-8")
    print(f"veri/asistan.md yazıldı ({len(t) // 1024} KB, {t.count(chr(10))} satır)")


def drive_kopyasi(veri):
    """Google Drive for Desktop kuruluysa asistan metnini 'Drive'ım/İTÜ Asistan.txt' olarak yazar.
    Telefonda Gemini'ye bu dosyayı ekleyip (+ > Drive) soru sorabilirsin. Drive yoksa sessizce geçer."""
    import drive_yolu
    kok = drive_yolu.drive_koku()
    if not kok:
        return None
    hedef = kok / "İTÜ Asistan.txt"
    try:
        hedef.write_text(metin(veri, mesajlar=True), encoding="utf-8")
    except OSError:
        return None
    return hedef

