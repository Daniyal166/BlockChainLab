$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$run = (Get-Content .\runs\latest.txt -Raw).Trim()
$c = Get-Content "$run\config.json" -Raw | ConvertFrom-Json
$cli = Join-Path (Split-Path $c.admin.daemon) 'multichain-cli.exe'
& $cli $c.chain "-datadir=$($c.admin.datadir)" getinfo
& $cli $c.chain "-datadir=$($c.rsu.datadir)" getinfo
& $cli $c.chain "-datadir=$($c.admin.datadir)" listpermissions
& $cli $c.chain "-datadir=$($c.rsu.datadir)" liststreamitems decisions false 100
& $cli $c.chain "-datadir=$($c.admin.datadir)" getaddressbalances $c.vehicles.V1
& $cli $c.chain "-datadir=$($c.admin.datadir)" getaddressbalances $c.vehicles.V5
