@echo off
rem Cift tikla: arka plan otomasyonlarini ac/kapat (WhatsApp koprusu + 3 saatlik veri cekme + aksam hatirlatmasi).
rem   otomasyon.bat         -> durumu degistir
rem   otomasyon.bat kapat   -> kapat
rem   otomasyon.bat ac      -> ac
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$islem='%~1'; $bayrak='veri\otomasyon_kapali'; $gorevler='ITUPanel-whatsapp','ITUPanel-veri','ITUPanel-hatirlatma';" ^
  "if(-not $islem){ $islem = if(Test-Path $bayrak){'ac'}else{'kapat'} };" ^
  "if($islem -eq 'kapat'){" ^
  "  foreach($g in $gorevler){ Stop-ScheduledTask $g -EA 0; Disable-ScheduledTask $g -EA 0 | Out-Null };" ^
  "  Get-CimInstance Win32_Process | ?{ $_.Name -like 'python*' -and $_.CommandLine -like '*whatsapp_kopru*' } | %%{ Stop-Process -Id $_.ProcessId -Force -EA 0 };" ^
  "  New-Item -ItemType File -Force -Path $bayrak | Out-Null; Write-Host 'Otomasyonlar KAPALI (oyun modu). Acmak icin tekrar cift tikla.' -F Yellow" ^
  "} else {" ^
  "  foreach($g in $gorevler){ Enable-ScheduledTask $g -EA 0 | Out-Null }; Start-ScheduledTask 'ITUPanel-whatsapp' -EA 0;" ^
  "  Remove-Item $bayrak -EA 0; Write-Host 'Otomasyonlar ACIK. WhatsApp koprusu baslatildi.' -F Green" ^
  "};" ^
  "Start-Sleep 4"
