# spill_test.ps1 -- does WDDM silently spill KV to Shared GPU memory (system RAM) instead of OOMing?
# For each f16 depth, allocate the ctx, sample Dedicated vs Shared GPU memory for the active card,
# then kill (the KV is allocated at ctx-creation, before the slow d-token prefill completes).
# Shared lifting off its ~0.3GB baseline at some depth = the spill knee = the real Windows "ceiling".
#   .\spill_test.ps1 2      # run on Vulkan device 2 (a B70); NEVER 0 (the 2070)
$ErrorActionPreference='Continue'
$bench='D:\work\llamacpp-b9279-vulkan\llama-bench.exe'
$m='D:\work\battlemage\models\Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf'
$out='D:\work\denning\results\raw\battery-spill'
$dev = if($args.Count -ge 1){[string]$args[0]}else{'1'}
if($dev -eq '0'){ "REFUSED: device 0 is the 2070 display card"; exit 2 }
$env:GGML_VK_VISIBLE_DEVICES=$dev
"# spill test on Vulkan device $dev  ($(Get-Date -Format o))" | Out-File "$out.csv" -Encoding utf8
"depth,dedicated_gb_max,shared_gb_max,sampled_s,proc_exited" | Out-File "$out.csv" -Append -Encoding utf8
foreach($d in 65536,81920,98304,114688,131072){
  $p = Start-Process -FilePath $bench -ArgumentList @('-m',$m,'-ngl','99','-fa','1','-p','8','-n','0','-d',"$d",'-r','1','-o','json') `
       -RedirectStandardOutput "$out-d$d.json" -RedirectStandardError "$out-d$d.err" -PassThru -NoNewWindow
  $maxDed=0.0; $maxShr=0.0; $t0=Get-Date
  while(-not $p.HasExited -and ((Get-Date)-$t0).TotalSeconds -lt 75){
    $ded=(Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage' -EA SilentlyContinue).CounterSamples
    $shr=(Get-Counter '\GPU Adapter Memory(*)\Shared Usage'    -EA SilentlyContinue).CounterSamples
    if($ded){ $dm=($ded|Measure-Object -Property CookedValue -Maximum).Maximum/1GB; if($dm -gt $maxDed){$maxDed=$dm} }
    if($shr){ $sm=($shr|Measure-Object -Property CookedValue -Maximum).Maximum/1GB; if($sm -gt $maxShr){$maxShr=$sm} }
    Start-Sleep -Milliseconds 1200
  }
  $el=[math]::Round(((Get-Date)-$t0).TotalSeconds,0); $exited=$p.HasExited
  if(-not $p.HasExited){ try{$p.Kill()}catch{} }
  ("{0},{1:N2},{2:N2},{3},{4}" -f $d,$maxDed,$maxShr,$el,$exited) | Out-File "$out.csv" -Append -Encoding utf8
  Start-Sleep -Seconds 3   # let VRAM free between depths
}
"# SPILL TEST DONE $(Get-Date -Format o)" | Out-File "$out.csv" -Append -Encoding utf8