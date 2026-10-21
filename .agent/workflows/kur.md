---
description: İTÜ panelini bu bilgisayara kur (ilk kurulum ya da onarım)
---

1. `GEMINI.md` dosyasındaki "Kurulum" bölümünü oku.
2. Proje klasöründe kurulum penceresini aç:
   `Start-Process -FilePath ".\kur.bat" -WorkingDirectory (Get-Location)`
3. Kullanıcıya söyle: "Açılan siyah pencereye İTÜ kullanıcı adını ve şifreni yaz, sorulara cevap ver. 'Bitti' yazınca bana 'bitti' yaz. Şifreni bana yazma."
4. Kullanıcı "bitti" deyince: `.\.venv\Scripts\python.exe src\kurulum.py --durum`
5. Çıktıdaki `SONRAKI:` satırlarına göre GEMINI.md'deki ilgili adımı uygula. `"panel": true` ise kullanıcıya masaüstündeki "İTÜ Panel"i açmasını söyle.
6. Kullanıcıya WhatsApp, bildirim ve Drive'ı da kurmak isteyip istemediğini sor (`/whatsapp`, `docs/BILDIRIM.md`, `docs/DRIVE.md`).
