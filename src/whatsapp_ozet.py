"""
WhatsApp mesajlarından değerlendirilmeye aday olanları kısa satırlar halinde çıkarır.
Gürültüyü (selam, emoji, kısa sohbet) anahtar kelime + uzunluk kuralıyla eler;
asıl değerlendirmeyi (önemli mi, doğru mu) yapay zekâ (Gemini) yapar ve veri/whatsapp/notlar.json'a yazar.

    python whatsapp_ozet.py              # değerlendirilmemiş adaylar
    python whatsapp_ozet.py --isaretle   # değerlendirilmemiş HER mesajı değerlendirildi say
    python whatsapp_ozet.py --sayi       # sadece kaç aday var

Gönderen adı/numarası çıktıya hiç yazılmaz.
"""
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "veri" / "whatsapp" / "mesajlar.db"

ANAHTAR = re.compile(
    r"sınav|sinav|quiz|kuiz|vize|final|midterm|exam|ödev|odev|homework|\bhw\b|assignment|teslim|deadline|"
    r"\blab\b|lab |rapor|report|duyuru|announce|hoca|prof|ninova|obs|kayıt|kayit|ekle.?bırak|drop|"
    r"harç|harc|katkı payı|burs|yurt|iptal|ertele|cancel|postpone|değişt|degist|tarih|saat \d|"
    r"\d{1,2}[:.]\d{2}|\d{1,2} (ekim|kasım|aralık|ocak|şubat|eylül)|derslik|amfi|sınıf değ|"
    r"drive\.google|docs\.google|forms\.|chat\.whatsapp|t\.me/|discord|teams|zoom|pdf|slayt|slide|"
    r"çıkmış|cikmis|cevap anahtar|solution|çözüm|syllabus|izlence|yoklama|attendance|devamsızlık|"
    r"online|uzaktan|erasmus|staj|internship|başvuru|basvuru|son gün|son tarih|kontenjan|crn|şube|"
    r"kitap|textbook|not(lar)? açıkland|grade|ortalama|bütünleme|mazeret|muaf|proficiency|ydy|"
    r"kyk|gsb|kredi|dilekçe|dilekce|yemekhane|\bring\b|moodle|pearson|giriş yapam|giremiyor|açılmıyor|sorun|problem|"
    r"aksaklık|kesinti|arıza|ödeme|depozito|rektörlük|öğrenci işleri|sks",
    re.I)
def _ders_grubu_deseni():
    try:
        d = json.loads((Path(__file__).resolve().parent / "ayarlar.json").read_text(encoding="utf-8"))
        return (d.get("whatsapp") or {}).get("dersGrubuDeseni") or "FIZ|MAT|KIM|EHB|ELE|EEF|BLG|havuz"
    except (OSError, ValueError):
        return "FIZ|MAT|KIM|EHB|ELE|EEF|BLG|havuz"


DERS_GRUBU = re.compile(_ders_grubu_deseni(), re.I)


def aday_mi(r):
    tur, metin, grup, alinti = r["tur"], (r["metin"] or "").strip(), r["grup_adi"], r["alinti"] or ""
    if tur in ("belge", "anket"):
        return True
    if not metin:
        return False
    if ANAHTAR.search(metin) and len(metin) >= 15:
        return True
    if re.search(r"https?://", metin) and not re.search(r"instagram|tiktok|youtu|x\.com|twitter", metin, re.I):
        return True
    if DERS_GRUBU.search(grup) and len(metin) >= 60:
        return True
    return len(metin) >= 220                      # uzun açıklama mesajları


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    if "--isaretle" in sys.argv:
        n = c.execute("UPDATE mesajlar SET degerlendirildi=1 WHERE degerlendirildi=0").rowcount
        c.commit()
        print(n, "mesaj değerlendirildi olarak işaretlendi")
        return
    satirlar = c.execute("SELECT rowid, * FROM mesajlar WHERE degerlendirildi=0 AND benden=0 "
                         "ORDER BY grup_adi, zaman").fetchall()
    adaylar = [r for r in satirlar if aday_mi(r)]
    if "--sayi" in sys.argv:
        print(f"{len(satirlar)} değerlendirilmemiş mesaj, {len(adaylar)} aday")
        return
    grup = None
    for r in adaylar:
        if r["grup_adi"] != grup:
            grup = r["grup_adi"]
            print(f"\n## {grup}" + (f"  ({r['topluluk']})" if r["topluluk"] else ""))
        metin = re.sub(r"\s+", " ", (r["metin"] or "").strip())[:400]
        ek = f" [{r['tur']}: {r['dosya_adi'] or ''}{' -> indirildi' if r['dosya'] else ' -> inmedi'}]" \
            if r["tur"] in ("belge", "foto", "video") else ""
        alinti = f" (yanıt: «{re.sub(chr(10), ' ', r['alinti'])[:80]}»)" if r["alinti"] else ""
        print(f"{r['rowid']}|{datetime.fromtimestamp(r['zaman']):%d.%m %H:%M}|{metin}{ek}{alinti}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
