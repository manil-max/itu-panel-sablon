# Sorun giderme

Önce durum: `.\.venv\Scripts\python.exe src\kurulum.py --durum` (şifre göstermez). Sonra belirtiye uyan satır:

| Belirti | Ne yapılır |
| --- | --- |
| `kur.bat` açılıp hemen kapanıyor | Klasörde sağ tık → "Terminalde aç" → `.\kur.bat` yaz, hatayı oku. Klasör yolunda garip karakter varsa projeyi `C:\itu-panel` gibi sade bir yere taşı. |
| "Python bulunamadı" ve winget de yok | https://www.python.org/downloads/ → indir, kurarken **Add python.exe to PATH** kutusunu işaretle → `kur.bat` tekrar. |
| `GIRIS_HATASI` / "İTÜ girişi olmadı" | **Tekrar deneme.** Tarayıcıda portal.itu.edu.tr'ye girip şifreyi kontrol et. Sonra `kur.bat`'a çift tıkla, bilgileri yeniden yaz. (Hata sonrası otomatik denemeler kendiliğinden durur, `kur.bat` ile doğru şifre girince açılır.) |
| `"girisEngellendi": true` | Yukarıdaki satır. |
| Bölüm bulunamadı | `.\.venv\Scripts\python.exe src\kurulum.py --bolum-liste` → kendi kodunu bul → `... src\kurulum.py --bolum EHBE_LS` |
| Panelde dersler boş | Dönem başında OBS'de kayıt yoksa normal. Kayıttan sonra: `... src\kurulum.py --veri` |
| Panel eski | `... src\kurulum.py --veri`; Görev Zamanlayıcı'da `ITUPanel-veri` var mı? Yoksa `... src\kurulum.py --gorevler` |
| "TOPLA_MESGUL" | Başka bir toplama sürüyor; 5 dakika sonra tekrar. |
| "OTOMASYON_KAPALI" | `otomasyon.bat` ile kapatılmış; tekrar çift tıkla. |
| Ninova alınamadı | Ninova bakımda olabilir; panelin geri kalanı çalışır, sonraki güncellemede gelir. |
| Ders seçme aracı açılmıyor | `baslat.bat`'a çift tıkla, açık kalan siyah pencereyi kapatma; tarayıcıda http://127.0.0.1:8770 |
| Türkçe karakterler bozuk | Paneli `panel.html` üzerinden çift tıklayarak aç (masaüstündeki "İTÜ Panel"). |
| Bilgisayar yeni / proje taşındı | `kur.bat`'a çift tıkla; eksik olanları kendisi kurar, görevleri yeni yola göre yeniler (`--gorevler`). |

Her şeyi sıfırlamak (verileri siler, kodu bırakır): `veri` klasörünü, `.env`'i, `src\ayarlar.json`'u sil → `kur.bat`.
Windows görevlerini silmek: Görev Zamanlayıcı → `ITUPanel-` ile başlayanlar → Sil.
