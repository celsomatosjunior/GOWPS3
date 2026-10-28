# Roda o God of War III no RPCS3 do usuário por N segundos, com uma cópia da configuração global (PPU LLVM),
# tira um print da janela e guarda o log, para comparar a ordem das chamadas com o GOW3Native.
param([int]$Segundos = 240)
$r = 'F:\Quadrado do Claude\rpcs3'
$w = 'F:\Quadrado do Claude\Projetos\GOW3_trabalho\rpcs3_gabarito'
New-Item -ItemType Directory -Force $w | Out-Null
Copy-Item "$r\config\config.yml" "$w\config_gabarito.yml" -Force
$eboot = 'F:\Quadrado do Claude\God.Of.War.3.PS3\PS3_GAME\USRDIR\EBOOT.BIN'
$p = Start-Process -FilePath "$r\rpcs3.exe" -ArgumentList @('--no-gui', '--config', "`"$w\config_gabarito.yml`"", "`"$eboot`"") -WorkingDirectory $r -PassThru
foreach ($t in 60, 120, 180, 240, 300) {
    if ($t -gt $Segundos) { break }
    Start-Sleep 60
    & 'F:\Quadrado do Claude\Projetos\scripts\print_janela.ps1' -Processo rpcs3 -Saida "$w\rpcs3_${t}s.png" | Out-Null
}
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep 3
Copy-Item "$r\log\RPCS3.log" "$w\RPCS3_gabarito.log" -Force
"log: $((Get-Item "$w\RPCS3_gabarito.log").Length) bytes"
