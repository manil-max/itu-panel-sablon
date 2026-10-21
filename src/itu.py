"""
İTÜ tek oturum açma (girisv3.itu.edu.tr) ile giriş yapıp OBS, Ninova, Portal gibi
uygulamalara oturum açmış bir requests.Session döndürür.

Kullanıcı adı/şifre SADECE .env dosyasından okunur (ITU_KULLANICI, ITU_SIFRE).
Şifre hiçbir yere yazdırılmaz, loglanmaz, repoya girmez (.env gitignore'da).
Hatalı şifreyle tekrar tekrar denemez: hesap kilitlenmesin diye ilk hatada durur.
"""
import os
import re
import html
from pathlib import Path
from urllib.parse import urljoin

import requests

GIRIS = "https://girisv3.itu.edu.tr"
KOK = Path(__file__).resolve().parent.parent                 # depo kökü (.env burada)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


class GirisHatasi(Exception):
    pass


def env_oku(dosya=None):
    """.env dosyasını okur (KEY=değer). Dosya yoksa boş sözlük."""
    yol = Path(dosya) if dosya else (KOK / ".env")
    d = {}
    if yol.exists():
        for satir in yol.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            k, v = satir.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():                          # ortam değişkeni .env'i ezer
        if k.startswith("ITU_"):
            d[k] = v
    return d


def _gizli_alanlar(sayfa):
    return {ad: html.unescape(deger) for ad, deger in
            re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', sayfa)}


def _form_gonder(s, sayfa, url):
    """Sayfadaki otomatik gönderilen formu (SSO geri dönüşü) gönderir. Form yoksa None."""
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', sayfa, re.S | re.I)
    if not m:
        return None
    hedef = urljoin(url, html.unescape(m.group(1)))
    alanlar = {ad: html.unescape(deger) for ad, deger in
               re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', m.group(2))}
    if not alanlar:
        return None
    return s.post(hedef, data=alanlar, timeout=60)


def oturum(hedef_url, kullanici=None, sifre=None, env=None):
    """hedef_url: giriş sonrası varılacak İTÜ uygulaması (ör. https://obs.itu.edu.tr/ogrenci).
    Giriş yapmış requests.Session döndürür."""
    env = env if env is not None else env_oku()
    kullanici = kullanici or env.get("ITU_KULLANICI", "")
    sifre = sifre or env.get("ITU_SIFRE", "")
    if not kullanici or not sifre:
        raise GirisHatasi("ITU_KULLANICI / ITU_SIFRE .env dosyasında yok. .env.ornek dosyasına bak.")

    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.get(hedef_url, timeout=60)
    if GIRIS not in str(r.url):                              # zaten oturum varsa
        return s, r

    alanlar = _gizli_alanlar(r.text)
    m = re.search(r'<form[^>]*action="([^"]+)"', r.text)
    hedef = urljoin(str(r.url), html.unescape(m.group(1))) if m else str(r.url)
    alanlar.update({
        "ctl00$ContentPlaceHolder1$tbUserName": kullanici,
        "ctl00$ContentPlaceHolder1$tbPassword": sifre,
        "ctl00$ContentPlaceHolder1$btnLogin": "Giriş / Login",
    })
    r = s.post(hedef, data=alanlar, timeout=60)

    for _ in range(4):                                       # SSO geri dönüş formlarını takip et
        if GIRIS not in str(r.url):
            break
        metin = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", r.text)))
        for kalip in ("Kullanıcı adı veya şifre hatalı", "hatalı", "kilitlen", "geçersiz", "invalid", "incorrect"):
            if kalip.lower() in metin.lower() and "Şifremi Unuttum" in r.text:
                parca = re.search(r"([^.]{0,120}(?:hatalı|kilitlen|geçersiz|invalid|incorrect)[^.]{0,80})", metin, re.I)
                raise GirisHatasi("Giriş reddedildi: " + (parca.group(1).strip() if parca else "kullanıcı adı/şifre kontrol et")
                                  + " — TEKRAR DENENMEDİ (hesap kilitlenmesin diye).")
        yeni = _form_gonder(s, r.text, str(r.url))
        if yeni is None:
            break
        r = yeni
    if GIRIS in str(r.url):
        raise GirisHatasi(f"Giriş tamamlanamadı, hâlâ giriş sayfasındayız: {str(r.url)[:120]}")
    return s, r


def obs_token(s):
    """OBS öğrenci arayüzünün kullandığı Bearer token'ı oturumdan alır."""
    for yol in ("https://obs.itu.edu.tr/ogrenci/auth/jwt", "https://obs.itu.edu.tr/api/jwt",
                "https://obs.itu.edu.tr/ogrenci/jwt", "https://obs.itu.edu.tr/auth/jwt"):
        try:
            r = s.get(yol, timeout=30)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        t = r.text.strip().strip('"')
        if t.count(".") == 2 and t.startswith("ey"):
            return "Bearer " + t
        try:
            j = r.json()
            for anahtar in ("token", "jwt", "access_token", "accessToken"):
                v = j.get(anahtar) if isinstance(j, dict) else None
                if isinstance(v, str) and v.count(".") == 2:
                    return "Bearer " + v
        except ValueError:
            pass
    return None
