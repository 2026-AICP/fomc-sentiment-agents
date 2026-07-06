# SentiBoard 대시보드 실행 (Windows) — dashboard/app.py
#
# 사용:  powershell -ExecutionPolicy Bypass -File scripts\run_dashboard.ps1
#        powershell -ExecutionPolicy Bypass -File scripts\run_dashboard.ps1 -Port 8080
#
# 하는 일:
#   1) 한글 사용자명 경로에서 생기는 인증서(curl 77)·TEMP 문제를 ASCII 경로로 우회
#      (대시보드는 DB만 읽어 필수는 아니나, 같은 세션에서 파이프라인도 돌릴 수 있게 미리 설정)
#   2) streamlit 실행 → 브라우저 자동 열림
#
# 사전: py -m pip install -r requirements.txt  (streamlit 포함)

param(
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"

# 저장소 루트 = 이 스크립트의 상위 폴더
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# ── 한글 경로 우회: 인증서를 ASCII 경로로 복사 + 환경변수 ──
$CertDir = "C:\aicp_cert"
$CertPem = Join-Path $CertDir "cacert.pem"
if (-not (Test-Path $CertPem)) {
    New-Item -ItemType Directory -Force $CertDir | Out-Null
    # certifi 인증서를 파이썬 안에서 복사(한글 경로 인코딩 깨짐 방지)
    py -c "import certifi,shutil; shutil.copy(certifi.where(), r'$CertPem')"
}
$env:CURL_CA_BUNDLE = $CertPem
$env:SSL_CERT_FILE  = $CertPem

$TmpDir = "C:\aicp_tmp"
if (-not (Test-Path $TmpDir)) { New-Item -ItemType Directory -Force $TmpDir | Out-Null }
$env:TMP  = $TmpDir
$env:TEMP = $TmpDir

$env:PYTHONUTF8 = "1"

# streamlit 첫 실행 이메일 프롬프트가 뜨면 멈추므로, 빈 credentials 로 미리 건너뜀
# (PowerShell 5.1 의 -Encoding utf8 은 BOM 을 붙여 TOML 을 깨뜨리므로 BOM 없이 기록)
$CredDir = Join-Path $env:USERPROFILE ".streamlit"
$CredFile = Join-Path $CredDir "credentials.toml"
if (-not (Test-Path $CredFile)) {
    New-Item -ItemType Directory -Force $CredDir | Out-Null
    [System.IO.File]::WriteAllText($CredFile, "[general]`r`nemail = `"`"`r`n",
        (New-Object System.Text.UTF8Encoding $false))
}

Write-Host "SentiBoard 실행 → http://localhost:$Port" -ForegroundColor Green
py -m streamlit run dashboard/app.py --server.port=$Port --browser.gatherUsageStats=false
