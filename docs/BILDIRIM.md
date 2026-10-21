# Telefona bildirim (isteğe bağlı, ücretsiz)

Her akşam 21:00'de "yarın şu sınav/lab/son başvuru var" hatırlatması ve değerlendirmeden sonra yeni önemli notlar
telefonuna bildirim olarak gelir. Bunun için **ntfy** adlı ücretsiz uygulama kullanılır. Hesap açmak gerekmez.

## Kurulum

1. Gemini şunu çalıştırır (yeni pencere açılır):
   ```powershell
   Start-Process -FilePath ".\kur.bat" -ArgumentList "--bildirim" -WorkingDirectory (Get-Location)
   ```
2. Telefona **ntfy** uygulamasını kur (Play Store / App Store).
3. Pencerede yazan **kanal adını** (örn. `itu-3f9a1c2b7d4e`) uygulamada **+ → Subscribe to topic** ile ekle.
   Ya da bilgisayarda açılan QR resmini telefonun kamerasıyla okut.
4. Pencerede Enter'a bas → telefona deneme bildirimi gelir.

Kanal adı rastgeledir; kimseyle paylaşma (bilen bildirimleri görebilir). Bu yüzden bildirimlere not, isim, numara
yazılmaz; sadece kısa hatırlatma ("Yarın FIZ 101E Quiz 3, 14:30").

Kanal ayarı: `veri/bildirim.json`. Kapatmak: bu dosyayı sil, Görev Zamanlayıcı'dan `ITUPanel-hatirlatma`'yı sil.
Deneme bildirimi: `.\.venv\Scripts\python.exe src\bildirim.py --deneme`
