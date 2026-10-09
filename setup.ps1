# Builds Hey Jev for Windows: a venv with the packages, plus "Hey Jev" shortcuts in the Start menu and on the Desktop.
# The shortcuts run the code straight from this folder. Run it again if you move the folder.
# It also has her start when you sign in; -NoStartup leaves that off.
#   powershell -ExecutionPolicy Bypass -File setup.ps1 [-NoStartup]
param([switch]$NoStartup)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# Python 3.10 or newer, from the py launcher if there is one
$python = $null
foreach ($candidate in @(@("py", "-3"), @("python"))) {
    try {
        $version = & $candidate[0] $candidate[1..9] -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        if ($version -eq "True") { $python = $candidate; break }
    } catch { }
}
if (-not $python) {
    Write-Host "Python 3.10+ not found. Install it with:  winget install Python.Python.3.12  (or from python.org), then run this again."
    exit 1
}

if (Test-Path ".venv\Scripts\python.exe") {
    & .venv\Scripts\python.exe -c "import sys" 2>$null
    if ($LASTEXITCODE -ne 0) { Remove-Item -Recurse -Force .venv }  # left over from another folder, venvs don't move
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv"
    & $python[0] $python[1..9] -m venv .venv
}
& .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "Installing packages failed, see above."; exit 1 }

$shell = New-Object -ComObject WScript.Shell
$targets = @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))
foreach ($dir in $targets) {
    $link = $shell.CreateShortcut((Join-Path $dir "Hey Jev.lnk"))
    $link.TargetPath = Join-Path $here ".venv\Scripts\pythonw.exe"
    $link.Arguments = '"' + (Join-Path $here "app.py") + '"'
    $link.WorkingDirectory = $here
    $link.IconLocation = (Join-Path $here "assets\icon.ico") + ",0"
    $link.Description = "Hey Jev voice assistant"
    $link.Save()
    Write-Host "Shortcut: $(Join-Path $dir 'Hey Jev.lnk')"
}
# Start when you sign in, the same as ticking Settings > Start when I sign in: minimised, and she says hello
$on = if ($NoStartup) { "False" } else { "True" }
& .venv\Scripts\python.exe -c "import winplatform; winplatform.set_start_with_windows($on)"
if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't change starting with Windows, see above. The Settings tab can do it too." }
elseif ($NoStartup) { Write-Host "Hey Jev won't start by itself when you sign in." }
else { Write-Host "Hey Jev will start when you sign in. To stop that, untick Settings > Start when I sign in." }

Write-Host ""
Write-Host "Done. Open Hey Jev from the Start menu or the Desktop."
Write-Host "Logs: $env:LOCALAPPDATA\Hey Jev\Logs\Hey Jev.log"
