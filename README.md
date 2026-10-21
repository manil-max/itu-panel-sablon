# İTÜ Panel

İTÜ'deki dağınık her şeyi tek sayfada toplayan kişisel panel. Bu bilgisayarda çalışır, verin hiçbir sunucuya gitmez.

- **Bugün:** şu anki/sıradaki ders ve dersliği, ring, yemekhane menüsü, yaklaşan sınav/quiz/ödevler
- **Hafta:** haftalık program; quiz, lab, ödev ve tatiller doğru güne ve derse işlenmiş
- **Gündem:** Ninova duyuruları, ödevler, dosyalar, e-posta ve (istersen) WhatsApp ders gruplarından önemli notlar
- **Takvim:** akademik takvim (sadece seni ilgilendirenler), final takvimi
- **Ben:** notlar, AGNO simülasyonu, devamsızlık, danışman, Erasmus puanı
- **Ders seçme aracı:** bölümünün ders planı, şubeler, hocalar, not dağılımları, çakışma kontrolü

Kaynaklar: OBS, Ninova, İTÜ e-posta (salt-okunur), İTÜ Portal (yemek, bakiye), akademik takvim, SKS (ring),
havuz derslerinin izlenceleri (quiz tarihleri), isteğe bağlı WhatsApp grupları.

## Kurulum

### Gemini / Antigravity ile (önerilen)
Antigravity'de (ya da Gemini CLI'da) şunu yaz:

> https://github.com/... bu repoyu indir ve GEMINI.md'ye göre benim için kur

Gemini bir pencere açacak; İTÜ kullanıcı adını ve şifreni **o pencereye** yaz (Gemini'ye değil). Gerisini o halleder.
Sonra "WhatsApp'ı kur", "bildirimi kur", "Drive'ı kur", "değerlendir", "güncelle" diyebilirsin.

### Kendin
1. Yeşil **Code → Download ZIP** → masaüstüne çıkar (ya da `git clone`).
2. Klasördeki **`kur.bat`**'a çift tıkla. Python yoksa kendisi kurar.
3. İTÜ kullanıcı adını ve şifreni yaz, sorulara cevap ver. 5-10 dakika sürer.
4. Masaüstünde **İTÜ Panel** ve **İTÜ Ders Programı** kısayolları oluşur.

Veriler her gün 07:30'dan itibaren 3 saatte bir kendiliğinden yenilenir (bilgisayar açıksa).

## İsteğe bağlı ekler

| Ek | Ne sağlar | Rehber |
| --- | --- | --- |
| WhatsApp ders grupları | Gruplarda konuşulan sınav/ödev/derslik bilgileri panele not olarak düşer, belgeler iner | [docs/WHATSAPP.md](docs/WHATSAPP.md) |
| Telefona bildirim | Her akşam yarınki sınav/lab hatırlatması | [docs/BILDIRIM.md](docs/BILDIRIM.md) |
| Google Drive | Telefonda Gemini'ye "yarın ne var?" sorabilmek; WhatsApp belgeleri Drive'da | [docs/DRIVE.md](docs/DRIVE.md) |
| İTÜ e-posta | Kendiliğinden kurulur | [docs/EPOSTA.md](docs/EPOSTA.md) |
| Yapay zekâ değerlendirmesi | WhatsApp/e-postadan önemli olanları ayıklar | [docs/DEGERLENDIRME.md](docs/DEGERLENDIRME.md) |

## Güvenlik ve gizlilik

- İTÜ şifren sadece bu bilgisayardaki `.env` dosyasında durur (git'e girmez). Sadece İTÜ'ye giriş için kullanılır.
- Şifre yanlışsa sistem **tekrar denemez** (İTÜ hesabın kilitlenmesin diye).
- E-posta ve WhatsApp **sadece okunur**; hiçbir şey gönderilmez, okundu işaretlenmez.
- `veri/` (notların, mesajlar), `panel.html` ve `.env` git'e girmez. Paneli herkese açık bir siteye koyma.

Sorun olursa: [docs/SORUN_GIDERME.md](docs/SORUN_GIDERME.md) — ya da Gemini'ye "çalışmıyor" de.

## Komutlar

```powershell
.\kur.bat                                  # kurulum / onarım (her zaman güvenle tekrar çalıştırılabilir)
.\kur.bat --whatsapp                       # tek bir adım (--bildirim, --drive, --veri, --durum ...)
.\.venv\Scripts\python.exe src\kurulum.py --durum
.\.venv\Scripts\python.exe src\kurulum.py --veri      # verileri şimdi yenile
.\baslat.bat                               # ders seçme aracı (http://127.0.0.1:8770)
.\otomasyon.bat                            # arka plan işlerini kapat/aç (oyun modu)
```
