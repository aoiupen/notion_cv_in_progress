import os
import asyncio
import sys
import re
import requests
from bs4 import BeautifulSoup
from notion_client import AsyncClient
from notion_client.errors import APIResponseError # APIResponseError 임포트 추가
from playwright.async_api import async_playwright
from dotenv import load_dotenv
import json

# --- 1. 설정: .env 파일에서 환경변수 불러오기 ---
load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
PAGE_ID = os.getenv("PAGE_ID")
# ORG_ID는 제거됩니다.
OUTPUT_PDF_NAME = "My_Portfolio_Final.pdf"

# 환경변수가 제대로 로드되었는지 확인
if not NOTION_API_KEY or not PAGE_ID:
    print("❌ 오류: .env 파일에 NOTION_API_KEY와 PAGE_ID를 설정해주세요.")
    sys.exit(1)

# 표 스타일 매핑 딕셔너리
NOTION_COLOR_MAP = {
    'default': '#000000',
    'gray': '#787774',
    'brown': '#9F6B53',
    'orange': '#D9730D',
    'yellow': '#CB912F',
    'green': '#448361',
    'blue': '#337EA9',
    'purple': '#9065B0',
    'pink': '#C14C8A',
    'red': '#D44C47'
}
NOTION_BG_MAP = {
    'default': '#FFFFFF',
    'gray_background': '#F1F1EF',
    'brown_background': '#F4EEEE',
    'orange_background': '#FAEBDD',
    'yellow_background': '#FBF3DB',
    'green_background': '#EDF3EC',
    'blue_background': '#E7F3F8',
    'purple_background': '#F6F3F9',
    'pink_background': '#FAF1F5',
    'red_background': '#FDEBEC'
}

CELL_PADDING_PX = 16  # 좌우 합계 (8px + 8px)
TABLE_TOTAL_WIDTH = 100  # % 기준

# --- 첫 번째 수정 지점: get_styles() 함수 ---
def get_styles():
    """PDF에 적용될 CSS 스타일을 반환합니다. (노션 줄간격/구분선/문단 간격 참고)"""
    return """
    /* --- 폰트 및 기본 설정 --- */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

    @page { 
        size: A4; 
        margin: 2cm; 
    }

    body {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
        line-height: 1.6;
        color: #333333;
        font-size: 10.5pt;
    }

    /* --- 제목 스타일 --- */
    h1 { 
    font-size: 2.5em; 
    font-weight: 800; /* 더 굵게 */
    margin: 0 0 0.5em 0; /* 위쪽 마진 제거, 아래쪽 여백 증가 */
    line-height: 1.2; /* 줄간격 조정 */
    color: #2d2d2d; /* 약간 더 진한 색 */
    }
    h2 { 
    font-size: 1.5em; 
    font-weight: 600; 
    margin: 1.2em 0 0.3em 0; 
    line-height: 1.3;
    color: #2d2d2d;
    }
    h3 { 
    font-size: 1.2em; 
    font-weight: 600; 
    margin: 1.0em 0 0.2em 0; 
    line-height: 1.3;
    color: #2d2d2d;
    }

    /* --- 텍스트 요소 --- */
    p { margin: 0.7em 0; line-height: 1.6; }

    /* --- 리스트 스타일 --- */
    ul, ol { margin: 0.25em 0 0.25em 1.5em; padding-left: 1.2em; }
    li { margin: 0.13em 0; line-height: 1.7; }
    li > ul, li > ol { margin: 0.13em 0 0.13em 1.2em; }

    .nested-list { margin-left: 1.2em; margin-top: 0.13em; }
    .nested-list li { margin: 0.13em 0; }

    /* --- 구분선 및 인용문 --- */
    hr { border: 0; border-top: 1px solid #eaeaea; margin: 0.9em 0; }
    blockquote { border-left: 3px solid #ccc; padding-left: 1em; color: #666; margin: 0.5em 0; }

    /* --- 코드 블록 --- */
    pre { 
        background-color: #f8f8f8; 
        padding: 1.2em; 
        border-radius: 6px; 
        white-space: pre-wrap; 
        overflow-wrap: break-word; 
        font-size: 0.9em; 
        margin: 0.5em 0; 
    }

    code { font-family: 'D2Coding', 'Consolas', 'Monaco', monospace; }

    /* --- 링크 --- */
    a { color: #0066cc; text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* --- 이미지 스타일 --- */
    /* 기본 이미지 스타일 */
    img { 
        max-width: 600px !important; 
        max-height: 350px !important; 
        object-fit: contain; 
    }

    /* 노션 블록 이미지 (큰 이미지) */
    .notion-block-image {
        display: block;
        margin: 1em auto;
        width: 100%;
        height: auto;
        max-width: 100% !important; /* 부모 너비 초과 방지 */
    }

    /* 파비콘 (작은 아이콘) */
    .favicon-img {
        width: 1em !important;
        height: 1em !important;
        vertical-align: middle;
        margin-right: 0.2em;
        display: inline !important;
        max-width: none !important; /* 기본 img 스타일 무시 */
        max-height: none !important;
    }

    /* 큰 다이어그램용 */
    .large-diagram { 
        max-width: 100% !important; 
        max-height: 60vh !important; 
    }

    figure { margin: 1.2em 0; width: 100%; }

    /* --- 접기/펼치기 --- */
    details { border: 1px solid #eaeaea; border-radius: 6px; padding: 1.2em; margin: 0.7em 0; }
    summary { font-weight: 600; cursor: default; }

    /* --- 테이블 --- */
    table { 
        width: 100%; 
        border-collapse: collapse; 
        margin: 1em 0; 
        font-size: 0.9em; 
        table-layout: fixed; 
    }

    th, td { 
        border: 1px solid #ddd; 
        padding: 0.5em 0.8em; 
        text-align: left; 
        vertical-align: top; 
        overflow-wrap: break-word; 
        white-space: pre-line; 
    }

    th { background-color: #f2f2f2; font-weight: 600; }

    /* --- 동기화 블록 --- */
    .synced-block-container {
        line-height: 1.6;
    }

    .synced-block-container p {
        margin: 0.7em 0;
    }

    .synced-block-container br {
        display: inline;
    }
    """

def extract_page_title(page_info):
    """Notion 페이지 정보에서 제목을 추출합니다."""
    try:
        properties = page_info.get('properties', {})
        for prop_name, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                title_array = prop_data.get('title', [])
                if title_array:
                    return ''.join([item['plain_text'] for item in title_array])
        return ""
    except Exception as e:
        print(f"제목 추출 중 오류: {e}")
        return ""

def is_youtube_url(url):
    return (
        url.startswith("https://www.youtube.com/") or
        url.startswith("https://youtu.be/")
    )

def get_youtube_info(url):
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    try:
        resp = requests.get(oembed_url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "title": data.get("title", "YouTube Video"),
                "favicon": "https://www.youtube.com/favicon.ico"
            }
    except Exception:
        pass
    return {
        "title": "YouTube Video",
        "favicon": "https://www.youtube.com/favicon.ico"
    }

def is_github_url(url):
    return url.startswith("https://github.com/")

def clean_github_title(title):
    title = re.sub(r'[-·]\s*GitHub.*$', '', title).strip()
    if ' - ' in title:
        parts = title.split(' - ')
        return parts[-1].strip()
    return title.strip()

def get_github_info(url):
    match = re.search(r'github\.com/([^/]+)/([^/?#]+)', url)
    if match:
        owner, repo = match.group(1), match.group(2)
        api_url = f'https://api.github.com/repos/{owner}/{repo}'
        try:
            resp = requests.get(api_url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "title": data.get("name", f"{owner}/{repo}"),
                    "favicon": "https://github.com/fluidicon.png"
                }
        except Exception:
            pass
        return {
            "title": repo,
            "favicon": "https://github.com/fluidicon.png"
        }
    try:
        resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else "GitHub"
            title = clean_github_title(title)
            return {
                "title": title,
                "favicon": "https://github.com/fluidicon.png"
            }
    except Exception:
        pass
    return {
        "title": "GitHub",
        "favicon": "https://github.com/fluidicon.png"
    }

def is_gmail_url(url):
    return url.startswith("mailto:") and ("@gmail.com" in url or "@googlemail.com" in url)

def get_gmail_info(url):
    return {
        "title": url.replace("mailto:", ""),
        "favicon": "https://ssl.gstatic.com/ui/v1/icons/mail/rfr/gmail.ico"
    }

def is_linkedin_url(url):
    return url.startswith("https://www.linkedin.com/") or url.startswith("http://www.linkedin.com/")

def get_linkedin_info(url):
    title_match = re.search(r'linkedin\.com/in/([^/?#]+)', url)
    if title_match:
        profile_name = title_match.group(1).replace('-', ' ').title()
        title = f"{profile_name}'s LinkedIn"
    else:
        title = "LinkedIn Profile"
    return {
        "title": title
    }

# --- 두 번째 수정 지점: rich_text_to_html 함수 ---
def rich_text_to_html(rich_text_array, process_nested_bullets=False):
    if not rich_text_array:
        return ""
    html = ""
    for chunk in rich_text_array:
        href = chunk.get("href")
        if href and is_youtube_url(href):
            info = get_youtube_info(href)
            html += (
                f'<img src="{info["favicon"]}" class="favicon-img">' # class 추가
                f'<a href="{href}" target="_blank" style="font-weight:600; text-decoration: none;">YouTube</a>'
            )
        elif href and is_github_url(href):
            info = get_github_info(href)
            html += (
                f'<img src="{info["favicon"]}" class="favicon-img">' # class 추가
                f'<a href="{href}" target="_blank" style="font-weight:600; text-decoration: none;">GitHub</a>'
            )
        elif href and is_gmail_url(href):
            info = get_gmail_info(href)
            html += (
                f'<img src="{info["favicon"]}" class="favicon-img">' # class 추가
                f'<a href="{href}" target="_blank" style="font-weight:600; text-decoration: none;">{info["title"]}</a>'
            )
        elif href and is_linkedin_url(href):
            info = get_linkedin_info(href)
            html += (
                f'<a href="{href}" target="_blank" style="font-weight:600;color:#0077B5;text-decoration: none;">{info["title"]}</a>'
            )
        else:
            text = chunk.get('plain_text', '').replace('\n', '<br>')
            html += apply_annotations(text, chunk)
    return html

def apply_annotations(text, chunk):
    if not text:
        return ""
    href = chunk.get('href')
    if href:
        return f'<a href="{href}">{text}</a>'
    annotations = chunk.get('annotations', {})
    if annotations.get('bold'): text = f'<strong>{text}</strong>'
    if annotations.get('italic'): text = f'<em>{text}</em>'
    if annotations.get('underline'): text = f'<u>{text}</u>'
    if annotations.get('strikethrough'): text = f'<s>{text}</s>'
    if annotations.get('code'): text = f'<code>{text}</code>'
    return text

def get_cell_style(cell, row_bg=None):
    if not cell:
        return ""
    first = cell[0] if cell else {}
    annotations = first.get('annotations', {})
    color = annotations.get('color', 'default')
    font_weight = 'bold' if annotations.get('bold') else 'normal'
    font_style = 'italic' if annotations.get('italic') else 'normal'
    text_color = NOTION_COLOR_MAP.get(color.replace('_background', ''), '#000')
    if 'background' in color:
        bg_color = NOTION_BG_MAP.get(color, '#fff')
    elif row_bg and row_bg != 'default':
        bg_color = NOTION_BG_MAP.get(row_bg, '#fff')
    else:
        bg_color = '#fff'
    style = f"color:{text_color};background:{bg_color};font-weight:{font_weight};font-style:{font_style};"
    return style

def get_plain_text_from_cell(cell):
    return ''.join([t.get('plain_text', '') for t in cell])

def estimate_column_widths_with_pixel_heuristic(table_rows):
    if not table_rows:
        return []
    col_lengths = []
    max_cols = max(len(row['table_row']['cells']) for row in table_rows)
    for col_idx in range(max_cols):
        max_length = 0
        for row in table_rows:
            cells = row['table_row']['cells']
            if col_idx < len(cells):
                cell_text = get_plain_text_from_cell(cells[col_idx])
                line_lengths = [len(line) for line in cell_text.split('\n')]
                cell_length = max(line_lengths) if line_lengths else 0
                max_length = max(max_length, cell_length)
        col_lengths.append(max_length)
    total_content_length = sum(col_lengths)
    if total_content_length == 0:
        return [100 / max_cols] * max_cols if max_cols > 0 else []
    PIXEL_PER_CHAR = 5.3
    MIN_COL_WIDTH_PX = 40
    estimated_px_widths = [max(MIN_COL_WIDTH_PX, length * PIXEL_PER_CHAR) for length in col_lengths]
    total_estimated_px_width = sum(estimated_px_widths)
    percent_widths = [(px_width / total_estimated_px_width) * 100 for px_width in estimated_px_widths]
    wrap_cols = set()
    for col_idx in range(max_cols):
        for row in table_rows:
            cells = row['table_row']['cells']
            if col_idx < len(cells):
                cell_text = get_plain_text_from_cell(cells[col_idx])
                if '\n' in cell_text:
                    wrap_cols.add(col_idx)
    current_sum = sum(percent_widths)
    remain = 100 - current_sum
    if remain > 0 and wrap_cols:
        add_per_col = remain / len(wrap_cols)
        for idx in wrap_cols:
            percent_widths[idx] += add_per_col
    current_sum2 = sum(percent_widths)
    if current_sum2 != 100 and percent_widths:
        diff = 100 - current_sum2
        percent_widths[0] += diff
    print(f"[최종 percent_widths with wrap 보정] {percent_widths}")
    return percent_widths

async def blocks_to_html(blocks, notion_client):
    """Notion 블록 리스트를 HTML로 변환합니다. (페이지 분류/나누기 없이 순서대로 출력)"""
    if not blocks:
        return ""
    html_parts = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        block_type = block['type']

        # --- 동기화 블록 처리 로직 ---
        if block_type == 'synced_block':
            print(f"DEBUG: blocks_to_html에서 synced_block 처리 중. ID: {block.get('id')}")
            synced_children = block.get('children')
            if synced_children:
                print(f"DEBUG: 동기화 블록에 children 있음. 개수: {len(synced_children)}")
                synced_block_content = await blocks_to_html(synced_children, notion_client)
            else:
                print(f"DEBUG: 동기화 블록에 children 없음 또는 비어있음. ID: {block.get('id')}")
                synced_block_content = ""
            block_html = f"<div class='synced-block-container'>{synced_block_content}</div>"
            html_parts.append(block_html)
            i += 1
            continue # 다음 블록으로 넘어감

        # 리스트 아이템 처리
        if block_type in ['bulleted_list_item', 'numbered_list_item']:
            list_tag = 'ul' if block_type == 'bulleted_list_item' else 'ol'
            list_items = []
            j = i
            while j < len(blocks) and blocks[j]['type'] == block_type:
                current_block = blocks[j]
                item_content = rich_text_to_html(
                    current_block[block_type]['rich_text'],
                    process_nested_bullets=True
                )
                if current_block.get('has_children') and current_block.get('children'):
                    children_html = await blocks_to_html(current_block['children'], notion_client)
                    item_content += children_html
                list_items.append(f"<li>{item_content}</li>")
                j += 1
            list_html = f"<{list_tag}>{''.join(list_items)}</{list_tag}>"
            html_parts.append(list_html)
            i = j
            continue

        # --- 기타 블록 타입 처리 (기존 로직 유지) ---
        block_html = ""
        if block_type == 'heading_1':
            block_html = f"<h1>{rich_text_to_html(block['heading_1']['rich_text'])}</h1>"
        elif block_type == 'heading_2':
            h2_text = rich_text_to_html(block['heading_2']['rich_text'])
            block_html = f"<h2>{h2_text}</h2>"
        elif block_type == 'heading_3':
            h3_text = rich_text_to_html(block['heading_3']['rich_text'])
            block_html = f"<h3>{h3_text}</h3>"
        elif block_type == 'paragraph':
            text = rich_text_to_html(block['paragraph']['rich_text'])
            block_html = f"<p>{text if text.strip() else ' '}</p>"
            if block.get('has_children') and block.get('children'):
                children_html = await blocks_to_html(block['children'], notion_client)
                block_html += f"<div style='margin-left: 2em;'>{children_html}</div>"
        # --- 세 번째 수정 지점: image 블록 처리 ---
        elif block_type == 'image':
            image_data = block['image']
            url = ''
            if image_data.get('file'):
                url = image_data['file']['url']
            elif image_data.get('external'):
                url = image_data['external']['url']
            # class="notion-block-image" 추가
            block_html = f"<figure style='margin:1.2em 0;width:100%;'><img src='{url}' alt='Image' class='notion-block-image'></figure>"
        elif block_type == 'code':
            code_text = rich_text_to_html(block['code']['rich_text'])
            language = block['code'].get('language', '')
            block_html = f"<pre><code class='language-{language}'>{code_text}</code></pre>"
        elif block_type == 'divider':
            block_html = "<hr>"
        elif block_type == 'quote':
            block_html = f"<blockquote>{rich_text_to_html(block['quote']['rich_text'])}</blockquote>"
        elif block_type == 'toggle':
            summary = rich_text_to_html(block['toggle']['rich_text'])
            children_html = ""
            if block.get('has_children') and block.get('children'):
                children_html = await blocks_to_html(block['children'], notion_client)
            block_html = f"<details open><summary>{summary}</summary>{children_html}</details>"
        elif block_type == 'table':
            table_info = block['table']
            has_column_header = table_info.get('has_column_header', False)
            width_ratios = estimate_column_widths_with_pixel_heuristic(block.get('children', []))
            colgroup_html = ''
            if width_ratios:
                colgroup_html = '<colgroup>'
                for ratio in width_ratios:
                    colgroup_html += f'<col style="width:{ratio:.2f}%">'
                colgroup_html += '</colgroup>'
            table_html_content = f"<table>{colgroup_html}"
            if block.get('children'):
                for i_row, row_block in enumerate(block['children']):
                    if row_block['type'] == 'table_row':
                        cells = row_block['table_row']['cells']
                        row_tag = 'th' if has_column_header and i_row == 0 else 'td'
                        row_bg = row_block['table_row'].get('background', 'default')
                        table_html_content += f"<tr style='background:{NOTION_BG_MAP.get(row_bg, '#fff')}'>"
                        for col_idx, cell in enumerate(cells):
                            style = get_cell_style(cell, row_bg=row_bg)
                            width_style = f"width:{width_ratios[col_idx]:.2f}%;" if col_idx < len(width_ratios) else ''
                            table_html_content += f"<{row_tag} style='{style}{width_style}'>{rich_text_to_html(cell)}</{row_tag}>"
                        table_html_content += "</tr>"
            table_html_content += "</table>"
            block_html = table_html_content
        elif block_type == 'callout':
            callout = block['callout']
            icon_html = ''
            if callout.get('icon'):
                icon = callout['icon']
                if icon['type'] == 'emoji':
                    icon_html = f"{icon['emoji']} "
            callout_text = rich_text_to_html(callout['rich_text'])
            children_html = ''
            if block.get('has_children') and block.get('children'):
                children_html = await blocks_to_html(block['children'], notion_client)
            block_html = (
                f"<div style='background:#f7f6f3;border-radius:8px;padding:0.001em 1em;margin:0.7em 0;'>"
                f"{icon_html}{callout_text}{children_html}</div>"
            )
        # 이 부분이 처리되지 않은 블록 타입에 대한 대비 (예: Unsupported 블록)
        elif 'type' in block:
            print(f"경고: 알 수 없거나 지원되지 않는 블록 타입: {block_type}. 블록 ID: {block.get('id')}")
            # 개발/디버깅을 위해 이 블록을 HTML에 포함시키지 않거나, 대체 텍스트를 넣을 수 있습니다.
            block_html = f"<p><em>[Unsupported Block Type: {block_type}]</em></p>"

        html_parts.append(block_html)
        i += 1
    return '\n'.join(html_parts)

# find_block_by_text_in_page 함수 제거됩니다.

async def get_top_level_parent_id(notion_client, block_id):
    """
    주어진 블록 ID의 최상위 부모 (페이지 또는 데이터베이스) ID를 재귀적으로 찾습니다.
    이 ID에 권한을 부여해야 합니다.
    반환 값: (최상위 부모 ID, 'page' 또는 'database')
    """
    current_id = block_id
    while True:
        try:
            block_info = await notion_client.blocks.retrieve(current_id)
            parent = block_info.get('parent', {})
            parent_type = parent.get('type')

            if parent_type == 'page_id':
                print(f"  [get_top_level_parent] 블록 {current_id}의 최상위 부모는 페이지: {parent.get('page_id')}")
                return parent.get('page_id'), 'page'
            elif parent_type == 'database_id':
                print(f"  [get_top_level_parent] 블록 {current_id}의 최상위 부모는 데이터베이스: {parent.get('database_id')}")
                return parent.get('database_id'), 'database'
            elif parent_type == 'block_id':
                # 부모가 블록인 경우, 그 부모 블록으로 다시 추적
                next_id = parent.get('block_id')
                print(f"  [get_top_level_parent] 블록 {current_id}의 부모는 블록: {next_id}. 계속 추적.")
                current_id = next_id
            elif parent_type == 'workspace':
                # 최상위 워크스페이스에 속한 경우 (대부분 페이지)
                # 이 경우는 현재 블록 ID 자체가 최상위 페이지 ID일 가능성이 높음.
                print(f"  [get_top_level_parent] 블록 {current_id}는 워크스페이스 직속. 자신을 최상위 페이지 ID로 간주.")
                return current_id, 'page' # 페이지 자체인 경우
            else:
                print(f"  [get_top_level_parent] 블록 {current_id}의 알 수 없는 부모 타입: {parent_type}")
                return None, None # 알 수 없는 부모 타입

        except APIResponseError as e:
            if e.code == "block_not_found":
                print(f"  [get_top_level_parent] 블록 {current_id}를 찾을 수 없습니다. (권한 문제 또는 삭제됨)")
            else:
                print(f"  [get_top_level_parent] API 오류 발생 ({current_id}): {e}")
            return None, None
        except Exception as e:
            print(f"  [get_top_level_parent] 예측 불가능한 오류 발생 ({current_id}): {e}")
            return None, None


async def get_synced_block_original_and_top_parent(notion, block):
    current_block = block
    # 1. synced_block 사본이면 원본을 재귀적으로 추적
    if current_block.get('type') == 'synced_block':
        synced_from = current_block['synced_block'].get('synced_from')
        if synced_from and 'block_id' in synced_from:
            try:
                original_block = await notion.blocks.retrieve(synced_from['block_id'])
                # 재귀 호출하여 원본 블록의 원본 및 최상위 부모를 찾습니다.
                return await get_synced_block_original_and_top_parent(notion, original_block)
            except Exception as e:
                # 오류 발생 시 출력 메시지 수정 (AttributeError 방지)
                print(f"[get_synced_block] 원본 블록 접근 실패 (ID: {synced_from.get('block_id', '알 수 없음')}): 코드={getattr(e, 'code', 'N/A')}, 상세={e}")
                # ORG_ID 관련 대체 로직 제거
                print(f"[get_synced_block] 원본 블록을 찾을 수 없거나 접근 권한이 없습니다. (ID: {synced_from.get('block_id', '알 수 없음')})")
                return None, None, None # 원본을 찾을 수 없거나 접근 실패 시

    # 2. 최상위 부모 추적
    block_id_to_find_parent = current_block['id'] # 현재 블록의 ID를 시작점으로 설정
    parent = current_block.get('parent', {})
    parent_type = parent.get('type')

    # 'block_id' 타입의 부모를 계속 추적하여 최상위 페이지/데이터베이스/워크스페이스 부모를 찾습니다.
    while parent_type == 'block_id':
        next_id = parent.get('block_id')
        try:
            parent_block = await notion.blocks.retrieve(next_id)
            parent = parent_block.get('parent', {})
            parent_type = parent.get('type')
            block_id_to_find_parent = parent_block['id'] # 현재 처리 중인 최상위 블록 ID 업데이트
        except Exception as e:
            print(f"[get_synced_block] 부모 블록 추적 실패 (ID: {next_id}): {e}")
            # 부모 블록을 찾지 못하면 현재 블록과 None 반환 (최상위 부모 알 수 없음)
            return current_block, None, None

    # 최상위 부모 타입에 따른 반환
    if parent_type == 'page_id':
        print(f"[get_synced_block] 최상위 부모: page_id={parent.get('page_id')}")
        return current_block, parent.get('page_id'), 'page'
    elif parent_type == 'database_id':
        print(f"[get_synced_block] 최상위 부모: database_id={parent.get('database_id')}")
        return current_block, parent.get('database_id'), 'database'
    elif parent_type == 'workspace':
        print(f"[get_synced_block] 최상위 부모: workspace (page로 간주) id={block_id_to_find_parent}")
        # workspace의 경우, Notion API는 특정 페이지 ID를 제공하지 않으므로
        # 현재 추적 중인 최상위 블록의 ID를 최상위 부모 ID로 간주합니다.
        return current_block, block_id_to_find_parent, 'page'
    else:
        print(f"[get_synced_block] 최상위 부모 타입 알 수 없음: {parent_type}. 블록 ID: {current_block.get('id')}")
        return current_block, None, None


async def fetch_all_child_blocks(notion, block_id):
    blocks = []
    try:
        response = await notion.blocks.children.list(block_id=block_id, page_size=100)
        blocks.extend(response['results'])
        next_cursor = response.get('next_cursor')
        while next_cursor:
            response = await notion.blocks.children.list(
                block_id=block_id,
                page_size=100,
                start_cursor=next_cursor
            )
            blocks.extend(response['results'])
            next_cursor = response.get('next_cursor')
    except Exception as e:
        print(f"블록 가져오기 오류: {e}")
        return []

    processed_blocks = [] # 새로운 리스트를 만들어 처리된 블록을 저장
    for block in blocks:
        # 동기화된 블록이면 항상 원본을 따라가고, 최상위 부모도 추적
        if block.get('type') == 'synced_block':
            orig_block, top_parent_id, top_parent_type = await get_synced_block_original_and_top_parent(notion, block)
            if orig_block is None:
                print(f"경고: 동기화 블록 {block.get('id')}의 원본을 찾거나 접근할 수 없어 건너뜜.")
                continue  # 원본도 못 찾으면 이 블록은 건너뜜

            # 원본 블록의 children 처리:
            # 원본 블록도 일반 블록처럼 'has_children'을 체크하고,
            # 다시 fetch_all_child_blocks를 재귀적으로 호출하여 모든 자식 블록을 가져옵니다.
            # 이렇게 해야 원본 동기화 블록 내부에 있는 다른 동기화 블록이나 복합 블록들이
            # 올바르게 파싱되고 처리될 수 있습니다.
            if orig_block.get('has_children'):
                orig_block['children'] = await fetch_all_child_blocks(notion, orig_block['id'])

            # 여기서 중요한 점: processed_blocks에 추가하는 것은 'orig_block' 그 자체입니다.
            # 이 'orig_block'은 이제 자신의 자식 블록 정보(orig_block['children'])를 포함하게 됩니다.
            # 그리고 blocks_to_html에서 이 orig_block의 type이 'synced_block'일 때
            # block['synced_block']['children']을 다시 blocks_to_html로 넘겨주므로,
            # 원본 블록의 자식들은 올바르게 렌더링됩니다.
            processed_blocks.append(orig_block)
            print(f"[fetch_all_child_blocks] 동기화 블록의 최상위 부모: {top_parent_id} (타입: {top_parent_type})")
        # 일반 블록의 children 처리 (이 부분은 기존과 동일)
        elif block.get('has_children'):
            block['children'] = await fetch_all_child_blocks(notion, block['id'])
            processed_blocks.append(block)
        else:
            processed_blocks.append(block) # 자식이 없는 일반 블록도 추가

    return processed_blocks # 처리된 블록 리스트 반환

async def main():
    print("--- Notion to PDF (분류 없이 전체 인쇄) ---")
    notion = AsyncClient(auth=NOTION_API_KEY)
    try:
        page_info = await notion.pages.retrieve(page_id=PAGE_ID)
        page_title = extract_page_title(page_info)
        print(f"   페이지 제목: {page_title}")
    except Exception as e:
        print(f"   페이지 제목을 가져오지 못했습니다: {e}")
        page_title = ""
    print(f"페이지({PAGE_ID}) 전체 블록을 가져오는 중...")
    blocks = await fetch_all_child_blocks(notion, PAGE_ID)
    print("HTML 변환 중...")
    content_html = await blocks_to_html(blocks, notion)
    styles = get_styles()
    full_html = f"""
    <!DOCTYPE html>
    <html lang=\"ko\">
    <head>
        <meta charset=\"UTF-8\">
        <title>{page_title}</title>
        <style>{styles}</style>
    </head>
    <body>
        <h1>{page_title}</h1>
        <div style='height: 0.3em;'></div>
        {content_html}
    </body>
    </html>
    """
    # HTML도 저장
    os.makedirs(".etc", exist_ok=True)
    html_path = os.path.join(".etc", "My_Portfolio_Final.html")
    pdf_path = os.path.join(".etc", OUTPUT_PDF_NAME)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print("PDF 변환 중...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(full_html, wait_until="networkidle")
            await page.pdf(path=pdf_path, format="A4", print_background=True)
            await browser.close()
        print(f"\n🎉 성공! '{os.path.abspath(pdf_path)}' 파일이 생성되었습니다.")
    except Exception as e:
        print(f"\n❌ PDF 생성 중 오류 발생: {e}")
        print("   - playwright install 명령어를 실행했는지 확인하세요.")

if __name__ == "__main__":
    asyncio.run(main())