# install.ps1
# Notion PDF Exporter 환경 자동 세팅 스크립트 (Windows PowerShell)

Write-Host "=== Notion PDF Exporter 환경 자동 설치 시작 ==="

# 1. Python 3.9+ 설치 여부 확인
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Python이 설치되어 있지 않습니다. python.org에서 Python 3.9 이상을 설치해 주세요."
    exit 1
}

# 2. venv 가상환경 생성
if (-not (Test-Path ".venv")) {
    Write-Host "가상환경(.venv) 생성 중..."
    python -m venv .venv
} else {
    Write-Host "가상환경(.venv)이 이미 존재합니다."
}

# 3. 가상환경 활성화
Write-Host "가상환경 활성화..."
.\\.venv\\Scripts\\Activate.ps1

# 4. pip 최신화 및 패키지 설치
Write-Host "pip 업그레이드 및 requirements.txt 설치..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Playwright 브라우저 설치
Write-Host "Playwright 브라우저 바이너리 설치..."
playwright install

Write-Host "=== 설치 완료! ==="
Write-Host "1) .env 파일을 프로젝트 루트에 생성하고, NOTION_API_KEY를 입력하세요."
Write-Host "2) 아래 명령어로 실행하세요:"
Write-Host "   .\\.venv\\Scripts\\Activate.ps1"
Write-Host "   python main.py"