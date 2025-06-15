import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ============================================================================
# API 키 설정 - 간소화됨!
# ============================================================================

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# PAGE_ID는 더 이상 필요하지 않습니다!
# Notion API Search를 통해 동적으로 페이지를 찾습니다.

# ============================================================================
# 애플리케이션 설정
# ============================================================================

class AppConfig:
    """애플리케이션 전역 설정 클래스"""
    BASE_DIR = Path.cwd()
    OUTPUT_DIR = BASE_DIR / ".etc"
    TEMP_DIR = OUTPUT_DIR / "temp"
    CSS_FILE = BASE_DIR / "portfolio_style.css"
    PDF_FILENAME_TEMPLATE = "{doc_type}_{lang}_{version}.pdf"
    HTML_FILENAME_TEMPLATE = "{doc_type}_{lang}_{version}.html"
    CLAUDE_MODEL = "claude-3-sonnet-20240229"
    CLAUDE_MAX_TOKENS = 2000
    CLAUDE_TIMEOUT = 30
    PDF_FORMAT = "A4"
    PDF_PRINT_BACKGROUND = True
    TRANSLATION_LANGUAGES = {
        "ko": "Korean",
        "en": "English"
    }
    
    @classmethod
    def ensure_directories(cls):
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
        cls.TEMP_DIR.mkdir(exist_ok=True)
    
    @classmethod
    def get_output_filename(cls, doc_type: str, lang: str, file_type: str = "pdf", version: str = "final") -> str:
        template = cls.PDF_FILENAME_TEMPLATE if file_type == "pdf" else cls.HTML_FILENAME_TEMPLATE
        return template.format(doc_type=doc_type, lang=lang, version=version)

# ============================================================================
# 환경 검증 및 초기화 - 간소화됨!
# ============================================================================

def check_environment_on_import():
    """환경 설정 체크 - PAGE_ID는 더 이상 체크하지 않음"""
    missing = []
    if not NOTION_API_KEY:
        missing.append("NOTION_API_KEY 환경변수")
    if not CLAUDE_API_KEY:
        missing.append("CLAUDE_API_KEY 환경변수")
    if not AppConfig.CSS_FILE.exists():
        missing.append("portfolio_style.css 파일")
    
    if missing:
        print("⚠️  환경 설정 경고:")
        for item in missing:
            print(f"   - {item}")
        print("   .env 파일과 필요한 파일들을 확인해주세요.")
        print("   ✅ PAGE_ID는 더 이상 필요하지 않습니다!")

AppConfig.ensure_directories()
if __name__ != "__main__":
    check_environment_on_import()

# ============================================================================
# 설정 예시 템플릿 생성 - 간소화됨!
# ============================================================================

def create_env_template():
    """환경변수 템플릿 파일 생성 - 훨씬 간단해짐"""
    template_content = """# Notion 포트폴리오 자동화 툴 환경설정 (간소화됨!)

# 필수 API 키들
NOTION_API_KEY=your_notion_api_key_here
CLAUDE_API_KEY=your_claude_api_key_here

# 🎉 PAGE_ID들은 더 이상 필요하지 않습니다!
# Integration이 접근할 수 있는 모든 페이지를 자동으로 찾습니다.

# 선택적 설정들 (기본값 사용 가능)
# OUTPUT_DIR=.etc
# TEMP_DIR=.etc/temp
"""
    
    env_file = Path(".env.example")
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(template_content)
    
    print(f"환경변수 템플릿 파일이 생성되었습니다: {env_file}")
    print("이 파일을 .env로 복사하고 API 키들만 입력해주세요.")
    print("✅ PAGE_ID는 더 이상 설정할 필요가 없습니다!")

# ============================================================================
# 개발자 도구 - 간소화됨!
# ============================================================================

def print_current_config():
    """현재 설정 상태 출력 - 간소화됨"""
    print("=== 현재 설정 상태 ===")
    print(f"Notion API Key: {'✅ 설정됨' if NOTION_API_KEY else '❌ 없음'}")
    print(f"Claude API Key: {'✅ 설정됨' if CLAUDE_API_KEY else '❌ 없음'}")
    print(f"CSS 파일: {'✅ 존재' if AppConfig.CSS_FILE.exists() else '❌ 없음'}")
    
    print("\n=== 페이지 접근 방식 ===")
    print("✅ 동적 페이지 검색 (PAGE_ID 불필요)")
    print("   → Integration이 접근할 수 있는 모든 페이지를 자동으로 찾습니다")
    
    validation = {
        "notion_api_key": bool(NOTION_API_KEY),
        "claude_api_key": bool(CLAUDE_API_KEY),
        "css_file_exists": AppConfig.CSS_FILE.exists()
    }
    
    print(f"\n전체 검증 결과: {'✅ 모든 설정 완료' if all(validation.values()) else '⚠️ 일부 설정 필요'}")
    print("💡 팁: PAGE_ID 설정은 더 이상 필요하지 않습니다!")

if __name__ == "__main__":
    # 개발/테스트 모드
    print("Config 모듈 개발자 모드 (v2.0 - PAGE_ID 불필요)")
    print("-" * 50)
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "template":
            create_env_template()
        elif command == "check":
            print_current_config()
        elif command == "validate":
            missing = []
            if not NOTION_API_KEY:
                missing.append("NOTION_API_KEY 환경변수")
            if not CLAUDE_API_KEY:
                missing.append("CLAUDE_API_KEY 환경변수")
            if not AppConfig.CSS_FILE.exists():
                missing.append("portfolio_style.css 파일")
                
            if missing:
                print("❌ 누락된 설정들:")
                for item in missing:
                    print(f"   - {item}")
                print("\n💡 PAGE_ID는 더 이상 체크하지 않습니다!")
                sys.exit(1)
            else:
                print("✅ 모든 설정이 완료되었습니다!")
                print("✅ PAGE_ID 설정 없이도 완벽하게 작동합니다!")
        else:
            print("사용법: python config.py [template|check|validate]")
    else:
        print_current_config()