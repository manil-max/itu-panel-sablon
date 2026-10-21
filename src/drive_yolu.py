"""Google Drive for Desktop klasörünü bulur (G:\\My Drive gibi). Başka bağımlılığı yok."""
import json
from pathlib import Path

AYAR = Path(__file__).resolve().parent / "ayarlar.json"


def drive_koku():
    """'My Drive' / 'Drive'ım' klasörü; ayarlar.json -> driveKlasoru elle verilmişse o."""
    try:
        elle = json.loads(AYAR.read_text(encoding="utf-8")).get("driveKlasoru")
    except (OSError, ValueError):
        elle = None
    if elle and Path(elle).is_dir():
        return Path(elle)
    for harf in "GHIJKLMNOPQRSTUVWXYZDEF":
        for ad in ("My Drive", "Drive'ım", "Drive\u2019ım"):
            kok = Path(f"{harf}:/") / ad
            if kok.is_dir():
                return kok
    return None


if __name__ == "__main__":
    print(drive_koku() or "Google Drive klasörü bulunamadı")
