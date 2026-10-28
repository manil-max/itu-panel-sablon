"""
WhatsApp grup köprüsü (sadece OKUR, hiçbir şey göndermez).

Telefona "bağlı cihaz" olarak eklenir (WhatsApp Web gibi), ayarlar.json'daki
whatsapp.dahil / whatsapp.haric kurallarına uyan grupların mesajlarını
veri/whatsapp/mesajlar.db'ye yazar, belge/fotoğrafları veri/whatsapp/dosyalar/'a indirir.

    python whatsapp_kopru.py            # bağlan ve dinle (ilk seferde QR -> veri/whatsapp/qr.png)
    python whatsapp_kopru.py --gruplar  # bağlan, katıldığın grupları ve seçilenleri yazdır, çık

Mesajlar ve dosyalar sadece bu bilgisayarda kalır (veri/ git'e girmez).
"""
import json
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

if sys.stdout is None:                       # pythonw (Görev Zamanlayıcı): çıktı log dosyasına
    (Path(__file__).resolve().parent.parent / "veri" / "whatsapp").mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(Path(__file__).resolve().parent.parent / "veri" / "whatsapp" / "kopru.log",
                                   "a", encoding="utf-8", buffering=1)

import segno
from neonize.client import NewClient
from neonize.events import (ConnectedEv, DisconnectedEv, HistorySyncEv, LoggedOutEv,
                            MessageEv, PairStatusEv)

KOK = Path(__file__).resolve().parent.parent
WA = KOK / "veri" / "whatsapp"
DOSYALAR = WA / "dosyalar"
DB = WA / "mesajlar.db"
AYAR = Path(__file__).resolve().parent / "ayarlar.json"
VIDEO_SINIR = 25 * 1024 * 1024
BELGE_SINIR = 60 * 1024 * 1024                  # daha büyük belge indirilmez, sadece işaretlenir
# foto/video sadece ders gruplarından iner; sohbet gruplarından sadece belge (PDF vb.)
DERS_GRUBU = re.compile(json.loads(AYAR.read_text(encoding="utf-8")).get("whatsapp", {}).get("dersGrubuDeseni")
                        or "FIZ|MAT|KIM|EHB|ELE|EEF|BLG|BBF|EKO|havuz", re.I)   # ayarlar.json -> whatsapp.dersGrubuDeseni

WA.mkdir(parents=True, exist_ok=True)
KURALLAR = json.loads(AYAR.read_text(encoding="utf-8")).get("whatsapp", {})


def drive_klasoru():
    """Google Drive for Desktop kuruluysa 'Drive'ım/İTÜ WhatsApp Dosyaları' (telefondan da açılır).
    ayarlar.json whatsapp.dosyaKlasoru elle verilmişse o kullanılır."""
    elle = KURALLAR.get("dosyaKlasoru")
    if elle:
        return Path(elle)
    from drive_yerel import drive_ana             # Windows: G:\My Drive · Pi: ITU_DRIVE (rclone mount)
    kok = drive_ana()
    return kok / "İTÜ WhatsApp Dosyaları" if kok else None


DRIVE = drive_klasoru()       # bilgisayar açılırken Drive henüz bağlanmamış olabilir: dosya_kok() tekrar bakar


def dosya_kok():
    """Dosyaların gideceği klasör. Drive sonradan bağlanırsa ona geçer ve PC'deki indirmeleri taşır."""
    global DRIVE
    if DRIVE is None:
        DRIVE = drive_klasoru()
        if DRIVE:
            drive_tasi()
    k = DRIVE or DOSYALAR
    k.mkdir(parents=True, exist_ok=True)
    return k


def _yol(p):
    """DB'de saklanacak yol: depo içindeyse göreli, Drive'daysa tam yol."""
    try:
        return str(Path(p).relative_to(KOK))
    except ValueError:
        return str(p)
GRUP_ADI = {}        # jid -> grup adı
TOPLULUK = {}        # jid -> bağlı olduğu topluluğun adı
SECILI = set()       # dinlenen grup jid'leri
kilit = threading.Lock()


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def _norm(s):
    s = (s or "").replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9]", "", s.encode("ascii", "ignore").decode())


def secili_mi(ad, topluluk):
    """Sadece ayarlar.json'daki whatsapp.gruplar listesinde birebir adıyla yazan gruplar.
    Yeni katıldığın bir grup listeye elle eklenmedikçe asla okunmaz."""
    tam = _norm((topluluk + " / " if topluluk else "") + ad)
    return tam in {_norm(g) for g in KURALLAR.get("gruplar", [])}


# Bu köprü hiçbir koşulda mesaj göndermez, okundu bilgisi/çevrimiçi durumu yollamaz, gruba
# katılmaz/ayrılmaz. NewClient'ın aşağıdakiler DIŞINDAKİ bütün genel metotları kapatılır.
IZINLI = {"connect", "connect_with_proxy", "disconnect", "stop", "get_joined_groups", "get_group_info",
          "download_any", "is_connected", "is_logged_in", "get_me", "event", "qr"}


def kilitle(client):
    def _yasak(ad):
        def f(*_, **__):
            log("ENGELLENDI:", ad, "(kopru sadece okur)")
            raise PermissionError(f"whatsapp_kopru sadece okur: {ad} kapali")
        return f
    for ad in dir(type(client)):
        if not ad.startswith("_") and ad not in IZINLI and callable(getattr(type(client), ad, None)):
            setattr(client, ad, _yasak(ad))
    return client


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("""CREATE TABLE IF NOT EXISTS mesajlar(
        id TEXT PRIMARY KEY, grup TEXT, grup_adi TEXT, topluluk TEXT,
        gonderen TEXT, gonderen_adi TEXT, benden INTEGER, zaman INTEGER,
        tur TEXT, metin TEXT, dosya_adi TEXT, dosya TEXT, alinti TEXT,
        kaynak TEXT, degerlendirildi INTEGER DEFAULT 0)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_zaman ON mesajlar(zaman)")
    if "hash" not in {r[1] for r in c.execute("PRAGMA table_info(mesajlar)")}:
        c.execute("ALTER TABLE mesajlar ADD COLUMN hash TEXT")
    return c


def durum_yaz(**k):
    yol = WA / "durum.json"
    d = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
    d.update(k, guncellendi=datetime.now().isoformat(timespec="seconds"))
    yol.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _guvenli(s, n=60):
    return re.sub(r'[\\/:*?"<>|\r\n]+', "_", s or "").strip(" .")[:n] or "dosya"


METIN_ALANLARI = {"text", "caption", "conversation", "name", "title", "description", "groupName", "matchedText",
                  "canonicalUrl", "body", "contentText", "footerText", "displayName", "selectedDisplayText", "url"}


def _metinler(m, derinlik=0):
    """Tanınmayan mesaj türlerinden (buton, şablon, etkileşimli, kanal iletisi…) okunabilir metni toplar."""
    out = []
    for fd, deger in m.ListFields():
        if fd.name in ("contextInfo", "messageContextInfo", "jpegThumbnail"):
            continue
        if fd.type == fd.TYPE_MESSAGE:
            if derinlik < 6:
                for v in (deger if isinstance(deger, (list, tuple)) or hasattr(deger, "__len__") and not hasattr(deger, "ListFields") else [deger]):
                    out += _metinler(v, derinlik + 1)
        elif fd.type == fd.TYPE_STRING and fd.name in METIN_ALANLARI and deger:
            out.append(deger)
        elif fd.type == fd.TYPE_STRING and fd.name == "inviteCode" and deger:
            out.append("https://chat.whatsapp.com/" + deger)
    return list(dict.fromkeys(out))


def _icerik(m):
    """waE2E.Message -> (tür, metin, dosya_adi, medya_mesajı, alıntı)"""
    for sarmal in ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2", "viewOnceMessageV2Extension", "editedMessage"):
        if m.HasField(sarmal):
            m = getattr(m, sarmal).message
    if m.HasField("documentWithCaptionMessage"):
        m = m.documentWithCaptionMessage.message
    alinti = ""
    for alan in ("extendedTextMessage", "imageMessage", "documentMessage", "videoMessage"):
        if m.HasField(alan):
            ci = getattr(m, alan).contextInfo
            if ci.HasField("quotedMessage"):
                q = ci.quotedMessage
                alinti = (q.conversation or q.extendedTextMessage.text or q.imageMessage.caption
                          or q.documentMessage.fileName or "")[:300]
    if m.conversation:
        return "metin", m.conversation, "", None, alinti
    if m.HasField("extendedTextMessage"):
        return "metin", m.extendedTextMessage.text, "", None, alinti
    if m.HasField("documentMessage"):
        d = m.documentMessage
        return "belge", d.caption, d.fileName or d.title or "belge", d, alinti
    if m.HasField("imageMessage"):
        return "foto", m.imageMessage.caption, "", m.imageMessage, alinti
    if m.HasField("videoMessage"):
        return "video", m.videoMessage.caption, "", m.videoMessage, alinti
    if m.HasField("audioMessage"):
        return "ses", "", "", None, alinti
    if m.HasField("pollCreationMessage") or m.HasField("pollCreationMessageV3"):
        p = m.pollCreationMessage if m.HasField("pollCreationMessage") else m.pollCreationMessageV3
        return "anket", p.name + " | " + " / ".join(o.optionName for o in p.options), "", None, ""
    if m.HasField("groupInviteMessage"):              # "gruba katıl" kartı: link metinde yok, davet kodundan kurulur
        g = m.groupInviteMessage
        return ("davet", f"Grup daveti: {g.groupName} https://chat.whatsapp.com/{g.inviteCode}"
                + (f" {g.caption}" if g.caption else ""), "", None, alinti)
    if m.HasField("eventMessage"):                   # WhatsApp etkinlik kartı (ad, zaman, yer)
        e = m.eventMessage
        zaman = datetime.fromtimestamp(e.startTime).strftime("%d.%m.%Y %H:%M") if e.startTime else ""
        return ("etkinlik", f"Etkinlik: {e.name} | {zaman} | {e.location.name or ''} | {e.description}"
                + (f" | {e.joinLink}" if e.joinLink else ""), "", None, alinti)
    if m.HasField("stickerMessage") or m.HasField("reactionMessage") or m.HasField("protocolMessage"):
        return None, "", "", None, ""
    metin = " | ".join(_metinler(m))[:4000]
    return ("diger", metin, "", None, alinti) if metin else (None, "", "", None, "")


def _indir(client, tam_mesaj, tur, medya, grup_adi, zaman, mid, dosya_adi, ders_grubu):
    """-> (yol, hash). Aynı dosya (WhatsApp'ın SHA256'sı) daha önce indiyse tekrar indirmez."""
    if medya is None:
        return "", ""
    ozet = medya.fileSHA256.hex() if medya.fileSHA256 else ""
    if tur in ("foto", "video") and not ders_grubu:
        return "", ozet
    if tur == "video" and medya.fileLength > VIDEO_SINIR:
        return "", ozet
    if tur == "belge" and medya.fileLength > BELGE_SINIR:
        log("büyük belge indirilmedi:", dosya_adi, f"{medya.fileLength // 1048576} MB")
        return "", ozet
    if ozet:
        with kilit:
            c = db()
            r = c.execute("SELECT dosya FROM mesajlar WHERE hash=? AND dosya!='' LIMIT 1", (ozet,)).fetchone()
            c.close()
        if r and (KOK / r[0]).exists():
            return r[0], ozet
    if dosya_adi and medya.fileLength:             # aynı ad + aynı boyut daha önce indiyse (farklı gruptan) tekrar indirme
        with kilit:
            c = db()
            for (y,) in c.execute("SELECT DISTINCT dosya FROM mesajlar WHERE dosya_adi=? AND dosya!=''", (dosya_adi,)):
                if (KOK / y).is_file() and (KOK / y).stat().st_size == medya.fileLength:
                    c.close()
                    return y, ozet
            c.close()
    uzanti = {"foto": ".jpg", "video": ".mp4"}.get(tur, "")
    ad = _guvenli(dosya_adi, 80) if dosya_adi else mid[:12] + uzanti
    klasor = dosya_kok() / _guvenli(grup_adi)
    klasor.mkdir(exist_ok=True)
    yol = klasor / f"{datetime.fromtimestamp(zaman):%Y-%m-%d}_{ad}"
    if yol.exists():
        return _yol(yol), ozet
    try:
        client.download_any(tam_mesaj, str(yol))
        return _yol(yol), ozet
    except Exception as e:                       # süresi dolmuş linkler vs.
        log("indirilemedi:", ad, type(e).__name__)
        return "", ozet


def kaydet(client, grup, gonderen, gonderen_adi, benden, zaman, mid, mesaj, kaynak):
    if grup not in SECILI:
        return
    tur, metin, dosya_adi, medya, alinti = _icerik(mesaj)
    if tur is None:
        return
    grup_adi = GRUP_ADI.get(grup, grup)
    with kilit:
        c = db()
        if c.execute("SELECT 1 FROM mesajlar WHERE id=?", (mid,)).fetchone():
            c.close()
            return
        c.close()
    ders_grubu = bool(DERS_GRUBU.search(grup_adi + " " + TOPLULUK.get(grup, "")))
    dosya, ozet = _indir(client, mesaj, tur, medya, grup_adi, zaman, mid, dosya_adi, ders_grubu)
    with kilit:
        c = db()
        c.execute("INSERT OR IGNORE INTO mesajlar(id,grup,grup_adi,topluluk,gonderen,gonderen_adi,"
                  "benden,zaman,tur,metin,dosya_adi,dosya,alinti,kaynak,hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (mid, grup, grup_adi, TOPLULUK.get(grup, ""), gonderen, gonderen_adi, int(benden),
                   zaman, tur, metin, dosya_adi, dosya, alinti, kaynak, ozet))
        c.commit()
        c.close()


def _jid(j):
    return f"{j.User}@{j.Server}" if j.User else ""


def gruplari_yukle(client):
    global KURALLAR                                  # ayarlar.json'a yeni onaylanan grup eklendiyse yeniden başlatmadan dinlensin
    KURALLAR = json.loads(AYAR.read_text(encoding="utf-8")).get("whatsapp", {})
    gruplar = list(client.get_joined_groups())
    SECILI.clear()
    for g in gruplar:
        GRUP_ADI[_jid(g.JID)] = g.GroupName.Name
    liste = []
    for g in gruplar:
        j = _jid(g.JID)
        ust = _jid(g.GroupLinkedParent.LinkedParentJID) if g.HasField("GroupLinkedParent") else ""
        if ust and ust not in GRUP_ADI:
            try:
                GRUP_ADI[ust] = client.get_group_info(g.GroupLinkedParent.LinkedParentJID).GroupName.Name
            except Exception:
                pass
        TOPLULUK[j] = GRUP_ADI.get(ust, "")
        topluluk_mu = g.HasField("GroupParent") and g.GroupParent.IsParent
        sec = (not topluluk_mu) and secili_mi(g.GroupName.Name, TOPLULUK[j])
        if sec:
            SECILI.add(j)
        liste.append({"jid": j, "ad": g.GroupName.Name, "topluluk": TOPLULUK[j],
                      "toplulukAnaGrubu": bool(topluluk_mu), "uye": len(g.Participants), "dinleniyor": sec})
    liste.sort(key=lambda x: (not x["dinleniyor"], x["topluluk"], x["ad"]))
    (WA / "gruplar.json").write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    return liste


def drive_tasi():
    """Drive klasörü varsa PC'deki eski indirmeleri oraya taşır (PC'de kalmasın), DB yollarını günceller."""
    yerel = WA / "dosyalar"
    if not DRIVE or not yerel.is_dir():
        return
    import shutil
    c = db()
    n = 0
    for f in sorted(yerel.rglob("*")):
        if not f.is_file():
            continue
        hedef = DRIVE / f.parent.name / f.name
        hedef.parent.mkdir(parents=True, exist_ok=True)
        if not hedef.exists():
            shutil.move(str(f), str(hedef))
        else:
            f.unlink()
        for eski in (str(f.relative_to(KOK)), str(f.relative_to(KOK)).replace("\\", "/")):
            c.execute("UPDATE mesajlar SET dosya=? WHERE dosya=?", (str(hedef), eski))
        n += 1
    c.commit()
    c.close()
    if n:
        log(f"{n} dosya Google Drive'a taşındı: {DRIVE}")


def main():
    sadece_liste = "--gruplar" in sys.argv
    import os
    drive_kurulu = (Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google" / "Drive File Stream").exists()
    for _ in range(36 if drive_kurulu and not sadece_liste else 0):   # açılışta Drive'ın bağlanmasını 3 dk bekle
        if dosya_kok() != DOSYALAR:
            break
        time.sleep(5)
    drive_tasi()
    log("dosya klasörü:", dosya_kok())
    client = kilitle(NewClient(str(WA / "oturum.sqlite3")))
    hazir = threading.Event()

    @client.qr
    def _qr(_, veri):
        segno.make_qr(veri).save(str(WA / "qr.png"), scale=10, border=3)
        durum_yaz(bagli=False, qrBekliyor=True)
        log("QR hazir -> veri/whatsapp/qr.png  (Telefon: Ayarlar > Bagli cihazlar > Cihaz bagla)")

    @client.event(PairStatusEv)
    def _eslesme(_, ev):
        log("eslesti:", ev.ID.User if ev.ID else "")
        (WA / "qr.png").unlink(missing_ok=True)

    @client.event(ConnectedEv)
    def _baglandi(c, __):
        liste = gruplari_yukle(c)
        secilen = [g for g in liste if g["dinleniyor"]]
        log(f"baglandi. {len(liste)} grup, {len(secilen)} tanesi dinleniyor:")
        for g in secilen:
            log("   -", (g["topluluk"] + " / " if g["topluluk"] else "") + g["ad"])
        durum_yaz(bagli=True, qrBekliyor=False, dinlenen=len(secilen),
                  sonBaglanti=datetime.now().isoformat(timespec="seconds"))
        hazir.set()

    def _yenile():                                   # yeni katılınan grupları gruplar.json'a yazar (panel "dinleyeyim mi?" diye sorar)
        while True:
            time.sleep(1800)
            try:
                if client.is_connected():
                    gruplari_yukle(client)
            except Exception as e:
                log("grup listesi yenilenemedi:", type(e).__name__)

    if not sadece_liste:
        threading.Thread(target=_yenile, daemon=True).start()

    @client.event(MessageEv)
    def _mesaj(c, ev):
        src = ev.Info.MessageSource
        if not src.IsGroup:
            return
        try:
            kaydet(c, _jid(src.Chat), "", ev.Info.Pushname, src.IsFromMe,
                   ev.Info.Timestamp // (1000 if ev.Info.Timestamp > 10**11 else 1),
                   ev.Info.ID, ev.Message, "canli")
            durum_yaz(sonMesaj=datetime.now().isoformat(timespec="seconds"))
        except Exception as e:
            log("mesaj islenemedi:", type(e).__name__, e)

    @client.event(HistorySyncEv)
    def _gecmis(c, ev):
        hazir.wait(60)
        n = 0
        for konusma in ev.Data.conversations:
            if konusma.ID not in SECILI:
                continue
            for hm in konusma.messages:
                w = hm.message
                if not w.HasField("message"):
                    continue
                try:
                    kaydet(c, konusma.ID, "", w.pushName,
                           w.key.fromMe, int(w.messageTimestamp), w.key.ID, w.message, "gecmis")
                    n += 1
                except Exception as e:
                    log("gecmis mesaj islenemedi:", type(e).__name__)
        if n:
            log(f"gecmisten {n} mesaj islendi")

    @client.event(LoggedOutEv)
    def _cikis(_, __):
        durum_yaz(bagli=False, cikisYapildi=True)
        log("Telefondan cihaz baglantisi kaldirildi. Yeniden QR gerekecek.")

    @client.event(DisconnectedEv)
    def _koptu(_, __):
        durum_yaz(bagli=False)
        log("baglanti koptu (otomatik yeniden denenecek)")

    if sadece_liste:
        def _bitir():
            if hazir.wait(300):
                time.sleep(2)
                client.disconnect()
        threading.Thread(target=_bitir, daemon=True).start()

    client.connect()


if __name__ == "__main__":
    main()
