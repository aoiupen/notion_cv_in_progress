import os
import asyncio
import sys
import re
import requests
import base64
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from notion_client import AsyncClient
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from config import NOTION_API_KEY, CLAUDE_API_KEY, PAGE_ID
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLabel, QSizePolicy
from ui_rule_selector import RuleSelectorWidget
from mainsub import get_styles, fetch_all_child_blocks, blocks_to_html, extract_page_title

# --- 1. 설정: .env 파일에서 환경변수 불러오기 ---
load_dotenv()

# 환경변수가 제대로 로드되었는지 확인
if not NOTION_API_KEY or not PAGE_ID:
    print("❌ 오류: .env 파일에 NOTION_API_KEY와 PAGE_ID를 설정해주세요.")
    sys.exit(1)

# 표 스타일 매핑 딕셔너리 추가
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

def get_styles():
    """PDF에 적용될 CSS 스타일을 반환합니다."""
    return """
    /* --- 폰트 및 기본 설정 --- */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
    @page { size: A4; margin: 2cm; }
    body {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
        line-height: 1.6;
        color: #333333;
        -webkit-font-smoothing: antialiased;
        font-size: 10.5pt; 
    }
    h1 { font-size: 2.5em; margin: 1.2em 0 0.1em 0; }
    h2 { font-size: 1.8em; margin: 1.1em 0 0.4em 0; }
    h3 { font-size: 1.2em; margin: 0.9em 0 0.3em 0; }
    p { margin: 0.7em 0 0.7em 0; line-height: 1.6; }
    .mention-inline { line-height: 1.1; }
    ul, ol { margin: 0.25em 0 0.25em 1.5em; padding-left: 1.2em; }
    li { margin: 0.13em 0; line-height: 1.7; }
    li > ul, li > ol { margin: 0.13em 0 0.13em 1.2em; }
    .nested-list { margin-left: 1.2em; margin-top: 0.13em; }
    .nested-list li { margin: 0.13em 0; }
    hr { border: 0; border-top: 1px solid #eaeaea; margin: 0.9em 0 0.9em 0; }
    blockquote { border-left: 3px solid #ccc; padding-left: 1em; color: #666; margin: 0.5em 0; }
    pre { background-color: #f8f8f8; padding: 1.2em; border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; font-size: 0.9em; margin: 0.5em 0; }
    code { font-family: 'D2Coding', 'Consolas', 'Monaco', monospace; }
    a { color: #0066cc; text-decoration: none; }
    a:hover { text-decoration: underline; }
    img { max-width: 600px !important; max-height: 350px !important; object-fit: contain; margin: 1em auto; display: block; }
    .large-diagram { max-width: 700px !important; max-height: 400px !important; }
    figure { margin: 1.2em 0; width: 100%; }
    details { border: 1px solid #eaeaea; border-radius: 6px; padding: 1.2em; margin: 0.7em 0; }
    summary { font-weight: 600; cursor: default; }
    table { width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 0.9em; table-layout: fixed; }
    th, td { border: 1px solid #ddd; padding: 0.5em 0.8em; text-align: left; vertical-align: top; word-wrap: break-word; word-break: break-all; white-space: pre-line; }
    th { background-color: #f2f2f2; font-weight: 600; }
    /* 동기화 블록도 동일하게 */
    .synced-block-container {
        line-height: 1.6;
    }
    .synced-block-container p {
        margin: 0.7em 0 0.7em 0;
        line-height: 1.6;
    }
    .synced-block-container br {
        display: inline;
    }
    """


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
    # " - GitHub" 또는 "· GitHub" 뒤는 모두 제거
    title = re.sub(r'[-·]\\s*GitHub.*$', '', title).strip()
    # 저장소: "설명 - 사용자/저장소" → "사용자/저장소"만 남기기
    if ' - ' in title:
        parts = title.split(' - ')
        # 마지막 파트가 "사용자/저장소" 또는 "사용자명"일 확률이 높음
        return parts[-1].strip()
    return title.strip()


def get_github_info(url):
    # URL에서 owner/repo 추출
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
        # fallback: URL에서 repo명만 추출
        return {
            "title": repo,
            "favicon": "https://github.com/fluidicon.png"
        }
    # 프로필 등 기타 링크는 기존 방식 유지
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


def rich_text_to_html(rich_text_array, process_nested_bullets=False):
    """
    Notion의 rich_text 객체를 HTML로 변환합니다.
    process_nested_bullets가 True인 경우, 텍스트 내의 불릿 포인트를 처리합니다.
    """
    if not rich_text_array:
        return ""
    
    html = ""
    full_text = ""
    
    # 전체 텍스트 조합
    for chunk in rich_text_array:
        href = chunk.get("href")
        if href and is_youtube_url(href):
            info = get_youtube_info(href)
            html += (
                f'<span style="display:inline-flex;align-items:center;gap:0.4em;">'
                f'<img src="{info["favicon"]}" style="width:1em;height:1em;vertical-align:middle;">'
                f'<a href="{href}" target="_blank" style="font-weight:600;">{info["title"]}</a>'
                f'</span>'
            )
        elif href and is_github_url(href):
            info = get_github_info(href)
            html += (
                f'<span style="display:inline-flex;align-items:center;gap:0.4em;">'
                f'<img src="{info["favicon"]}" style="width:1em;height:1em;vertical-align:middle;">'
                f'<a href="{href}" target="_blank" style="font-weight:600;">{info["title"]}</a>'
                f'</span>'
            )
        elif href and is_gmail_url(href):
            info = get_gmail_info(href)
            html += (
                f'<span style="display:inline-flex;align-items:center;gap:0.4em;">'
                f'<img src="{info["favicon"]}" style="width:1em;height:1em;vertical-align:middle;">'
                f'<a href="{href}" target="_blank" style="font-weight:600;">{info["title"]}</a>'
                f'</span>'
            )
        else:
            # plain_text의 \n을 <br>로 변환하여 줄바꿈 반영
            text = chunk.get('plain_text', '').replace('\n', '<br>')
            html += apply_annotations(text, chunk)
    
    # 불릿 포인트 처리가 필요한 경우
    if process_nested_bullets and ('•' in html or '\n' in html):
        # 첫 번째 줄과 나머지 줄들을 분리
        lines = html.split('\n')
        
        # 첫 번째 줄은 메인 리스트 아이템
        if lines[0].strip():
            # 첫 줄에 대한 스타일 적용
            first_line_html = lines[0]
            html = first_line_html
            
            # 나머지 줄들에서 불릿 포인트 찾기
            nested_items = []
            for line in lines[1:]:
                line = line.strip()
                if line.startswith('•'):
                    nested_items.append(line[1:].strip())
            
            # 중첩된 불릿 포인트가 있으면 처리
            if nested_items:
                html += '<ul class="nested-list">'
                for item in nested_items:
                    html += f'<li>{item}</li>'
                html += '</ul>'
        else:
            # 첫 줄이 비어있는 경우, 전체를 처리
            html = ''.join(lines)
    return html


def apply_annotations(text, chunk):
    """텍스트에 Notion 주석(bold, italic 등)을 적용합니다."""
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
    # cell: rich_text 리스트
    if not cell:
        return ""
    first = cell[0] if cell else {}
    annotations = first.get('annotations', {})
    color = annotations.get('color', 'default')
    font_weight = 'bold' if annotations.get('bold') else 'normal'
    font_style = 'italic' if annotations.get('italic') else 'normal'
    text_color = NOTION_COLOR_MAP.get(color.replace('_background', ''), '#000')
    # 배경색 우선순위: rich_text color가 *_background면 그걸로, 아니면 row_bg, 아니면 흰색
    if 'background' in color:
        bg_color = NOTION_BG_MAP.get(color, '#fff')
    elif row_bg and row_bg != 'default':
        bg_color = NOTION_BG_MAP.get(row_bg, '#fff')
    else:
        bg_color = '#fff'
    style = f"color:{text_color};background:{bg_color};font-weight:{font_weight};font-style:{font_style};"
    return style


def get_plain_text_from_cell(cell):
    # rich_text 리스트에서 plain_text만 합침
    return ''.join([t.get('plain_text', '') for t in cell])


def estimate_column_widths(table_rows):
    """셀 내용의 길이를 기반으로 너비 추정 (줄바꿈이 있으면 각 줄의 길이 중 최대값 사용)"""
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
                # 줄바꿈이 있으면 각 줄의 길이 중 최대값 사용
                line_lengths = [len(line) for line in cell_text.split('\n')]
                cell_length = max(line_lengths) if line_lengths else 0
                max_length = max(max_length, cell_length)
        col_lengths.append(max_length)
    total_length = sum(col_lengths) or 1
    return [length / total_length for length in col_lengths]


def estimate_column_widths_with_pixel_heuristic(table_rows):
    # 인덱스 행(헤더) 포함 모든 행을 컨텐츠 길이 계산에 포함
    if not table_rows:
        return []
    col_lengths = []
    max_cols = max(len(row['table_row']['cells']) for row in table_rows)
    # 각 열의 최대 텍스트 길이(줄바꿈 포함) 계산
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
    # 2차 보정: 남는 여백을 줄바꿈 발생 열에 우선 분배
    # 1. 줄바꿈 발생 열 찾기
    wrap_cols = set()
    for col_idx in range(max_cols):
        for row in table_rows:
            cells = row['table_row']['cells']
            if col_idx < len(cells):
                cell_text = get_plain_text_from_cell(cells[col_idx])
                if '\n' in cell_text:
                    wrap_cols.add(col_idx)
    # 2. 남는 여백 계산
    current_sum = sum(percent_widths)
    remain = 100 - current_sum
    # 3. 줄바꿈 열에 우선 분배
    if remain > 0 and wrap_cols:
        add_per_col = remain / len(wrap_cols)
        for idx in wrap_cols:
            percent_widths[idx] += add_per_col
    # 4. 혹시 오버되면 첫 열에서 차감
    current_sum2 = sum(percent_widths)
    if current_sum2 != 100 and percent_widths:
        diff = 100 - current_sum2
        percent_widths[0] += diff
    print(f"[최종 percent_widths with wrap 보정] {percent_widths}")
    return percent_widths


async def blocks_to_html(blocks, notion_client):
    """Notion 블록 리스트를 HTML로 변환합니다."""
    if not blocks:
        return ""
    
    html_parts = []
    i = 0
    after_project_h2 = False
    h3_after_project_count = 0
    while i < len(blocks):
        block = blocks[i]
        block_type = block['type']
        
        # 리스트 아이템 처리
        if block_type in ['bulleted_list_item', 'numbered_list_item']:
            list_tag = 'ul' if block_type == 'bulleted_list_item' else 'ol'
            list_items = []
            
            # 연속된 같은 타입의 리스트 아이템들을 모음
            j = i
            while j < len(blocks) and blocks[j]['type'] == block_type:
                current_block = blocks[j]
                
                # 리스트 아이템 내용을 가져오고, 중첩된 불릿 포인트 처리
                item_content = rich_text_to_html(
                    current_block[block_type]['rich_text'], 
                    process_nested_bullets=True
                )
                
                # 자식 블록이 있으면 재귀적으로 처리
                if current_block.get('has_children') and current_block.get('children'):
                    children_html = await blocks_to_html(current_block['children'], notion_client)
                    item_content += children_html
                
                list_items.append(f"<li>{item_content}</li>")
                j += 1
            
            # 리스트 HTML 생성
            list_html = f"<{list_tag}>{''.join(list_items)}</{list_tag}>"
            html_parts.append(list_html)
            
            # 처리한 블록들만큼 인덱스 이동
            i = j
            continue
        
        # 리스트가 아닌 다른 블록 타입들 처리
        block_html = ""
        
        if block_type == 'heading_1':
            block_html = f"<h1>{rich_text_to_html(block['heading_1']['rich_text'])}</h1>"
        elif block_type == 'heading_2':
            h2_text = rich_text_to_html(block['heading_2']['rich_text'])
            plain_text = ''.join([chunk.get('plain_text', '') for chunk in block['heading_2']['rich_text']])
            if 'Project' in plain_text:
                block_html = f"<h2 style='page-break-before:always'>{h2_text}</h2>"
                after_project_h2 = True
                h3_after_project_count = 0
            else:
                block_html = f"<h2>{h2_text}</h2>"
                after_project_h2 = False
                h3_after_project_count = 0
        elif block_type == 'heading_3':
            h3_text = rich_text_to_html(block['heading_3']['rich_text'])
            if after_project_h2:
                h3_after_project_count += 1
                if h3_after_project_count == 1:
                    block_html = f"<h3>{h3_text}</h3>"
                else:
                    block_html = f"<h3 style='page-break-before:always'>{h3_text}</h3>"
            else:
                block_html = f"<h3>{h3_text}</h3>"
        elif block_type == 'paragraph':
            text = rich_text_to_html(block['paragraph']['rich_text'])
            block_html = f"<p>{text if text.strip() else '&nbsp;'}</p>"
            
            # 자식이 있는 paragraph 처리
            if block.get('has_children') and block.get('children'):
                children_html = await blocks_to_html(block['children'], notion_client)
                block_html += f"<div style='margin-left: 2em;'>{children_html}</div>"
                
        elif block_type == 'image':
            image_data = block['image']
            url = ''
            if image_data.get('file'):
                url = image_data['file']['url']
            elif image_data.get('external'):
                url = image_data['external']['url']
            block_html = f"<figure><img src='{url}' alt='Image'></figure>"
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
            # 표의 열 너비를 픽셀 기반(글자수*픽셀+최소값)으로 추정
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
                        # 행 배경색
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
            # 콜아웃 본문과 자식 블록을 모두 박스 안에 출력
            block_html = (
                f"<div style='background:#f7f6f3;border-radius:8px;padding:0.001em 1em;margin:0.7em 0;'>"
                f"{icon_html}{callout_text}{children_html}</div>"
            )
        
        html_parts.append(block_html)
        i += 1
    
    return ''.join(html_parts)


async def fetch_all_child_blocks(notion, block_id):
    """페이지 내의 모든 블록과 그 자식 블록을 재귀적으로 가져옵니다."""
    blocks = []
    try:
        response = await notion.blocks.children.list(block_id=block_id, page_size=100)
        blocks.extend(response['.etc'])
        
        next_cursor = response.get('next_cursor')
        while next_cursor:
            response = await notion.blocks.children.list(
                block_id=block_id, 
                page_size=100, 
                start_cursor=next_cursor
            )
            blocks.extend(response['.etc'])
            next_cursor = response.get('next_cursor')

    except Exception as e:
        print(f"블록 가져오기 오류: {e}")
        return []

    # 자식 블록 재귀적으로 가져오기
    for block in blocks:
        if block.get('has_children'):
            block['children'] = await fetch_all_child_blocks(notion, block['id'])
    
    return blocks


async def main():
    print("--- Notion to PDF (분류 없이 전체 인쇄) ---")
    notion = AsyncClient(auth=NOTION_API_KEY)
    try:
        page_info = await notion.pages.retrieve(page_id=PAGE_ID)
        page_title = extract_page_title(page_info)
        print(f"   페이지 제목: {page_title}")
    except Exception as e:
        print(f"   페이지 제목을 가져오지 못했습니다: {e}")
        page_title = "My Portfolio"
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
        <div style='height: 1.5em;'></div>
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("이력서/포폴 자동화 툴")
        central = QWidget()
        main_layout = QHBoxLayout()

        # 좌측: 드롭박스
        self.rule_selector = RuleSelectorWidget()
        self.rule_selector.combo.currentIndexChanged.connect(self.update_buttons)
        main_layout.addWidget(self.rule_selector)

        # 우측: 버튼 3개 + 로딩 인디케이터(아래)
        right_layout = QVBoxLayout()
        self.translate_btn = QPushButton("번역")
        self.improve_btn = QPushButton("개선")
        self.export_btn = QPushButton("출력")
        self.translate_btn.clicked.connect(self.on_translate)
        self.improve_btn.clicked.connect(self.on_improve)
        self.export_btn.clicked.connect(self.on_export)
        right_layout.addWidget(self.translate_btn)
        right_layout.addWidget(self.improve_btn)
        right_layout.addWidget(self.export_btn)
        right_layout.addStretch()
        self.loading_label = QLabel("")
        self.loading_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_layout.addWidget(self.loading_label)
        main_layout.addLayout(right_layout)

        central.setLayout(main_layout)
        self.setCentralWidget(central)
        self.update_buttons()  # 초기 버튼 상태

    def update_buttons(self):
        code = self.rule_selector.get_selected_rule()
        # 한글 버전 4종: ko로 시작
        if code.startswith("ko_"):
            self.translate_btn.setEnabled(True)
            self.improve_btn.setEnabled(True)
            self.export_btn.setEnabled(True)
        else:
            self.translate_btn.setEnabled(False)
            self.improve_btn.setEnabled(True)
            self.export_btn.setEnabled(True)

    def on_translate(self):
        self.loading_label.setText("번역 중입니다...")
        QApplication.processEvents()
        # 실제 번역 작업 함수 호출 (여기서는 더미)
        self.fake_work()
        self.loading_label.setText("")

    def on_improve(self):
        self.loading_label.setText("개선(첨삭) 중입니다...")
        QApplication.processEvents()
        # 실제 개선 작업 함수 호출 (여기서는 더미)
        self.fake_work()
        self.loading_label.setText("")

    def on_export(self):
        self.loading_label.setText("출력 중입니다...")
        QApplication.processEvents()
        # 실제 출력 작업 함수 호출 (여기서는 더미)
        self.fake_work()
        self.loading_label.setText("")

    def fake_work(self):
        import time
        time.sleep(1)  # 실제 작업 대체용 (1초 대기)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())