# Google Drive (isteğe bağlı, önerilir)

Bilgisayarda **Google Drive for Desktop** kuruluysa her şey Drive'ındaki **`İTÜ`** klasörüne gider ve telefondan da açılır:

| Ne | Nerede |
| --- | --- |
| Ders dosyaları (Ninova sınıf/ders dosyaları, ödev ekleri, Moodle) | `İTÜ/Dersler/<DERS KODU>/{Slaytlar, Recitation-Problem Session, Ödevler, Sınavlar, Syllabus, Diğer}/` |
| WhatsApp ders gruplarından inen belgeler | `İTÜ/Dersler/<DERS KODU>/Diğer/` (dersle eşleşmeyen `İTÜ/Genel/`) |
| Panelin düz metin özeti | `İTÜ/İTÜ Asistan.txt` |
| Grup mesajları + e-postaların dökümü | `İTÜ/İTÜ Asistan - ham kayıtlar.md` |

- Daha önce inen dosya tekrar inmez; Ninova'da güncellenen dosyanın eskisi "(eski)" adıyla kalır. **Hiçbir şey silinmez.**
- 100 MB üstü dosyalar ve YouTube bağlantıları inmez, sadece panelde listelenir.
- Drive yoksa ders dosyaları bilgisayarda `veri\dersler\` klasörüne iner (telefondan açılmaz).
- Panelde derse dokununca o dersin dosyaları Drive linkleriyle görünür.

**Telefonda yapay zekâya sormak:** Gemini uygulamasında **+ → Drive → İTÜ → İTÜ Asistan.txt** ekle, sonra
"yarın ne var?", "fizik vizesi hangi konular?" diye sor. Bilgisayar kapalıyken de çalışır; dosya son güncellemedeki hâliyle durur.

## Kurulum

1. **Google Drive for Desktop**'u kur. Gemini çalıştırabilir:
   ```powershell
   winget install -e --id Google.GoogleDrive --accept-source-agreements --accept-package-agreements
   ```
   (winget yoksa: https://www.google.com/drive/download/ → indir, kur.)
2. Açılan pencerede **Google hesabınla giriş yap** (bunu kullanıcı kendisi yapar). Drive, Bilgisayarım'da `G:` gibi bir
   sürücü olarak görünür ("Drive'ım" / "My Drive" klasörü).
3. Sonra:
   ```powershell
   .\.venv\Scripts\python.exe src\kurulum.py --drive
   .\.venv\Scripts\python.exe src\kurulum.py --dosyalar
   ```
   İlki `TAMAM: Drive klasörü: G:\My Drive` demeli; ikincisi ders dosyalarını arka planda indirmeye başlar.

Drive farklı bir yerdeyse `src/ayarlar.json`'a `"driveKlasoru": "D:\\Drive'ım"` gibi elle ekle.

> Not: `İTÜ Asistan` dosyalarında ders grubu mesajlarının kısa hâlleri de bulunur; `İTÜ` klasörünü kimseyle paylaşma.
