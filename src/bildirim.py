"""
Telefona bildirim (ntfy). Kanal adı veri/bildirim.json'da (git'e girmez; adı bilen dinleyebilir, o yüzden
bildirimlere kişisel veri — not, numara, isim — yazılmaz, sadece kısa hatırlatma).

    python bildirim.py --deneme       # deneme bildirimi
    python bildirim.py --aksam        # yarınki sınav/lab/son başvuru hatırlatması (21:00, Windows görevi)
    python bildirim.py --yeni         # yeni önemli notlar (gorev.py --panel sonrası)
"""
import datetime as dt
import json
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
VERI = HERE.parent / "veri"
AYAR = VERI / "bildirim.json"
GONDERILEN = VERI / "bildirim_gonderilen.json"
PANEL = None                     # bildirime tıklayınca açılacak link yok (panel bu bilgisayarda)
GUN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def ayar():
    return json.loads(AYAR.read_text(encoding="utf-8")) if AYAR.exists() else {}


def gonder(baslik, metin, oncelik=3, etiket="bell", tikla=None):
    """oncelik: 1 en sessiz … 5 acil. Kanal ayarlı değilse sessizce geçer."""
    a = ayar()
    if tikla is None:
        tikla = a.get("panel") or ""           # veri/bildirim.json -> "panel": telefondan açılan panel linki (varsa)
    if not a.get("kanal") or (VERI / "otomasyon_kapali").exists() and oncelik < 5:
        return False
    r = requests.post(f"{a.get('sunucu', 'https://ntfy.sh')}/{a['kanal']}", data=metin.encode("utf-8"), timeout=20,
                      headers={"Title": baslik.encode("utf-8"), "Priority": str(oncelik), "Tags": etiket,
                               "Click": tikla})
    r.raise_for_status()
    return True


def _gonderildi():
    return set(json.loads(GONDERILEN.read_text(encoding="utf-8"))) if GONDERILEN.exists() else set()


def _kaydet(s):
    GONDERILEN.write_text(json.dumps(sorted(s)[-500:], ensure_ascii=False), encoding="utf-8")


def _t(s):
    try:
        return dt.datetime.fromisoformat(str(s)[:16])
    except ValueError:
        return None


def yarin_olaylari():
    """Yarına düşen: WhatsApp/Ninova'dan çıkarılan olaylar, Ninova sınav tarihleri, final, önemli tarihler."""
    yarin = dt.date.today() + dt.timedelta(days=1)
    d = json.loads((VERI / "panel.json").read_text(encoding="utf-8"))
    wa = VERI / "whatsapp" / "notlar.json"
    notlar = json.loads(wa.read_text(encoding="utf-8")) if wa.exists() else {}
    gizle = json.loads((HERE / "ayarlar.json").read_text(encoding="utf-8")).get("takvimGizle", [])
    out = []
    for o in notlar.get("olaylar", []):
        t = _t(o.get("bas"))
        if t and t.date() == yarin:
            out.append(f"{t:%H:%M} {o.get('ders', '')} {o.get('tur', '')}".strip()
                       + (f" — {o['konu']}" if o.get("konu") else "") + (f" · {o['yer']}" if o.get("yer") and o["yer"].split(" (")[0] not in o.get("konu", "") else ""))
    n = d.get("ninova") or {}
    for x in n.get("sinavTarihleri", []):
        if x.get("tarih") == yarin.isoformat():
            out.append(f"{x.get('saat') or ''} {(x.get('ders') or '').split(' - ')[0]} {x.get('tur')} (Ninova duyurusu)".strip())
    for x in (d.get("obs") or {}).get("finalTakvimim") or []:
        t = _t(x.get("tarih") or x.get("sinavTarihi"))
        if t and t.date() == yarin:
            out.append(f"{t:%H:%M} {x.get('dersKodu') or x.get('ders')} FİNAL")
    for x in (d.get("onemliTarihler") or []) + (d.get("akademikTakvim") or []):
        if "Lisans / Önlisans" not in x.get("tablo", "Lisans / Önlisans") or x.get("tur") == "idari" \
                or any(g in x.get("olay", "") for g in gizle):
            continue
        b, s = _t(x.get("bas")), _t(x.get("bit"))
        if (b and b.date() == yarin) or (s and s.date() == yarin and x.get("tur") in ("başvuru", "kayıt")):
            out.append(("SON GÜN: " if s and s.date() == yarin and b and b.date() != yarin else "") + x["olay"])
    return list(dict.fromkeys(out))


def aksam():
    olaylar = yarin_olaylari()
    if not olaylar:
        return print("yarın için hatırlatılacak bir şey yok")
    yarin = dt.date.today() + dt.timedelta(days=1)
    gonder(f"Yarın ({GUN[yarin.weekday()]}) unutma", "\n".join("• " + o for o in olaylar[:6]), oncelik=4, etiket="alarm_clock")
    print(len(olaylar), "olay bildirildi")


def yeni_notlar():
    """Değerlendirmeden sonra: daha önce bildirilmemiş onem 1 notlar (ilk çalışmada sadece kaydeder)."""
    wa = VERI / "whatsapp" / "notlar.json"
    if not wa.exists():
        return
    notlar = json.loads(wa.read_text(encoding="utf-8")).get("notlar", [])
    ilk = not GONDERILEN.exists()
    eski = _gonderildi()
    yeni = [n for n in notlar if (n.get("onem") or 3) == 1 and f"not:{n['id']}:{n.get('tarih')}" not in eski]
    if yeni and not ilk:
        if len(yeni) == 1:
            n = yeni[0]
            gonder(n["baslik"][:120], n["metin"][:300] + ("" if n.get("teyit") != "yok" else "\n(öğrenci söylentisi)"),
                   oncelik=4, etiket="loudspeaker")
        else:
            gonder(f"{len(yeni)} önemli yeni not", "\n".join("• " + n["baslik"][:90] for n in yeni[:6]),
                   oncelik=4, etiket="loudspeaker")
    _kaydet(eski | {f"not:{n['id']}:{n.get('tarih')}" for n in notlar if (n.get("onem") or 3) == 1})
    print(len(yeni), "yeni önemli not" + (" (ilk çalışma: sadece kaydedildi)" if ilk else ""))


if __name__ == "__main__":
    if sys.stdout:                                 # pythonw (Windows görevi) altında stdout yok
        sys.stdout.reconfigure(encoding="utf-8")
    else:
        sys.stdout = sys.stderr = open(VERI / "bildirim.log", "a", encoding="utf-8")
    if "--deneme" in sys.argv:
        print("gönderildi" if gonder("İTÜ bildirimleri çalışıyor ✓", "Yarınki lab, sınav ve önemli notlar buraya gelecek. "
                                     "Dokununca panel açılır.", etiket="tada") else "kanal ayarlı değil")
    elif "--aksam" in sys.argv:
        aksam()
    elif "--yeni" in sys.argv:
        yeni_notlar()
