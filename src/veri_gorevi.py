"""
Windows'taki "ITUPanel-veri" zamanlanmış görevinin çalıştırdığı betik:
  1) GitHub'daki değişiklikleri çeker (git pull --ff-only). Yerelde commit edilmemiş değişiklik varsa
     ya da dal ileri gitmişse pull'u atlar, hiçbir şeyi ezmez; sebebi veri/guncelleme.log'a yazar.
  2) Veriyi toplar (topla.py, ayrı süreçte: pull ile gelen yeni kod kullanılsın).

    pythonw.exe src/veri_gorevi.py
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
LOG = KOK / "veri" / "guncelleme.log"


def log(*a):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        print(datetime.now().isoformat(timespec="seconds"), *a, file=f)


def git(*arg):
    return subprocess.run(["git", *arg], cwd=KOK, capture_output=True, text=True, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def cek():
    degisen = [s for s in git("status", "--porcelain", "--untracked-files=no").stdout.splitlines() if s.strip()]
    if degisen:
        log("git pull atlandı: commit edilmemiş değişiklik var ->", ", ".join(s[3:] for s in degisen[:8]))
        return
    once = git("rev-parse", "HEAD").stdout.strip()
    r = git("pull", "--ff-only", "-q")
    if r.returncode:
        log("git pull atlandı/başarısız:", (r.stderr or r.stdout).strip().replace("\n", " ")[:300])
        return
    sonra = git("rev-parse", "HEAD").stdout.strip()
    if once != sonra:
        log("git pull:", git("log", "--oneline", f"{once}..{sonra}").stdout.strip().replace("\n", " | ")[:500])
        if "requirements.txt" in git("diff", "--name-only", once, sonra).stdout.split():
            p = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r",
                                str(KOK / "requirements.txt")], capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            log("yeni paketler kuruldu" if p.returncode == 0 else "paket kurulumu başarısız: " + (p.stderr or "")[-300:])


def main():
    try:
        cek()
    except Exception as e:                       # git yoksa/ağ yoksa veri toplama yine çalışsın
        log("git pull yapılamadı:", type(e).__name__, e)
    r = subprocess.run([sys.executable, str(KOK / "src" / "topla.py")], cwd=KOK / "src",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log("topla.py bitti, çıkış kodu", r.returncode)
    son = KOK / "veri" / "dosyalar_son.txt"
    try:
        eski = datetime.fromisoformat(son.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        eski = datetime.min
    if r.returncode == 0 and (datetime.now() - eski).total_seconds() > 10 * 3600:
        d = subprocess.run([sys.executable, "-c", "import dosyalar, wa_dosya; dosyalar.calistir(log=lambda *x: None); wa_dosya.duzenle()"], cwd=KOK / "src", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        son.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        log("ders dosyaları bitti, çıkış kodu", d.returncode)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
