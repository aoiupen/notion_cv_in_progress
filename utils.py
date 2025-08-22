def extract_page_title(page_info):
    """Notion 페이지 정보에서 제목을 추출합니다."""
    try:
        properties = page_info.get('properties', {})
        for prop_name, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                title_array = prop_data.get('title', [])
                if title_array:
                    title = ''.join([item['plain_text'] for item in title_array])
                    # 제목이 괄호로 시작하면 빈 문자열 반환
                    if title.strip().startswith('('):
                        return ""
                    return title
        return "Untitled"
    except Exception as e:
        print(f"제목 추출 중 오류: {e}")
        return "Untitled" 