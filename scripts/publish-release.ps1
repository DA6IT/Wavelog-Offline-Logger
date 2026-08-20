[CmdletBinding()]
param(
    [switch]$SkipScreenshotCapture,
    [switch]$SkipLocalBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repository = "DA6IT/Wavelog-Offline-Logger"
$coreVersionText = [System.IO.File]::ReadAllText((Join-Path $projectRoot "logger_core.py"))
$coreVersionMatch = [regex]::Match($coreVersionText, '(?m)^VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)"\s*$')
if (-not $coreVersionMatch.Success) {
    throw "Die Release-Version konnte nicht aus logger_core.py gelesen werden."
}
$version = $coreVersionMatch.Groups[1].Value
$tag = "v$version"
$branch = "agent/v$version"
$expectedExe = Join-Path $projectRoot "dist\DA6IT.de-Wavelog-Offline-Logger-v$version-windows-x64.exe"
$publishScriptRelativePath = "scripts/$(Split-Path -Leaf $PSCommandPath)"

function Find-Tool {
    param([string]$Name, [string[]]$Candidates)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*WindowsApps*") {
        return $command.Source
    }
    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    throw "$Name wurde nicht gefunden."
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory=$true)][string]$File,
        [string[]]$CommandArguments = @()
    )
    & $File @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Befehl fehlgeschlagen ($LASTEXITCODE): $File $($CommandArguments -join ' ')"
    }
}

function Invoke-CapturedNative {
    param(
        [Parameter(Mandatory=$true)][string]$File,
        [string[]]$CommandArguments = @()
    )
    # Windows PowerShell 5.1 converts native stderr into error records. During
    # an intentional retry those records must be captured instead of being
    # promoted to a terminating error by the script-wide Stop preference.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $capturedOutput = @(& $File @CommandArguments 2>&1)
        $capturedExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    [pscustomobject]@{
        ExitCode = $capturedExitCode
        Output = $capturedOutput
    }
}

function Convert-NativeOutputToText {
    param([object[]]$Output)
    return (($Output | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Convert-JsonArray {
    param([Parameter(Mandatory=$true)][string]$Json)
    if ([string]::IsNullOrWhiteSpace($Json)) {
        return @()
    }
    $parsed = ConvertFrom-Json -InputObject $Json
    # Windows PowerShell 5.1 can retain a JSON array as one nested pipeline
    # object.  This pipeline deliberately enumerates it exactly once.
    return @($parsed | ForEach-Object { $_ })
}

$git = Find-Tool "git" @("C:\Program Files\Git\cmd\git.exe")
$gh = Find-Tool "gh" @("C:\Program Files\GitHub CLI\gh.exe")
$python = Find-Tool "python" @(
    (Join-Path $env:LOCALAPPDATA "AFU-Tools\WavelogOfflineLogger\runtime\python312\python.exe"),
    (Join-Path $projectRoot "build\embedded\python312\python.exe")
)
$go = Find-Tool "go" @(
    (Join-Path $projectRoot "..\go1.23.2-complete\go\bin\go.exe"),
    (Join-Path $projectRoot "..\go1.23.2-windows-amd64\go\bin\go.exe"),
    (Join-Path $projectRoot "..\go1.23.2-runtime\go\bin\go.exe")
)
$env:PATH = "$(Split-Path -Parent $python);$(Split-Path -Parent $go);$env:PATH"

Push-Location $projectRoot
try {
    Write-Host "1/10 Werkzeuge, Anmeldung und Version pruefen ..."
    Invoke-Checked $gh @("auth", "status")

    $safeDirectories = @(& $git config --global --get-all safe.directory 2>$null)
    if ($safeDirectories -notcontains $projectRoot) {
        Invoke-Checked $git @("config", "--global", "--add", "safe.directory", $projectRoot)
    }

    $core = Get-Content -LiteralPath "logger_core.py" -Raw -Encoding UTF8
    $bootstrap = Get-Content -LiteralPath "bootstrap_windows.go" -Raw -Encoding UTF8
    $pkgbuild = Get-Content -LiteralPath "packaging\arch\PKGBUILD" -Raw -Encoding UTF8
    $releaseNotes = Get-Content -LiteralPath "docs\RELEASE_NOTES.md" -Raw -Encoding UTF8
    if ($core -notmatch ('(?m)^VERSION\s*=\s*"' + [regex]::Escape($version) + '"\s*$')) {
        throw "logger_core.py enthaelt nicht Version $version."
    }
    if ($bootstrap -notmatch ('(?m)^\s*appVersion\s*=\s*"' + [regex]::Escape($version) + '"\s*$')) {
        throw "bootstrap_windows.go enthaelt nicht Version $version."
    }
    if ($pkgbuild -notmatch ('(?m)^pkgver=' + [regex]::Escape($version) + '\s*$')) {
        throw "packaging/arch/PKGBUILD enthaelt nicht Version $version."
    }
    $expectedAppDirectory = "app-v$($version -replace '[^0-9A-Za-z]', '')"
    if ($bootstrap -notmatch ('filepath\.Join\(base,\s*"' + [regex]::Escape($expectedAppDirectory) + '"\)')) {
        throw "bootstrap_windows.go enthaelt nicht das erwartete App-Verzeichnis $expectedAppDirectory."
    }
    if ($releaseNotes -notmatch ('(?m)^# .+ v' + [regex]::Escape($version) + '\s*$')) {
        throw "docs/RELEASE_NOTES.md enthaelt nicht Version $version."
    }

    $remoteTagResult = Invoke-CapturedNative $git @("ls-remote", "--tags", "origin", "refs/tags/$tag")
    if ($remoteTagResult.ExitCode -ne 0) {
        throw "Remote-Tags konnten nicht geprueft werden: $(Convert-NativeOutputToText $remoteTagResult.Output)"
    }
    $releaseAlreadyTagged = -not [string]::IsNullOrWhiteSpace((Convert-NativeOutputToText $remoteTagResult.Output))
    if ($releaseAlreadyTagged) {
        Write-Host "Der Tag $tag existiert bereits. Branch-, PR- und Tag-Schritte werden uebersprungen; der Release-Workflow wird weiter beobachtet."
    }

    if (-not $releaseAlreadyTagged) {
    Write-Host "2/10 Vollstaendige Dokumentations-Screenshots erzeugen ..."
    if (-not $SkipScreenshotCapture) {
        & (Join-Path $PSScriptRoot "capture-doc-screenshots.ps1")
        if ($LASTEXITCODE -ne 0) {
            throw "Screenshot-Aufnahme fehlgeschlagen."
        }
    }
    $requiredScreenshots = @(
        "qso-logging.png", "fast-log.png", "contest-logging.png", "logbook-sync.png",
        "statistics.png", "cat-setup.png", "dx-cluster.png", "udp-logging.png",
        "settings-general.png", "settings-wavelog.png", "settings-callbook.png",
        "settings-data-connections.png", "sync-progress-running.png", "sync-progress-complete.png",
        "qso-logging-english-dark.png"
    )
    $missingScreenshots = $requiredScreenshots | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $projectRoot "docs\screenshots\$_"))
    }
    if ($missingScreenshots) {
        throw "Pflicht-Screenshots fehlen: $($missingScreenshots -join ', ')"
    }

    Write-Host "3/10 Selftests und Skript-Syntax pruefen ..."
    $packagePath = Join-Path $projectRoot "build\embedded\python-packages\windows-x64-release"
    if (Test-Path -LiteralPath $packagePath) {
        $env:PYTHONPATH = if ($env:PYTHONPATH) { "$packagePath;$env:PYTHONPATH" } else { $packagePath }
    }
    Invoke-Checked $python @("selftest.py")
    Invoke-Checked $python @(
        "-m", "py_compile", "app.py", "logger_core.py", "callbook.py",
        "notifications.py", "ui_preferences.py", "update_check.py",
        "scripts\capture-doc-screenshots.py"
    )

    foreach ($scriptPath in @(
        "scripts\build-windows.ps1",
        "scripts\prepare-network-trust-windows.ps1",
        "scripts\prepare-pillow-windows.ps1",
        "scripts\prepare-hamlib-windows.ps1",
        "scripts\package-release.ps1",
        "scripts\capture-doc-screenshots.ps1",
        $publishScriptRelativePath
    )) {
        $parseTokens = $null
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            (Resolve-Path $scriptPath),
            [ref]$parseTokens,
            [ref]$parseErrors
        ) | Out-Null
        if ($parseErrors) {
            $messages = $parseErrors | ForEach-Object { $_.Message }
            throw "PowerShell-Syntaxfehler in ${scriptPath}: $($messages -join '; ')"
        }
    }

    $bash = $null
    foreach ($candidate in @("C:\Program Files\Git\bin\bash.exe", "C:\Program Files\Git\usr\bin\bash.exe")) {
        if (Test-Path -LiteralPath $candidate) { $bash = $candidate; break }
    }
    if ($bash) {
        Invoke-Checked $bash @("-n", "scripts/build-macos.sh")
        Invoke-Checked $bash @("-n", "scripts/build-linux.sh")
        Invoke-Checked $bash @("-n", "scripts/prepare-hamlib-linux.sh")
    } else {
        Write-Warning "Git Bash nicht gefunden; Shell-Syntax wird erst in GitHub Actions geprueft."
    }

    Write-Host "4/10 Lokales Windows-Release bauen ..."
    if (-not $SkipLocalBuild) {
        & (Join-Path $PSScriptRoot "package-release.ps1") -OutputDirectory "dist" -SkipTests
        if ($LASTEXITCODE -ne 0) {
            throw "Lokaler Windows-Release-Build fehlgeschlagen."
        }
    }
    if (-not $SkipLocalBuild -and -not (Test-Path -LiteralPath $expectedExe)) {
        throw "Erwartete Test-EXE fehlt: $expectedExe"
    }

    Write-Host "5/10 Release-Branch vorbereiten ..."
    Invoke-Checked $git @("fetch", "--prune", "origin", "main")
    $currentBranch = (& $git branch --show-current).Trim()
    $localBranches = @(& $git branch --format="%(refname:short)")
    if ($currentBranch -ne $branch) {
        if ($localBranches -contains $branch) {
            Invoke-Checked $git @("switch", $branch)
        } else {
            # The release branch must always start at the current remote main,
            # even when the working copy still points to an older release PR.
            Invoke-Checked $git @("switch", "-c", $branch, "origin/main")
        }
    }

    Write-Host "6/10 Gepruefte Dateien committen und Branch pushen ..."
    $releaseFiles = @(
        ".gitattributes",
        "app.py",
        "bootstrap_windows.go",
        "callbook.py",
        "logger_core.py",
        "notifications.py",
        "selftest.py",
        "ui_preferences.py",
        "update_check.py",
        "packaging/arch/PKGBUILD",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "CHANGELOG.md",
        "docs/ARCHITECTURE.md",
        "docs/RELEASE_NOTES.md",
        "docs/RELEASING.md",
        "docs/TROUBLESHOOTING.md",
        "docs/USER_GUIDE.md",
        "scripts/build-linux.sh",
        "scripts/build-macos.sh",
        "scripts/build-windows.ps1",
        "scripts/prepare-network-trust-windows.ps1",
        "scripts/publish-v0.16.1.ps1",
        $publishScriptRelativePath
    )
    $releaseFiles += $requiredScreenshots | ForEach-Object { "docs/screenshots/$_" }
    Invoke-Checked $git (@("add", "--") + $releaseFiles)
    $staged = @(& $git diff --cached --name-only)
    $unexpected = $staged | Where-Object { $_ -notin $releaseFiles }
    if ($unexpected) {
        throw "Unerwartete Datei(en) sind bereits gestaged: $($unexpected -join ', '). Bitte zuerst den Git-Index pruefen."
    }
    $forbidden = $staged | Where-Object {
        $_ -eq "AGENTS.md" -or
        $_ -match '(^|/)(dist|build)/' -or
        $_ -match '\.(adi|sqlite|sqlite3|db)$' -or
        $_ -match '(^|/)(startup\.log|profiles\.json|ui-preferences\.json)$'
    }
    if ($forbidden) {
        throw "Nicht veroeffentlichbare Datei(en) im Commit: $($forbidden -join ', ')"
    }
    & $git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        Invoke-Checked $git @("commit", "-m", "Release v$version")
    } else {
        Write-Host "Kein neuer Commit noetig; Branch enthaelt bereits alle Aenderungen."
    }
    Invoke-Checked $git @("push", "--set-upstream", "origin", $branch)

    Write-Host "7/10 Pull Request erstellen oder wiederverwenden ..."
    $prUrl = ""
    $prListResult = Invoke-CapturedNative $gh @(
        "pr", "list", "--repo", $repository, "--head", $branch,
        "--base", "main", "--state", "all", "--limit", "10",
        "--json", "number,url,isDraft,state,mergedAt"
    )
    if ($prListResult.ExitCode -ne 0) {
        throw "Pull Requests konnten nicht abgefragt werden: $($prListResult.Output -join ' ')"
    }
    $prJson = Convert-NativeOutputToText $prListResult.Output
    if ([string]::IsNullOrWhiteSpace($prJson)) {
        throw "GitHub CLI lieferte bei der Pull-Request-Abfrage keine JSON-Antwort."
    }
    try {
        $prRows = @(Convert-JsonArray $prJson)
    } catch {
        throw "Pull-Request-JSON konnte nicht gelesen werden: $prJson"
    }
    $pr = $prRows | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_.url) -and
        ($_.state -eq "OPEN" -or -not [string]::IsNullOrWhiteSpace([string]$_.mergedAt))
    } | Select-Object -First 1
    $prAlreadyMerged = $false

    if ($null -ne $pr) {
        $prUrl = [string]$pr.url
        $prAlreadyMerged = -not [string]::IsNullOrWhiteSpace([string]$pr.mergedAt)
        if ($pr.isDraft -and -not $prAlreadyMerged) {
            Invoke-Checked $gh @("pr", "ready", $prUrl, "--repo", $repository)
        }
    } else {
        $createResult = Invoke-CapturedNative $gh @(
            "pr", "create", "--repo", $repository, "--base", "main",
            "--head", $branch, "--title", "Release v$version",
            "--body-file", "docs\RELEASE_NOTES.md"
        )
        if ($createResult.ExitCode -ne 0) {
            throw "Pull Request konnte nicht erstellt werden: $($createResult.Output -join ' ')"
        }
        $prUrl = [string]($createResult.Output | ForEach-Object { [string]$_ } | Where-Object {
            $_ -match '^https://github\.com/[^/]+/[^/]+/pull/[0-9]+/?$'
        } | Select-Object -Last 1)

        # gh-Ausgaben koennen je nach Version oder Terminalformatierung von
        # der reinen URL abweichen. In diesem Fall wird der gerade erstellte
        # PR noch einmal strukturiert abgefragt.
        if ([string]::IsNullOrWhiteSpace($prUrl)) {
            $lookupResult = Invoke-CapturedNative $gh @(
                "pr", "list", "--repo", $repository, "--head", $branch,
                "--base", "main", "--state", "open", "--limit", "1",
                "--json", "number,url,isDraft,state,mergedAt"
            )
            if ($lookupResult.ExitCode -ne 0) {
                throw "Der erstellte Pull Request konnte nicht erneut abgefragt werden: $($lookupResult.Output -join ' ')"
            }
            $lookupJson = Convert-NativeOutputToText $lookupResult.Output
            try {
                $lookupRows = @(Convert-JsonArray $lookupJson)
            } catch {
                throw "Die erneute Pull-Request-Abfrage lieferte ungueltiges JSON: $lookupJson"
            }
            $createdPr = $lookupRows | Where-Object {
                -not [string]::IsNullOrWhiteSpace([string]$_.url)
            } | Select-Object -First 1
            if ($null -ne $createdPr) {
                $prUrl = [string]$createdPr.url
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($prUrl)) {
        throw "Pull-Request-URL fehlt trotz erfolgreichem Erstellen bzw. Abfragen."
    }
    Write-Host "Pull Request: $prUrl"

    Write-Host "8/10 GitHub-Actions-Pruefungen abwarten ..."
    if ($prAlreadyMerged) {
        Write-Host "Pull Request ist bereits gemergt; CI-Wartephase wird uebersprungen."
    } else {
    $checksSeen = $false
    $lastCheckMessage = ""
    for ($attempt = 1; $attempt -le 120; $attempt++) {
        $checkResult = Invoke-CapturedNative $gh @(
            "pr", "checks", $prUrl, "--repo", $repository,
            "--json", "name,state,bucket,link"
        )
        $raw = Convert-NativeOutputToText $checkResult.Output
        if ($raw.StartsWith("[")) {
            try {
                $checks = @(Convert-JsonArray $raw)
            } catch {
                $checks = @()
                $lastCheckMessage = "Ungueltige Check-JSON-Antwort: $raw"
            }
            if ($checks.Count -gt 0) {
                $checksSeen = $true
                $failed = @($checks | Where-Object { $_.bucket -in @("fail", "cancel") })
                $pending = @($checks | Where-Object { $_.bucket -eq "pending" })
                if ($failed.Count -gt 0) {
                    $details = $failed | ForEach-Object { "$($_.name): $($_.link)" }
                    throw "GitHub-Pruefung fehlgeschlagen: $($details -join '; ')"
                }
                if ($pending.Count -eq 0) {
                    Write-Host "Alle $($checks.Count) GitHub-Pruefungen erfolgreich."
                    break
                }
                Write-Host "Noch $($pending.Count) Pruefung(en) aktiv ..."
            }
        } elseif ($raw -match 'no checks reported') {
            $lastCheckMessage = $raw
            if ($attempt -eq 1) {
                Write-Host "GitHub hat die neuen Pruefungen noch nicht registriert; warte ..."
            }
        } elseif ($checkResult.ExitCode -ne 0) {
            $lastCheckMessage = if ($raw) { $raw } else { "gh pr checks Exit-Code $($checkResult.ExitCode)" }
            if (($attempt % 6) -eq 1) {
                Write-Warning "Check-Status voruebergehend nicht abrufbar; warte weiter: $lastCheckMessage"
            }
        }
        if ($attempt -eq 120) {
            $reason = if ($checksSeen) {
                "Pruefungen wurden nicht rechtzeitig abgeschlossen."
            } else {
                "GitHub hat keine Pruefungen gemeldet. Letzte Antwort: $lastCheckMessage"
            }
            throw $reason
        }
        Start-Sleep -Seconds 10
    }
    }

    Write-Host "9/10 Pull Request mergen und Release-Tag pushen ..."
    if ($prUrl -notmatch '/pull/([0-9]+)/?$') {
        throw "Pull-Request-Nummer konnte nicht aus der URL gelesen werden: $prUrl"
    }
    $prNumber = $Matches[1]
    $mergeSucceeded = $false
    $mergeCommit = ""
    $lastMergeOutput = ""

    for ($mergeAttempt = 1; $mergeAttempt -le 6; $mergeAttempt++) {
        # REST status is deliberately used here because the normal gh merge
        # path itself talks to GraphQL and may fail transiently.
        $stateResult = Invoke-CapturedNative $gh @("api", "repos/$repository/pulls/$prNumber")
        if ($stateResult.ExitCode -eq 0) {
            try {
                $state = ConvertFrom-Json -InputObject (Convert-NativeOutputToText $stateResult.Output)
                if (-not [string]::IsNullOrWhiteSpace([string]$state.merged_at)) {
                    $mergeSucceeded = $true
                    $mergeCommit = [string]$state.merge_commit_sha
                    break
                }
            } catch {
                # A malformed transient response is handled by the retry.
            }
        }

        Write-Host "Merge-Versuch $mergeAttempt/6 ..."
        $mergeResult = Invoke-CapturedNative $gh @(
            "pr", "merge", $prUrl, "--repo", $repository,
            "--merge", "--delete-branch"
        )
        if ($mergeResult.ExitCode -eq 0) {
            $mergeSucceeded = $true
            break
        }
        $lastMergeOutput = ($mergeResult.Output | ForEach-Object { [string]$_ }) -join " "
        if ($mergeAttempt -lt 6) {
            Write-Warning "GitHub-Merge noch nicht erfolgreich: $lastMergeOutput"
            Start-Sleep -Seconds 10
        }
    }

    if (-not $mergeSucceeded) {
        Write-Warning "GraphQL-Merge blieb erfolglos; versuche den offiziellen REST-Merge-Endpunkt."
        $restMerge = Invoke-CapturedNative $gh @(
            "api", "--method", "PUT", "repos/$repository/pulls/$prNumber/merge",
            "-f", "merge_method=merge"
        )
        if ($restMerge.ExitCode -eq 0) {
            try {
                $restResult = ConvertFrom-Json -InputObject (Convert-NativeOutputToText $restMerge.Output)
                $mergeSucceeded = [bool]$restResult.merged
            } catch {
                $mergeSucceeded = $false
            }
        }
        if (-not $mergeSucceeded) {
            $restMessage = ($restMerge.Output | ForEach-Object { [string]$_ }) -join " "
            throw "Pull Request konnte auch nach Wiederholungen nicht gemergt werden. GraphQL: $lastMergeOutput REST: $restMessage"
        }
    }

    # Do not tag a moving `origin/main`.  Read the exact merge commit from the
    # PR and wait briefly for GitHub's status endpoint to become consistent.
    for ($confirmAttempt = 1; $confirmAttempt -le 30 -and [string]::IsNullOrWhiteSpace($mergeCommit); $confirmAttempt++) {
        $confirmResult = Invoke-CapturedNative $gh @("api", "repos/$repository/pulls/$prNumber")
        if ($confirmResult.ExitCode -eq 0) {
            try {
                $confirmedPr = ConvertFrom-Json -InputObject (Convert-NativeOutputToText $confirmResult.Output)
                if (-not [string]::IsNullOrWhiteSpace([string]$confirmedPr.merged_at)) {
                    $mergeCommit = [string]$confirmedPr.merge_commit_sha
                    break
                }
            } catch {
                # A transient malformed response is retried below.
            }
        }
        Start-Sleep -Seconds 2
    }
    if ([string]::IsNullOrWhiteSpace($mergeCommit)) {
        throw "Der Pull Request wurde gemergt, aber GitHub lieferte keinen Merge-Commit. Es wurde bewusst kein Tag erstellt."
    }

    Invoke-Checked $git @("fetch", "--prune", "origin", "main")
    Invoke-Checked $git @("cat-file", "-e", "$mergeCommit^{commit}")
    Invoke-Checked $git @("merge-base", "--is-ancestor", $mergeCommit, "origin/main")
    # `git tag --list` writes no pipeline object when the tag is absent.
    # Joining an explicit array keeps the value an empty string instead of
    # `$null`, which is important under Windows PowerShell 5.1.
    $localTag = ((@(& $git tag --list $tag) | ForEach-Object { [string]$_ }) -join "`n").Trim()
    if ($localTag) {
        Invoke-Checked $git @("tag", "-d", $tag)
    }
    Invoke-Checked $git @("tag", "-a", $tag, $mergeCommit, "-m", "DA6IT.de Wavelog Offline Logger $tag")
    Invoke-Checked $git @("push", "origin", $tag)
    }

    Write-Host "10/10 Plattform-Builds und GitHub-Release abwarten ..."
    $releaseRun = $null
    for ($attempt = 1; $attempt -le 120; $attempt++) {
        $runsResult = Invoke-CapturedNative $gh @(
            "run", "list", "--repo", $repository, "--workflow", "release.yml",
            "--event", "push", "--limit", "50",
            "--json", "databaseId,headBranch,status,conclusion,url"
        )
        if ($runsResult.ExitCode -eq 0) {
            $runsJson = Convert-NativeOutputToText $runsResult.Output
            if ($runsJson.StartsWith("[")) {
                try {
                    $runs = @(Convert-JsonArray $runsJson)
                    $releaseRun = $runs | Where-Object { [string]$_.headBranch -eq $tag } | Select-Object -First 1
                    if ($releaseRun) { break }
                } catch {
                    # GitHub may briefly return an incomplete response; retry.
                }
            }
        }
        if (($attempt % 12) -eq 0) {
            Write-Host "Release-Workflow ist noch nicht sichtbar; warte weiter ..."
        }
        Start-Sleep -Seconds 5
    }
    if (-not $releaseRun) {
        throw "Der Release-Workflow fuer $tag wurde nicht gefunden."
    }
    Write-Host "Release-Workflow: $($releaseRun.url)"
    Invoke-Checked $gh @("run", "watch", [string]$releaseRun.databaseId, "--repo", $repository, "--exit-status", "--interval", "10")

    $releaseUrl = "https://github.com/$repository/releases/tag/$tag"
    Write-Host ""
    Write-Host "RELEASE ERFOLGREICH: $releaseUrl" -ForegroundColor Green
    if (Test-Path -LiteralPath $expectedExe) {
        Write-Host "Lokale Test-EXE: $expectedExe"
    }
} finally {
    Pop-Location
}
