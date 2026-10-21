<!-- GEMINI.md ile aynı içerik (bazı araçlar AGENTS.md okur). Değiştirirsen ikisini birlikte değiştir. -->

# İTÜ Panel — yapay zekâ (Gemini / Antigravity) için talimatlar

Bu dosyayı baştan sona oku ve adımları **sırayla, aynen** uygula. Kendi yöntemini icat etme.
Kullanıcı İTÜ öğrencisi. Türkçe, kısa ve samimi yaz. Teknik terim kullanma, ne yaptığını tek cümleyle söyle.

Bu proje kullanıcının İTÜ sistemlerini (OBS, Ninova, İTÜ e-posta, akademik takvim, yemekhane, ring,
isteğe bağlı WhatsApp ders grupları) tek bir panelde toplar. Panel bu bilgisayarda bir HTML dosyasıdır.

## Asla yapma (kesin kurallar)

1. **Kullanıcıdan şifresini sohbette isteme.** Şifre sadece `kur.bat` penceresine kullanıcının kendisi tarafından yazılır.
   Kullanıcı şifresini sohbete yazarsa: kullanma, "şifreni buraya yazma, kur.bat penceresine yaz" de.
2. `.env` dosyasını açma, okuma, yazdırma, değiştirme. İçinde şifre var.
3. Çıktıda `GIRIS_HATASI` ya da `HATA: İTÜ girişi` görürsen **aynı komutu tekrar çalıştırma.** İTÜ hesabı kilitlenir.
   Kullanıcıya şunu söyle: "İTÜ girişi olmadı. kur.bat'a çift tıklayıp kullanıcı adını ve şifreni yeniden yaz."
4. WhatsApp'a ya da e-postaya mesaj gönderen, okundu yapan, silen hiçbir kod yazma/çalıştırma. Sistem sadece okur.
5. `veri/` klasörünü, `.env`'i, `panel.html`'i git'e ekleme, commit'leme, internete yükleme.
6. Paneli herkese açık bir yere (GitHub Pages, Netlify, Vercel...) koyma. İçinde notlar ve kişisel bilgi var.
7. Diğer öğrencilerin adlarını, telefon numaralarını bir yere yazma; WhatsApp mesajlarını aynen alıntılama.
8. `src/` içindeki Python dosyalarını kullanıcı açıkça istemedikçe değiştirme. Sorun çıkarsa önce `docs/SORUN_GIDERME.md`.

## Komutlar nasıl çalıştırılır

Proje klasöründe, PowerShell'de. Her zaman bu Python'u kullan (sistemdeki `python`'u değil):

```powershell
.\.venv\Scripts\python.exe src\kurulum.py --durum
```

`.venv` klasörü yoksa henüz kurulum yapılmamıştır → aşağıdaki "Kurulum".

Komut çıktısında:
- `TAMAM:` → o adım bitti.
- `HATA:` → sorun var; hemen altındaki `->` satırı ne yapılacağını söyler. Onu uygula.
- `SONRAKI:` → sıradaki adımlar.

## Kullanıcı "kur", "bu sistemi kur", "repoyu kur" derse → Kurulum

**Adım 1 — Proje bilgisayarda mı?** Bu dosyayı okuyabiliyorsan evet, 2. adıma geç.
Değilse kullanıcının verdiği GitHub linkini indir:
```powershell
git clone <LINK> "$HOME\Desktop\itu-panel"
```
`git` yoksa: `winget install -e --id Git.Git` (sonra terminali kapatıp aç) ya da kullanıcıya
"GitHub sayfasında yeşil Code > Download ZIP, masaüstüne çıkar" de. Sonra o klasörü aç.

**Adım 2 — Kurulum penceresini aç.** Proje klasöründe çalıştır:
```powershell
Start-Process -FilePath ".\kur.bat" -WorkingDirectory (Get-Location)
```
Kullanıcıya **aynen** şunu söyle:
> Siyah bir pencere açıldı. Orada İTÜ kullanıcı adını ve şifreni yaz (şifre yazarken görünmez, normal).
> Sonra sorulara cevap ver: bildirim için "e", WhatsApp için şimdilik "h" diyebilirsin.
> Pencerede "Bitti" yazınca bana "bitti" yaz. Şifreni bana yazma.

Pencere 5-10 dakika sürebilir (bölümünün ders planını ve bütün verini çekiyor). Kullanıcı "bitti" diyene kadar bekle.

**Adım 3 — Kontrol et:**
```powershell
.\.venv\Scripts\python.exe src\kurulum.py --durum
```
- `"panel": true` ise kurulum tamam. Kullanıcıya: "Masaüstünde **İTÜ Panel** var, ona çift tıkla. Veriler 3 saatte bir kendiliğinden yenilenir."
- `"girisBilgisi": false` ya da `"girisEngellendi": true` → Adım 2'yi tekrarla (kullanıcı şifreyi yeniden yazacak).
- `"bolum": null` → `.\.venv\Scripts\python.exe src\kurulum.py --bolum` çalıştır. Bölüm bulunamazsa kullanıcıya bölümünü sor ve
  kodu ver: Elektronik ve Haberleşme (İngilizce) = `EHBE_LS`, Türkçe = `EHB_LS`. Örnek: `... src\kurulum.py --bolum EHBE_LS`.
  Diğer bölümlerin kodları: `... src\kurulum.py --bolum-liste`
- `"panel": false` → `.\.venv\Scripts\python.exe src\kurulum.py --veri`

**Adım 4 — İsteğe bağlı ekler.** Kullanıcıya sor: "WhatsApp ders gruplarını, telefona bildirimi ve Google Drive'ı da kuralım mı?"
İstediği her biri için ilgili rehberi aç ve adımlarını uygula:
- WhatsApp → `docs/WHATSAPP.md`
- Telefona bildirim → `docs/BILDIRIM.md`
- Google Drive (telefonda Gemini'ye panel özetini sormak için) → `docs/DRIVE.md`
- İTÜ e-postası kendiliğinden kurulur; sorun olursa `docs/EPOSTA.md`

## Kullanıcı "güncelle", "verileri yenile" derse

```powershell
.\.venv\Scripts\python.exe src\kurulum.py --veri
```
Sonra kullanıcıya masaüstündeki **İTÜ Panel**'i yeniden açmasını söyle.

## Kullanıcı "değerlendir", "grupları/mailleri özetle", "yeni ne var" derse

`docs/DEGERLENDIRME.md` dosyasını aç ve **aynen** uygula. Bu, WhatsApp gruplarından ve İTÜ e-postasından önemli
şeyleri (sınav, quiz, ödev, derslik değişikliği, burs...) panele not olarak ekler.

## Kullanıcı bir soru sorarsa ("yarın ne var", "fizik quiz ne zaman", "derslik nerede")

`veri/asistan.md` dosyasını oku (panelin düz metin özeti) ve ona göre cevap ver. Dosya yoksa ya da eskiyse önce "güncelle".
"teyit yok" yazan bilgiler öğrenci söylentisidir; öyle belirt. Dosyada olmayanı uydurma, "panelde yok" de.

## Kullanıcı "çalışmıyor", "hata veriyor" derse

1. `.\.venv\Scripts\python.exe src\kurulum.py --durum` çalıştır.
2. `docs/SORUN_GIDERME.md`'de belirtiye uyan satırı bul, onu uygula.
3. Orada yoksa hatanın son 10 satırını kullanıcıya göster ve ne denediğini söyle. Rastgele kod değiştirme.

## Kullanıcı "oyun moduna al", "arka planı kapat" derse

Kullanıcıya proje klasöründeki `otomasyon.bat`'a çift tıklamasını söyle (bir daha tıklayınca açılır).

## Dosyalar (bilmen yeterli)

| Yol | Ne |
| --- | --- |
| `kur.bat` | Çift tıklanan kurulum (Python'u bile kurar) |
| `src/kurulum.py` | Kurulum adımları ve `--durum` |
| `src/topla.py` | Bütün veriyi çeker → `veri/panel.json`, `panel.html`, `veri/asistan.md` |
| `src/gorev.py` | Değerlendirme adayları (`--ozet --dosya`) ve panel yenileme (`--panel`) |
| `src/ayarlar.json` | Kişisel ayarlar: bölüm kodu, dil puanı, WhatsApp grupları (kullanıcı isterse düzenle) |
| `src/onemli_tarihler.json` | Elle eklenen tarihler (kullanıcı "şu tarihi ekle" derse buraya ekle, aynı biçimde) |
| `veri/` | Kullanıcının verisi (git'e girmez) |
| `baslat.bat` | Ders seçme/program hazırlama aracı (tarayıcıda açılır) |
| `otomasyon.bat` | Arka plan işlerini aç/kapat |
