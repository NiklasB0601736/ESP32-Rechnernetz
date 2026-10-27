param(
    [ValidateSet('master','slave')][string]$Role='master',
    [ValidateSet('build','menuconfig','flash','monitor')][string]$Action='build',
    [string]$Port,
    [string]$IdfPath='C:\esp\v6.0.1\esp-idf',
    [string]$ToolsPath='C:\Espressif'
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $IdfPath 'tools\idf.py'))) { throw 'ESP-IDF 6.0.1 fehlt. IdfPath angeben oder eine ESP-IDF-Shell verwenden.' }
$idfPython=Join-Path $ToolsPath 'tools\python\v6.0.1\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $idfPython)) { throw 'EIM-Python-Umgebung fehlt. In einer aktivierten ESP-IDF-Shell die Befehle aus README.md verwenden.' }
if (($Action -eq 'flash' -or $Action -eq 'monitor') -and -not $Port) { throw 'Für Flash/Monitor ist -Port erforderlich.' }
$env:IDF_PATH=$IdfPath
$env:IDF_TOOLS_PATH=$ToolsPath
$env:ESP_IDF_VERSION='6.0.1'
$romDirectory=Get-ChildItem -LiteralPath (Join-Path $ToolsPath 'tools\esp-rom-elfs') -Directory -ErrorAction SilentlyContinue | Select-Object -Last 1
if($romDirectory){$env:ESP_ROM_ELF_DIR=$romDirectory.FullName}
$env:IDF_PYTHON_ENV_PATH=Split-Path -Parent (Split-Path -Parent $idfPython)
# EIM installs a version-specific environment but may omit the legacy constraints file.
if (-not (Test-Path -LiteralPath (Join-Path $ToolsPath 'espidf.constraints.v6.0.txt'))) { $env:IDF_PYTHON_CHECK_CONSTRAINTS='no' }
$toolDirectories=@((Split-Path -Parent $idfPython))
foreach($pattern in @('tools\cmake\*\bin','tools\ninja\*','tools\xtensa-esp-elf\*\xtensa-esp-elf\bin','tools\esp32ulp-elf\*\esp32ulp-elf\bin')) {
    $toolDirectories += Get-Item -Path (Join-Path $ToolsPath $pattern) -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
}
$env:Path=($toolDirectories -join ';')+';'+$env:Path
$defaults='sdkconfig.defaults'
if($Role -eq 'slave'){$defaults+=';sdkconfig.slave.defaults'}
$idfArgs=@('-B',"build-$Role",'-D',"SDKCONFIG=sdkconfig.$Role",'-D',"SDKCONFIG_DEFAULTS=$defaults")
if($Port){$idfArgs+=@('-p',$Port)}
$idfArgs+=$Action
Push-Location (Join-Path $projectRoot 'firmware')
try {
    & $idfPython (Join-Path $IdfPath 'tools\idf.py') @idfArgs
    if($LASTEXITCODE -ne 0){throw "ESP-IDF beendet mit Code $LASTEXITCODE"}
} finally { Pop-Location }
