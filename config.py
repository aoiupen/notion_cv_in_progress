import os
from typing import Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ============================================================================
# API 키 설정
# ============================================================================

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# ============================================================================
# 페이지 ID 매핑 (개선된 구조)
# ============================================================================

# 기존 방식 호환성 유지
PAGE_ID_MAP = {
    "ko_cv_b_none": os.getenv("PAGE_ID_KO_CV_B_NONE"),
    "en_cv_b_none": os.getenv("PAGE_ID_EN_CV_B_NONE"),
    "ko_cv_b_rule": os.getenv("PAGE_ID_KO_CV_B_RULE"),
    "en_cv_b_rule": os.getenv("PAGE_ID_EN_CV_B_RULE"),
    "ko_pf_b_none": os.getenv("PAGE_ID_KO_PF_B_NONE"),
    "en_pf_b_none": os.getenv("PAGE_ID_EN_PF_B_NONE"),
    "ko_pf_e_none": os.getenv("PAGE_ID_KO_PF_E_NONE"),
    "en_pf_e_none": os.getenv("PAGE_ID_EN_PF_E_NONE"),
}

# 새로운 구조화된 페이지 ID 매핑
STRUCTURED_PAGE_MAP = {
    "resume": {
        "ko": {
            "basic": os.getenv("PAGE_ID_KO_CV_B_NONE"),
            "with_rule": os.getenv("PAGE_ID_KO_CV_B_RULE"),
        },
        "en": {
            "basic": os.getenv("PAGE_ID_EN_CV_B_NONE"),
            "with_rule": os.getenv("PAGE_ID_EN_CV_B_RULE"),
        }
    },
    "portfolio": {
        "ko": {
            "basic": os.getenv("PAGE_ID_KO_PF_B_NONE"),
            "expanded": os.getenv("PAGE_ID_KO_PF_E_NONE"),
        },
        "en": {
            "basic": os.getenv("PAGE_ID_EN_PF_B_NONE"),
            "expanded": os.getenv("PAGE_ID_EN_PF_E_NONE"),
        }
    }
}

# 기본 PAGE_ID (호환성 유지)
PAGE_ID = PAGE_ID_MAP.get("ko_cv_b_none")

# ============================================================================
# 애플리케이션 설정
# ============================================================================

class AppConfig:
    """애플리케이션 전역 설정 클래스"""
    
    # 디렉토리 설정
    BASE_DIR = Path.cwd()
    OUTPUT_DIR = BASE_DIR / ".etc"
    TEMP_DIR = OUTPUT_DIR / "temp"
    CSS_FILE = BASE_DIR / "portfolio_style.css"
    
    # 파일명 템플릿
    PDF_FILENAME_TEMPLATE = "{doc_type}_{lang}_{version}.pdf"
    HTML_FILENAME_TEMPLATE = "{doc_type}_{lang}_{version}.html"
    
    # API 설정
    CLAUDE_MODEL = "claude-3-sonnet-20240229"
    CLAUDE_MAX_TOKENS = 2000
    CLAUDE_TIMEOUT = 30
    
    # PDF 설정
    PDF_FORMAT = "A4"
    PDF_PRINT_BACKGROUND = True
    
    # 번역 설정
    TRANSLATION_LANGUAGES = {
        "ko": "Korean",
        "en": "English"
    }
    
    @classmethod
    def ensure_directories(cls):
        """필요한 디렉토리들을 생성합니다."""
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
        cls.TEMP_DIR.mkdir(exist_ok=True)
    
    @classmethod
    def get_page_id(cls, doc_type: str, lang: str, version: str = "basic") -> Optional[str]:
        """구조화된 방식으로 페이지 ID를 가져옵니다."""
        try:
            return STRUCTURED_PAGE_MAP[doc_type][lang][version]
        except KeyError:
            # 기존 방식으로 fallback
            legacy_key = f"{lang}_{doc_type[:2]}_b_none"
            return PAGE_ID_MAP.get(legacy_key)
    
    @classmethod
    def get_output_filename(cls, doc_type: str, lang: str, file_type: str = "pdf", version: str = "final") -> str:
        """출력 파일명을 생성합니다."""
        template = cls.PDF_FILENAME_TEMPLATE if file_type == "pdf" else cls.HTML_FILENAME_TEMPLATE
        return template.format(doc_type=doc_type, lang=lang, version=version)
    
    @classmethod
    def validate_environment(cls) -> Dict[str, bool]:
        """환경 설정 검증"""
        checks = {
            "notion_api_key": bool(NOTION_API_KEY),
            "claude_api_key": bool(CLAUDE_API_KEY),
            "css_file_exists": cls.CSS_FILE.exists(),
            "has_page_ids": any(PAGE_ID_MAP.values())
        }
        return checks
    
    @classmethod
    def get_missing_requirements(cls) -> list:
        """누락된 필수 요소 목록 반환"""
        validation = cls.validate_environment()
        missing = []
        
        if not validation["notion_api_key"]:
            missing.append("NOTION_API_KEY 환경변수")
        if not validation["claude_api_key"]:
            missing.append("CLAUDE_API_KEY 환경변수")
        if not validation["css_file_exists"]:
            missing.append("portfolio_style.css 파일")
        if not validation["has_page_ids"]:
            missing.append("PAGE_ID 환경변수들")
        
        return missing


# ============================================================================
# 레거시 호환성 함수들
# ============================================================================

def get_legacy_page_id_map() -> Dict[str, str]:
    """기존 방식의 페이지 ID 맵 반환 (호환성 유지)"""
    return PAGE_ID_MAP.copy()


def get_page_id_by_rule_selector(rule_code: str) -> Optional[str]:
    """ui_rule_selector.py와의 호환성을 위한 함수"""
    return PAGE_ID_MAP.get(rule_code)


# ============================================================================
# 환경 검증 및 초기화
# ============================================================================

def check_environment_on_import():
    """임포트 시 환경 검증"""
    missing = AppConfig.get_missing_requirements()
    if missing:
        print("⚠️  환경 설정 경고:")
        for item in missing:
            print(f"   - {item}")
        print("   .env 파일과 필요한 파일들을 확인해주세요.")


# 초기화 실행
AppConfig.ensure_directories()
if __name__ != "__main__":
    check_environment_on_import()


# ============================================================================
# 설정 예시 템플릿 생성
# ============================================================================

def create_env_template():
    """환경변수 템플릿 파일 생성"""
    template_content = """# Notion 포트폴리오 자동화 툴 환경설정

# API 키들
NOTION_API_KEY=your_notion_api_key_here
CLAUDE_API_KEY=your_claude_api_key_here

# 이력서 페이지 ID들
PAGE_ID_KO_CV_B_NONE=your_korean_resume_basic_page_id
PAGE_ID_EN_CV_B_NONE=your_english_resume_basic_page_id
PAGE_ID_KO_CV_B_RULE=your_korean_resume_with_rules_page_id
PAGE_ID_EN_CV_B_RULE=your_english_resume_with_rules_page_id

# 포트폴리오 페이지 ID들
PAGE_ID_KO_PF_B_NONE=your_korean_portfolio_basic_page_id
PAGE_ID_EN_PF_B_NONE=your_english_portfolio_basic_page_id
PAGE_ID_KO_PF_E_NONE=your_korean_portfolio_expanded_page_id
PAGE_ID_EN_PF_E_NONE=your_english_portfolio_expanded_page_id

# 선택적 설정들
# OUTPUT_DIR=.etc
# TEMP_DIR=.etc/temp
"""
    
    env_file = Path(".env.example")
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(template_content)
    
    print(f"환경변수 템플릿 파일이 생성되었습니다: {env_file}")
    print("이 파일을 .env로 복사하고 실제 값들을 입력해주세요.")


# ============================================================================
# 개발자 도구
# ============================================================================

def print_current_config():
    """현재 설정 상태 출력"""
    print("=== 현재 설정 상태 ===")
    print(f"Notion API Key: {'✅ 설정됨' if NOTION_API_KEY else '❌ 없음'}")
    print(f"Claude API Key: {'✅ 설정됨' if CLAUDE_API_KEY else '❌ 없음'}")
    print(f"CSS 파일: {'✅ 존재' if AppConfig.CSS_FILE.exists() else '❌ 없음'}")
    
    print("\n=== 페이지 ID 현황 ===")
    for key, value in PAGE_ID_MAP.items():
        status = "✅ 설정됨" if value else "❌ 없음"
        print(f"{key}: {status}")
    
    validation = AppConfig.validate_environment()
    print(f"\n전체 검증 결과: {'✅ 모든 설정 완료' if all(validation.values()) else '⚠️ 일부 설정 필요'}")


if __name__ == "__main__":
    # 개발/테스트 모드
    print("Config 모듈 개발자 모드")
    print("-" * 40)
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "template":
            create_env_template()
        elif command == "check":
            print_current_config()
        elif command == "validate":
            missing = AppConfig.get_missing_requirements()
            if missing:
                print("❌ 누락된 설정들:")
                for item in missing:
                    print(f"   - {item}")
                sys.exit(1)
            else:
                print("✅ 모든 설정이 완료되었습니다!")
        else:
            print("사용법: python config.py [template|check|validate]")
    else:
        print_current_config() 