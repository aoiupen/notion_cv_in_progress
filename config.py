import os
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

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

# 기본 PAGE_ID는 한글 이력서 기본
PAGE_ID = PAGE_ID_MAP["ko_cv_b_none"] 