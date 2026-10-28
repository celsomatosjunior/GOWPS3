# Salva um PNG só da área cliente da janela principal de um processo (sem o resto da área de trabalho).
param([string]$Processo = 'GOW3Native', [string]$Saida)
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct PT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref PT p);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
$p = Get-Process $Processo -ErrorAction Stop | ? { $_.MainWindowHandle -ne 0 } | Select -First 1
if (-not $p) { throw "sem janela de $Processo" }
$h = $p.MainWindowHandle
$r = New-Object W+RECT; [W]::GetClientRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $hh = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $g.GetHdc(); $ok = [W]::PrintWindow($h, $dc, 3); $g.ReleaseHdc($dc)   # 1 = só cliente, 2 = conteúdo renderizado
$bmp.Save($Saida, [System.Drawing.Imaging.ImageFormat]::Png)
"janela ${w}x${hh} PrintWindow=$ok -> $Saida"
