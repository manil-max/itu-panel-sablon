"""Google Drive klasörü (G:\\My Drive gibi). Asıl iş drive_yerel.drive_ana()'da; ayarlar.json -> driveKlasoru'yu da okur."""


def drive_koku():
    from drive_yerel import drive_ana
    return drive_ana()


if __name__ == "__main__":
    print(drive_koku() or "Google Drive klasörü bulunamadı")
