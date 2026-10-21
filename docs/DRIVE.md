# Google Drive (isteğe bağlı)

Drive kuruluysa iki şey kendiliğinden olur:

1. Panelin düz metin özeti her güncellemede **`Drive'ım/İTÜ Asistan.txt`** dosyasına yazılır.
   Telefonda **Gemini** uygulamasında **+ → Drive → İTÜ Asistan.txt** ekleyip "yarın ne var?", "fizik quiz ne zaman?"
   gibi sorular sorabilirsin. (Bilgisayar kapalıyken de çalışır; dosya son güncellemedeki hâliyle durur.)
2. WhatsApp gruplarından inen belgeler **`Drive'ım/İTÜ WhatsApp Dosyaları/<grup>/`** klasörüne gider; panelde
   tıklayınca telefonda Drive'da açılır.

## Kurulum

1. **Google Drive for Desktop**'u kur. Gemini çalıştırabilir:
   ```powershell
   winget install -e --id Google.GoogleDrive --accept-source-agreements --accept-package-agreements
   ```
   (winget yoksa: https://www.google.com/drive/download/ → indir, kur.)
2. Kurulum bitince açılan pencerede **Google hesabınla giriş yap** (bunu kullanıcı kendisi yapar).
   Drive, Bilgisayarım'da `G:` gibi bir sürücü olarak görünür ("Drive'ım" / "My Drive" klasörü).
3. Sonra:
   ```powershell
   .\.venv\Scripts\python.exe src\kurulum.py --drive
   ```
   `TAMAM: Drive klasörü: G:\My Drive` görmelisin. Görmezsen Drive'ın açılıp giriş yaptığından emin ol.

Drive farklı bir yerdeyse `src/ayarlar.json`'a `"driveKlasoru": "D:\\Drive'ım"` gibi elle ekle.

> Not: İTÜ Asistan dosyasında ders grubu mesajlarının kısa hâlleri de bulunur; Drive'ını kimseyle paylaşma.
