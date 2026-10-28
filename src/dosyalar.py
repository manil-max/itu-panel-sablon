"""
Ders dosyalarını Google Drive'a indirir: Drive'ım/İTÜ/Dersler/<DERS KODU>/<kategori>/<Ninova alt klasörü>/dosya
Kaynaklar: Ninova Sınıf/Ders Dosyaları (alt klasörler dahil), Ninova ödev ekleri, MAT havuz sitesi,
Moodle ders materyalleri (giriş çalışırsa). Sadece indirir; Drive'da hiçbir şey silmez.

- Daha önce indirilen (aynı Ninova kaydı + aynı tarih/boyut) tekrar inmez.
- Ninova'da dosya güncellenirse eski kopyanın adına " (eski)" eklenir, yenisi iner.
- 100 MB üstü dosyalar ve dış bağlantılar (YouTube vb.) inmez, sadece listelenir.
- Her dosyanın metni veri/dosya_metin/ altına çıkarılır, slayt/başlık listesi kayda yazılır
  (asistan belgesi ve değerlendirme bunları kullanır).

    python dosyalar.py                 # hepsi
    python dosyalar.py --ders "BBF 102E"
"""
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests

HERE = Path(__file__).resolve().parent
VERI = HERE.parent / "veri"
KAYIT = VERI / "dosyalar.json"
METIN = VERI / "dosya_metin"
NINOVA = "https://ninova.itu.edu.tr"
AZAMI = 100 * 1024 * 1024
KATEGORILER = ("Slaytlar", "Recitation-Problem Session", "Ödevler", "Sınavlar (çıkmış + oturma planları)",
               "Syllabus", "Diğer")


def drive_kok():
    from drive_yerel import drive_ana               # Windows: G:\My Drive · Pi: ITU_DRIVE (rclone mount)
    k = drive_ana()
    return k / "İTÜ" if k else None


def dersler_kok():
    k = drive_kok()
    return k / "Dersler" if k else VERI / "dersler"      # Drive yoksa yerelde tut


def kategori(yol_metni, ikon=""):
    t = yol_metni.lower()
    if re.search(r"seating|oturma|exam|quiz|midterm|final|sınav|sinav|vize|çıkmış|past", t):
        return KATEGORILER[3]
    if re.search(r"syllabus|izlence|evaluation|criteria|catalog|course info|ders bilgi|grading", t):
        return KATEGORILER[4]
    if re.search(r"recitation|problem session|problem set|\bps\s*\d|tutorial|uygulama|worksheet|exercise", t):
        return KATEGORILER[1]
    if re.search(r"homework|\bhw\s*\d|assignment|ödev|odev", t):
        return KATEGORILER[2]
    if ikon == "ikon-ppt" or re.search(r"lecture|slide|chapter|week|hafta|ders notu|bölüm|chp|ch\s*\d|\bppts?\b|\bpdfs\b|"
                                       r"sunum|\.pptx?$", t):
        return KATEGORILER[0]
    return KATEGORILER[5]


def temiz(ad):
    ad = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", html.unescape(ad)).strip().rstrip(".")
    return ad[:150] or "dosya"


def boyut_bayt(s):
    m = re.match(r"([\d.,]+)\s*(KB|MB|GB|B)", s or "", re.I)
    if not m:
        return None
    return int(float(m.group(1).replace(",", ".")) * {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}[m.group(2).upper()])


def kayit_oku():
    try:
        return json.loads(KAYIT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"dosyalar": {}, "odevler": {}, "buyuk": {}, "linkler": {}}


def kayit_yaz(k):
    VERI.mkdir(exist_ok=True)
    KAYIT.write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ metin çıkarma
def metin_cikar(yol):
    """-> (düz metin, başlık listesi). PDF: sayfa başları; PPTX: slayt başlıkları; DOCX: başlık paragrafları."""
    uz = yol.suffix.lower()
    try:
        if uz == ".pdf":
            import pymupdf
            d = pymupdf.open(yol)
            sayfalar = [p.get_text() for p in d]
            toc = [t[1] for t in d.get_toc()]
            if not toc:                       # slayt PDF'i: her sayfanın ilk anlamlı satırı başlıktır
                for s in sayfalar:
                    satir = next((x.strip() for x in s.splitlines() if len(x.strip()) > 3), "")
                    if satir and not re.fullmatch(r"[\d\s/.-]+", satir):
                        toc.append(satir[:90])
            return "\n\n".join(sayfalar), toc
        if uz == ".pptx":
            from pptx import Presentation
            p, metinler, basliklar = Presentation(yol), [], []
            for sl in p.slides:
                parca = [sh.text_frame.text for sh in sl.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
                metinler.append("\n".join(parca))
                b = sl.shapes.title.text if sl.shapes.title is not None and sl.shapes.title.text.strip() else (parca[0] if parca else "")
                if b.strip():
                    basliklar.append(re.sub(r"\s+", " ", b).strip()[:90])
            return "\n\n".join(metinler), basliklar
        if uz == ".docx":
            import docx
            d = docx.Document(yol)
            return ("\n".join(p.text for p in d.paragraphs),
                    [p.text.strip()[:90] for p in d.paragraphs if p.style.name.lower().startswith("heading") and p.text.strip()])
        if uz in (".txt", ".md", ".csv"):
            return yol.read_text(encoding="utf-8", errors="replace"), []
    except Exception as e:                    # bozuk/şifreli dosya indirmeyi bozmasın
        return f"(metin çıkarılamadı: {e.__class__.__name__})", []
    return "", []


def tekil(basliklar):
    out = []
    for b in basliklar:
        b = re.sub(r"\s+", " ", b).strip(" -•·")
        if b and b.lower() not in {x.lower() for x in out} and not re.fullmatch(r"(slide|page)?\s*\d+", b, re.I):
            out.append(b)
    return out


def isle(anahtar, yol, k):
    """İnen dosyanın metnini çıkarır, başlıklarını kayda yazar."""
    metin, basliklar = metin_cikar(yol)
    METIN.mkdir(parents=True, exist_ok=True)
    if metin:
        (METIN / (hashlib.sha1(anahtar.encode()).hexdigest()[:16] + ".txt")).write_text(metin, encoding="utf-8")
    k["basliklar"] = tekil(basliklar)[:60]
    k["metinDosyasi"] = f"veri/dosya_metin/{hashlib.sha1(anahtar.encode()).hexdigest()[:16]}.txt" if metin else None


# ------------------------------------------------------------------ indirme
def _dosya_adi(r, varsayilan):
    cd = r.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    ad = unquote(m.group(1)) if m else varsayilan
    try:                                       # Ninova bazen UTF-8 adı latin-1 gönderiyor
        ad = ad.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return temiz(ad)


def _eskiye_cevir(yol):
    if yol.exists():
        hedef = yol.with_name(f"{yol.stem} (eski){yol.suffix}")
        n = 2
        while hedef.exists():
            hedef = yol.with_name(f"{yol.stem} (eski {n}){yol.suffix}")
            n += 1
        yol.rename(hedef)
        return hedef


def indir(s, url, klasor, anahtar, meta, kayit, log):
    """Kayıtta aynı sürüm varsa atlar; güncellenmişse eskiyi '(eski)' yapar. -> 'yeni'|'guncel'|'ayni'|'link'|'buyuk'|'hata'"""
    eski = kayit["dosyalar"].get(anahtar)
    if eski and eski.get("tarih") == meta.get("tarih") and eski.get("boyut") == meta.get("boyut") \
            and eski.get("yol") and Path(eski["yol"]).exists():
        return "ayni"
    b = boyut_bayt(meta.get("boyut"))
    if b and b > AZAMI:
        kayit["buyuk"][anahtar] = {**meta, "url": url}
        return "buyuk"
    try:
        r = s.get(url, timeout=120, stream=True)
    except requests.RequestException as e:
        log(f"    ! {meta.get('ad')}: {e.__class__.__name__}")
        return "hata"
    if not re.match(r"https?://(ninova|moodle|mathavuz)\.itu\.edu\.tr", r.url):   # YouTube vb. dış bağlantı
        kayit["linkler"][anahtar] = {**meta, "url": r.url, "ders": meta.get("ders")}
        r.close()
        return "link"
    if "text/html" in r.headers.get("content-type", "") and "attachment" not in r.headers.get("content-disposition", ""):
        r.close()
        return "hata"
    if int(r.headers.get("content-length") or 0) > AZAMI:
        kayit["buyuk"][anahtar] = {**meta, "url": url}
        r.close()
        return "buyuk"
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / _dosya_adi(r, temiz(meta.get("ad") or "dosya"))
    eskiye = None
    if eski and eski.get("yol") and Path(eski["yol"]).exists():
        eskiye = _eskiye_cevir(Path(eski["yol"]))
    elif yol.exists():                         # aynı adda başka bir şey var (ör. elle konmuş): üstüne yazma
        yol = yol.with_name(f"{yol.stem} ({anahtar.split(':')[-1][-8:]}){yol.suffix}")
    gecici = yol.with_name(yol.name + ".indiriliyor")
    h = hashlib.sha256()
    with open(gecici, "wb") as f:
        for parca in r.iter_content(1 << 16):
            f.write(parca)
            h.update(parca)
    gecici.replace(yol)
    k = {**meta, "url": url, "yol": str(yol), "sha256": h.hexdigest(),
         "indirildi": dt.datetime.now().isoformat(timespec="minutes")}
    if eskiye:
        k["eskiSurum"] = str(eskiye)
    isle(anahtar, yol, k)
    kayit["dosyalar"][anahtar] = k
    log(f"    + {meta.get('ders')}: {yol.relative_to(yol.parents[2]) if len(yol.parents) > 2 else yol.name}"
        + (" (güncellendi, eskisi '(eski)')" if eskiye and eski else ""))
    return "guncel" if eski else "yeni"


def _satirlar(s, url):
    from topla import _orta, metin
    try:
        ic = _orta(s.get(url, timeout=40).text)
    except requests.RequestException:
        return []
    out = []
    for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", ic, re.S):
        a = re.search(r'<a href="([^"]+\?g\d+)">(.*?)</a>', satir, re.S)
        if not a:
            continue
        ikon = re.search(r"ds/([\w-]+)\.png", satir)
        hucre = [metin(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", satir, re.S)]
        out.append({"href": NINOVA + html.unescape(a.group(1)), "ad": metin(a.group(2)),
                    "klasor": bool(ikon and ikon.group(1) == "folder"), "ikon": ikon.group(1) if ikon else "",
                    "boyut": hucre[1] if len(hucre) > 1 else None, "tarih": hucre[2] if len(hucre) > 2 else None})
    return out


def ninova_sinif(s, sid, ders, kayit, log, sayac):
    kok = dersler_kok() / temiz(ders)
    for alt in ("SinifDosyalari", "DersDosyalari"):
        yigin = [(f"{NINOVA}/Sinif/{sid}/{alt}", [])]
        gorulen = set()
        while yigin:
            url, yol = yigin.pop()
            if url in gorulen:
                continue
            gorulen.add(url)
            for x in _satirlar(s, url):
                if x["klasor"]:
                    yigin.append((x["href"], yol + [temiz(x["ad"])]))
                    continue
                kat = kategori(" / ".join(yol + [x["ad"]]), x["ikon"])
                anahtar = "ninova:" + x["href"].split("?")[-1]
                meta = {"ders": ders, "ad": x["ad"], "boyut": x["boyut"], "tarih": x["tarih"], "kaynak": "Ninova",
                        "ikon": x["ikon"],
                        "ninovaYolu": "/".join(yol + [x["ad"]]), "kategori": kat,
                        "ninovaUrl": x["href"]}
                sonuc = indir(s, x["href"], kok / kat / Path(*yol) if yol else kok / kat, anahtar, meta, kayit, log)
                sayac[sonuc] = sayac.get(sonuc, 0) + 1


def ninova_odevler(s, kayit, log, sayac, sadece=None):
    """Ödev sayfaları: ek dosyalar -> Ödevler/<ödev adı>/, teslim durumu (yükleme zamanı) kayda."""
    from topla import _orta, metin
    o = _orta(s.get(f"{NINOVA}/Kampus?1/Odevler", timeout=40).text)
    for href in sorted(set(re.findall(r'href="(/Sinif/[\d.]+/Odev/\d+)"', o))):
        sayfa = _orta(s.get(NINOVA + href, timeout=40).text)
        duz = metin(sayfa)
        baslik = re.match(r"\s*(.*?)\s+Teslim Başlangıcı", duz)
        baslik = baslik.group(1).strip() if baslik else href.split("/")[-1]
        ders = kayit.get("sinifDers", {}).get(href.split("/")[2], href.split("/")[2])
        if sadece and ders != sadece:
            continue
        bit = re.search(r"Teslim Bitişi\s+(\d+ \w+ \d{4} \d\d:\d\d)", duz)
        gonder = metin(_orta(s.get(NINOVA + href + "/OdevGonder", timeout=40).text))
        yuklenen = re.findall(r"Dosyayı (\d+ \w+ \d{4} \d\d:\d\d) tarihinde sisteme yüklediniz", gonder)
        kayit["odevler"][href] = {"ders": ders, "baslik": baslik, "teslimBitis": bit.group(1) if bit else None,
                                  "yuklendi": yuklenen[-1] if yuklenen else None, "url": NINOVA + href}
        for a_href, ad in re.findall(r'<a href="(' + re.escape(href) + r'\?g\d+)">(.*?)</a>', sayfa):
            ad = metin(ad)
            satir = re.search(re.escape(ad) + r"\s+([\d.,]+ [KMG]?B)\s+(\d+ \w+ \d{4} \d\d:\d\d)", duz)
            meta = {"ders": ders, "ad": ad, "boyut": satir.group(1) if satir else None,
                    "tarih": satir.group(2) if satir else None, "kaynak": "Ninova ödev",
                    "kategori": KATEGORILER[2], "odev": baslik, "ninovaUrl": NINOVA + href}
            sonuc = indir(s, NINOVA + html.unescape(a_href), dersler_kok() / temiz(ders) / KATEGORILER[2] / temiz(baslik),
                          "ninova:" + a_href.split("?")[-1], meta, kayit, log)
            sayac[sonuc] = sayac.get(sonuc, 0) + 1


# ------------------------------------------------------------------ MAT havuz (herkese açık)
MATHAVUZ = "https://mathavuz.itu.edu.tr/"


def mathavuz(s, kodlar, kayit, log, sayac):
    """mathavuz.itu.edu.tr: kayıtlı MAT derslerinin çıkmış sınav/çözüm ve çalışma soruları (PDF)."""
    g = requests.Session()
    g.headers["User-Agent"] = "Mozilla/5.0"
    for kod in [k for k in kodlar if k.startswith("MAT")]:
        kk = kod.replace(" ", "")
        try:
            ana = g.get(MATHAVUZ, timeout=30).text
        except requests.RequestException as e:
            log(f"  mathavuz alınamadı ({e.__class__.__name__})")
            return
        sayfalar = {MATHAVUZ}
        for h in re.findall(r'href="([^"]+)"', ana):
            u = urljoin(MATHAVUZ, html.unescape(h))
            if u.startswith(MATHAVUZ) and re.search(kk + r"|exam|sinav|sınav|old|past|question|soru|calisma|çalışma", u, re.I) \
                    and not u.lower().endswith(".pdf"):
                sayfalar.add(u)
        pdfler = {}
        for sayfa in list(sayfalar)[:25]:
            try:
                t = g.get(sayfa, timeout=30).text
            except requests.RequestException:
                continue
            for h, ad in re.findall(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>', t, re.S | re.I):
                u = urljoin(sayfa, html.unescape(h))
                if kk.lower() in (u + ad).lower().replace(" ", "") or (kk[-4:-1] in u and "MAT" in u.upper()):
                    pdfler[u] = re.sub(r"<[^>]+>|\s+", " ", ad).strip() or Path(u).name
        for u, ad in pdfler.items():
            kat = KATEGORILER[3] if re.search(r"exam|sınav|sinav|midterm|final|quiz|çıkmış|vize|answer|cevap|solution|çözüm", u + ad, re.I) \
                else KATEGORILER[1]
            meta = {"ders": kod, "ad": ad, "boyut": None, "tarih": None, "kaynak": "mathavuz", "kategori": kat}
            sonuc = indir(g, u, dersler_kok() / temiz(kod) / kat / "MAT havuz", "mathavuz:" + u, meta, kayit, log) \
                if u not in [v.get("url") for v in kayit["dosyalar"].values()] else "ayni"
            sayac[sonuc] = sayac.get(sonuc, 0) + 1


# ------------------------------------------------------------------ Moodle
MOODLE = "https://moodle.itu.edu.tr"
MOODLE_ENGEL = VERI / "moodle_giris_hatasi.json"


def moodle_oturum(log=print):
    """Moodle'ın kendi giriş formu (kullanıcı adı = İTÜ e-postasının @ öncesi). Reddedilirse engel dosyası
    yazar ve bir daha denemez (hesap kilitlenmesin)."""
    import itu
    if MOODLE_ENGEL.exists():
        log("  Moodle: önceki giriş reddedildi, denenmedi (veri/moodle_giris_hatasi.json'u silince tekrar dener)")
        return None
    env = itu.env_oku()
    k, p = env.get("ITU_KULLANICI", "").split("@")[0], env.get("ITU_SIFRE", "")
    if not k or not p:
        return None
    g = requests.Session()
    g.headers["User-Agent"] = "Mozilla/5.0"
    t = g.get(f"{MOODLE}/login/index.php", timeout=40).text
    tok = re.search(r'name="logintoken" value="([^"]+)"', t)
    r = g.post(f"{MOODLE}/login/index.php", data={"anchor": "", "logintoken": tok.group(1) if tok else "",
                                                  "username": k, "password": p}, timeout=40)
    if "/login/index.php" in r.url or "loginerrormessage" in r.text:
        MOODLE_ENGEL.write_text(json.dumps({"tarih": dt.datetime.now().isoformat(timespec="minutes"),
                                            "hata": "giriş reddedildi"}), encoding="utf-8")
        log("  Moodle girişi reddedildi — tekrar denenmeyecek")
        return None
    return g, r.text


def moodle(kodlar, kayit, log, sayac):
    o = moodle_oturum(log)
    if not o:
        return
    g, sayfa = o
    sk = re.search(r'"sesskey":"([^"]+)"', sayfa)
    if not sk:
        return
    r = g.post(f"{MOODLE}/lib/ajax/service.php?sesskey={sk.group(1)}", timeout=40, json=[{
        "index": 0, "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
        "args": {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname"}}])
    try:
        kurslar = r.json()[0]["data"]["courses"]
    except (ValueError, KeyError, IndexError, TypeError):
        log("  Moodle: ders listesi alınamadı")
        return
    for c in kurslar:
        ad = f"{c.get('fullname', '')} {c.get('shortname', '')}"
        kod = next((k for k in sorted(kodlar, key=len, reverse=True)     # FIZ 101EL, FIZ 101E'den önce
                    if re.search(re.escape(k.replace(" ", "")) + r"(?![A-Z])", ad.replace(" ", ""), re.I)), None)
        if not kod:
            continue
        t = g.get(f"{MOODLE}/course/view.php?id={c['id']}", timeout=40).text
        for href, isim in re.findall(r'href="(https://moodle\.itu\.edu\.tr/mod/(?:resource|folder)/view\.php\?id=\d+)"[^>]*>'
                                     r'.*?<span class="instancename">(.*?)<', t, re.S):
            isim = re.sub(r"<[^>]+>", "", html.unescape(isim)).strip()
            if "/folder/" in href:                    # klasör: içindeki dosyalar
                ic = g.get(href, timeout=40).text
                dosyalar_ = re.findall(r'href="(https://moodle\.itu\.edu\.tr/pluginfile\.php/[^"]+)"', ic)
            else:
                dosyalar_ = [href]
            for u in dict.fromkeys(html.unescape(x) for x in dosyalar_):
                ad_ = unquote(u.split("?")[0].split("/")[-1]) if "pluginfile" in u else isim
                kat = kategori(f"{isim} / {ad_}")
                meta = {"ders": kod, "ad": ad_ if "pluginfile" in u else isim, "boyut": None, "tarih": None,
                        "kaynak": "Moodle", "kategori": kat, "moodleKurs": c.get("fullname")}
                anahtar = "moodle:" + u
                if anahtar in kayit["dosyalar"] and Path(kayit["dosyalar"][anahtar].get("yol") or "").exists():
                    sayac["ayni"] = sayac.get("ayni", 0) + 1
                    continue
                sonuc = indir(g, u, dersler_kok() / temiz(kod) / kat / "Moodle", anahtar, meta, kayit, log)
                sayac[sonuc] = sayac.get(sonuc, 0) + 1


def yerlestir(kayit, log=print):
    """Kayıttaki dosyaları olması gereken klasöre taşır (ders eşleşmesi/kategori kuralı değiştiyse). Silmez."""
    kok, tasinan = dersler_kok(), 0
    for a, v in kayit["dosyalar"].items():
        yol = Path(v.get("yol") or "")
        if v.get("kaynak") not in ("Ninova", "Ninova ödev") or not yol.exists():
            continue
        sid = re.search(r"/Sinif/([\d.]+)", v.get("ninovaUrl") or "")
        ders = kayit.get("sinifDers", {}).get(sid.group(1), v["ders"]) if sid else v["ders"]
        if v["kaynak"] == "Ninova ödev":
            hedef = kok / temiz(ders) / KATEGORILER[2] / temiz(v.get("odev") or "")
        else:
            parcalar = (v.get("ninovaYolu") or v["ad"]).split("/")
            kat = kategori(" / ".join(parcalar) + yol.suffix.lower(), v.get("ikon") or "")
            v["kategori"] = kat
            hedef = kok / temiz(ders) / kat / Path(*parcalar[:-1]) if len(parcalar) > 1 else kok / temiz(ders) / kat
        v["ders"] = ders
        if yol.parent != hedef:
            hedef.mkdir(parents=True, exist_ok=True)
            yeni = hedef / yol.name
            if yeni.exists():
                continue
            shutil.move(str(yol), str(yeni))
            v["yol"] = str(yeni)
            tasinan += 1
            ust = yol.parent
            while ust != kok and ust.exists() and not any(ust.iterdir()):     # boş kalan klasör
                ust.rmdir()
                ust = ust.parent
    if tasinan:
        log(f"  {tasinan} dosya doğru klasöre taşındı")


# ------------------------------------------------------------------ oturma planı
def oturma_ara(kayit, no):
    """Oturma planı PDF'lerinde öğrenci numarasını arar -> {anahtar: {salon, sira, sutun, ...}}.
    sıra = kürsüden (sayfanın üstünden) kaçıncı numara satırı, sütun = soldan kaçıncı numara sütunu."""
    import pymupdf
    out = {}
    for a, v in kayit["dosyalar"].items():
        yol = Path(v.get("yol") or "")
        if yol.suffix.lower() != ".pdf" or not re.search(r"seating|oturma|salon", v.get("ad", "") + yol.name, re.I) \
                or not yol.exists():
            continue
        try:
            d = pymupdf.open(yol)
        except Exception:
            continue
        for pg in d:
            kelimeler = [w for w in pg.get_text("words") if re.fullmatch(r"\d{9}", w[4])]
            hedef = [w for w in kelimeler if w[4] == no]
            if not hedef:
                continue
            w = hedef[0]
            satirlar = sorted({round(k[1] / 8) for k in kelimeler})
            sutunlar = sorted({round(k[0] / 25) for k in kelimeler})
            ilk = next((x.strip() for x in pg.get_text().splitlines() if x.strip()), "")
            salon = ilk.split("|")[-1].strip() if "|" in ilk else ilk
            out[a] = {"ders": v.get("ders"), "dosya": v.get("ad"), "yol": str(yol), "baslik": ilk, "salon": salon,
                      "sira": satirlar.index(round(w[1] / 8)) + 1, "siraSayisi": len(satirlar),
                      "sutun": sutunlar.index(round(w[0] / 25)) + 1, "sutunSayisi": len(sutunlar),
                      "dosyaTarihi": v.get("tarih")}
    return out


# ------------------------------------------------------------------ ana akış
def calistir(log=print, sadece=None):
    import itu
    from topla import metin
    kayit = kayit_oku()
    for k in ("dosyalar", "odevler", "buyuk", "linkler"):
        kayit.setdefault(k, {})
    sayac = {}
    s, r = itu.oturum(f"{NINOVA}/Kampus1")
    siniflar = []
    for sid in sorted(set(re.findall(r'href="/Sinif/(\d+\.\d+)"', r.text))):
        ana = s.get(f"{NINOVA}/Sinif/{sid}", timeout=40).text
        yol = re.search(r"Neredeyim:(.*?)(?:Kampüse d|</div>)", re.sub(r"<[^>]+>", " ", ana), re.S)
        ad = metin(yol.group(1)).split("/")[-1].strip() if yol else sid
        kod = re.match(r"([A-ZÇĞİÖŞÜ]{2,4}\s?\d{3}[A-Z]{0,2})", ad)
        siniflar.append((sid, kod.group(1) if kod else ad))
    try:                                       # "MAT 000 - MAT Havuz" gibi ortak sınıflar: aynı branştaki kendi dersin
        obs = [d["kod"] for d in json.loads((VERI / "panel.json").read_text(encoding="utf-8"))["obs"]["dersler"]]
    except (OSError, ValueError, KeyError):
        obs = []
    def esle(kod):
        if kod in obs or not obs:
            return kod
        ayni = [o for o in obs if o.split()[0] == kod.split()[0] and not o.endswith("L")]
        return ayni[0] if len(ayni) == 1 else kod
    siniflar = [(sid, esle(kod)) for sid, kod in siniflar]
    kayit["sinifDers"] = {sid: kod for sid, kod in siniflar}
    for sid, kod in siniflar:
        if sadece and kod != sadece:
            continue
        log(f"  {kod}")
        ninova_sinif(s, sid, kod, kayit, log, sayac)
        kayit_yaz(kayit)
    ninova_odevler(s, kayit, log, sayac, sadece)
    if not sadece or sadece in obs:
        moodle(sorted({k for _, k in siniflar} | set(obs)) if not sadece else [sadece], kayit, log, sayac)
    yerlestir(kayit, log)
    if not sadece or sadece.startswith("MAT"):
        mathavuz(s, sorted({k for _, k in siniflar}), kayit, log, sayac)
    try:
        no = json.loads((VERI / "panel.json").read_text(encoding="utf-8"))["obs"]["ogrenci"].get("no")
    except (OSError, ValueError, KeyError):
        no = None
    if no:
        kayit["oturma"] = oturma_ara(kayit, str(no))
    kayit["guncellendi"] = dt.datetime.now().isoformat(timespec="minutes")
    kayit_yaz(kayit)
    log("  dosyalar: " + ", ".join(f"{k} {v}" for k, v in sorted(sayac.items())))
    return kayit


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = sys.argv[sys.argv.index("--ders") + 1] if "--ders" in sys.argv else None
    calistir(sadece=d)
