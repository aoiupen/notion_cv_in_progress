# 숨김 표시 이모지: 사용자가 요청한 ✅ 만 사용합니다
# 주의: 일부 환경에서 변형 셀렉터가 포함된 형태(✅️)가 입력될 수 있으므로 둘 다 허용
HIDE_EMOJI_SET = {"✅", "✅️"}

def _title_starts_with_hide_emoji(title: str) -> bool:
    if not title:
        return False
    t = title.strip()
    for emoji in HIDE_EMOJI_SET:
        if t.startswith(emoji):
            return True
    return False

def has_hide_marker(page_info) -> bool:
    """페이지의 아이콘 또는 타이틀 선두 이모지로 숨김 여부를 판별합니다."""
    try:
        # 페이지 아이콘(emoji) 우선 확인
        icon = page_info.get('icon')
        if icon and icon.get('type') == 'emoji':
            if icon.get('emoji') in HIDE_EMOJI_SET:
                return True
        # 타이틀 선두 이모지 확인
        properties = page_info.get('properties', {})
        for _, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                title_array = prop_data.get('title', [])
                if title_array:
                    title = ''.join([item.get('plain_text', '') for item in title_array])
                    if _title_starts_with_hide_emoji(title):
                        return True
        return False
    except Exception:
        return False

def extract_page_title(page_info):
    """Notion 페이지 정보에서 제목을 추출합니다.
    - 숨김 마커(페이지 아이콘 또는 타이틀 선두 이모지)가 있으면 빈 문자열을 반환합니다.
    - 과거 호환: 괄호 규칙은 제거하고, 이모지 기반만 사용합니다.
    """
    try:
        if has_hide_marker(page_info):
            return ""
        properties = page_info.get('properties', {})
        for _, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                title_array = prop_data.get('title', [])
                if title_array:
                    return ''.join([item['plain_text'] for item in title_array])
        return "Untitled"
    except Exception as e:
        print(f"제목 추출 중 오류: {e}")
        return "Untitled"

def extract_page_title_raw(page_info):
    """괄호 필터 없이 원본 타이틀 그대로 추출합니다."""
    try:
        properties = page_info.get('properties', {})
        for _, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                title_array = prop_data.get('title', [])
                if title_array:
                    return ''.join([item['plain_text'] for item in title_array])
        return "Untitled"
    except Exception as e:
        print(f"제목 추출(raw) 중 오류: {e}")
        return "Untitled"

def strip_hide_marker_from_title(title: str) -> str:
    """선두의 숨김 이모지(✅, ✅️)와 뒤따르는 공백을 제거합니다."""
    if not title:
        return title
    t = title.lstrip()
    prefixes = ["✅️", "✅"]
    for p in prefixes:
        if t.startswith(p):
            # 이모지 다음 한 칸 공백도 함께 제거
            t = t[len(p):].lstrip()
            break
    return t

def extract_page_title_for_tree(page_info) -> str:
    """트리에 표시할 제목: 원본 제목에서 숨김 이모지는 보이지 않게 제거합니다."""
    raw = extract_page_title_raw(page_info)
    return strip_hide_marker_from_title(raw)