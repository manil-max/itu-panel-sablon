"""
İTÜ e-postasını (mail.itu.edu.tr, IMAP) SADECE OKUR: klasör salt-okunur açılır, mailler BODY.PEEK ile
alınır (okundu işaretlenmez); hiçbir şey gönderilmez, taşınmaz, silinmez.
Giriş bilgisi .env'deki ITU_KULLANICI / ITU_SIFRE. Giriş reddedilirse TEKRAR DENEMEZ.

    python eposta.py            # son 30 günün gelen kutusunu veri/eposta/epostalar.db'ye çeker
    python eposta.py --test     # sadece giriş + kaç mail var
"""
import datetime as dt
import email
import email.header
import email.utils
import html
import imaplib
import re
import sqlite3
import sys
from pathlib import Path

import itu

KOK = Path(__file__).resolve().parent.parent
KLASOR = KOK / "veri" / "eposta"
DB = KLASOR / "epostalar.db"
SUNUCU = "mail.itu.edu.tr"


class EpostaHatasi(Exception):
    pass


def _coz(s):
    if not s:
        return ""
    out = []
    for parca, kod in email.header.decode_header(s):
        if isinstance(parca, bytes):
            try:
                out.append(parca.decode(kod or "utf-8", errors="replace"))
            except LookupError:
                out.append(parca.decode("utf-8", errors="replace"))
        else:
            out.append(parca)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _govde(msg):
    duz, html_ = "", ""
    ekler = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ad = part.get_filename()
        if ad or part.get_content_disposition() == "attachment":
            ekler.append(_coz(ad or "ek"))
            continue
        tip = part.get_content_type()
        try:
            yuk = part.get_payload(decode=True) or b""
            metin = yuk.decode(part.get_content_charset() or "utf-8", errors="replace")
        except (LookupError, AssertionError):
            continue
        if tip == "text/plain" and not duz:
            duz = metin
        elif tip == "text/html" and not html_:
            html_ = metin
    if not duz and html_:
        duz = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_)
        duz = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", duz)
        duz = html.unescape(re.sub(r"<[^>]+>", " ", duz))
    duz = re.sub(r"[ \t ]+", " ", duz)
    duz = re.sub(r"\n\s*\n+", "\n", duz).strip()
    return duz, ekler


def baglan():
    env = itu.env_oku()
    kul = (env.get("ITU_KULLANICI") or "").split("@")[0]
    sifre = env.get("ITU_SIFRE") or ""
    if not kul or not sifre:
        raise EpostaHatasi("ITU_KULLANICI / ITU_SIFRE .env'de yok")
    m = imaplib.IMAP4_SSL(SUNUCU, 993, timeout=60)
    try:
        m.login(kul, sifre)
    except imaplib.IMAP4.error as e:
        raise EpostaHatasi(f"E-posta girişi reddedildi ({e}) — TEKRAR DENENMEDİ (hesap kilitlenmesin)")
    return m


def db():
    KLASOR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS epostalar(
        mid TEXT PRIMARY KEY, uid INTEGER, tarih TEXT, kimden TEXT, kime TEXT, konu TEXT,
        metin TEXT, ekler TEXT, degerlendirildi INTEGER DEFAULT 0)""")
    return c


def cek(gun=30, log=print):
    m = baglan()
    try:
        tip, _ = m.select("INBOX", readonly=True)
        if tip != "OK":
            raise EpostaHatasi("Gelen kutusu açılamadı")
        tarih = (dt.date.today() - dt.timedelta(days=gun)).strftime("%d-%b-%Y")
        tip, veri = m.uid("SEARCH", None, f"SINCE {tarih}")
        uidler = (veri[0] or b"").split()
        c = db()
        var = {r[0] for r in c.execute("SELECT uid FROM epostalar")}
        yeni = 0
        for uid in uidler:
            if int(uid) in var:
                continue
            tip, parca = m.uid("FETCH", uid, "(BODY.PEEK[])")
            if tip != "OK" or not parca or not isinstance(parca[0], tuple):
                continue
            msg = email.message_from_bytes(parca[0][1])
            metin, ekler = _govde(msg)
            try:
                t = email.utils.parsedate_to_datetime(msg.get("Date")).astimezone().isoformat(timespec="minutes")
            except (TypeError, ValueError):
                t = ""
            mid = msg.get("Message-ID") or f"uid-{uid.decode()}"
            c.execute("INSERT OR IGNORE INTO epostalar(mid,uid,tarih,kimden,kime,konu,metin,ekler) VALUES(?,?,?,?,?,?,?,?)",
                      (mid, int(uid), t, _coz(msg.get("From")), _coz(msg.get("To"))[:200], _coz(msg.get("Subject")),
                       metin[:8000], ", ".join(ekler)))
            yeni += 1
        c.commit()
        c.close()
        log(f"  e-posta: {len(uidler)} mail (son {gun} gün), {yeni} yeni")
        return yeni
    finally:
        try:
            m.logout()
        except Exception:
            pass


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--test" in sys.argv:
        m = baglan()
        tip, veri = m.select("INBOX", readonly=True)
        print("Giriş başarılı. Gelen kutusunda", veri[0].decode(), "mail var.")
        m.logout()
    else:
        cek()
