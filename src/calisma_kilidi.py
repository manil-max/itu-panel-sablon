"""Veri toplama süreçlerini sıraya koyar; süreç kapanınca işletim sistemi kilidi bırakır."""
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class Mesgul(Exception):
    pass


def atomik_yaz(yol, metin):
    yol = Path(yol)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=yol.parent,
                                     prefix=yol.name + ".", suffix=".tmp", delete=False) as dosya:
        gecici = Path(dosya.name)
        try:
            dosya.write(metin)
        except BaseException:
            dosya.close()
            gecici.unlink(missing_ok=True)
            raise
    try:
        gecici.replace(yol)
    finally:
        gecici.unlink(missing_ok=True)


@contextmanager
def topla_kilidi():
    yol = Path(__file__).resolve().parent.parent / "veri" / "topla.lock"
    yol.parent.mkdir(exist_ok=True)
    with yol.open("a+b") as dosya:
        if dosya.tell() == 0:
            dosya.write(b"0")
            dosya.flush()
        dosya.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(dosya.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(dosya.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as hata:
            raise Mesgul from hata
        try:
            yield
        finally:
            dosya.seek(0)
            if os.name == "nt":
                msvcrt.locking(dosya.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(dosya.fileno(), fcntl.LOCK_UN)
