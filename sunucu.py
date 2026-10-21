"""
Ders programı aracını yerel sunucuyla açar: bölüm seçme ve "Verileri güncelle" butonu bu modda çalışır
(tarayıcı OBS'den doğrudan veri çekemiyor, istekleri bu sunucu yapıyor).

Çalıştır: baslat.bat  (ya da: python sunucu.py)  ->  http://127.0.0.1:8770
Sadece bu bilgisayardan erişilir. Profiller veri/profiller.json'a da yedeklenir.
"""
import json
import sys
import threading
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))
import guncelle as G  # noqa: E402

PORT = 8770
PROFILLER = G.VERI / "profiller.json"
PROGRAM_LISTESI = G.VERI / "_programlar.json"

durum = {"calisiyor": False, "program": None, "mesaj": "", "i": 0, "n": 0, "hata": None, "bitti": False}
kilit = threading.Lock()


def program_listesi(yenile=False):
    if not yenile:
        try:
            return json.loads(PROGRAM_LISTESI.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    fak = G.fakulteler()
    with ThreadPoolExecutor(6) as ex:
        progs = list(ex.map(lambda f: G.programlar(f[0]), fak))
    liste = [{"id": f[0], "ad": f[1], "programlar": [{"kod": k, "ad": a} for k, a in p]} for f, p in zip(fak, progs) if p]
    G.VERI.mkdir(exist_ok=True)
    PROGRAM_LISTESI.write_text(json.dumps(liste, ensure_ascii=False), encoding="utf-8")
    return liste


def veri_tarihi(kod):
    try:
        with open(G.veri_yolu(kod), encoding="utf-8") as f:
            return json.load(f).get("fetched")
    except (OSError, ValueError):
        return None


def guncelle_is(kod, tam):
    def log(msg, i=None, n=None):
        durum.update(mesaj=msg, i=i or 0, n=n or 0)
    try:
        data = G.veri_cek(kod, None, tam=tam, log=log)
        G.veri_yaz(data)
        if kod == G.PROGRAM:
            G.build()                              # çift tıklanan HTML de güncel kalsın
        durum.update(bitti=True, mesaj=f"Bitti: {data['fetched']}")
    except Exception as e:                         # arayüzde gösterilsin
        traceback.print_exc()
        durum.update(hata=f"{e.__class__.__name__}: {e}", bitti=True)
    finally:
        durum["calisiyor"] = False


def topla_is():
    """OBS/Ninova/e-posta verisini çekip panel.html ve profil.json üretir (src/topla.py'nin aynısı)."""
    import os
    import subprocess
    durum.update(mesaj="Veri toplanıyor (birkaç dakika)...")
    try:
        p = subprocess.run([sys.executable, str(HERE / "src" / "topla.py")], cwd=HERE / "src", text=True,
                           encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        son = (p.stdout or "").strip().splitlines()[-3:]
        if p.returncode == 0:
            durum.update(bitti=True, mesaj="Bitti: " + (son[-1] if son else ""))
        else:
            durum.update(hata=("İTÜ girişi başarısız (tekrar denenmedi). kur.bat ile şifreni yeniden gir."
                               if p.returncode == 2 else " | ".join(son)), bitti=True)
    except Exception as e:                         # arayüzde gösterilsin
        traceback.print_exc()
        durum.update(hata=f"{e.__class__.__name__}: {e}", bitti=True)
    finally:
        durum["calisiyor"] = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/api/durum" not in (str(args[0]) if args else ""):   # send_error'da args[0] HTTPStatus olabiliyor
            sys.stderr.write("  " + (fmt % args) + "\n")

    def gonder(self, kod, govde, tur="application/json; charset=utf-8"):
        b = govde.encode("utf-8") if isinstance(govde, str) else govde
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def json(self, obj, kod=200):
        self.gonder(kod, json.dumps(obj, ensure_ascii=False))

    def guvenli(self):
        """Başka sitelerin localhost'a istek atmasını engelle (DNS rebinding / CSRF)."""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        if self.command != "GET" and self.headers.get("X-Ders-Secme") != "1":
            return False
        return True

    def do_GET(self):
        if not self.guvenli():
            return self.gonder(403, "yasak", "text/plain")
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in ("/", "/index.html"):
            kod = q.get("p") or G.PROGRAM
            yol = G.veri_yolu(kod)
            if not yol.exists():
                kod, yol = G.PROGRAM, G.veri_yolu(G.PROGRAM)
            return self.gonder(200, G.sayfa(yol.read_text(encoding="utf-8"), {"served": True}), "text/html; charset=utf-8")
        if u.path == "/api/programlar":
            try:
                liste = program_listesi(q.get("yenile") == "1")
            except Exception as e:
                return self.json({"hata": f"OBS'den program listesi alınamadı: {e}"}, 502)
            for f in liste:
                for p in f["programlar"]:
                    p["veri"] = veri_tarihi(p["kod"])
            return self.json(liste)
        if u.path == "/panel":                            # toplanan verilerden üretilen panel
            yol = HERE / "panel.html"
            if not yol.exists():
                return self.gonder(404, "Panel henüz üretilmedi. Önce: python src/topla.py", "text/plain; charset=utf-8")
            return self.gonder(200, yol.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if u.path == "/api/obs-profil":                   # OBS'den üretilen profil (ders seçme aracına aktarılır)
            try:
                return self.gonder(200, (G.VERI / "profil.json").read_text(encoding="utf-8"))
            except OSError:
                return self.json({"hata": "profil.json yok. Önce src/topla.py çalıştır."}, 404)
        if u.path == "/api/durum":
            return self.json(durum)
        if u.path == "/api/profiller":
            try:
                return self.gonder(200, PROFILLER.read_text(encoding="utf-8"))
            except OSError:
                return self.json(None)
        self.gonder(404, "yok", "text/plain")

    def do_POST(self):
        if not self.guvenli():
            return self.gonder(403, "yasak", "text/plain")
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/api/guncelle":
            kod = q.get("p", "")
            if not kod.replace("_", "").isalnum():
                return self.json({"hata": "geçersiz program kodu"}, 400)
            with kilit:
                if durum["calisiyor"]:
                    return self.json({"hata": f"Zaten {durum['program']} güncelleniyor"}, 409)
                durum.update(calisiyor=True, program=kod, mesaj="Başlıyor...", i=0, n=0, hata=None, bitti=False)
            threading.Thread(target=guncelle_is, args=(kod, q.get("tam") == "1"), daemon=True).start()
            return self.json({"ok": True})
        if u.path == "/api/topla":                        # OBS + Ninova verisini çek, profil ve paneli üret
            with kilit:
                if durum["calisiyor"]:
                    return self.json({"hata": f"Zaten {durum['program']} işleniyor"}, 409)
                durum.update(calisiyor=True, program="OBS/Ninova", mesaj="Giriş yapılıyor...", i=0, n=0,
                             hata=None, bitti=False)
            threading.Thread(target=topla_is, daemon=True).start()
            return self.json({"ok": True})
        if u.path == "/api/profiller":
            n = int(self.headers.get("Content-Length") or 0)
            govde = self.rfile.read(n).decode("utf-8")
            try:
                d = json.loads(govde)
                assert isinstance(d, dict) and isinstance(d.get("profiles"), dict)
            except (ValueError, AssertionError):
                return self.json({"hata": "geçersiz profil verisi"}, 400)
            G.VERI.mkdir(exist_ok=True)
            tmp = PROFILLER.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            tmp.replace(PROFILLER)
            return self.json({"ok": True})
        self.gonder(404, "yok", "text/plain")


if __name__ == "__main__":
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Port {PORT} kullanımda — sunucu zaten açık olabilir. Tarayıcıda http://127.0.0.1:{PORT} adresini aç.")
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        sys.exit(1)
    print(f"Ders programı: http://127.0.0.1:{PORT}   (kapatmak için bu pencereyi kapat ya da Ctrl+C)")
    if "--tarayici-acma" not in sys.argv:
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
