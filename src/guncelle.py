"""
OBS'den (obs.itu.edu.tr, herkese açık sayfalar) ders planı, bu dönemin şubeleri, önşartlar ve
not dağılımlarını çekip data.json oluşturur; sonra template.html'e gömerek ../ders-programi.html üretir.

Kullanım (kökteki .venv içindeki python; requests yeterli):
    python guncelle.py                      -> kendi bölümünün verisini çek + HTML üret
    python guncelle.py --build              -> sadece mevcut data.json'dan HTML üret
    python guncelle.py --program ELKE_LS    -> başka programı çek (../veri/ELKE_LS.json)
Arayüzden bölüm seçip güncellemek için: ../baslat.bat (sunucu.py)
"""
import datetime
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

def _ayar_programi():
    """Kurulumda OBS'den bulunan bölüm kodu (src/ayarlar.json -> "program"), yoksa BLGE_LS."""
    try:
        return json.loads((Path(__file__).resolve().parent / "ayarlar.json").read_text(encoding="utf-8")).get("program") or "BLGE_LS"
    except (OSError, ValueError):
        return "BLGE_LS"


PROGRAM = _ayar_programi()          # bölüm kodu (data.json + ders-programi.html), örn. EHBE_LS
OBS = "https://obs.itu.edu.tr"
HERE = Path(__file__).resolve().parent
VERI = HERE.parent / "veri"         # diğer programların verisi + ders bilgisi önbelleği (git'e girmez)
BILGI_CACHE = VERI / "_ders_bilgi.json"

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (ders-secme araci)"


def get(url, **params):
    for deneme in range(3):
        try:
            r = S.get(url, params=params or None, timeout=60)
            r.raise_for_status()
            if "charset" not in r.headers.get("content-type", "").lower():
                r.encoding = r.apparent_encoding or "utf-8"   # başlıkta charset yoksa requests ISO-8859-1 sanıyor
            return r.text
        except requests.RequestException as e:
            kalici = isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code < 502
            if deneme == 2 or kalici:
                raise
            time.sleep(2)


def temiz(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def num(s):
    s = s.strip().replace(",", ".")
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


# ---------------------------------------------------------------- fakülte / program / plan listeleri
def fakulteler():
    t = get(f"{OBS}/public/DersPlan")
    m = re.search(r'name="FakulteId".*?</select>', t, re.S) or re.search(r"<select[^>]*Fakulte.*?</select>", t, re.S)
    return [(int(i), temiz(n)) for i, n in re.findall(r'<option value="(\d+)"[^>]*>([^<]+)', m.group(0) if m else t)]


def programlar(fakulte_id):
    return [(p["programKodu"], p["programAdi"]) for p in json.loads(
        get(f"{OBS}/public/DersPlan/GetAkademikProgramByBirimIdAndPlanTipi", birimId=fakulte_id, planTipiKodu="lisans"))]


def planlar(program):
    t = re.sub(r"\s+", " ", get(f"{OBS}/public/DersPlan/DersPlanlariList", programKodu=program, planTipiKodu="lisans"))
    return [(int(i), temiz(n)) for i, n in re.findall(r"DersPlanDetay/(\d+)\"[^>]*>.*?</td>\s*<td>(.*?)</td>", t)]


def guncel_plan(program):
    """Listede en son (genelde '... Dönemi Sonrası') plan."""
    pl = planlar(program)
    if not pl:
        raise RuntimeError(f"{program} için OBS'de lisans ders planı bulunamadı")
    sonra = [p for p in pl if "Sonras" in p[1]]
    return max(sonra or pl)


# ---------------------------------------------------------------- ders planı
def plan_cek(plan_id):
    t = html.unescape(re.sub(r"\s+", " ", get(f"{OBS}/public/DersPlan/DersPlanDetay/{plan_id}")))
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", t)
    h2 = re.search(r"<h2[^>]*>(.*?)</h2>", t)
    adlar = (re.sub(r"\s*Ders Planı\s*$", "", temiz(h1.group(1))) if h1 else "", temiz(h2.group(1)) if h2 else "")
    parts = re.split(r"<h2>\s*(\d+)\. Yarıyıl\s*</h2>", t)
    plan = []
    for i in range(1, len(parts), 2):
        sem = int(parts[i])
        for r in re.findall(r"<tr>.*?</tr>", parts[i + 1]):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", r)
            if len(tds) < 10:
                continue
            txt = [temiz(x) for x in tds]
            g = re.search(r"grupId=(\d+)", tds[0])
            plan.append({"sem": sem, "code": None if g else txt[0], "group": int(g.group(1)) if g else None,
                         "name": txt[1], "kredi": num(txt[4]), "akts": txt[5], "type": txt[9]})
    groups = {}
    for p in plan:
        if p["group"] and p["group"] not in groups:
            g = get(f"{OBS}/public/DersPlan/_DersGrupSearch", grupId=p["group"])
            rows = []
            for r in re.findall(r"<tr.*?</tr>", re.sub(r"\s+", " ", g)):
                c = [temiz(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r)]
                m = re.match(r"([A-Z]{2,4} \d{3,4}[A-Z]*)\s+(.*)", c[0]) if len(c) >= 4 else None
                if m:
                    rows.append({"code": m.group(1), "name": m.group(2), "kredi": num(c[2]), "akts": c[3]})
            groups[p["group"]] = rows
    return plan, groups, adlar


# ---------------------------------------------------------------- şubeler
DAYS = {"Paz": 0, "Sal": 1, "Çar": 2, "Per": 3, "Cum": 4, "Cmt": 5}


def dk(x):
    return int(x[:2]) * 60 + int(x[3:5])


def brans_listesi():
    return {b["dersBransKodu"]: b["bransKoduId"]
            for b in json.loads(get(f"{OBS}/public/DersProgram/SearchBransKoduByProgramSeviye", programSeviyeTipiAnahtari="LS"))}


def subeler(brans_id):
    t = re.sub(r"\s+", " ", get(f"{OBS}/public/DersProgram/DersProgramSearch", programSeviyeTipiAnahtari="LS", dersBransKoduId=brans_id))
    hdr, out = None, []
    for row in re.findall(r"<tr.*?</tr>", t):
        cells = [temiz(re.sub(r"<br\s*/?>", " ; ", c)) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row)]
        if cells and cells[0] == "CRN":
            hdr = cells
        elif hdr and len(cells) >= len(hdr):
            out.append(dict(zip(hdr, cells)))
    return out


# ---------------------------------------------------------------- önşart + not dağılımı
GP = {"AA": 4, "BA+": 3.75, "BA": 3.5, "BB+": 3.25, "BB": 3, "CB+": 2.75, "CB": 2.5, "CC+": 2.25, "CC": 2,
      "DC+": 1.75, "DC": 1.5, "DD+": 1.25, "DD": 1, "FF": 0, "VF": 0}
BILGI_ALANLARI = ("onsart", "sinif", "grades", "tanim", "tanimKaynak", "denk", "bilgiYok")


def ders_bilgi(code):
    try:
        return _ders_bilgi(code)
    except requests.RequestException as e:      # OBS bazı derslerde 500 dönüyor; o dersi bilgisiz bırak
        print(f"  uyarı: {code} bilgisi alınamadı ({e.__class__.__name__})")
        return code, {"onsart": None, "sinif": None, "grades": [], "tanim": None, "denk": [], "bilgiYok": True}


def pipe_metni(t):
    return re.sub(r"(\s*\|\s*)+", " | ", html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", t))))


def obs_tanim(b, no):
    """OBS DersBilgiSearch: (önşart, sınıf şartı, eşdeğer ders kodları, Türkçe tanım)"""
    s = pipe_metni(get(f"{OBS}/public/DersBilgi/DersBilgiSearch", bransKodu=b, dersNo=no))
    onsart = sinif = None
    m = re.search(r"Ders Önşartları \|(.*?)\| Başarılan Kredi/Sınıf Önşartı \|(.*?)\| (Ders Denklikleri|Ders Tanımı)", s)
    if m:
        o = re.sub(r"\(\s+", "(", re.sub(r"\s*\|\s*", " ", m.group(1)).strip())
        onsart = re.sub(r"\s+\)", ")", o) or None
        sinif = re.sub(r"\s*\|\s*", " ", m.group(2)).strip()
    denk = []
    m = re.search(r"Ders Denklikleri \|(.*?)\| Ders Tanımı", s)
    if m:
        denk = re.findall(r"\b([A-Z]{2,4} \d{3,4}[A-Z]*)\b", m.group(1))
    tanim = None
    m = re.search(r"Ders Tanımı \|(.*)$", s)
    if m:
        tanim = re.sub(r"\s*\|\s*", " ", m.group(1)).strip(" -|") or None
    return onsart, sinif, denk, tanim


def sis_tanim(b, no):
    """Öğrenci İşleri eski ders bilgi sayfası (İngilizce 'Course Description')."""
    for numara in dict.fromkeys([no, no if no.endswith("E") else no + "E"]):
        try:
            s = pipe_metni(get("https://www.sis.itu.edu.tr/EN/student/undergraduate/course-information/course-information.php", subj=b, numb=numara))
        except requests.RequestException:
            continue
        m = re.search(r"Course Description \|(.*?)\| Academic Calendar", s)
        if m:
            t = re.sub(r"\s*\|\s*", " ", m.group(1)).strip(" -|")
            if t:
                return t
    return None


def _ders_bilgi(code):
    b, no = code.split()
    res = {"onsart": None, "sinif": None, "grades": []}
    res["onsart"], res["sinif"], res["denk"], res["tanim"] = obs_tanim(b, no)
    res["tanimKaynak"] = "OBS" if res["tanim"] else None
    if not res["tanim"]:
        res["tanim"] = sis_tanim(b, no)
        res["tanimKaynak"] = "SIS" if res["tanim"] else None
    if not res["tanim"]:                          # yeni açılan ders: eşdeğer dersin tanımını kullan
        for d in res["denk"]:
            db, dno = d.split()
            try:
                t = obs_tanim(db, dno)[3] or sis_tanim(db, dno)
            except requests.RequestException:
                t = None
            if t:
                res["tanim"], res["tanimKaynak"] = t, f"eşdeğer {d}"
                break
    for yil in (datetime.date.today().year, datetime.date.today().year - 1):
        try:
            sayfa = get(f"{OBS}/public/DersNotDagilimi/NotDagilimiSearch", bransKodu=b, dersNo=no, yil=yil)
        except requests.RequestException:
            continue
        m = re.search(r"const ALL_DATA = (\[.*?\]);", sayfa, re.S)
        if not m:
            continue
        for d in json.loads(m.group(1)):
            n = d.get("ToplamAciklananOgrenci") or 0
            if n <= 0:
                continue
            dist = {x["HarfNotu"]: x["Sayi"] for x in d["Dagilim"]}
            graded = sum(v for k, v in dist.items() if k in GP)
            avg = round(sum(GP[k] * v for k, v in dist.items() if k in GP) / graded, 2) if graded else None
            pct = lambda ks: round(100 * sum(dist.get(k, 0) for k in ks) / n, 1)
            res["grades"].append({"term": f"{d['YilAdi']} {d['DonemTipAdi'].replace(' Dönemi', '')}", "kod": d["DonemKodu"], "n": n,
                                  "aa": pct(["AA"]), "ab": pct(["AA", "BA+", "BA"]), "fail": pct(["FF", "VF"]),
                                  "bl": pct(["BL"]), "bz": pct(["BZ"]), "avg": avg, "dist": dist})
        if res["grades"]:
            break
    res["grades"].sort(key=lambda g: g["kod"], reverse=True)
    return code, res


# ---------------------------------------------------------------- ders bilgisi önbelleği (programlar arası ortak)
def bilgi_cache_oku():
    try:
        return json.loads(BILGI_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    cache = {}                                    # ilk kez: mevcut data.json'daki dersleri tohum olarak al
    try:
        d = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
        for code, c in d["courses"].items():
            if "grades" in c:
                cache[code] = {k: c[k] for k in BILGI_ALANLARI if k in c} | {"_t": d.get("fetched", "")}
    except (OSError, ValueError, KeyError):
        pass
    return cache


def bilgi_cache_yaz(cache):
    VERI.mkdir(exist_ok=True)
    tmp = BILGI_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(BILGI_CACHE)


# ---------------------------------------------------------------- hepsini topla
def veri_cek(program=PROGRAM, plan_id=None, tam=True, log=None):
    """program: OBS program kodu (ör. ELKE_LS). tam=False ise önbellekte olan derslerin
    açıklama/önşart/not dağılımı tekrar çekilmez, sadece plan + şube/kontenjan yenilenir.
    log(mesaj, yapilan, toplam) ilerleme bildirir."""
    log = log or (lambda msg, i=None, n=None: print(msg if n is None else f"{msg} {i}/{n}"))
    if plan_id is None:
        log("Güncel ders planı bulunuyor...")
        plan_id = guncel_plan(program)[0]
    log("Ders planı çekiliyor...")
    plan, groups, (program_adi, plan_adi) = plan_cek(plan_id)
    courses, planrows = {}, []

    def add(code, name, kredi, akts, sem=None, group=None, typ=None):
        c = courses.setdefault(code, {"code": code, "name": name, "kredi": kredi, "akts": akts, "sems": [], "groups": [], "type": None})
        if sem and sem not in c["sems"]:
            c["sems"].append(sem)
        if group and group not in c["groups"]:
            c["groups"].append(group)
        if typ:
            c["type"] = typ

    for p in plan:
        if p["code"]:
            add(p["code"], p["name"], p["kredi"], p["akts"], sem=p["sem"], typ=p["type"])
            planrows.append({"sem": p["sem"], "code": p["code"]})
        else:
            planrows.append({"sem": p["sem"], "group": p["group"], "name": p["name"], "kredi": p["kredi"], "akts": p["akts"], "type": p["type"]})
            for r in groups[p["group"]]:
                add(r["code"], r["name"], r["kredi"], r["akts"], group=p["group"])
    if not courses:
        raise RuntimeError(f"{program} planında ders bulunamadı (plan {plan_id})")

    brans = brans_listesi()
    need = sorted({c.split()[0] for c in courses} & set(brans))
    sch, bitti = {}, 0
    with ThreadPoolExecutor(5) as ex:
        for b, rows in zip(need, ex.map(lambda b: subeler(brans[b]), need)):
            sch[b] = rows
            bitti += 1
            log(f"{len(courses)} ders. Şubeler çekiliyor", bitti, len(need))
    for code, c in courses.items():
        secs, hid = [], {"program": 0, "kontenjan": 0}
        for s in sch.get(code.split()[0], []):
            if s["Ders Kodu"] != code:
                continue
            if program not in [p.strip() for p in s["Dersi Alabilen Programlar"].split(",")]:
                hid["program"] += 1
                continue
            if int(s["Kontenjan"] or 0) <= 0:
                hid["kontenjan"] += 1
                continue
            m = []
            for g, tt, bb in zip(s["Gün"].split(" ; "), s["Saat"].split(" ; "), s["Bina"].split(" ; ")):
                g, tt = g.strip(), tt.strip()
                if g[:3] in DAYS and "/" in tt and not tt.startswith("-"):
                    a, e = tt.split("/")
                    m.append([DAYS[g[:3]], dk(a), dk(e) + 1, bb.strip()])
            secs.append({"crn": s["CRN"], "m": m, "kont": int(s["Kontenjan"]), "yaz": int(s["Yazılan"] or 0),
                         "hoca": ", ".join(h for h in re.split(r"\s*[,;]\s*", s["Öğretim Üyesi"]) if h.strip()) or "-", "yontem": s["Öğretim Yöntemi"]})
        c["sections"], c["hidden"] = secs, hid

    cache = bilgi_cache_oku()
    cekilecek = [k for k in courses if tam or k not in cache or cache[k].get("bilgiYok")]
    for k in courses:
        if k in cache and k not in cekilecek:
            courses[k].update({f: v for f, v in cache[k].items() if f != "_t"})
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    with ThreadPoolExecutor(6) as ex:
        for i, (code, res) in enumerate(ex.map(ders_bilgi, cekilecek), 1):
            courses[code].update(res)
            cache[code] = dict(res, _t=now)
            log("Önşartlar, açıklamalar ve not dağılımları çekiliyor", i, len(cekilecek))
    if cekilecek:
        bilgi_cache_yaz(cache)

    donem = json.loads(get(f"{OBS}/public/DersProgram/GetAktifDonemByProgramSeviye", programSeviyeTipiAnahtari="LS")).get("aktifDonem", "")
    data = {"fetched": now, "term": donem.replace(" Dönemi", ""),
            "program": program, "programName": program_adi or program, "planName": plan_adi, "planId": plan_id,
            "bransIds": {b: brans[b] for b in need},
            "planRows": planrows, "groupNames": {str(p["group"]): p["name"] for p in plan if p["group"]}, "courses": courses}
    log(f"Bitti: {sum(1 for c in courses.values() if c['sections'])}/{len(courses)} ders bu dönem açık.")
    return data


def veri_yaz(data):
    """Varsayılan program src/data.json'a (HTML'e gömülen), diğerleri veri/KOD.json'a."""
    metin = json.dumps(data, ensure_ascii=False)
    if data["program"] == PROGRAM:
        (HERE / "data.json").write_text(metin, encoding="utf-8")
    else:
        VERI.mkdir(exist_ok=True)
        (VERI / f"{data['program']}.json").write_text(metin, encoding="utf-8")


def veri_yolu(program):
    return HERE / "data.json" if program == PROGRAM else VERI / f"{program}.json"


def sayfa(data_metni, extra=None):
    """template.html'e veriyi gömer. extra: DATA'ya eklenecek alanlar (sunucu modu için)."""
    if extra:
        d = json.loads(data_metni)
        d.update(extra)
        data_metni = json.dumps(d, ensure_ascii=False)
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    return tpl.replace("__DATA__", data_metni.replace("</", "<\\/"))


def build():
    data = (HERE / "data.json").read_text(encoding="utf-8")
    json.loads(data)
    out = sayfa(data)
    (HERE.parent / "ders-programi.html").write_text(out, encoding="utf-8")
    print(f"ders-programi.html üretildi ({len(out) // 1024} KB)")


if __name__ == "__main__":
    args = sys.argv[1:]
    prog = args[args.index("--program") + 1] if "--program" in args else PROGRAM
    plan = int(args[args.index("--plan") + 1]) if "--plan" in args else None
    if "--build" not in args:
        veri_yaz(veri_cek(prog, plan, tam="--hizli" not in args))
    if prog == PROGRAM:
        build()
