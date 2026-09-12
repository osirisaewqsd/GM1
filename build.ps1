[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8:ignore"
$env:LC_CTYPE = "C.UTF-8"
[System.Text.Encoding]::Default = [System.Text.Encoding]::UTF8
try { chcp 65001 > $null } catch { }

if ($PSVersionTable.PSVersion.Major -le 5) {
    $global:ErrorView = "NormalView"
}
if ($null -ne $PSStyle) {
    try { $PSStyle.Formatting.Error = "" } catch {}
    try { $PSStyle.Progress.View = "Minimal" } catch {}
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$cleanMode = $false
foreach ($arg in $args) {
    if ($arg -in "--clean", "-c", "/clean") { $cleanMode = $true }
}
$enableEncrypt = $false
foreach ($arg in $args) {
    if ($arg -in "--encrypt", "-e", "/encrypt") { $enableEncrypt = $true }
}

function Invoke-PySideTrim {
    $pysideDir = Join-Path $projectRoot "dist\猫之琴轻量版\_internal\PySide6"
    if (-not (Test-Path $pysideDir)) {
        Write-Host "[WARN] 未找到 PySide6 目录，跳过精简：$pysideDir" -ForegroundColor Yellow
        return
    }

    Write-Host "正在精简 PySide6 打包目录..." -ForegroundColor Cyan

    $dirsToRemove = @(
        "translations",
        "plugins\generic",
        "plugins\iconengines",
        "plugins\platforminputcontexts"
    )
    foreach ($rel in $dirsToRemove) {
        $target = Join-Path $pysideDir $rel
        if (Test-Path $target) {
            Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "  已删除 $rel" -ForegroundColor Gray
        }
    }

    $imageDir = Join-Path $pysideDir "plugins\imageformats"
    if (Test-Path $imageDir) {
        Get-ChildItem -Path $imageDir -File -Filter "*.dll" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notin @("qico.dll", "qjpeg.dll") } |
            ForEach-Object {
                Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
                Write-Host "  删除 imageformats\$($_.Name)" -ForegroundColor Gray
            }
    }

    $platformsDir = Join-Path $pysideDir "plugins\platforms"
    if (Test-Path $platformsDir) {
        Get-ChildItem -Path $platformsDir -File -Filter "*.dll" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne "qwindows.dll" } |
            ForEach-Object {
                Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
                Write-Host "  删除 platforms\$($_.Name)" -ForegroundColor Gray
            }
    }

    $qtDllsToRemove = @(
        "opengl32sw.dll",
        "Qt6Network.dll",
        "Qt6OpenGL.dll",
        "Qt6Pdf.dll",
        "Qt6Qml.dll",
        "Qt6QmlMeta.dll",
        "Qt6QmlModels.dll",
        "Qt6QmlWorkerScript.dll",
        "Qt6Quick.dll",
        "Qt6VirtualKeyboard.dll"
    )
    foreach ($dll in $qtDllsToRemove) {
        $target = Join-Path $pysideDir $dll
        if (Test-Path $target) {
            Remove-Item $target -Force -ErrorAction SilentlyContinue
            Write-Host "  删除 $dll" -ForegroundColor Gray
        }
    }

    Write-Host "精简完成！" -ForegroundColor Green
}

Write-Host "========================================" -ForegroundColor Cyan
if ($cleanMode) {
    Write-Host " FULL CLEAN BUILD MODE" -ForegroundColor Yellow
} else {
    Write-Host " CACHED BUILD MODE (faster)" -ForegroundColor Green
    Write-Host "   Use  .\build.ps1 --clean  to force full rebuild" -ForegroundColor DarkGray
}
if ($enableEncrypt) {
    Write-Host " [ENCRYPT] PyArmor 加密打包已开启" -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Cleaning old build files..." -ForegroundColor Cyan
if ($cleanMode) {
    if (Test-Path "build") {
        Write-Host "  Removing build directory..." -ForegroundColor Gray
        Remove-Item "build" -Recurse -Force
    }
    if (Test-Path "dist") {
        Write-Host "  Removing dist directory..." -ForegroundColor Gray
        Remove-Item "dist" -Recurse -Force
    }
}
Get-ChildItem -Path . -Filter "*.spec" -File | ForEach-Object {
    Write-Host "  Removing $($_.Name)..." -ForegroundColor Gray
    Remove-Item $_.FullName -Force
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " PyArmor 源码加密..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$encDir = Join-Path $projectRoot "build\enc"
if ($enableEncrypt) {
    if (-not (Get-Command pyarmor -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] 未找到 pyarmor，请先安装：pip install pyarmor" -ForegroundColor Red
        exit 1
    }
    if (Test-Path $encDir) {
        Write-Host "  Cleaning old encrypted files..." -ForegroundColor Gray
        Remove-Item $encDir -Recurse -Force
    }
    Write-Host "[Encrypt] pyarmor gen ..." -ForegroundColor DarkGreen
    pyarmor gen -O $encDir -r main.py core gui utils license --exclude "*/__pycache__/*"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[ERROR] PyArmor 加密失败。" -ForegroundColor Red
        Write-Host "        试用版无法加密超过 32KB 字节码的模块（本项目 main.py 超出限制）。" -ForegroundColor Red
        Write-Host "        请购买 PyArmor 授权后执行 pyarmor reg <注册文件>，再重新运行本脚本。" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "[OK] PyArmor 加密完成: $encDir" -ForegroundColor Green
} else {
    Write-Host "[INFO] 明文打包（默认）。如需 PyArmor 加密：.\build.ps1 -encrypt（需购买授权）" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Running PyInstaller..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$pyside6Excludes = @(
    "PySide6.QtMultimedia", "PySide6.QtWebEngine", "PySide6.QtWebEngineWidgets",
    "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtPositioning",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtTest", "PySide6.QtXml",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebSockets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtGamepad", "PySide6.QtScxml", "PySide6.QtUiTools", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtConcurrent", "PySide6.QtPrintSupport",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtMultimediaWidgets"
)

if ($enableEncrypt) {
    $argsList = @("--clean", "--onedir", "--noconsole", "--noupx", "--noconfirm", "--paths", $encDir, "--paths", $projectRoot)
    $entry = Join-Path $encDir "main.py"
    $runtimeDirs = Get-ChildItem -Path $encDir -Directory -Filter "pyarmor_runtime_*"
    foreach ($rd in $runtimeDirs) {
        $argsList += @("--collect-all", $rd.Name)
    }
} else {
    $argsList = @("--clean", "--onedir", "--noconsole", "--noupx", "--noconfirm", "--paths", $projectRoot)
    $entry = "main.py"
}
foreach ($m in $pyside6Excludes)  { $argsList += @("--exclude-module", $m) }
$argsList += @("-i", "resources\yq.ico")
$argsList += @("--add-data", "resources\yq.ico;resources/")
$argsList += @("--add-data", "resources\adb;resources/adb/")
$argsList += @("-n", "猫之琴轻量版", $entry)

$escapedArgs = ($argsList | ForEach-Object {
    if ($_ -match '[\s";]') {
        '"' + ($_ -replace '"', '\"') + '"'
    } else {
        $_
    }
}) -join ' '
cmd /c "python -m PyInstaller $escapedArgs"
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " BUILD SUCCESS!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Invoke-PySideTrim
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host " BUILD FAILED (exit code $exitCode) - check error messages above." -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Tip: if this is a weird cached error, try:" -ForegroundColor Yellow
    Write-Host "   .\build.ps1 --clean" -ForegroundColor Yellow
}

Write-Host ""
exit $exitCode
