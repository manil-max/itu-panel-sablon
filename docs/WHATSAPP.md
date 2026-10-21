# WhatsApp ders grupları (isteğe bağlı)

Bilgisayar, WhatsApp Web gibi telefonuna **bağlı cihaz** olarak eklenir. Sadece seçtiğin grupların mesajlarını
**okur**; belge/PDF'leri indirir (Google Drive kuruluysa Drive'a). **Hiçbir zaman mesaj göndermez**, okundu yapmaz,
"çevrimiçi" görünmez (bu özellikler kodda kapatılmış). Mesajlar sadece bu bilgisayarda kalır.

Mesajların kendisi panele girmez. Gemini'ye "değerlendir" deyince önemli olanlar (sınav, ödev, derslik değişikliği...)
not olarak panele eklenir (`docs/DEGERLENDIRME.md`).

> Bilmen gereken: WhatsApp resmi olmayan bağlı cihazları nadiren de olsa engelleyebilir. Sadece okuduğu için risk
> düşüktür ama sıfır değildir. İstemezsen kurma, panelin geri kalanı aynen çalışır.

## Kurulum (Gemini adım adım yaptırır)

1. Gemini şunu çalıştırır (yeni pencere açılır, kullanıcı orada cevap verir):
   ```powershell
   Start-Process -FilePath ".\kur.bat" -ArgumentList "--whatsapp" -WorkingDirectory (Get-Location)
   ```
2. İlk seferde WhatsApp paketi kurulur (1-2 dakika).
3. Tarayıcıda bir QR sayfası açılır. **Telefonda: WhatsApp > Ayarlar > Bağlı cihazlar > Cihaz bağla** ve QR'ı okut.
   QR 20 saniyede bir kendiliğinden yenilenir; sayfa da kendini yeniler. 5 dakika içinde okutmak lazım.
4. Bağlanınca pencerede gruplarının numaralı listesi çıkar. **Sadece ders/bölüm/sınıf gruplarının** numaralarını yaz
   (örn. `1,3,5-8`). Arkadaş/aile sohbetlerini seçme.
5. Bitti. Köprü arka planda çalışır ve bilgisayar her açıldığında kendiliğinden başlar (Windows görevi `ITUPanel-whatsapp`).

Grup listesini sonradan değiştirmek için:
```powershell
.\.venv\Scripts\python.exe src\kurulum.py --whatsapp-liste
.\.venv\Scripts\python.exe src\kurulum.py --whatsapp-sec 1,3,5-8
```
(Gemini listeyi kullanıcıya gösterir, numaraları sorar, ikinci komutu çalıştırır.)

## Ayarlar (`src/ayarlar.json` → `whatsapp`)

- `gruplar`: okunan grupların adları (birebir). Kurulum doldurur.
- `dersGrubuDeseni`: grup adında bunlardan biri geçerse "ders grubu" sayılır; oradan foto/video da iner, mesajlar
  değerlendirmeye daha kolay girer. Varsayılan `FIZ|MAT|KIM|EHB|ELE|EEF|BLG|havuz`. Kendi ders kodlarını ekleyebilirsin.

## Sorun giderme

| Belirti | Çözüm |
| --- | --- |
| QR sayfası açılmadı | `veri\whatsapp\qr.html` dosyasını tarayıcıda aç |
| "Süre doldu" | Tekrar `kur.bat --whatsapp`; QR'ı 5 dakika içinde okut |
| Telefonda bağlı cihazı kaldırdım | Yeniden QR gerekir: `kur.bat --whatsapp` |
| Yeni mesaj gelmiyor | `veri\whatsapp\kopru.log` son satırlarına bak; `otomasyon.bat` kapalı mı? Görev Zamanlayıcı'da `ITUPanel-whatsapp` çalışıyor mu? |
| neonize kurulamadı | `.\.venv\Scripts\python.exe -m pip install neonize` hatasını oku; Python 3.10+ gerekli |
| "ffmpeg not found" uyarısı | Önemsiz; sadece sesli mesaj/çıkartma işlenmez. Belgeler yine iner. |

WhatsApp'ı tamamen kaldırmak: telefonda Bağlı cihazlar'dan bu bilgisayarı çıkar, `veri\whatsapp` klasörünü sil,
Görev Zamanlayıcı'dan `ITUPanel-whatsapp`'ı sil.
