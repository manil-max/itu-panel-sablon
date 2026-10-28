"""
İTÜ'deki dağınık bilgileri tek dosyada toplar: veri/panel.json

Kaynaklar
  OBS (giriş gerekir)  : kayıtlı derslerin + derslik/saat, akademik durum (AGNO), dönem içi notlar,
                         harf notları, duyurular, akademik takvim
  Ninova (giriş gerekir): sınıflar, sınıf duyuruları, ödevler
  Herkese açık          : final sınav takvimi, ders açıklaması/not dağılımı (data.json), havuz duyuruları

Kullanım:  python topla.py            (hepsi)
           python topla.py --acik     (giriş gerektirmeyenler; .env olmadan çalışır)
Giriş bilgileri .env'den okunur, hiçbir yere yazılmaz.
"""
import datetime
import html
import json
import re
import sqlite3
import sys
from pathlib import Path

import requests

import itu
import guncelle as G

OBS = "https://obs.itu.edu.tr"
NINOVA = "https://ninova.itu.edu.tr"
HERE = Path(__file__).resolve().parent
VERI = HERE.parent / "veri"
GUN = {"Pazartesi": 0, "Salı": 1, "Çarşamba": 2, "Perşembe": 3, "Cuma": 4, "Cumartesi": 5, "Pazar": 6}


def metin(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# ------------------------------------------------------------------ OBS
def obs_topla(log=print):
    s, _ = itu.oturum(f"{OBS}/ogrenci")
    token = itu.obs_token(s)
    if not token:
        raise itu.GirisHatasi("OBS jwt alınamadı")
    s.headers["Authorization"] = token

    def api(yol):
        r = s.get(OBS + yol, timeout=40)
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    yetki = (api("/api/ogrenci/OgrenciYetkiListesi") or {}).get("kisiYetkiListesi") or []
    try:                                                # program adını ders planı verisinden al (yetki adı numara içeriyor)
        prog_adi = json.loads((HERE / "data.json").read_text(encoding="utf-8")).get("programName")
    except (OSError, ValueError):
        prog_adi = None
    ogrenci = {"no": yetki[0].get("ogrenciNo") if yetki else None,
               "program": prog_adi or (yetki[0].get("programAdiTR") if yetki else None),
               "seviye": yetki[0].get("programSeviyesiTR") if yetki else None}
    donemler = ((api("/api/ogrenci/DonemListesi/") or {}).get("ogrenciDonemListesi") or [])
    donemler = [d for d in donemler if (d.get("akademikDonemId") or -1) > -1]
    aktif = donemler[-1]["akademikDonemId"] if donemler else None
    log(f"OBS: {len(donemler)} dönem, aktif {aktif}")

    # Saat/derslik bilgisi DersTakvimi'nde yapısal; kayıt CRN'i ise KayitliSinifListesi'nde (ikisi farklı olabiliyor)
    zaman = {}
    donem_kodu = None
    for d in ((api(f"/api/ogrenci/Takvim/DersTakvimi/{aktif}") or {}).get("kayitSinifResultList") or []):
        donem_kodu = d.get("donem") or donem_kodu
        zaman[f'{d.get("bransKodu")} {d.get("dersKodu")}'] = [
            {"gun": GUN.get(y.get("gunAdiTR"), -1), "bas": y.get("baslangicSaati"), "bit": y.get("bitisSaati"),
             "bina": y.get("binaAdi"), "binaKodu": y.get("binaKodu"), "mekan": y.get("mekanAdi"),
             "kapi": y.get("mekanKapiTabelasi"), "mekanTipi": y.get("mekanTipiAdi"),
             "kampus": y.get("kampusAdi")} for y in (d.get("sinifYerZaman") or [])]
    dersler = []
    for d in ((api(f"/api/ogrenci/sinif/KayitliSinifListesi/{aktif}") or {}).get("kayitSinifResultList") or []):
        kod = f'{d.get("bransKodu")} {d.get("dersKodu")}'
        donem_kodu = d.get("donem") or donem_kodu
        yoklama = api(f'/api/ogrenci/Sinif/SinifOgrenciYoklama/{d.get("sinifId")}') if d.get("sinifId") else None
        saatler = _yer_birlestir(zaman.get(kod, []), d.get("yerZamanBilgiTR"))
        dersler.append({"crn": d.get("crn"), "kod": kod, "ad": d.get("dersAdiEN") or d.get("dersAdiTR"),
                        "adTR": d.get("dersAdiTR"), "saatler": saatler,
                        "yerZaman": d.get("yerZamanBilgiTR"), "sinifId": d.get("sinifId"),
                        "yoklama": _yoklama_ozet(yoklama)})
    durum = (api(f"/api/ogrenci/AkademikDurum/{aktif}") or {}).get("akademikDurum") or {}
    donemici = api(f"/api/ogrenci/Sinif/SinifDonemIciNotListesi/{aktif}") or {}
    harf = (api(f"/api/ogrenci/Sinif/SinifHarfNotuListesi/{aktif}") or {}).get("sinifHarfNotuResultList") or []
    duyuru = (api("/api/ogrenci/Duyuru/Liste/1/20") or {}).get("duyuruOzetList") or []
    tum_harf = []                                        # geçmiş dönemlerin harf notları (profil için)
    for d in donemler:
        for h in ((api(f'/api/ogrenci/Sinif/SinifHarfNotuListesi/{d["akademikDonemId"]}') or {})
                  .get("sinifHarfNotuResultList") or []):
            tum_harf.append(dict(h, akademikDonemId=d["akademikDonemId"]))
        d["dersSayisi"] = len((api(f'/api/ogrenci/sinif/KayitliSinifListesi/{d["akademikDonemId"]}') or {})
                              .get("kayitSinifResultList") or [])
    takvim = []
    tdonemler = (api("/api/ogrenci/Takvim/DonemListesi/1") or {}).get("ogrenciDonemListesi") or []
    simdiki = next((d for d in tdonemler if d.get("donemKodu") == donem_kodu), None) or \
              (max(tdonemler, key=lambda d: d.get("donemKodu") or "") if tdonemler else None)
    if simdiki:
        ham = api(f'/api/ogrenci/Takvim/AkademikTakvimDetay/{simdiki["akademikDonemId"]}') or {}
        for t in (ham.get("akademikTakvimDetayList") or []):
            bit = t.get("bitisTarihi")
            takvim.append({"ad": (t.get("baslik") or "").strip() or None, "bas": t.get("baslangicTarihi"),
                           "bit": None if (bit or "").startswith("1900") else bit, "yil": t.get("yilAdi")})
    danisman = [{"ad": f'{d.get("unvanAdiTR","")} {d.get("adi","")} {d.get("soyadi","")}'.strip(),
                 "tip": d.get("danismanTipiAnahtari"), "birim": d.get("akademikBirimAdiTR")}
                for d in ((api("/api/ogrenci/DanismanBilgi") or {}).get("ogrenciDanismanBilgiList") or [])]
    borclar = (api(f"/api/ogrenci/BorcBilgisi/{aktif}") or {}).get("ogrenciBorcList") or []
    stajlar = (api("/api/ogrenci/StajBilgi") or {}).get("ogrenciStajBilgiList") or []
    anketler = (api(f"/api/ogrenci/sinif/SinifAnketBilgileri/{aktif}") or {}).get("sinifAnketList") or []
    kayit_gecmisi = [{"zaman": x.get("timeStamp"), "eklenen": (x.get("requestBody") or {}).get("ecrn"),
                      "birakilan": (x.get("requestBody") or {}).get("scrn")}
                     for x in ((api("/api/ogrenci/Sinif/DersKayitIstekleri") or {}).get("dersKayitIstekListesi") or [])][:10]
    final = api(f"/api/ogrenci/Takvim/FinalTakvimi?donemId={aktif}") or {}
    finaller = final.get("finalTakvimiList") or final.get("sinavTakvimiList") or []
    log(f"OBS: danışman {len(danisman)}, borç {len(borclar)}, anket {len(anketler)}")
    log(f"OBS: {len(dersler)} kayıtlı ders, {len(harf)} harf notu, {len(duyuru)} duyuru, "
        f"{len(takvim)} takvim maddesi, {len(finaller)} final sınavı")
    return {"ogrenci": ogrenci, "dersler": dersler, "akademikDurum": durum,
            "donemIciNotlar": donemici.get("sinifDonemIciNotListesi") or [], "donemIciOrtalama": donemici.get("ortalama"),
            "harfNotlari": harf, "tumHarfNotlari": tum_harf, "duyurular": duyuru, "akademikTakvim": takvim,
            "finalTakvimim": finaller, "aktifDonemId": aktif, "donemler": donemler,
            "danisman": danisman, "borclar": borclar, "stajlar": stajlar, "anketler": anketler,
            "kayitGecmisi": kayit_gecmisi}


def _yer_birlestir(saatler, yer_zaman_metni):
    """OBS'nin yapısal verisinde amfiler 'Amfi' olarak geçiyor; gerçek sınıf (A34 gibi)
    yerZamanBilgi metninde. İkisini eşleştirip saatlere 'sinif' alanı ekler."""
    parcalar = []
    for p in re.split(r"\s+-\s+(?=\w+\s+\d{2}:\d{2})", yer_zaman_metni or ""):
        m = re.match(r"\s*(\w+)\s+(\d{2}):(\d{2})-(\d{2}):(\d{2})\s*/\s*(.*)", p.strip())
        if m:
            parcalar.append({"gun": GUN.get(m.group(1), -1), "bas": int(m.group(2)) * 60 + int(m.group(3)),
                             "yer": metin(m.group(6))})
    for s in saatler:
        esit = next((p for p in parcalar if p["gun"] == s.get("gun") and abs((p["bas"] or 0) - (s.get("bas") or 0)) <= 1), None)
        metinsel = esit["yer"] if esit else ""
        # "Ayazağa, Merkezi Derslik Binası A34" -> "A34"
        sinif = ""
        if metinsel and s.get("bina"):
            kalan = metinsel.split(s["bina"])[-1].strip(" ,") if s["bina"] in metinsel else ""
            sinif = kalan
        s["sinif"] = sinif or (s.get("kapi") if s.get("kapi") not in (None, "", s.get("mekan")) else "") or s.get("mekan") or ""
        s["yerMetni"] = metinsel
    return saatler


def _yoklama_ozet(ham):
    """OBS yoklama cevabı: {genelKatilim, katilim '3 / 3 (%100.0)', yoklamaHaftaListe[...]}"""
    y = (ham or {}).get("sinifOgrenciYoklama") if isinstance(ham, dict) else None
    if not y:
        return None
    haftalar, katildi, toplam = [], 0, 0
    for h in (y.get("yoklamaHaftaListe") or []):
        for z in (h.get("yoklamaSinifZamanListe") or []):
            saatler_ = z.get("yoklamaSaatListesi") or []
            k = sum(1 for x in saatler_ if x.get("katildiMi"))
            katildi += k
            toplam += len(saatler_)
            haftalar.append({"hafta": h.get("hafta"), "gun": z.get("gunAdiTR"),
                             "katilim": k, "ders": len(saatler_)})
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", str(y.get("katilim") or ""))
    if m and not toplam:
        katildi, toplam = int(m.group(1)), int(m.group(2))
    return {"haftalar": haftalar, "katildi": katildi, "toplam": toplam,
            "oran": round(100 * katildi / toplam, 1) if toplam else None,
            "ozet": y.get("katilim"), "sinifGeneli": y.get("genelKatilim")}


# ------------------------------------------------------------------ Ninova
def _orta(sayfa):
    m = re.search(r'<div class="orta">(.*?)<div class="sag">', sayfa, re.S)
    return m.group(1) if m else sayfa


def _toplanti_linki(sayfa):
    """Online ders bağlantısı (Teams/Zoom/Meet) varsa ilkini döndürür."""
    m = re.search(r'href="(https://(?:teams\.microsoft\.com|teams\.live\.com|[\w.-]*zoom\.us|meet\.google\.com)/[^"]+)"', sayfa)
    return html.unescape(m.group(1)) if m else None



def _ninova_tablo(s, sid, alt):
    """Ninova'daki not / yoklama tablosunu satır listesi olarak döndürür."""
    try:
        ic = _orta(s.get(f"{NINOVA}{sid}{alt}", timeout=40).text)
    except requests.RequestException:
        return []
    out, basliklar = [], None
    for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", ic, re.S):
        h = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", satir, re.S)]
        h = [x for x in h if x]
        if not h or h[0].startswith(("Bilgilendirme", "Öğrencinin")):
            continue
        if basliklar is None and len(h) > 1 and not re.search(r"\d", " ".join(h)):
            basliklar = h
            continue
        out.append(dict(zip(basliklar, h)) if basliklar and len(h) == len(basliklar) else {"satir": " · ".join(h)})
    return out[:30]


def _yoklama_ninova(satirlar):
    """Ninova yoklama tablosu: haftalara göre 1/0 değerleri -> katılım özeti."""
    haftalar, katildi, toplam = [], 0, 0
    for r in satirlar:
        hafta = r.get("Hafta")
        if not hafta:
            continue
        for gun, deger in r.items():
            if gun == "Hafta":
                continue
            saatler_ = [x for x in re.findall(r"[01]", str(deger))]
            if not saatler_:
                continue
            k = sum(1 for x in saatler_ if x == "1")
            katildi += k
            toplam += len(saatler_)
            haftalar.append({"hafta": hafta, "gun": gun, "katilim": k, "ders": len(saatler_)})
    if not toplam:
        return None
    return {"haftalar": haftalar, "katildi": katildi, "toplam": toplam,
            "oran": round(100 * katildi / toplam, 1)}


def _mesaj_panosu(s, sid):
    """Sınıf mesaj panosundaki başlıklar ve içlerindeki bağlantılar (WhatsApp grubu vb.)."""
    try:
        ic = _orta(s.get(f"{NINOVA}{sid}/MesajPanosu", timeout=40).text)
    except requests.RequestException:
        return []
    out = []
    for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", ic, re.S):
        hucre = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", satir, re.S)]
        hucre = [x for x in hucre if x]
        if not hucre or hucre[0].startswith(("Mesaj Başlığı", "Mesaj panosunda")):
            continue
        baglanti = [html.unescape(u) for u in re.findall(r"""href=["'](https?://[^"']+)["']""", satir)]
        ic_link = re.findall(r"(https?://\S+)", " ".join(hucre))
        detay = re.search(r"""href=["'](/Sinif/[\d.]+/MesajPanosu/\d+)["']""", satir)
        # listede mesajın sadece başı görünüyor ("…"): linki görünmüyorsa mesajı açıp tamamından al
        if detay and not (baglanti or ic_link) and (hucre[0].endswith("...") or re.search(r"link|whatsapp|grup", hucre[0], re.I)):
            try:
                tam = _orta(s.get(NINOVA + detay.group(1), timeout=40).text)
                baglanti = [html.unescape(u) for u in re.findall(r"""href=["'](https?://[^"']+)["']""", tam)]
                ic_link = re.findall(r"(https?://[^\s<\"']+)", re.sub(r"<[^>]+>", " ", tam))
            except requests.RequestException:
                pass
        out.append({"baslik": hucre[0], "bilgi": " · ".join(hucre[1:])[:120],
                    "linkler": sorted({u.rstrip(".,)") for u in baglanti + ic_link
                                 if len(u) > 15 and not re.search(r"(ninova|girisv3|bidb)\.itu\.edu\.tr", u)})[:4],
                    **({"url": NINOVA + detay.group(1)} if detay else {})})
    return out


def _sinif_dosyalari(s, sid):
    """Sınıf ve ders dosyaları listesi (izlence, problem seti vb.)."""
    out = []
    for alt, etiket in (("/SinifDosyalari", "sınıf"), ("/DersDosyalari", "ders")):
        try:
            ic = _orta(s.get(f"{NINOVA}{sid}{alt}", timeout=40).text)
        except requests.RequestException:
            continue
        for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", ic, re.S):
            link = re.search(r'href="([^"]*(?:Dosya|Download|dosya)[^"]*)"', satir)
            hucre = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", satir, re.S)]
            hucre = [x for x in hucre if x]
            if not hucre or not link or hucre[0].startswith(("Dosyalar", "Ana Dizin", "Üst Dizin", "/ klasöründe")):
                continue
            out.append({"ad": hucre[0], "boyut": hucre[1] if len(hucre) > 1 else None,
                        "tarih": hucre[2] if len(hucre) > 2 else None, "nerede": etiket,
                        "url": NINOVA + html.unescape(link.group(1)) if link else None})
    return out

def ninova_topla(log=print):
    s, r = itu.oturum(f"{NINOVA}/Kampus1")
    siniflar = []
    for sid in sorted(set(re.findall(r'href="(/Sinif/\d+\.\d+)"', r.text))):
        ana = s.get(NINOVA + sid, timeout=40).text
        yol = re.search(r"Neredeyim:(.*?)(?:Kampüse d|</div>)", re.sub(r"<[^>]+>", " ", ana), re.S)
        ad = metin(yol.group(1)).split("/")[-1].strip() if yol else sid
        kayit = {"id": sid.split("/")[-1], "ders": ad, "url": NINOVA + sid,
                 "mesajPanosu": _mesaj_panosu(s, sid), "dosyalar": _sinif_dosyalari(s, sid),
                 "notlar": _ninova_tablo(s, sid, "/Notlar"),
                 "yoklama": _yoklama_ninova(_ninova_tablo(s, sid, "/Yoklama"))}
        siniflar.append(kayit)

    duyurular, odevler, sinavlar = [], [], []
    d = _orta(s.get(f"{NINOVA}/Kampus?1/Duyurular", timeout=40).text)
    for blok in re.findall(r'<div class="duyuruGoruntule">(.*?)(?=<div class="duyuruGoruntule">|\Z)', d, re.S):
        baslik = re.search(r'<h2><a href="([^"]+)">(.*?)</a>', blok, re.S)
        ders = re.search(r"<strong>(.*?)</strong>", blok, re.S)
        tarihler = re.findall(r'<span class="tarih">(.*?)</span>', blok, re.S)
        crn = re.search(r"CRN:\s*(\d+)", metin(blok))
        icerik = metin(re.sub(r"<span.*?</span>|<strong>.*?</strong>|<h2>.*?</h2>|<a [^>]*>.*?</a>", " ", blok, flags=re.S))
        if baslik:
            url = NINOVA + html.unescape(baslik.group(1))
            toplanti = _toplanti_linki(blok)
            if not toplanti and re.search(r"teams|zoom|meet|link|toplantı", metin(blok), re.I):
                try:                                   # özet kesik olabilir, linki duyurunun kendisinden al
                    toplanti = _toplanti_linki(_orta(s.get(url, timeout=40).text))
                except requests.RequestException:
                    pass
            kod = re.search(r"(?:Team|Takım)\s*(?:Code|Kodu)\s*[:\-]?\s*([A-Za-z0-9]{5,10})\b", metin(blok), re.I)
            duyurular.append({"baslik": metin(baslik.group(2)), "url": url,
                              "ders": metin(ders.group(1)) if ders else None, "crn": crn.group(1) if crn else None,
                              "tarih": metin(tarihler[0]) if tarihler else None,
                              "kimden": metin(tarihler[-1]) if len(tarihler) > 1 else None,
                              "ozet": icerik[:200] or None,
                              "toplanti": toplanti, "takimKodu": kod.group(1) if kod else None})
    o = _orta(s.get(f"{NINOVA}/Kampus?1/Odevler", timeout=40).text)
    if "Duyurulmuş bir ödev bulunmamaktadır" not in metin(o):
        basliklar = None
        for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", o, re.S):
            hucre = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", satir, re.S)]
            link = re.search(r'href="([^"]+)"', satir)
            if not hucre:
                continue
            if basliklar is None and not link:
                basliklar = hucre
            elif link:
                odevler.append({"alanlar": dict(zip(basliklar, hucre)) if basliklar else hucre,
                                "url": NINOVA + html.unescape(link.group(1))})
    for d in duyurular:                                   # duyuru metninde sınav/quiz tarihi var mı?
        try:
            tam = metin(_orta(s.get(d["url"], timeout=40).text))
        except requests.RequestException:
            tam = ""
        d["tamMetin"] = tam[:1200] or None
        blok = f'{d.get("baslik","")} {tam}'.replace(d.get("tarih") or "@@yok@@", " ")   # duyurunun kendi tarihi sınav değil
        sinavlar += _sinav_tarihleri(blok, d.get("ders"), d["url"])
    izlence = []
    for sinif in siniflar:
        kod = (sinif.get("ders") or "").split(" - ")[0]
        for dosya in sinif.get("dosyalar") or []:
            if dosya.get("url") and re.search(r"syllabus|izlence|plan", dosya.get("ad", ""), re.I):
                izlence += izlence_ayristir(_pdf_metni(s, dosya["url"]), kod, dosya["url"])
    log(f"  Ninova: {len(siniflar)} sınıf, {len(duyurular)} duyuru, {len(odevler)} ödev, "
        f"{len(sinavlar)} duyuruda sınav tarihi, {len(izlence)} izlencede quiz")
    return {"siniflar": siniflar, "duyurular": duyurular, "odevler": odevler, "sinavTarihleri": sinavlar,
            "izlenceSinavlari": izlence,
            "dersBilgisiTarihleri": ninova_sinif_bilgileri(s, siniflar, log)}


# ------------------------------------------------------------------ herkese açık
def final_takvimi(branslar, log=print):
    brans = G.brans_listesi()
    out = []
    for b in sorted(set(branslar) & set(brans)):
        t = re.sub(r"\s+", " ", G.get(f"{OBS}/public/FinalTakvimi/SearchFinalTakvimiByDersBransKodu",
                                      dersBransKoduId=brans[b], programSeviyeTipiAnahtari="LS"))
        if "yayınlanmamıştır" in metin(t):
            continue
        basliklar, satirlar = None, []
        for row in re.findall(r"<tr.*?</tr>", t):
            h = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row)]
            if h and h[0].upper() in ("CRN", "DERS KODU"):
                basliklar = h
            elif basliklar and len(h) >= len(basliklar):
                satirlar.append(dict(zip(basliklar, h)))
        out += satirlar
        log(f"  final takvimi {b}: {len(satirlar)} satır")
    return out


AYLAR = {"ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5, "haziran": 6,
         "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11, "kasim": 11,
         "aralık": 12, "aralik": 12}
TAKVIM_URL = "https://www.takvim.sis.itu.edu.tr/AkademikTakvim/TR/akademik-takvim/AkademikTakvimTablo.php"


def _tarih_coz(s):
    """'15 Eylül 14:00 - 16 Eylül 2026 17:00' / '24 - 26 Ağustos 2026' -> (ISO başlangıç, ISO bitiş)"""
    yil = re.search(r"\b(20\d{2})\b", s)
    if not yil:
        return None, None
    yil = int(yil.group(1))
    parcalar = re.split(r"\s*[-–]\s*", s)
    sonuc = []
    son_ay = None
    for p in reversed(parcalar):                       # ay/yıl çoğu zaman sadece sonda yazıyor
        gun = re.search(r"\b(\d{1,2})\b(?!\s*:)", p)
        ay = re.search(r"([A-Za-zÇĞİÖŞÜçğıöşü]+)", p)
        ay = AYLAR.get(ay.group(1).lower()) if ay else None
        son_ay = ay or son_ay
        saat = re.search(r"\b(\d{1,2}):(\d{2})", p)
        if gun and son_ay:
            try:
                d = datetime.datetime(yil, son_ay, int(gun.group(1)),
                                      int(saat.group(1)) if saat else 0, int(saat.group(2)) if saat else 0)
            except ValueError:
                continue
            sonuc.append(d.isoformat(timespec="minutes"))
    sonuc.reverse()
    return (sonuc[0] if sonuc else None), (sonuc[-1] if len(sonuc) > 1 else None)


def akademik_takvim(log=print):
    """İTÜ'nün herkese açık akademik takvimi (lisans, hazırlık, lisansüstü tabloları)."""
    try:
        ham = re.sub(r"\s+", " ", G.get(TAKVIM_URL))
    except requests.RequestException as e:
        log(f"  akademik takvim alınamadı ({e.__class__.__name__})")
        return []
    out, baslik = [], None
    for parca in re.split(r"(<h[1-4][^>]*>.*?</h[1-4]>)", ham):
        if re.match(r"<h[1-4]", parca):
            baslik = metin(parca)
            continue
        for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", parca, re.S):
            h = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", satir, re.S)]
            h = [x for x in h if x]
            if len(h) < 2 or h[1] in ("Tarih",):
                continue
            bas, bit = _tarih_coz(h[1])
            if not bas:
                continue
            out.append({"tablo": baslik, "olay": h[0], "tarihMetni": h[1], "bas": bas, "bit": bit,
                        "tur": _tur(h[0])})
    log(f"  akademik takvim: {len(out)} madde")
    return out


def _tur(olay):
    o = olay.lower()
    if re.search(r"fakülteler tarafından|öğretim üyesi tarafından|öi̇db'ye|öidb'ye|bölüm başkanlık|senato|"
                 r"komisyon|ilgili birim|danışman onay|akademik takvim(?:in)? ilan", o):
        return "idari"
    if re.search(r"final|ara sınav|bütünleme|mazeret sınav|yeterlilik sınav|sınav", o):
        return "sınav"
    if re.search(r"ders kayd|ders kayıt|ekleme|bırak|çekilme|kayıt yenile|katkı pay|ders seçim|yazılma", o):
        return "kayıt"
    if re.search(r"başvuru|son bildir|ilan|müracaat", o):
        return "başvuru"
    if re.search(r"tatil|bayram|yarıyıl tatili|mezuniyet töreni", o):
        return "tatil"
    if re.search(r"ders(ler)?in başla|derslerin bit|öğretim", o):
        return "dönem"
    return "diğer"


SINAV_SOZCUK = r"(?:ara\s*sınav|vize|quiz|kısa\s*sınav|final|sınav|ödev|teslim|proje|sunum|midterm|exam|homework|deadline)"


def _sinav_tarihleri(metin_blok, ders, url):
    """Duyuru metninde geçen sınav/quiz/ödev tarihlerini yakalar: '15 Ekim', '15.10.2026', '15/10' + saat."""
    out, gorulen = [], set()
    for m in re.finditer(SINAV_SOZCUK, metin_blok, re.I):
        pencere = metin_blok[max(0, m.start() - 120):m.start() + 180]
        tarih = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", pencere) or \
                re.search(r"(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)", pencere, re.I)
        if not tarih:
            continue
        bugun = datetime.date.today()
        try:
            if tarih.lastindex and tarih.group(2) and tarih.group(2).isdigit():
                g, a = int(tarih.group(1)), int(tarih.group(2))
                y = int(tarih.group(3) or bugun.year) if tarih.lastindex >= 3 and tarih.group(3) else bugun.year
                y = y + 2000 if y < 100 else y
            else:
                g, a, y = int(tarih.group(1)), AYLAR[tarih.group(2).lower()], bugun.year
            if a < bugun.month - 6:                       # yıl dönümü: ocak-şubat gelecek yıla ait
                y += 1
            t = datetime.date(y, a, g)
        except (ValueError, KeyError):
            continue
        saat = next((x for x in re.finditer(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", pencere)
                     if not (tarih.start() <= x.start() < tarih.end())), None)   # tarihin içindeki sayıyı saat sanma
        anahtar = t.isoformat()
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        out.append({"ders": ders, "tur": m.group(0).lower(), "tarih": t.isoformat(),
                    "saat": f"{saat.group(1).zfill(2)}:{saat.group(2)}" if saat else None,
                    "baglam": re.sub(r"\s+", " ", pencere).strip()[:160], "url": url})
    return out


def ninova_sinif_bilgileri(s, siniflar, log=print):
    """Sınıf Bilgileri sayfalarında geçen sınav/quiz/ödev tarihlerini yakalar (izlence varsa)."""
    bulunan = []
    for sinif in siniflar:
        try:
            t = _orta(s.get(f'{NINOVA}/Sinif/{sinif["id"]}/SinifBilgileri', timeout=40).text)
        except requests.RequestException:
            continue
        duz = metin(t)
        for m in re.finditer(r"([^.;]{0,90}?(?:sınav|quiz|vize|final|ödev|kısa sınav)[^.;]{0,90})", duz, re.I):
            cumle = m.group(1).strip()
            if re.search(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)", cumle, re.I):
                bulunan.append({"ders": sinif["ders"], "metin": cumle[:160], "url": sinif["url"] + "/SinifBilgileri"})
    log(f"  Ninova ders bilgisi: {len(bulunan)} tarihli satır")
    return bulunan


PORTAL = "https://portal.itu.edu.tr"


def portal_kesif(log=print):
    """Portal'daki uygulama bağlantılarını listeler (yemek menüsü gibi verileri bulmak için)."""
    s, r = itu.oturum(f"{PORTAL}/apps/default/", env=itu.env_oku())
    baglantilar = []
    for u, ad in re.findall(r'href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
        ad = metin(ad)
        if ad and len(ad) < 60:
            baglantilar.append((ad, u if u.startswith("http") else PORTAL + u))
    log(f"  portal: {len(baglantilar)} bağlantı")
    return s, baglantilar


def portal_yemek(s=None, tarih=None, log=print):
    """Portal'daki günlük yemek menüsü (öğle + akşam, genel ve vejetaryen)."""
    if s is None:
        s, _ = itu.oturum(f"{PORTAL}/apps/default/", env=itu.env_oku())
    gun = tarih or datetime.date.today()
    gun_str = gun.strftime("%d.%m.%Y")
    url = f"{PORTAL}/apps/default/service/service.aspx/GetFoodMenu2"
    basliklar = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json",
                 "X-Requested-With": "XMLHttpRequest", "Referer": f"{PORTAL}/apps/default/"}
    out = {"tarih": gun_str, "ogunler": []}
    for ogun, ad in (("itu-ogle-yemegi-genel", "Öğle"), ("itu-aksam-yemegi-genel", "Akşam"),
                     ("itu-ogle-yemegi-vegan", "Öğle (vejetaryen/vegan)"),
                     ("itu-aksam-yemegi-vegan", "Akşam (vejetaryen/vegan)")):
        haric = "ana-yemek" if "vegan" in ogun else "vejeteryan"
        q = f"notIncludeKey='{haric}'&ogunKey='{ogun}'&date='{gun_str}'"
        try:
            r = s.get(f"{url}?{q}", headers=basliklar, timeout=40)
            d = r.json().get("d") or {}
        except (requests.RequestException, ValueError):
            continue
        kalemler = []
        for x in (d.get("FoodList") or []):
            if not isinstance(x, dict) or not x.get("FoodName"):
                continue
            kalemler.append({
                "ad": metin(x["FoodName"]), "tur": metin(x.get("FoodType") or ""),
                "gramaj": x.get("TotalWeight"),
                "alerjen": [metin(a.get("SideEffectName") or "") for a in (x.get("FoodSideEffectInformationList") or [])],
            })
        if kalemler:
            out["ogunler"].append({"ogun": ad, "anahtar": ogun, "kalemler": kalemler,
                                   "menuTarihi": d.get("MenuDate")})
    log(f"  portal yemek: {len(out['ogunler'])} öğün, {sum(len(o['kalemler']) for o in out['ogunler'])} kalem")
    return out


def portal_hesap(s=None, log=print):
    """Portal: yemek kartı bakiyesi, son kart hareketleri ve internet kotası."""
    if s is None:
        s, _ = itu.oturum(f"{PORTAL}/apps/default/", env=itu.env_oku())
    basliklar = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json",
                 "X-Requested-With": "XMLHttpRequest", "Referer": f"{PORTAL}/apps/default/"}

    def cagir(metot, sorgu=""):
        try:
            r = s.get(f"{PORTAL}/apps/default/service/service.aspx/{metot}" + (f"?{sorgu}" if sorgu else ""),
                      headers=basliklar, timeout=40)
            return r.json().get("d") if "json" in r.headers.get("Content-Type", "") else None
        except (requests.RequestException, ValueError):
            return None

    bakiye, kota = cagir("GetBalance"), cagir("GetQuota")
    out = {}
    b = (bakiye or {}).get("BalanceInformation") if isinstance(bakiye, dict) else None
    if isinstance(b, dict):
        out["kart"] = {"bakiye": b.get("Balance"), "zaman": b.get("BalanceGetDate"),
                       "hareketler": [{"tip": metin(h.get("TypeName") or ""), "tutar": h.get("TransactionAmount"),
                                       "kalan": h.get("Balance")}
                                      for h in (b.get("Transitions") or [])[:8]]}
    if isinstance(kota, dict):
        k = kota.get("KotaInformation") if isinstance(kota.get("KotaInformation"), dict) else kota
        out["kota"] = {a: k.get(a) for a in k if not isinstance(k.get(a), (dict, list)) and a != "PersonPublicId"}
    log(f"  portal hesap: bakiye {'var' if out.get('kart') else 'yok'}, kota {'var' if out.get('kota') else 'yok'}")
    return out


SKS = "https://sks.itu.edu.tr"


def _tablolar(url):
    """Sayfadaki tabloları [{baslik, satirlar:[[hücre,...]]}] olarak döndürür."""
    ham = re.sub(r"\s+", " ", G.get(url))
    ham = re.sub(r"<script.*?</script>", " ", ham, flags=re.S | re.I)
    out = []
    for parca in re.findall(r"<table.*?</table>", ham, re.S | re.I):
        satirlar = []
        for s in re.findall(r"<tr[^>]*>(.*?)</tr>", parca, re.S | re.I):
            h = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", s, re.S | re.I)]
            h = [x for x in h if x]
            if h:
                satirlar.append(h)
        if satirlar:
            out.append(satirlar)
    return out


NINOVA_YANKISI = re.compile(r"^Sınıfınız(a|daki) (Duyuru|ödev)", re.I)   # Ninova duyurusunun bildirimi: Ninova'dan zaten geliyor


def portal_bildirim(s, log=print):
    """İTÜ Mobil'deki 'Bildirimler' listesi (Portal GetNotification, salt-okunur) + İTÜ etkinlik listesi (GetEtkinlik).
    Kampüs duyuruları (yemekhane, yol, ring) ve hocanın Ninova'dan gönderdiği kişisel bildirimler buradan gelir."""
    basliklar = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json",
                 "X-Requested-With": "XMLHttpRequest", "Referer": f"{PORTAL}/apps/default/"}

    def cagir(metot, sorgu=""):
        try:
            r = s.get(f"{PORTAL}/apps/default/service/service.aspx/{metot}" + (f"?{sorgu}" if sorgu else ""),
                      headers=basliklar, timeout=40)
            return r.json().get("d") if "json" in r.headers.get("Content-Type", "") else None
        except (requests.RequestException, ValueError):
            return None

    bildirimler, gorulen = [], set()
    for n in ((cagir("GetNotification", "all=true") or {}).get("NotificationInformationList") or []):
        anahtar = (n.get("Title"), n.get("CreateDate"))          # aynı bildirim iki kez gelebiliyor
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        icerik = n.get("ContentText") or ""
        tire = lambda x: re.sub(r"\s\?(?=\s)", " –", x)     # Portal tireyi (–) "?" olarak gönderiyor; gerçek soru işaretinden önce boşluk olmaz
        bildirimler.append({"id": str(n.get("ObjectId")), "baslik": tire(metin(n.get("Title") or "")),
                            "tarih": n.get("CreateDate") or n.get("BeforeCreateDate"),
                            "ozet": tire(re.sub(r"\s+", " ", metin(n.get("SummaryText") or "")))[:400],
                            "metin": tire(re.sub(r"\s+", " ", metin(re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", icerik))))[:3000],
                            "ninova": bool(NINOVA_YANKISI.search(n.get("Title") or ""))})
    etkinlik = [{"ad": metin(e.get("EtkinlikAdi") or ""), "aciklama": metin(e.get("EtkinlikAciklamasi") or ""),
                 "url": e.get("URL")} for e in ((cagir("GetEtkinlik") or {}).get("EtkinlikInformationList") or [])][:30]
    log(f"  portal bildirimleri: {len(bildirimler)} (kampüs/kişisel {sum(not b['ninova'] for b in bildirimler)}), "
        f"İTÜ etkinlik listesi: {len(etkinlik)}")
    return bildirimler, etkinlik


def kampus_bilgileri(log=print):
    """Ring servis saatleri, yemek saatleri ve yemek fiyatları (sks.itu.edu.tr, herkese açık)."""
    veri = {"kaynak": {"ring": f"{SKS}/kampus-ici-ring-servis", "saat": f"{SKS}/yemek-saatleri",
                       "fiyat": f"{SKS}/yemek-fiyatlari"}}
    try:                                                 # günlük menü + kart/kota Portal'da (giriş gerekir)
        s, _ = itu.oturum(f"{PORTAL}/apps/default/", env=itu.env_oku())
        veri["yemekMenusu"] = portal_yemek(s, log=log)
        veri["hesap"] = portal_hesap(s, log=log)
        veri["bildirimler"], veri["portalEtkinlik"] = portal_bildirim(s, log=log)
    except (itu.GirisHatasi, requests.RequestException) as e:
        log(f"  portal verisi alınamadı ({e.__class__.__name__})")
        veri["yemekMenusu"], veri["hesap"] = None, None
    for ad, yol in (("ring", "/kampus-ici-ring-servis"), ("yemekSaatleri", "/yemek-saatleri"),
                    ("yemekFiyatlari", "/yemek-fiyatlari")):
        try:
            veri[ad] = _tablolar(SKS + yol)
        except requests.RequestException as e:
            log(f"  {ad} alınamadı ({e.__class__.__name__})")
            veri[ad] = []
        log(f"  {ad}: {len(veri[ad])} tablo")
    return veri


def duyuru_sitesi(url, log=print):
    """Bölüm/havuz sitelerinin duyuru listesi (matmuh, fizik vb.)."""
    try:
        t = G.get(url)
    except requests.RequestException as e:
        log(f"  {url}: alınamadı ({e.__class__.__name__})")
        return []
    out, gorulen = [], set()
    # bazı siteler (fizikhavuz) duyuruyu link değil sayfa içinde açılır kutu olarak veriyor: başlık + tarih + metin
    for m in re.finditer(r'class="index_ann_item".*?<strong>(.*?)</strong>.*?class="index_ann_date">(.*?)</small>'
                         r'.*?class="index_ann_content"[^>]*>(.*?)</li>', t, re.S):
        baslik = metin(m.group(1))
        if baslik and baslik.lower() not in gorulen:
            gorulen.add(baslik.lower())
            out.append({"baslik": baslik, "url": url, "tarih": metin(m.group(2)), "ozet": metin(m.group(3))[:400]})
    if out:
        return out[:15]
    for m in re.finditer(r'<a[^>]*href="([^"#]{4,200})"[^>]*>(.{3,160}?)</a>', t, re.S):
        baslik = metin(m.group(2))
        if len(baslik) < 12 or baslik.lower() in gorulen:
            continue
        if not re.search(r"duyuru|haber|announce|news|sınav|sinav|ders", m.group(1), re.I) and \
           not re.search(r"sınav|ders|duyuru|kayıt|telafi|ödev", baslik, re.I):
            continue
        gorulen.add(baslik.lower())
        link = m.group(1)
        if link.startswith("/"):
            link = re.match(r"https?://[^/]+", url).group(0) + link
        out.append({"baslik": baslik, "url": html.unescape(link)})
    # detay sayfası linki (duyuru-detay.php?id=..., /haber/123) yeterince varsa menü linklerini at
    detay = [x for x in out if re.search(r"detay|[?&]id=\d+|/(duyuru|haber|news)[^/]*/\S*\d{2,}", x["url"], re.I)]
    return (detay if len(detay) >= 3 else out)[:15]


def main():
    from calisma_kilidi import Mesgul, topla_kilidi
    if (VERI / "otomasyon_kapali").exists():
        print("OTOMASYON_KAPALI: veri toplama atlandı.")
        return 0
    if (VERI / "giris_hatasi.json").exists() and "--acik" not in sys.argv:
        print("GIRIS_HATASI: önceki giriş hatası çözülene kadar tekrar denenmeyecek.")
        return 2
    try:
        with topla_kilidi():
            return _main()
    except Mesgul:
        print("TOPLA_MESGUL: başka bir veri toplama işlemi sürüyor, atlandı.")
        return 3
    except itu.GirisHatasi:
        (VERI / "giris_hatasi.json").write_text(
            json.dumps({"tarih": datetime.datetime.now().isoformat(timespec="seconds"),
                        "hata": "GirisHatasi"}), encoding="utf-8")
        print("GIRIS_HATASI: İTÜ girişi başarısız. Tekrar deneme.")
        return 2


def _main():
    acik_only = "--acik" in sys.argv
    VERI.mkdir(exist_ok=True)
    veri = {"guncellendi": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}
    if not acik_only:
        veri["obs"] = obs_topla()
        try:
            veri["ninova"] = ninova_topla()
        except Exception as e:
            print("  Ninova alınamadı:", e.__class__.__name__, e)
            veri["ninova"] = {}
        try:                                        # İTÜ e-postası (sadece okur) -> veri/eposta/epostalar.db
            import eposta
            eposta.cek(gun=30)
        except Exception as e:
            print("  e-posta alınamadı:", e.__class__.__name__, e)
    branslar = {d["kod"].split()[0] for d in veri.get("obs", {}).get("dersler", [])} or {"MAT", "FIZ"}
    print("Herkese açık kaynaklar...")
    veri["akademikTakvim"] = akademik_takvim()
    for ad, dosya in (("onemliTarihler", "onemli_tarihler.json"), ("ayarlar", "ayarlar.json")):
        try:
            veri[ad] = json.loads((HERE / dosya).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            veri[ad] = [] if ad == "onemliTarihler" else {}
    veri["izlenceler"], veri["izlenceBilgi"] = izlenceler(
        G.S, [d["kod"] for d in (veri.get("obs") or {}).get("dersler", [])],
        (veri.get("ayarlar") or {}).get("izlenceler"), takvim=veri.get("akademikTakvim"))
    veri["kampus"] = kampus_bilgileri()
    veri["finalTakvimi"] = final_takvimi(branslar)
    veri["havuzDuyurulari"] = {
        "Matematik": duyuru_sitesi("https://matmuh.itu.edu.tr/"),
        "Fizik": duyuru_sitesi("https://fizik.itu.edu.tr/"),
        "MAT havuz": duyuru_sitesi("https://mathavuz.itu.edu.tr/index.php"),      # vize salonu/sıra, telafi
        "Fizik havuz": duyuru_sitesi("https://fizikhavuz.itu.edu.tr/"),
        "Ekonomi (EKO 201E)": duyuru_sitesi("https://econ.itu.edu.tr/haberler"),  # quiz/vize tarihleri, salonlar
        "Öğrenci İşleri": duyuru_sitesi("https://www.sis.itu.edu.tr/TR/duyurular/duyurular.php"),
    }
    for k, v in veri["havuzDuyurulari"].items():
        print(f"  {k}: {len(v)} duyuru")
    try:                                            # kaynak o an boş döndüyse (site hatası) eski veriyi koru
        eski = json.loads((VERI / "panel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        eski = {}
    for ad in ("akademikTakvim", "izlenceler", "kampus", "finalTakvimi"):
        if not veri.get(ad) and eski.get(ad):
            print(f"  {ad} boş geldi, önceki veri korundu")
            veri[ad] = eski[ad]
    if veri.get("obs"):
        veri["dersDetay"] = ders_detay(veri)
    from calisma_kilidi import atomik_yaz
    atomik_yaz(VERI / "panel.json", json.dumps(veri, ensure_ascii=False, indent=1))
    print(f"\nveri/panel.json yazıldı ({len(json.dumps(veri))//1024} KB)")
    if veri.get("obs"):
        profil_uret(veri)
    panel_uret(veri)
    return 0


HARF_ALANLARI = ("harfNotu", "harfNotuAdi", "notu", "not", "basariNotu", "harf")
KOD_ALANLARI = (("bransKodu", "dersKodu"), ("dersBransKodu", "dersNo"))


def _ders_kodu(kayit):
    for b, n in KOD_ALANLARI:
        if kayit.get(b) and kayit.get(n):
            return f'{kayit[b]} {kayit[n]}'
    kod = kayit.get("dersKoduTam") or kayit.get("ders") or ""
    m = re.match(r"([A-Z]{2,4})\s*(\d{3,4}[A-Z]*)", str(kod))
    return f"{m.group(1)} {m.group(2)}" if m else None


def _harf(kayit):
    for a in HARF_ALANLARI:
        v = kayit.get(a)
        if isinstance(v, str) and re.fullmatch(r"(AA|BA\+?|BB\+?|CB\+?|CC\+?|DC\+?|DD\+?|FF|VF|BL|BZ|T)", v.strip()):
            return v.strip()
    return None


def ders_detay(veri, log=print):
    """Kayıtlı dersleri araçtaki ders verisiyle birleştirir: hoca, kredi, AKTS, tanım, not dağılımı, Ninova bağlantısı."""
    try:
        plan = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        plan = {}
    kurslar, havuzAdlari = plan.get("courses") or {}, plan.get("groupNames") or {}
    TUR_ADI = {"TB": "Temel bilim", "TM": "Temel mühendislik", "MT": "Bölüm dersi",
               "ITB": "İnsan ve toplum bilimleri", "EC": "İngilizce"}
    ninova = {s.get("ders", "").split(" - ")[0]: s for s in ((veri.get("ninova") or {}).get("siniflar") or [])}
    out = {}
    for d in (veri.get("obs") or {}).get("dersler") or []:
        kod = d["kod"]
        c = kurslar.get(kod) or {}
        sube = next((s for s in c.get("sections") or [] if s["crn"] == d["crn"]), None)
        notlar = (c.get("grades") or [])
        basli = next((g for g in notlar if "Güz" in g["term"]), None) or (notlar[0] if notlar else None)
        b, n = (kod.split() + [""])[:2]
        havuzlar = [havuzAdlari.get(str(g)) for g in (c.get("groups") or []) if havuzAdlari.get(str(g))]
        if c.get("sems"):
            kategori, kategoriNot = "zorunlu", f'{", ".join(str(x) for x in c["sems"])}. yarıyıl zorunlusu'
        elif havuzlar:
            kategori, kategoriNot = "havuz", sorted(set(havuzlar))[0]
        elif c:
            kategori, kategoriNot = "plandisi", "Planda görünmüyor"
        else:
            kategori, kategoriNot = "bilinmiyor", "Bu programın planında yok"
        out[kod] = {
            "kategori": kategori, "kategoriNot": kategoriNot,
            "tur": c.get("type"), "turAdi": TUR_ADI.get(c.get("type") or "", c.get("type")),
            "planYy": c.get("sems") or [], "havuzlar": sorted(set(havuzlar)),
            "kredi": c.get("kredi"), "akts": c.get("akts"), "tanim": c.get("tanim"),
            "hoca": (sube or {}).get("hoca") if (sube or {}).get("hoca") not in (None, "-") else None,
            "yontem": (sube or {}).get("yontem"), "kont": (sube or {}).get("kont"),
            "notDagilimi": basli and {"donem": basli["term"], "aa": basli["aa"], "ort": basli["avg"],
                                      "kalma": basli["fail"], "kisi": basli["n"]},
            "ninovaUrl": (ninova.get(kod) or {}).get("url"),
            "obsUrl": f"https://obs.itu.edu.tr/public/DersBilgi?bransKodu={b}&dersNo={n}",
            "notUrl": f"https://obs.itu.edu.tr/public/DersNotDagilimi?bransKodu={b}&dersNo={n}&yil={datetime.date.today().year}",
        }
    log(f"  ders detayı: {sum(1 for v in out.values() if v['hoca'])} derste hoca, "
        f"{sum(1 for v in out.values() if v['notDagilimi'])} derste not dağılımı")
    return out


def profil_uret(veri, log=print):
    """OBS verisinden ders seçme aracının profil dosyasını üretir: veri/profil.json
    Tamamlanan dersler + notlar, bu dönem kayıtlı dersler ve CRN'leri, dönem numarası."""
    obs = veri.get("obs") or {}
    tamamlanan, krediler = {}, {}
    for h in obs.get("tumHarfNotlari") or []:
        kod, harf = _ders_kodu(h), _harf(h)
        if kod and harf and harf != "T":
            tamamlanan[kod] = harf
            if h.get("kredi") is not None:
                krediler[kod] = h["kredi"]
    try:                                                 # araçtaki şube verisi (CRN eşleştirmesi için)
        kurslar = json.loads((HERE / "data.json").read_text(encoding="utf-8")).get("courses") or {}
    except (OSError, ValueError):
        kurslar = {}
    secili, acik, eslesmeyen = {}, {}, []
    for d in obs.get("dersler") or []:
        kod, crn = d["kod"], d["crn"]
        subeler = (kurslar.get(kod) or {}).get("sections") or []
        if subeler and not any(x["crn"] == crn for x in subeler):
            # OBS bazen aynı dersin alt grubuna yazıyor; aynı saatteki şubeyi kullan
            imza = sorted((y["gun"], y["bas"]) for y in d.get("saatler") or [])
            esit = next((x for x in subeler if sorted((m[0], m[1]) for m in x["m"]) == imza), None)
            eslesmeyen.append(f'{kod} {crn}' + (f' -> {esit["crn"]}' if esit else " (karşılığı yok)"))
            crn = esit["crn"] if esit else crn
        secili[kod] = crn
        acik[kod] = True
    if eslesmeyen:
        log("  CRN eşleşmesi: " + ", ".join(eslesmeyen))
    # kaçıncı yarıyıl: ders alınan dönem sayısı (hazırlık dönemleri sayılmaz)
    donem_sayisi = len([d for d in (obs.get("donemler") or []) if (d.get("dersSayisi") or 0) > 0]) or 1
    profil = {
        "type": "itu-ders-secme-profil", "version": 3, "kaynak": "OBS",
        "exportedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "profile": {
            "id": "obs", "name": "OBS (otomatik)", "program": veri.get("program") or G.PROGRAM,
            "semester": min(8, donem_sayisi), "muaf": secili.get("ING 100") == "11839",
            "completed": tamamlanan, "kredi": krediler,
            "enabled": acik, "selected": secili,
            "obsCrn": {d["kod"]: d["crn"] for d in obs.get("dersler") or []},
            "savedAt": datetime.datetime.now().strftime("%d.%m.%Y %H:%M") + " (OBS'den)",
        },
    }
    (VERI / "profil.json").write_text(json.dumps(profil, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  profil.json: {len(tamamlanan)} tamamlanan ders, {len(secili)} kayıtlı ders, {profil['profile']['semester']}. dönem")
    return profil


def whatsapp_ozeti():
    """veri/whatsapp/notlar.json (yapay zekâ değerlendirmesi) + köprü durumu. Mesajların kendisi panele girmez."""
    wa = VERI / "whatsapp"
    oku = lambda ad: json.loads((wa / ad).read_text(encoding="utf-8")) if (wa / ad).exists() else {}
    notlar, durum = oku("notlar.json"), oku("durum.json")
    if not notlar and not durum:
        return None
    import drive_yerel                               # PC'deki Drive dosyası -> telefonda açılan link
    try:
        klasor_id, idler = drive_yerel.klasor_idleri("İTÜ")       # İTÜ/Dersler/<kod>/Diğer, İTÜ/Genel/<grup>
        _, eski = drive_yerel.klasor_idleri()                      # henüz taşınmamış: İTÜ WhatsApp Dosyaları/<grup>
        idler.update({"@eski/" + k: v for k, v in eski.items()})
    except Exception as e:
        print("  Drive linkleri okunamadı:", e.__class__.__name__)
        klasor_id, idler = None, {}

    def goreli(yol):                                 # İTÜ klasörüne göre "Dersler/FIZ 101E/Diğer/x.pdf"
        yol = str(yol or "").replace("\\", "/")
        if drive_yerel.KLASOR + "/" in yol:
            return "@eski/" + yol.split(drive_yerel.KLASOR + "/", 1)[1]
        for ayrac in ("/İTÜ/", "whatsapp/dosyalar/"):
            if ayrac in yol:
                return yol.split(ayrac, 1)[1]
        return ""

    def drive_link(yol):
        g = goreli(yol)
        if not g:
            return None
        if g.endswith("/"):
            return drive_yerel.link(idler.get(g), klasor=True) if idler.get(g) else None
        return drive_yerel.link(idler.get(g), ad=g.rsplit("/", 1)[-1])

    not_listesi = [{**n, "dosyaLink": drive_link(n["dosya"])} if n.get("dosya") else n
                   for n in notlar.get("notlar", [])]
    dosyalar = []
    db = wa / "mesajlar.db"
    if db.exists():
        c = sqlite3.connect(db)
        for zaman, grup, tur, ad, yol in c.execute(
                "SELECT zaman, grup_adi, tur, dosya_adi, dosya FROM mesajlar WHERE dosya != '' AND tur IN ('belge','video') "
                "ORDER BY zaman DESC LIMIT 60"):
            dosyalar.append({"ad": ad or Path(yol).name, "grup": grup, "tur": tur, "link": drive_link(yol),
                             "tarih": datetime.datetime.fromtimestamp(zaman).isoformat(timespec="minutes")})
        c.close()
    # ödev teslim durumu (dosyalar.py Ninova'dan okur): yüklenen ödev "yapılacaklar"da çıkmaz
    try:
        odevler = list(json.loads((VERI / "dosyalar.json").read_text(encoding="utf-8")).get("odevler", {}).values())
    except (OSError, ValueError):
        odevler = []
    # katıldığın ama dinlenmeyen İTÜ/kulüp grupları: panel "dinleyeyim mi?" diye sorar (karar verilmedikçe okunmaz)
    ayar = json.loads((HERE / "ayarlar.json").read_text(encoding="utf-8")).get("whatsapp", {})
    gecilen = set(ayar.get("gecilen", []))
    ilgili = re.compile(r"\b[A-Z]{3}\s?\d{3}E?\b|itü|itu\b|kulüb|kulub|club|ieee|acm|inzva|havk|eestec|best\b|workshop|hackathon", re.I)
    ilgisiz = re.compile(r"hazırlık|hazirlik|mezun|dolu\)|tercih|sohbet|halı ?saha|clash|\bcr\b|satranç|yurdu|koç", re.I)
    try:
        gruplar = json.loads((wa / "gruplar.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        gruplar = []
    adaylar = []
    for g in gruplar:
        tam = (g["topluluk"] + " / " if g.get("topluluk") else "") + g["ad"]
        if g.get("dinleniyor") or g.get("toplulukAnaGrubu") or tam in gecilen:
            continue
        if ilgili.search(tam) and not ilgisiz.search(tam):
            adaylar.append({"ad": tam, "uye": g.get("uye")})
    # gruplarda paylaşılan WhatsApp grup davet linkleri (son 21 gün): panelde "Paylaşılan grup linkleri"
    linkler, gorulen_link = [], set()
    if (wa / "mesajlar.db").exists():
        c = sqlite3.connect(wa / "mesajlar.db")
        for zaman, grup, metin in c.execute(
                "SELECT zaman, grup_adi, metin FROM mesajlar WHERE metin LIKE '%chat.whatsapp.com/%' "
                "AND zaman > strftime('%s','now','-21 days') ORDER BY zaman DESC"):
            for kod in re.findall(r"chat\.whatsapp\.com/([A-Za-z0-9]{10,})", metin or ""):
                if kod in gorulen_link:
                    continue
                gorulen_link.add(kod)
                ad = re.match(r"Grup daveti: (.+?) https://", metin or "")      # davet kartında grubun adı var
                linkler.append({"link": "https://chat.whatsapp.com/" + kod, "grup": grup, "ad": ad.group(1) if ad else "",
                                "tarih": datetime.datetime.fromtimestamp(zaman).isoformat(timespec="minutes")})
        c.close()
    try:
        import etkinlikler
        kaynaklar = [{"ad": k["ad"], "url": k["url"], "tur": k["tur"]} for k in etkinlikler.durum()["kaynaklar"]]
    except Exception:
        kaynaklar = []
    return {"guncellendi": notlar.get("guncellendi"), "olaylar": notlar.get("olaylar", []),
            "brifing": notlar.get("brifing"), "odevDurumu": odevler, "grupAdaylari": adaylar[:30],
            "etkinlikKaynaklari": kaynaklar, "grupLinkleri": linkler[:20],
            "dersler": notlar.get("dersler", {}), "firsatlar": notlar.get("firsatlar", []),
            "notlar": not_listesi, "dosyalar": dosyalar,
            "klasorLink": drive_yerel.link(klasor_id, klasor=True) if klasor_id else None,
            "kopru": {k: durum.get(k) for k in ("bagli", "dinlenen", "sonMesaj", "sonBaglanti")}}


def panel_uret(veri=None):
    """panel_template.html + veri/panel.json -> ../panel.html (tarayıcıda açılan kişisel panel)"""
    if veri is None:
        veri = json.loads((VERI / "panel.json").read_text(encoding="utf-8"))
    veri = {**veri, "whatsapp": whatsapp_ozeti(),
            "ayarlar": json.loads((HERE / "ayarlar.json").read_text(encoding="utf-8")),   # ayar değişince hemen yansısın
            "onemliTarihler": json.loads((HERE / "onemli_tarihler.json").read_text(encoding="utf-8"))}
    import asistan                                   # Sor kutusu + Drive'daki "İTÜ Asistan" belgesi
    try:
        asistan.yaz(veri)                            # veri/asistan.md + Drive'daki ham kayıtlar belgesi
        veri["asistanMetni"] = asistan.metin(veri, mesajlar=False)
        veri["dersDosyalari"] = asistan.ders_dosyalari()
    except Exception as e:                           # asistan metni olmasa da panel üretilsin
        print("  asistan metni üretilemedi:", e.__class__.__name__, e)
    tpl = (HERE / "panel_template.html").read_text(encoding="utf-8")
    out = tpl.replace("__VERI__", json.dumps(veri, ensure_ascii=False).replace("</", "<\\/"))
    from calisma_kilidi import atomik_yaz
    atomik_yaz(HERE.parent / "panel.html", out)
    print(f"panel.html üretildi ({len(out)//1024} KB)")


# ------------------------------------------------------------------ izlence (syllabus) tarama
AY_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
         "sep": 9, "oct": 10, "nov": 11, "dec": 12,
         "oca": 1, "şub": 2, "sub": 2, "mar.": 3, "nis": 4, "may.": 5, "haz": 6, "tem": 7,
         "ağu": 8, "agu": 8, "eyl": 9, "eki": 10, "kas": 11, "ara": 12}
SINAV_SATIR = re.compile(
    r"(?P<hafta>\d{1,2})\s+(?P<g1>\d{1,2})\s*(?:(?P<a1>[A-Za-zÇĞİÖŞÜçğıöşü]{3,9})\s*)?[–\-]\s*(?P<g2>\d{1,2})\s*"
    r"(?P<a2>[A-Za-zÇĞİÖŞÜçğıöşü]{3,9})\s+(?P<icerik>.{0,120}?)(?=\s+\d{1,2}\s+\d{1,2}\s*[A-Za-zÇĞİÖŞÜçğıöşü–\-]|\Z)", re.S)


def _ay_no(s):
    return AY_EN.get((s or "").strip().lower()[:3])


def izlence_ayristir(metin_blok, kod, kaynak, yil=None):
    """İzlencedeki haftalık tablodan quiz / ara sınav satırlarını çıkarır."""
    yil = yil or datetime.date.today().year
    out = []
    for m in SINAV_SATIR.finditer(re.sub(r"\s+", " ", metin_blok)):
        icerik = m.group("icerik").strip()
        olay = re.search(r"(Make-?up\s+Quiz|Quiz\s*\d*|Demo\s+Quiz|Ara\s*Sınav|Midterm|Vize|Final)", icerik, re.I)
        if not olay:
            continue
        ay1, ay2 = _ay_no(m.group("a1")) or _ay_no(m.group("a2")), _ay_no(m.group("a2"))
        if not ay2:
            continue
        y1 = yil + 1 if ay1 and ay1 < 7 else yil
        y2 = yil + 1 if ay2 < 7 else yil
        try:
            bas = datetime.date(y1, ay1 or ay2, int(m.group("g1")))
            bit = datetime.date(y2, ay2, int(m.group("g2")))
        except ValueError:
            continue
        out.append({"ders": kod, "tur": olay.group(1).strip(), "hafta": int(m.group("hafta")),
                    "bas": bas.isoformat(), "bit": bit.isoformat(),
                    "konu": re.sub(r"\s*(Make-?up\s+Quiz|Quiz\s*\d*|Demo\s+Quiz|Ara\s*Sınav|Midterm|Vize|Final)\s*$", "", icerik).strip(),
                    "kaynak": kaynak})
    return out or izlence_tarihli_ayristir(metin_blok, kod, kaynak)


# BLG 113E tipi: "04 (Oct.21, 2026) ... Quiz1 ... 05 (Oct.28, 2026) ..." — her haftanın tek bir ders tarihi var
HAFTA_TARIHLI = re.compile(r"\b(?P<hafta>\d{1,2})\s*\(\s*(?P<ay>[A-Za-z]{3})[a-z]*\.?\s*(?P<gun>\d{1,2}),?\s*(?P<yil>20\d{2})\s*\)")
TARIHLI_OLAY = [(r"\bQuiz\s*(\d+)", "Quiz {0}"), (r"Group\s+Project\s+Proposal", "Grup proje önerisi"),
                (r"Student\s+Group\s+Presentations?|Poster\s+Presentations?", "Grup poster sunumu"),
                (r"\bMidterm\b", "Midterm")]


def izlence_tarihli_ayristir(metin_blok, kod, kaynak):
    duz = re.sub(r"\s+", " ", metin_blok or "")
    eslesme = list(HAFTA_TARIHLI.finditer(duz))
    out = []
    for i, m in enumerate(eslesme):
        icerik = duz[m.end(): eslesme[i + 1].start() if i + 1 < len(eslesme) else min(len(duz), m.end() + 300)]
        if re.search(r"National Holiday|Resmi Tatil|Resmî Tatil", icerik, re.I):
            continue
        ay = _ay_no(m.group("ay"))
        if not ay:
            continue
        try:
            gun = datetime.date(int(m.group("yil")), ay, int(m.group("gun")))
        except ValueError:
            continue
        for desen, ad in TARIHLI_OLAY:
            for o in re.finditer(desen, icerik, re.I):
                out.append({"ders": kod, "tur": ad.format(*o.groups()), "hafta": int(m.group("hafta")),
                            "bas": gun.isoformat(), "bit": gun.isoformat(), "konu": "", "kaynak": kaynak})
    return out


def _pdf_metni(s, url):
    try:
        import pypdf
    except ImportError:
        return ""
    try:
        ham = s.get(url, timeout=60).content
    except requests.RequestException:
        return ""
    try:
        from io import BytesIO
        return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(BytesIO(ham)).pages)
    except Exception:
        return ""


IZLENCE_KAYNAK = {"FIZ": "https://fizikhavuz.itu.edu.tr/docs/syllabus/{kod}.pdf",
                  "MAT": "https://mathavuz.itu.edu.tr/syllabus.php?ders={kod}"}


def hafta_araliklari(takvim, yil=None):
    """Akademik takvimden 'n. hafta -> (pazartesi, cuma)'. Ara tatil haftası numara almaz (havuz izlenceleri böyle)."""
    lisans = [x for x in (takvim or []) if re.search(r"Lisans / Önlisans", x.get("tablo") or "")]
    bul = lambda r: next((x for x in lisans if re.search(r, x.get("olay") or "", re.I)), None)
    bas = bul(r"Güz Yarıyılı Başlangıcı")
    if bas:
        b = datetime.date.fromisoformat(bas["bas"][:10])
    else:                                               # takvim yoksa: eylülün son pazartesi civarı
        y = yil or datetime.date.today().year
        b = datetime.date(y, 9, 28)
    pzt = b - datetime.timedelta(days=b.weekday())
    tatil = bul(r"^Ara Tatil")
    tatil_pzt = None
    if tatil:
        t = datetime.date.fromisoformat(tatil["bas"][:10])
        tatil_pzt = t - datetime.timedelta(days=t.weekday())

    def aralik(n):
        d = pzt + datetime.timedelta(weeks=n - 1)
        if tatil_pzt and d >= tatil_pzt:
            d += datetime.timedelta(weeks=1)
        return d, d + datetime.timedelta(days=4)
    return aralik


def html_izlence_ayristir(ham, kod, kaynak, aralik):
    """mathavuz syllabus.php: 'Hafta | Konular | Quiz' tablosu (quiz sütununda numara) -> quiz olayları."""
    out = []
    for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", ham, re.S | re.I):
        h = [metin(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", satir, re.S | re.I)]
        if len(h) < 3 or not re.fullmatch(r"\d{1,2}", h[0]):
            continue
        hafta, konu, quiz = int(h[0]), h[1], h[-1]
        q = re.fullmatch(r"(?:Quiz\s*)?(\d{1,2})", quiz, re.I)
        if not q:
            continue
        bas, bit = aralik(hafta)
        out.append({"ders": kod, "tur": f"Quiz {q.group(1)}", "hafta": hafta, "bas": bas.isoformat(),
                    "bit": bit.isoformat(), "kaynak": kaynak,
                    "konu": konu + (" · 3 saatlik dersin sonunda" if kod.startswith("MAT") else "")})
    return out


def izlenceler(s, kodlar, ek=None, log=print, takvim=None):
    """Havuz derslerinin izlencelerinden quiz/sınav takvimi + not ağırlıkları."""
    out, bilgi = [], {}
    aralik = hafta_araliklari(takvim)
    for kod in sorted(set(kodlar)):
        brans, no = (kod.split() + [""])[:2]
        url = (ek or {}).get(kod) or (IZLENCE_KAYNAK.get(brans, "").format(kod=brans + no) if brans in IZLENCE_KAYNAK else "")
        if not url:
            continue
        if not url.lower().endswith(".pdf"):            # HTML izlence (mathavuz)
            try:
                ham = s.get(url, timeout=40).text
            except requests.RequestException as e:
                log(f"  izlence {kod} alınamadı ({e.__class__.__name__})")
                continue
            bulunan = html_izlence_ayristir(ham, kod, url, aralik)
            if not bulunan:
                log(f"  izlence {kod}: tabloda quiz bulunamadı")
                continue
            out += bulunan
            duz = metin(ham)
            ag = re.search(r"(\w+ quizzes with \d+%[^.]*)", duz, re.I)
            vf = re.search(r"([^.]{0,120}(?:at least \*?\*?70%|VF)[^.]{0,120})", duz, re.I)
            bilgi[kod] = {"url": url, "agirliklar": [ag.group(1)] if ag else [],
                          "vfKurali": vf.group(1).strip()[:220] if vf else None}
            log(f"  izlence {kod}: {len(bulunan)} quiz (HTML)")
            continue
        metin_pdf = _pdf_metni(s, url)
        if not metin_pdf:
            continue
        bulunan = izlence_ayristir(metin_pdf, kod, url)
        out += bulunan
        agirlik = re.findall(r"((?:Midterm|Final\s*Exam|Quizzes|Ara\s*Sınav|Final|Quiz|Ödev|Homework|Lab)[^.]{0,40}\(\s*\d{1,3}\s*%\s*\))", metin_pdf, re.I)
        vf = re.search(r"([^.]{0,160}(?:VF|at\s*least\s*70|%\s*70)[^.]{0,160})", metin_pdf, re.I)
        bilgi[kod] = {"url": url, "agirliklar": [re.sub(r"\s+", " ", a).strip() for a in agirlik][:6],
                      "vfKurali": re.sub(r"\s+", " ", vf.group(1)).strip()[:220] if vf else None}
        log(f"  izlence {kod}: {len(bulunan)} sınav/quiz" + (f" · {', '.join(bilgi[kod]['agirliklar'][:4])}" if agirlik else ""))
    return out, bilgi


if __name__ == "__main__":
    sys.exit(main())
