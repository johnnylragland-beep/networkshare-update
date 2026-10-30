# Public entry point: irm https://.../install.ps1 | iex
& {
    $ErrorActionPreference = 'Stop'
    $pythonExe = $null
    foreach ($candidate in @('python.exe', 'py.exe', 'python3.exe')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command -or $command.Source -like '*\WindowsApps\*') {
            continue
        }
        $probeArgs = @('-c', 'import sys; print(sys.executable)')
        if ($candidate -eq 'py.exe') {
            $probeArgs = @('-3') + $probeArgs
        }
        try {
            $resolved = & $command.Source @probeArgs 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath ([string]$resolved))) {
                $pythonExe = ([string]$resolved).Trim()
                break
            }
        } catch {
            continue
        }
    }
    if (-not $pythonExe) {
        throw 'Python 3 is required. Install Python from https://www.python.org/downloads/windows/, then run this command again.'
    }

    $installerFile = [System.IO.Path]::GetTempFileName()
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest 'https://johnnylragland-beep.github.io/networkshare-update/install.py' -UseBasicParsing -OutFile $installerFile
        & $pythonExe $installerFile
        if ($LASTEXITCODE -ne 0) {
            throw "NetworkShare installer exited with code $LASTEXITCODE."
        }
    } finally {
        Remove-Item -LiteralPath $installerFile -Force -ErrorAction SilentlyContinue
    }
}
