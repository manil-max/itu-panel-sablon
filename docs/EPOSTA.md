# İTÜ e-postası

Ayrı kurulum gerekmez. Veri toplama her çalıştığında İTÜ e-postanın (mail.itu.edu.tr) **son 30 gününü** aynı
İTÜ kullanıcı adı/şifresiyle **sadece okur**: klasör salt-okunur açılır, mailler okundu işaretlenmez, hiçbir şey
gönderilmez/silinmez/taşınmaz. Mailler `veri/eposta/epostalar.db`'de, sadece bu bilgisayarda durur.

Ninova duyuruları, hocaların mailleri, burs/yurt duyuruları buradan gelir; Gemini'ye "değerlendir" deyince
önemli olanlar panele not olarak eklenir (`docs/DEGERLENDIRME.md`).

## Test

```powershell
.\.venv\Scripts\python.exe src\kurulum.py --eposta
```
`TAMAM: E-posta okunabiliyor` görmelisin.

## Sorun olursa

| Belirti | Çözüm |
| --- | --- |
| `LOGIN failed` / kimlik hatası | Şifre doğruysa İTÜ e-postanda IMAP kapalı olabilir: https://mail.itu.edu.tr'ye gir, ayarlarda IMAP/POP erişimini aç. **Tekrar tekrar deneme.** |
| Zaman aşımı | Okul/yurt ağı 993 portunu engelliyor olabilir; başka ağda dene. |
| Hiç mail yok | Normal olabilir (son 30 gün). |

E-postayı kapatmak istersen: hiçbir şey yapmana gerek yok, panel e-postasız da çalışır; ama veri toplama her seferinde
dener. Tamamen kapatmak için Gemini'den `src/topla.py` içindeki `eposta.cek(gun=30)` satırını yorum satırı yapmasını iste.
