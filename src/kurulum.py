"""
İTÜ paneli kurulumu. kur.bat bunu çalıştırır; tek tek adımlar da çağrılabilir.

    python src/kurulum.py               # hepsi: giriş -> bölüm -> ders planı -> veri -> görevler -> kısayollar -> ekler
    python src/kurulum.py --durum       # neler kurulu (Gemini önce buna bakar). Şifre yazdırmaz.
    python src/kurulum.py --giris       # İTÜ kullanıcı adı/şifre (.env) — sadece kullanıcı yazar
    python src/kurulum.py --bolum       # bölümü OBS'den bul + ders planını çek
    python src/kurulum.py --veri        # bütün veriyi çek, paneli üret
    python src/kurulum.py --gorevler    # Windows otomatik görevleri (3 saatte bir veri, açılışta WhatsApp, 21:00 hatırlatma)
    python src/kurulum.py --kisayol     # masaüstüne "İTÜ Panel" ve "İTÜ Ders Programı"
    python src/kurulum.py --eposta      # İTÜ e-postası okunabiliyor mu (salt-okunur)
    python src/kurulum.py --bildirim    # telefona bildirim (ntfy uygulaması)
    python src/kurulum.py --drive       # Google Drive klasörü (WhatsApp dosyaları + İTÜ Asistan.txt)
    python src/kurulum.py --whatsapp    # WhatsApp grupları: QR ile bağla, grupları seç
    python src/kurulum.py --whatsapp-sec 1,3,5-7   # grupları numarayla seç (listeyi --whatsapp-liste verir)
    python src/kurulum.py --notlar-kontrol         # veri/whatsapp/notlar.json geçerli mi (değerlendirmeden sonra)

Çıktıdaki satırlar: "TAMAM:" bitti, "HATA:" sorun var (yanında ne yapılacağı yazar), "SONRAKI:" ne yapılmalı.
Şifre hiçbir yere yazdırılmaz; sadece .env dosyasına kaydedilir (git'e girmez).
"""
import datetime as dt
import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
VERI = KOK / "veri"
ENV = KOK / ".env"
AYAR = HERE / "ayarlar.json"
PY = Path(sys.executable)
PYW = PY.with_name("pythonw.exe") if PY.with_name("pythonw.exe").exists() else PY
GOREV = {"veri": "ITUPanel-veri", "whatsapp": "ITUPanel-whatsapp", "hatirlatma": "ITUPanel-hatirlatma"}
WINDOWS = os.name == "nt"

sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def baslik(s):
    print(f"\n=== {s} ===")


def tamam(s):
    print(f"TAMAM: {s}")


def hata(s, ne_yapmali=""):
    print(f"HATA: {s}" + (f"\n  -> {ne_yapmali}" if ne_yapmali else ""))


def sor(soru, varsayilan="e"):
    """e/h sorusu. Etkileşimsiz (Gemini) çalıştırmada varsayılanı kullanır."""
    if not sys.stdin or not sys.stdin.isatty():
        return varsayilan == "e"
    c = input(f"{soru} [{'E/h' if varsayilan == 'e' else 'e/H'}]: ").strip().lower()
    return (c or varsayilan).startswith("e")


def ac(yol):
    """Dosyayı/linki varsayılan programla aç (QR sayfası, panel). ITU_PANEL_ACMA=1 iken açmaz (test)."""
    if os.environ.get("ITU_PANEL_ACMA"):
        print(f"  (açılmadı: {yol})")
        return
    try:
        if WINDOWS:
            os.startfile(str(yol))
        else:
            subprocess.Popen(["xdg-open", str(yol)])
    except OSError:
        pass


def ayar_oku():
    if not AYAR.exists():
        shutil.copy(HERE / "ayarlar.ornek.json", AYAR)
    return json.loads(AYAR.read_text(encoding="utf-8"))


def ayar_yaz(a):
    AYAR.write_text(json.dumps(a, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ornekleri_kopyala():
    VERI.mkdir(exist_ok=True)
    ayar_oku()
    if not (HERE / "onemli_tarihler.json").exists():
        shutil.copy(HERE / "onemli_tarihler.ornek.json", HERE / "onemli_tarihler.json")
    nj = VERI / "whatsapp" / "notlar.json"
    if not nj.exists():
        nj.parent.mkdir(parents=True, exist_ok=True)
        nj.write_text(json.dumps({
            "guncellendi": dt.datetime.now().isoformat(timespec="minutes"),
            "aciklama": "WhatsApp grupları ve İTÜ e-postasından yapay zekânın çıkardığı notlar (docs/DEGERLENDIRME.md). "
                        "teyit: 'ninova'/'resmi' = doğrulandı, 'yok' = sadece öğrenci mesajı, 'celiski' = resmi kaynakla çelişiyor.",
            "notlar": [], "olaylar": [], "dersler": {}}, ensure_ascii=False, indent=1), encoding="utf-8")


def notlar_kontrol():
    """veri/whatsapp/notlar.json doğru mu? Gemini düzenledikten sonra, --panel'den ÖNCE çalıştırır."""
    yol = VERI / "whatsapp" / "notlar.json"
    try:
        d = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        hata(f"notlar.json okunamadı: {e}", "Dosya geçerli JSON olmalı (virgüller, tırnaklar). Düzeltip tekrar çalıştır.")
        return False
    sorun = []
    if not isinstance(d.get("notlar"), list) or not isinstance(d.get("olaylar"), list) or not isinstance(d.get("dersler"), dict):
        sorun.append('en üstte "notlar": [], "olaylar": [], "dersler": {} olmalı')

    def zaman(s):
        try:
            dt.datetime.fromisoformat(str(s)[:16])
            return True
        except ValueError:
            return False
    idler = set()
    for i, n in enumerate(d.get("notlar") or []):
        for alan in ("id", "tarih", "kategori", "onem", "baslik", "metin", "teyit"):
            if alan not in n:
                sorun.append(f"notlar[{i}] '{alan}' alanı yok")
        if n.get("id") in idler:
            sorun.append(f"notlar[{i}] id tekrar ediyor: {n.get('id')}")
        idler.add(n.get("id"))
        if n.get("tarih") and not zaman(n["tarih"]):
            sorun.append(f"notlar[{i}] tarih YYYY-MM-DDTHH:MM olmalı: {n['tarih']}")
        if n.get("onem") not in (1, 2, 3):
            sorun.append(f"notlar[{i}] onem 1, 2 ya da 3 olmalı")
        if n.get("teyit") not in ("ninova", "resmi", "yok", "celiski"):
            sorun.append(f"notlar[{i}] teyit ninova/resmi/yok/celiski olmalı")
    for i, o in enumerate(d.get("olaylar") or []):
        for alan in ("tur", "bas", "teyit"):
            if alan not in o:
                sorun.append(f"olaylar[{i}] '{alan}' alanı yok")
        for alan in ("bas", "bit"):
            if o.get(alan) and not zaman(o[alan]):
                sorun.append(f"olaylar[{i}] {alan} YYYY-MM-DDTHH:MM olmalı: {o[alan]}")
    if sorun:
        hata(f"notlar.json'da {len(sorun)} sorun:\n  - " + "\n  - ".join(sorun[:30]), "Düzelt, sonra tekrar: python src/kurulum.py --notlar-kontrol")
        return False
    tamam(f"notlar.json geçerli: {len(d['notlar'])} not, {len(d['olaylar'])} olay, {len(d['dersler'])} ders bilgisi")
    return True


# ------------------------------------------------------------------ durum
def env_var():
    import itu
    e = itu.env_oku()
    return bool(e.get("ITU_KULLANICI")) and bool(e.get("ITU_SIFRE"))


def gorev_var(ad):
    if not WINDOWS:
        return False
    r = subprocess.run(["schtasks", "/query", "/tn", ad], capture_output=True)
    return r.returncode == 0


def durum(yazdir=True):
    ornekleri_kopyala()
    a = ayar_oku()
    import drive_yolu
    wa = VERI / "whatsapp"
    wa_durum = {}
    try:
        wa_durum = json.loads((wa / "durum.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        import neonize  # noqa: F401
        neonize_var = True
    except Exception:
        neonize_var = False
    panel = KOK / "panel.html"
    try:
        guncellendi = json.loads((VERI / "panel.json").read_text(encoding="utf-8")).get("guncellendi")
    except (OSError, ValueError):
        guncellendi = None
    d = {
        "python": sys.version.split()[0],
        "girisBilgisi": env_var(),
        "girisEngellendi": (VERI / "giris_hatasi.json").exists(),
        "bolum": a.get("program"),
        "dersPlani": (HERE / "data.json").exists(),
        "panel": panel.exists(),
        "panelGuncellendi": guncellendi,
        "gorevler": {k: gorev_var(v) for k, v in GOREV.items()},
        "kisayol": (masaustu() / "İTÜ Panel.lnk").exists() if WINDOWS else None,
        "eposta": (VERI / "eposta" / "epostalar.db").exists(),
        "bildirim": (VERI / "bildirim.json").exists(),
        "drive": str(drive_yolu.drive_koku() or "") or None,
        "whatsapp": {"paketKurulu": neonize_var, "bagli": bool(wa_durum.get("bagli")),
                     "eslesmisOturum": (wa / "oturum.sqlite3").exists(),
                     "seciliGrup": len((a.get("whatsapp") or {}).get("gruplar") or [])},
    }
    if yazdir:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        eksik = []
        if not d["girisBilgisi"] or d["girisEngellendi"]:
            eksik.append("giriş bilgisi -> kullanıcı kur.bat'a çift tıklasın (ya da: python src/kurulum.py --giris)")
        elif not d["bolum"] or not d["dersPlani"]:
            eksik.append("bölüm/ders planı -> python src/kurulum.py --bolum")
        elif not d["panel"]:
            eksik.append("panel -> python src/kurulum.py --veri")
        if WINDOWS and not d["gorevler"]["veri"]:
            eksik.append("otomatik güncelleme -> python src/kurulum.py --gorevler")
        if not d["bildirim"]:
            eksik.append("(isteğe bağlı) telefona bildirim -> python src/kurulum.py --bildirim")
        if not d["drive"]:
            eksik.append("(isteğe bağlı) Google Drive -> docs/DRIVE.md")
        if not d["whatsapp"]["seciliGrup"]:
            eksik.append("(isteğe bağlı) WhatsApp grupları -> docs/WHATSAPP.md")
        print("SONRAKI:\n  " + ("\n  ".join(eksik) if eksik else "her şey kurulu"))
    return d


# ------------------------------------------------------------------ giriş
def giris(deneme_hakki=2):
    """Kullanıcı adı/şifreyi KULLANICI yazar (şifre ekranda görünmez), .env'e kaydedilir, bir kez denenir."""
    import itu
    baslik("İTÜ girişi")
    if not sys.stdin or not sys.stdin.isatty():
        hata("Şifre bu pencerede sorulamıyor (etkileşimli terminal değil).",
             "Kullanıcı proje klasöründeki kur.bat dosyasına ÇİFT TIKLASIN; şifreyi orada kendisi yazsın. "
             "Şifreyi sohbette isteme.")
        return False
    print("İTÜ kullanıcı adın ve şifren (Ninova/OBS'ye girdiğin). Şifre yazarken ekranda görünmez, bu normal.")
    print("Bunlar sadece bu bilgisayardaki .env dosyasına kaydedilir, hiçbir yere gönderilmez (sadece İTÜ'ye giriş için).")
    for i in range(deneme_hakki):
        kullanici = input("Kullanıcı adı (örn. yilmaz22): ").strip()
        kullanici = kullanici.split("@")[0]
        sifre = getpass.getpass("Şifre: ")
        if not kullanici or not sifre:
            hata("Kullanıcı adı ya da şifre boş.")
            continue
        print("İTÜ'ye giriş deneniyor (bir kez)...")
        try:
            itu.oturum("https://obs.itu.edu.tr/ogrenci", kullanici, sifre, env={})
        except itu.GirisHatasi as e:
            hata(f"Giriş olmadı: {e}")
            if i + 1 < deneme_hakki:
                print("Bir kez daha dene. Emin değilsen önce tarayıcıda portal.itu.edu.tr'ye girip şifreni kontrol et.")
            continue
        except Exception as e:
            hata(f"İTÜ'ye ulaşılamadı ({e.__class__.__name__}). İnternetini kontrol et, sonra kur.bat'ı tekrar aç.")
            return False
        ENV.write_text(f"ITU_KULLANICI={kullanici}\nITU_SIFRE={sifre}\n", encoding="utf-8")
        (VERI / "giris_hatasi.json").unlink(missing_ok=True)
        tamam("Giriş başarılı, bilgiler .env dosyasına kaydedildi.")
        return True
    hata("Giriş yapılamadı. Hesabın kilitlenmesin diye daha fazla denemiyorum.",
         "Tarayıcıda portal.itu.edu.tr'de şifreni kontrol et, sonra kur.bat'ı tekrar çalıştır.")
    return False


# ------------------------------------------------------------------ bölüm + ders planı
def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").casefold())
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("ı", "i")
    s = re.sub(r"\(\s*%?\s*100\s*", "(", s)
    s = re.sub(r"\b(lisans|programi|program|ogretim|bolumu|\d+)\b", " ", s)
    return set(re.findall(r"[a-z]+", s))


def _program_listesi():
    import guncelle as G
    from concurrent.futures import ThreadPoolExecutor
    fak = G.fakulteler()
    with ThreadPoolExecutor(6) as ex:
        progs = list(ex.map(lambda f: G.programlar(f[0]), fak))
    return [(kod, ad, f[1]) for f, p in zip(fak, progs) for kod, ad in p]


def bolum_bul():
    """OBS'deki öğrenci programını İTÜ program listesiyle eşleştirir (örn. EHBE_LS)."""
    import itu
    s, _ = itu.oturum("https://obs.itu.edu.tr/ogrenci")
    token = itu.obs_token(s)
    s.headers["Authorization"] = token
    r = s.get("https://obs.itu.edu.tr/api/ogrenci/OgrenciProgamListesi", timeout=40)   # (OBS'de yazımı böyle)
    progs = ((r.json() or {}).get("ogrenciProgramBilgiListesi") or []) if r.ok else []
    adaylar = [p.get("programAdi") for p in progs if p.get("programAdi")]   # örn. "Bilgisayar Mühendisliği (İngilizce) Lisans"
    liste = _program_listesi()
    for metin in adaylar:                                # adı birebir aynı olan lisans programı
        tam = [(k, ad) for k, ad, _ in liste if k.endswith("_LS") and _norm(ad) == _norm(metin)]
        if len(tam) == 1:
            return tam[0][0], tam[0][1], []
    puanlar = []
    for metin in adaylar:
        a = _norm(metin)
        if not a:
            continue
        for kod, ad, fak in liste:
            if not kod.endswith("_LS"):
                continue
            b = _norm(ad)
            puan = len(a & b) / len(a | b)
            if ("ingilizce" in a) != ("ingilizce" in b):
                puan -= 0.3
            puanlar.append((puan, kod, ad, fak))
    puanlar.sort(reverse=True)
    if puanlar and puanlar[0][0] >= 0.6 and (len(puanlar) == 1 or puanlar[0][0] - puanlar[1][0] >= 0.1):
        return puanlar[0][1], puanlar[0][2], []
    return None, None, [p[1:] for p in puanlar[:8]] or [(k, a, f) for k, a, f in liste if k.endswith("_LS")]


def bolum(kod=None):
    import guncelle as G
    baslik("Bölüm ve ders planı")
    a = ayar_oku()
    ad = None
    if kod:
        kod = kod.upper()
    elif a.get("program"):
        kod = a["program"]
    else:
        print("Bölümün OBS'den bulunuyor...")
        try:
            kod, ad, adaylar = bolum_bul()
        except Exception as e:
            import itu
            if isinstance(e, itu.GirisHatasi):
                hata("İTÜ girişi olmadı.", "Tekrar deneme. Kullanıcı kur.bat'ı açıp şifresini yeniden girsin.")
                return False
            hata(f"Bölüm bulunamadı ({e.__class__.__name__}: {e})")
            adaylar = []
        if not kod:
            if not adaylar or not sys.stdin or not sys.stdin.isatty():
                hata("Bölüm otomatik bulunamadı.",
                     "Bölüm kodunu ver: python src/kurulum.py --bolum EHBE_LS  (EHBE_LS = Elektronik ve Haberleşme "
                     "İngilizce, EHB_LS = Türkçe; liste: python src/kurulum.py --bolum-liste)")
                return False
            print("Bölümünü seç:")
            for i, (k, n, f) in enumerate(adaylar, 1):
                print(f"  {i}. {n}  ({k})")
            secim = input("Numara: ").strip()
            if not secim.isdigit() or not 1 <= int(secim) <= len(adaylar):
                hata("Geçersiz seçim.")
                return False
            kod, ad = adaylar[int(secim) - 1][0], adaylar[int(secim) - 1][1]
    a["program"] = kod
    ayar_yaz(a)
    G.PROGRAM = kod
    tamam(f"Bölüm: {ad or kod} ({kod})")
    print("Ders planı, şubeler, hocalar ve not dağılımları OBS'den çekiliyor (2-5 dakika sürebilir)...")
    son = [0.0]

    def log(msg, i=None, n=None):
        if time.time() - son[0] > 4 or (i and n and i == n):
            son[0] = time.time()
            print(f"  {msg}" + (f" ({i}/{n})" if i and n else ""), flush=True)
    try:
        data = G.veri_cek(kod, None, tam=True, log=log)
    except Exception as e:
        hata(f"Ders planı çekilemedi ({e.__class__.__name__}: {e})", "İnternet bağlantısını kontrol edip tekrar dene: python src/kurulum.py --bolum")
        return False
    (HERE / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    G.build()
    tamam(f"Ders planı hazır: {data.get('programName')} — {len(data.get('courses') or {})} ders")
    return True


def bolum_liste():
    for kod, ad, fak in _program_listesi():
        if kod.endswith("_LS"):
            print(f"{kod:12} {ad}   [{fak}]")


# ------------------------------------------------------------------ veri
def veri():
    baslik("Veri toplama (OBS, Ninova, e-posta, takvim, yemek, ring)")
    print("Birkaç dakika sürer...")
    p = subprocess.run([str(PY), str(HERE / "topla.py")], cwd=HERE,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, text=True, encoding="utf-8", errors="replace",
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    cikti = p.stdout or ""
    for satir in cikti.splitlines()[-25:]:
        print("  " + satir)
    if p.returncode == 2 or "GIRIS_HATASI" in cikti:
        hata("İTÜ girişi başarısız.", "TEKRAR DENEME (hesap kilitlenir). Kullanıcı kur.bat'ı açıp şifresini yeniden girsin.")
        return False
    if p.returncode != 0 or not (KOK / "panel.html").exists():
        hata(f"Veri toplanamadı (çıkış kodu {p.returncode}).", "Yukarıdaki son satırlara bak; docs/SORUN_GIDERME.md")
        return False
    tamam("Panel üretildi: panel.html")
    return True


# ------------------------------------------------------------------ Windows görevleri + kısayol
def _ps(komut):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", komut],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def gorev_kur(ad, tetik, program, arguman, klasor):
    k = (f"$a = New-ScheduledTaskAction -Execute '{program}' -Argument '{arguman}' -WorkingDirectory '{klasor}';"
         f"$t = {tetik};"
         "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
         "-ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew;"
         f"Register-ScheduledTask -TaskName '{ad}' -Action $a -Trigger $t -Settings $s -Force | Out-Null")
    r = _ps(k)
    if r.returncode != 0:
        hata(f"Görev kurulamadı: {ad}", (r.stderr or r.stdout).strip()[-300:])
        return False
    tamam(f"Windows görevi: {ad}")
    return True


def gorevler():
    if not WINDOWS:
        hata("Otomatik görevler sadece Windows'ta kurulur.", "Linux/Mac: cron ile 'python src/topla.py' çalıştır.")
        return False
    baslik("Otomatik güncelleme (Windows Görev Zamanlayıcı)")
    ok = gorev_kur(GOREV["veri"], "New-ScheduledTaskTrigger -Once -At 07:30 -RepetitionInterval (New-TimeSpan -Hours 3)",
                   PYW, f'"{HERE / "topla.py"}"', HERE)
    print("  Her gün 07:30'dan itibaren 3 saatte bir veri çekilir; bilgisayar kapalıysa açılınca çalışır.")
    if (VERI / "bildirim.json").exists():
        gorev_kur(GOREV["hatirlatma"], "New-ScheduledTaskTrigger -Daily -At 21:00", PYW, f'"{HERE / "bildirim.py"}" --aksam', HERE)
    if (ayar_oku().get("whatsapp") or {}).get("gruplar") and (VERI / "whatsapp" / "oturum.sqlite3").exists():
        gorev_kur(GOREV["whatsapp"], f"New-ScheduledTaskTrigger -AtLogOn -User '{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}'",
                  PYW, "whatsapp_kopru.py", HERE)
    return ok


def masaustu():
    if not WINDOWS:
        return Path.home() / "Desktop"
    r = _ps("[Environment]::GetFolderPath('Desktop')")
    return Path(r.stdout.strip() or Path.home() / "Desktop")


def kisayol():
    if not WINDOWS:
        return False
    baslik("Masaüstü kısayolları")
    ms = masaustu()
    for ad, hedef in (("İTÜ Panel", KOK / "panel.html"), ("İTÜ Ders Programı", KOK / "baslat.bat")):
        r = _ps(f"$k=(New-Object -ComObject WScript.Shell).CreateShortcut('{ms / (ad + '.lnk')}');"
                f"$k.TargetPath='{hedef}';$k.WorkingDirectory='{KOK}';$k.Save()")
        if r.returncode == 0:
            tamam(f"Masaüstünde '{ad}'")
        else:
            hata(f"Kısayol oluşturulamadı: {ad}", r.stderr.strip()[-200:])
    return True


# ------------------------------------------------------------------ ekler
def eposta():
    baslik("İTÜ e-postası (sadece okunur)")
    p = subprocess.run([str(PY), str(HERE / "eposta.py"), "--test"], cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    print("  " + "\n  ".join((p.stdout + p.stderr).strip().splitlines()[-4:]))
    if p.returncode == 0:
        tamam("E-posta okunabiliyor; veri toplamada son 30 gün çekilir (hiçbir mail okundu işaretlenmez).")
        return True
    hata("E-postaya bağlanılamadı.", "docs/EPOSTA.md")
    return False


def bildirim():
    baslik("Telefona bildirim (ntfy)")
    yol = VERI / "bildirim.json"
    a = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
    if not a.get("kanal"):
        a = {"kanal": "itu-" + secrets.token_hex(6), "sunucu": "https://ntfy.sh"}
        yol.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    url = f"{a['sunucu']}/{a['kanal']}"
    try:
        import segno
        qr = VERI / "bildirim_qr.png"
        segno.make_qr(url).save(str(qr), scale=10, border=3)
        ac(qr)
    except Exception:
        pass
    print(f"""
  1) Telefona "ntfy" uygulamasını kur (Play Store / App Store, ücretsiz).
  2) Uygulamada + (Subscribe to topic) -> kanal adı:  {a['kanal']}
     (ya da açılan QR resmini telefonun kamerasıyla okut)
  3) Kanal adını kimseyle paylaşma; bilen bildirimleri görebilir. Bildirimlere not/isim yazılmaz.""")
    if sys.stdin and sys.stdin.isatty():
        input("  Telefonda kanala abone olunca Enter'a bas (deneme bildirimi gidecek)...")
    import bildirim as b
    try:
        b.gonder("İTÜ Panel", "Deneme bildirimi: kurulum tamam 🎉", 3, "tada")
        tamam("Deneme bildirimi gönderildi. Telefonda göründüyse hazır.")
    except Exception as e:
        hata(f"Bildirim gönderilemedi ({e.__class__.__name__})", "İnternet bağlantısını kontrol et.")
    if WINDOWS:
        gorev_kur(GOREV["hatirlatma"], "New-ScheduledTaskTrigger -Daily -At 21:00", PYW, f'"{HERE / "bildirim.py"}" --aksam', HERE)
        print("  Her akşam 21:00'de yarınki sınav/lab/son gün hatırlatması gelir.")
    return True


def drive():
    import drive_yolu
    baslik("Google Drive")
    kok = drive_yolu.drive_koku()
    if not kok:
        hata("Google Drive for Desktop bulunamadı.",
             "docs/DRIVE.md: 'winget install -e --id Google.GoogleDrive' ile kur, Google hesabınla giriş yap, "
             "sonra tekrar: python src/kurulum.py --drive")
        return False
    tamam(f"Drive klasörü: {kok}")
    print("  WhatsApp dosyaları 'İTÜ WhatsApp Dosyaları' klasörüne, panel özeti 'İTÜ Asistan.txt' dosyasına yazılır.")
    print("  Telefonda Gemini'de + > Drive > 'İTÜ Asistan.txt' ekleyip soru sorabilirsin.")
    if (VERI / "panel.json").exists():
        import topla
        topla.panel_uret()
    return True


def _whatsapp_paket():
    try:
        import neonize  # noqa: F401
        return True
    except Exception:
        pass
    print("WhatsApp paketi kuruluyor (bir kere, 1-2 dakika)...")
    r = subprocess.run([str(PY), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r",
                        str(KOK / "requirements-whatsapp.txt")])
    if r.returncode != 0:
        hata("neonize kurulamadı.", "docs/WHATSAPP.md -> Sorun giderme")
        return False
    return True


def _whatsapp_gruplari():
    try:
        return json.loads((VERI / "whatsapp" / "gruplar.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def whatsapp_liste():
    gr = [g for g in _whatsapp_gruplari() if not g.get("toplulukAnaGrubu")]
    if not gr:
        hata("Grup listesi yok.", "Önce: python src/kurulum.py --whatsapp (QR ile bağlanır, grupları çeker)")
        return []
    for i, g in enumerate(gr, 1):
        print(f"{i:3}. {'[x]' if g.get('dinleniyor') else '[ ]'} {(g['topluluk'] + ' / ') if g.get('topluluk') else ''}{g['ad']}  ({g.get('uye', '?')} kişi)")
    return gr


def whatsapp_sec(secim):
    gr = [g for g in _whatsapp_gruplari() if not g.get("toplulukAnaGrubu")]
    idx = set()
    for parca in re.split(r"[,\s]+", secim.strip()):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", parca)
        if m:
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            idx.update(range(min(a, b), max(a, b) + 1))
    secilen = [gr[i - 1] for i in sorted(idx) if 1 <= i <= len(gr)]
    if not secilen:
        hata("Hiç grup seçilmedi.", "Örnek: python src/kurulum.py --whatsapp-sec 1,3,5-8")
        return False
    a = ayar_oku()
    a.setdefault("whatsapp", {})["gruplar"] = [(g["topluluk"] + " / " + g["ad"]) if g.get("topluluk") else g["ad"]
                                               for g in secilen]
    ayar_yaz(a)
    tamam(f"{len(secilen)} grup seçildi: " + ", ".join(g["ad"] for g in secilen))
    if WINDOWS:
        gorev_kur(GOREV["whatsapp"], f"New-ScheduledTaskTrigger -AtLogOn -User '{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}'",
                  PYW, "whatsapp_kopru.py", HERE)
        _ps(f"Start-ScheduledTask -TaskName '{GOREV['whatsapp']}'")
        tamam("WhatsApp köprüsü arka planda başladı; bilgisayar her açıldığında kendiliğinden çalışır.")
    return True


def whatsapp():
    baslik("WhatsApp grupları (sadece okur, asla mesaj göndermez)")
    if not _whatsapp_paket():
        return False
    wa = VERI / "whatsapp"
    wa.mkdir(parents=True, exist_ok=True)
    qr = wa / "qr.png"
    qr.unlink(missing_ok=True)
    if WINDOWS:                                       # arka plandaki köprü açıksa kapat (aynı oturumu kullanır)
        _ps(f"Stop-ScheduledTask -TaskName '{GOREV['whatsapp']}' -ErrorAction SilentlyContinue")
    sayfa = wa / "qr.html"                            # QR ~20 sn'de bir yenilenir; sayfa resmi kendisi tazeler
    sayfa.write_text("""<!doctype html><meta charset="utf-8"><title>WhatsApp bağla</title>
<body style="font:18px sans-serif;text-align:center;padding:24px">
<h2>WhatsApp &gt; Ayarlar &gt; Bağlı cihazlar &gt; Cihaz bağla</h2>
<p>Telefonla bu QR'ı okut. Kod kendiliğinden yenilenir.</p>
<img id="qr" style="width:360px;max-width:90vw" alt="">
<p id="d">QR bekleniyor...</p>
<script>
const img = document.getElementById("qr"), d = document.getElementById("d");
img.onload = () => { img.hidden = false; d.textContent = "Okut (kod kendiliğinden yenilenir)"; };
img.onerror = () => { img.hidden = true; d.textContent = "QR bekleniyor ya da bağlandı. Bağlandıysa bu sayfayı kapatıp kurulum penceresine dön."; };
setInterval(() => img.src = "qr.png?t=" + Date.now(), 2000); img.src = "qr.png?t=0";
</script>""", encoding="utf-8")
    print("""  Telefonda: WhatsApp > Ayarlar > Bağlı cihazlar > Cihaz bağla
  Tarayıcıda açılacak sayfadaki QR'ı okut (açılmazsa: veri\\whatsapp\\qr.html). 5 dakika içinde okutman lazım.""")
    p = subprocess.Popen([str(PY), str(HERE / "whatsapp_kopru.py"), "--gruplar"], cwd=HERE,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    acildi, bas = False, time.time()
    while p.poll() is None:
        if qr.exists() and not acildi:
            ac(sayfa)
            acildi = True
            print("  QR sayfası açıldı, telefonla okut...")
        if time.time() - bas > 420:                   # 7 dk: okutulmadı ya da takıldı
            p.terminate()
            print("  Süre doldu.")
            break
        time.sleep(1)
    qr.unlink(missing_ok=True)
    gr = whatsapp_liste()
    if not gr:
        hata("Bağlanılamadı ya da grup bulunamadı.", "QR'ı 5 dakika içinde okuttun mu? Tekrar: python src/kurulum.py --whatsapp")
        return False
    tamam("WhatsApp bağlandı.")
    print("\nHangi grupları okuyayım? Sadece ders/bölüm/sınıf gruplarını seç (arkadaş sohbetleri okunmasın).")
    if not sys.stdin or not sys.stdin.isatty():
        print("SONRAKI: Kullanıcıya listeyi göster, numaraları sor, sonra: python src/kurulum.py --whatsapp-sec 1,3,5-8")
        return True
    secim = input("Numaralar (örn. 1,3,5-8): ")
    return whatsapp_sec(secim)


# ------------------------------------------------------------------ hepsi
def hepsi():
    print("İTÜ Panel kurulumu. Her adımda ne olduğunu yazacağım.\n")
    ornekleri_kopyala()
    import itu
    if not env_var() or (VERI / "giris_hatasi.json").exists():
        if not giris():
            return 1
    else:
        tamam("Giriş bilgileri zaten var (.env).")
    if not (ayar_oku().get("program") and (HERE / "data.json").exists()):
        if not bolum():
            return 1
    else:
        tamam(f"Bölüm zaten seçili: {ayar_oku()['program']}")
    if not veri():
        return 1
    gorevler()
    kisayol()
    eposta()
    if sor("\nTelefona bildirim (sınav/lab hatırlatması) kurulsun mu?"):
        bildirim()
    import drive_yolu
    if drive_yolu.drive_koku():
        drive()
    else:
        print("\nGoogle Drive for Desktop yok; isteğe bağlı (docs/DRIVE.md). Sonra: python src/kurulum.py --drive")
    if sor("\nWhatsApp ders gruplarını da okuyayım mı? (telefonla QR okutman gerekir)", "h"):
        whatsapp()
    else:
        print("WhatsApp'ı sonra kurmak için: python src/kurulum.py --whatsapp  (ya da Gemini'ye 'WhatsApp'ı kur' de)")
    baslik("Bitti")
    print(f"Panel: masaüstündeki 'İTÜ Panel' (ya da {KOK / 'panel.html'})")
    print("Ders programı aracı: masaüstündeki 'İTÜ Ders Programı'")
    ac(KOK / "panel.html")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    VERI.mkdir(exist_ok=True)
    if "--durum" in a:
        durum()
    elif "--giris" in a:
        ornekleri_kopyala()
        sys.exit(0 if giris() else 1)
    elif "--bolum-liste" in a:
        bolum_liste()
    elif "--bolum" in a:
        ornekleri_kopyala()
        i = a.index("--bolum")
        sys.exit(0 if bolum(a[i + 1] if len(a) > i + 1 and not a[i + 1].startswith("--") else None) else 1)
    elif "--veri" in a:
        sys.exit(0 if veri() else 1)
    elif "--gorevler" in a:
        sys.exit(0 if gorevler() else 1)
    elif "--kisayol" in a:
        kisayol()
    elif "--eposta" in a:
        eposta()
    elif "--bildirim" in a:
        bildirim()
    elif "--drive" in a:
        drive()
    elif "--notlar-kontrol" in a:
        ornekleri_kopyala()
        sys.exit(0 if notlar_kontrol() else 1)
    elif "--whatsapp-liste" in a:
        whatsapp_liste()
    elif "--whatsapp-sec" in a:
        sys.exit(0 if whatsapp_sec(" ".join(a[a.index("--whatsapp-sec") + 1:])) else 1)
    elif "--whatsapp" in a:
        sys.exit(0 if whatsapp() else 1)
    else:
        sys.exit(hepsi())
