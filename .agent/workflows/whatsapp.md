---
description: WhatsApp ders gruplarını panele bağla (sadece okur)
---

1. `docs/WHATSAPP.md` dosyasını oku. Kullanıcıya ilk paragraftaki "Bilmen gereken" notunu söyle ve devam etmek isteyip istemediğini sor.
2. Evet derse: `Start-Process -FilePath ".\kur.bat" -ArgumentList "--whatsapp" -WorkingDirectory (Get-Location)`
3. Kullanıcıya söyle: "Tarayıcıda açılan QR'ı telefonda WhatsApp > Ayarlar > Bağlı cihazlar > Cihaz bağla ile okut. Sonra siyah pencerede sadece ders gruplarının numaralarını yaz."
4. Kullanıcı bitti deyince: `.\.venv\Scripts\python.exe src\kurulum.py --durum` → `"whatsapp"` altında `"seciliGrup"` 0'dan büyük olmalı.
