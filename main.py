# 모든 한글 주석과 from, import 구문을 삭제합니다.

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
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLabel, QSizePolicy, QProgressBar, QTextEdit, QTextBrowser, QGroupBox, QMessageBox, QFileDialog, QListWidget, QListWidgetItem, QAbstractItemView, QLineEdit, QSplitter, QCheckBox
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QColor
from translate_engine import TranslateEngine, TranslationConfig
from html2pdf_engine import HTML2PDFEngine
from typing import Optional
from pathlib import Path
import threading
from core_engine import NotionEngine

# --- 1. 설정: .env 파일에서 환경변수 불러오기 ---
load_dotenv()

# 환경변수가 제대로 로드되었는지 확인
if not NOTION_API_KEY:
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
    if not blocks:
        return "<p style='color:#888'>블록 데이터가 없습니다.</p>"
    html_parts = []
    i = 0
    after_project_h2 = False
    h3_after_project_count = 0
    while i < len(blocks):
        block = blocks[i]
        if not block or 'type' not in block:
            i += 1
            continue
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
        results = response.get('results')
        if not results:
            print(f"[경고] 블록이 없습니다: {block_id}")
            return []
        blocks.extend(results)
        next_cursor = response.get('next_cursor')
        while next_cursor:
            response = await notion.blocks.children.list(
                block_id=block_id, 
                page_size=100, 
                start_cursor=next_cursor
            )
            results = response.get('results')
            if not results:
                break
            blocks.extend(results)
            next_cursor = response.get('next_cursor')
    except Exception as e:
        print(f"블록 가져오기 오류: {e}")
        return []
    # 자식 블록 재귀적으로 가져오기
    for block in blocks:
        if block and block.get('has_children'):
            block['children'] = await fetch_all_child_blocks(notion, block.get('id'))
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
    pdf_path = os.path.join(".etc", "My_Portfolio_Final.pdf")
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


class WorkerThread(QThread):
    """백그라운드에서 비동기 작업을 처리하는 워커 스레드"""
    
    # 시그널 정의
    progress_updated = Signal(int)  # 진행률 업데이트
    status_updated = Signal(str)    # 상태 메시지 업데이트  
    finished = Signal(str)          # 작업 완료 (결과 경로)
    error_occurred = Signal(str)    # 에러 발생
    
    def __init__(self, config, workflow_type: str):
        super().__init__()
        self.config = config
        self.workflow_type = workflow_type  # 'translate', 'export', 'full'
        self.notion_engine = NotionEngine()
        self.translate_engine = TranslateEngine()
        self.html2pdf_engine = HTML2PDFEngine()
    
    def run(self):
        """워커 스레드 실행 메인 함수"""
        try:
            # 새로운 이벤트 루프 생성
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if self.workflow_type == 'translate':
                result = loop.run_until_complete(self._run_translation())
            elif self.workflow_type == 'export':
                result = loop.run_until_complete(self._run_export())
            elif self.workflow_type == 'full':
                result = loop.run_until_complete(self._run_full_workflow())
            else:
                raise ValueError(f"Unknown workflow type: {self.workflow_type}")
            
            if result:
                self.finished.emit(result)
            else:
                self.error_occurred.emit("작업이 실패했습니다.")
                
        except Exception as e:
            self.error_occurred.emit(f"오류 발생: {str(e)}")
        finally:
            loop.close()
    
    async def _run_translation(self) -> Optional[str]:
        """번역 워크플로우 실행"""
        self.status_updated.emit("🔄 번역 작업 시작...")
        self.progress_updated.emit(10)
        
        # 예시: 첫 번째 페이지의 제목만 번역
        page_id = self.config["selected_page_ids"][0]
        page_info = await self.notion_engine.notion.pages.retrieve(page_id=page_id)
        title = await self.notion_engine.extract_page_title(page_info)
        result = await self.translate_engine.translate_and_enhance(title, {
            "source_lang": self.config["source_lang"],
            "target_lang": self.config["target_lang"],
            "with_translation": self.config["with_translation"]
        })
        self.progress_updated.emit(100)
        
        return f"번역 완료: {result}" if result else None
    
    async def _run_export(self) -> Optional[str]:
        """PDF 출력 워크플로우 실행"""
        self.status_updated.emit("📄 PDF 생성 시작...")
        self.progress_updated.emit(10)
        
        self.status_updated.emit("📥 Notion 데이터 가져오는 중...")
        self.progress_updated.emit(30)
        
        self.status_updated.emit("🔄 HTML 변환 중...")
        self.progress_updated.emit(60)
        
        self.status_updated.emit("📋 PDF 생성 중...")
        self.progress_updated.emit(80)
        
        page_id = self.config["selected_page_ids"][0]
        page_info = await self.notion_engine.notion.pages.retrieve(page_id=page_id)
        title = await self.notion_engine.extract_page_title(page_info)
        blocks = await self.notion_engine.fetch_all_child_blocks(page_id)
        # blocks_to_html 함수는 main.py에 있으므로 import해서 사용해야 함
        from main import blocks_to_html
        content_html = await blocks_to_html(blocks, self.notion_engine.notion)
        html = self.html2pdf_engine.generate_full_html(title, content_html)
        output_filename = f"{title}.pdf"
        pdf_path = await self.html2pdf_engine.html_to_pdf(html, output_filename)
        self.progress_updated.emit(100)
        
        return pdf_path
    
    async def _run_full_workflow(self) -> Optional[str]:
        """전체 워크플로우 실행"""
        self.status_updated.emit("🚀 전체 프로세스 시작...")
        self.progress_updated.emit(5)
        
        if self.config["with_translation"]:
            self.status_updated.emit("🔄 번역 작업 중...")
            self.progress_updated.emit(20)
            await self._run_translation()
            self.progress_updated.emit(50)
        
        self.status_updated.emit("📄 PDF 생성 중...")
        self.progress_updated.emit(70)
        
        result = await self._run_export()
        self.progress_updated.emit(100)
        
        return result


class ModernButton(QPushButton):
    """현대적인 스타일의 커스텀 버튼"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(45)
        self.setFont(QFont("Arial", 11, QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def set_primary_style(self):
        """주요 버튼 스타일 적용"""
        self.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton:disabled {
                background-color: #94a3b8;
            }
        """)
    
    def set_toggle_style(self, is_active: bool = False):
        """토글 버튼 스타일 적용"""
        if is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: white;
                    border: 2px solid #059669;
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #047857;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #374151;
                    border: 2px solid #d1d5db;
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    border-color: #9ca3af;
                    background-color: #f9fafb;
                }
            """)


class MainWindow(QMainWindow):
    """메인 애플리케이션 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("이력서/포폴 자동화 툴 v2.0")
        self.setMinimumSize(300, 500)
        
        # 상태 변수
        self.doc_type = "resume"      # "resume" or "portfolio"
        self.source_lang = "ko"       # "ko" or "en"
        self.target_lang = "en"       # "ko" or "en"
        self.worker_thread = None
        
        # UI 초기화
        self._init_ui()
        self._check_environment()
        
    def _init_ui(self):
        """UI 구성요소 초기화"""
        main_hbox = QHBoxLayout()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setLayout(main_hbox)
        # 좌측: 기존 컨트롤들 (VBox)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(20)
        left_layout.setContentsMargins(30, 30, 30, 30)
        # 제목
        title_label = QLabel("이력서/포폴 자동화 툴")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #1f2937; margin-bottom: 10px;")
        left_layout.addWidget(title_label)
        # Notion 페이지 목록 그룹
        page_group = self._create_page_list_group()
        left_layout.addWidget(page_group)
        # 언어/실행/옵션 그룹 한 줄
        row_layout = QHBoxLayout()
        lang_group = self._create_language_group()
        action_group, full_btn = self._create_action_group_with_full_btn()
        option_group = self._create_option_group()
        row_layout.addWidget(lang_group, 2)
        row_layout.addWidget(action_group, 2)
        row_layout.addWidget(option_group, 2)
        row_layout.addWidget(full_btn, 1)
        left_layout.addLayout(row_layout)
        # 진행 상황 표시
        progress_group = self._create_progress_group()
        left_layout.addWidget(progress_group)
        # 결과 표시 영역
        result_group = self._create_result_group()
        left_layout.addWidget(result_group)
        left_layout.addStretch()
        # 모든 위젯 생성 후 상태 초기화
        self._set_language("ko", "ko")  # '한'만 디폴트
        self.export_btn.setEnabled(True)
        self.export_btn.set_primary_style()
        self.translate_btn.setEnabled(False)
        self.translate_btn.setStyleSheet("")
        main_hbox.addWidget(left_widget, 2)
        # 우측: 미리보기/번역 결과
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        self.splitter = QSplitter()
        self.original_preview = QTextBrowser()
        self.original_preview.setOpenExternalLinks(True)
        self.translated_preview = QTextEdit()
        self.translated_preview.setReadOnly(True)
        self.splitter.addWidget(self.original_preview)
        self.splitter.addWidget(self.translated_preview)
        preview_layout.addWidget(self.splitter)
        self.sync_scroll_checkbox = QCheckBox("Sync Scroll")
        self.sync_scroll_checkbox.stateChanged.connect(self.toggle_sync_scroll)
        preview_layout.addWidget(self.sync_scroll_checkbox)
        main_hbox.addWidget(preview_widget, 3)
        # 페이지 선택/번역 버튼 이벤트 연결
        self.page_list.itemSelectionChanged.connect(self._on_page_selected)
        self.translate_btn.clicked.connect(self._on_translate_clicked)
    
    def _create_page_list_group(self) -> QGroupBox:
        """Notion 페이지 목록 그룹 생성"""
        group = QGroupBox("📄 Notion 페이지 선택 (단일 선택)")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        self.page_list = QListWidget()
        self.page_list.setFont(QFont("Arial", 12))
        self.page_list.setFixedHeight(400)  # 기존보다 2배 높이
        self.page_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.page_list)
        threading.Thread(target=self._load_notion_pages).start()
        return group

    def _load_notion_pages(self):
        try:
            notion = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
            import asyncio
            def extract_title(page):
                try:
                    props = page.get('properties', {})
                    for prop in props.values():
                        if prop.get('type') == 'title':
                            arr = prop.get('title', [])
                            if arr:
                                return ''.join([t['plain_text'] for t in arr])
                    return "Untitled"
                except Exception:
                    return "Untitled"
            async def fetch_pages():
                result = await notion.search(filter={"property": "object", "value": "page"})
                return result["results"]
            pages = asyncio.run(fetch_pages())
            self.page_list.clear()
            for page in pages:
                title = extract_title(page)
                item = QListWidgetItem(f"{title} ({page['id'][:8]})")
                item.setData(Qt.UserRole, page['id'])
                self.page_list.addItem(item)
        except Exception as e:
            self.page_list.addItem(f"페이지 목록 불러오기 실패: {e}")
    
    def _create_language_group(self) -> QGroupBox:
        """언어 방향 선택 그룹 생성 (버튼 배치 커스텀)"""
        group = QGroupBox("🌐 언어 설정")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        grid = QHBoxLayout(group)
        # 왼쪽: 한→영, 영→한 (상하)
        left_col = QVBoxLayout()
        self.ko_to_en_btn = ModernButton("한→영")
        self.en_to_ko_btn = ModernButton("영→한")
        self.ko_to_en_btn.setCheckable(True)
        self.en_to_ko_btn.setCheckable(True)
        self.ko_to_en_btn.clicked.connect(lambda: self._set_language("ko", "en"))
        self.en_to_ko_btn.clicked.connect(lambda: self._set_language("en", "ko"))
        left_col.addWidget(self.ko_to_en_btn)
        left_col.addWidget(self.en_to_ko_btn)
        # 오른쪽: 한, 영 (상하)
        right_col = QVBoxLayout()
        self.ko_only_btn = ModernButton("한")
        self.en_only_btn = ModernButton("영")
        self.ko_only_btn.setCheckable(True)
        self.en_only_btn.setCheckable(True)
        self.ko_only_btn.clicked.connect(lambda: self._set_language("ko", "ko"))
        self.en_only_btn.clicked.connect(lambda: self._set_language("en", "en"))
        right_col.addWidget(self.ko_only_btn)
        right_col.addWidget(self.en_only_btn)
        grid.addLayout(left_col)
        grid.addLayout(right_col)
        return group
    
    def _create_action_group_with_full_btn(self):
        """실행 버튼 그룹(번역, PDF) + 실행 버튼을 우측에 따로 반환"""
        group = QGroupBox("⚡ 실행")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        self.translate_btn = ModernButton("번역")
        self.export_btn = ModernButton("PDF")
        self.translate_btn.clicked.connect(lambda: self._start_workflow("translate"))
        self.export_btn.clicked.connect(lambda: self._start_workflow("export"))
        layout.addWidget(self.translate_btn)
        layout.addWidget(self.export_btn)
        # 전체 실행 버튼은 따로 반환
        self.full_btn = ModernButton("실행")
        self.full_btn.set_primary_style()
        self.full_btn.setMinimumHeight(90)  # 두 행에 걸쳐 보이도록
        self.full_btn.clicked.connect(lambda: self._start_workflow("full"))
        return group, self.full_btn
    
    def _create_option_group(self) -> QGroupBox:
        """옵션 박스: 시작/끝 입력, 더미 버튼 포함"""
        group = QGroupBox("옵션")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        # 시작/끝 입력
        row = QHBoxLayout()
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("시작")
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("끝")
        row.addWidget(self.start_edit)
        row.addWidget(self.end_edit)
        layout.addLayout(row)
        # 더미 버튼
        self.dummy_btn = ModernButton("옵션 적용")
        layout.addWidget(self.dummy_btn)
        return group
    
    def _create_progress_group(self) -> QGroupBox:
        """진행 상황 표시 그룹 생성"""
        group = QGroupBox("📊 진행 상황")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        
        self.status_label = QLabel("대기 중...")
        self.status_label.setFont(QFont("Arial", 10))
        self.status_label.setStyleSheet("color: #6b7280;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #e5e7eb;
                border-radius: 8px;
                background-color: #f3f4f6;
                text-align: center;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: #059669;
                border-radius: 6px;
            }
        """)
        
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        
        return group
    
    def _create_result_group(self) -> QGroupBox:
        """결과 표시 그룹 생성"""
        group = QGroupBox("📋 결과")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        
        self.result_text = QTextEdit()
        self.result_text.setMaximumHeight(120)
        self.result_text.setFont(QFont("Consolas", 9))
        self.result_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                background-color: #f9fafb;
                padding: 8px;
            }
        """)
        
        # 결과 관리 버튼들
        button_layout = QHBoxLayout()
        
        self.open_folder_btn = ModernButton("📂 결과 폴더 열기")
        self.clear_result_btn = ModernButton("🗑️ 결과 지우기")
        
        self.open_folder_btn.clicked.connect(self._open_result_folder)
        self.clear_result_btn.clicked.connect(self._clear_results)
        
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.clear_result_btn)
        button_layout.addStretch()
        
        layout.addWidget(self.result_text)
        layout.addLayout(button_layout)
        
        return group
    
    def _check_environment(self):
        """환경 설정 확인"""
        missing = []
        if not NOTION_API_KEY:
            missing.append("NOTION_API_KEY")
        if not CLAUDE_API_KEY:
            missing.append("CLAUDE_API_KEY")
        
        if missing:
            QMessageBox.warning(
                self, 
                "환경 설정 확인", 
                f"다음 환경변수가 설정되지 않았습니다:\n{', '.join(missing)}\n\n"
                ".env 파일을 확인해주세요."
            )
    
    def _set_language(self, source: str, target: str):
        """언어 설정"""
        self.source_lang = source
        self.target_lang = target
        # 모든 버튼 비활성화 스타일로 초기화
        for btn in [self.ko_to_en_btn, self.en_to_ko_btn, self.ko_only_btn, self.en_only_btn]:
            btn.set_toggle_style(False)
        # 선택된 버튼만 활성화 스타일 적용
        if source == "ko" and target == "en":
            self.ko_to_en_btn.set_toggle_style(True)
        elif source == "en" and target == "ko":
            self.en_to_ko_btn.set_toggle_style(True)
        elif source == "ko" and target == "ko":
            self.ko_only_btn.set_toggle_style(True)
        elif source == "en" and target == "en":
            self.en_only_btn.set_toggle_style(True)
        # 버튼 활성/비활성 및 스타일 처리
        if self.source_lang == self.target_lang:
            self.translate_btn.setEnabled(False)
            self.translate_btn.setStyleSheet("")
            self.export_btn.setEnabled(True)
            self.export_btn.set_primary_style()
        else:
            self.export_btn.setEnabled(False)
            self.export_btn.setStyleSheet("")
            self.translate_btn.setEnabled(True)
            self.translate_btn.set_primary_style()
        self._update_status_display()
    
    def _update_status_display(self):
        """상태 표시 업데이트 (선택된 페이지 수, 언어)"""
        selected = self.page_list.selectedItems()
        if selected:
            titles = [item.text() for item in selected]
            page_info = ", ".join(titles)
        else:
            page_info = "(페이지 미선택)"
        if self.source_lang == self.target_lang:
            lang_info = f"{self.source_lang.upper()} 출력"
        else:
            lang_info = f"{self.source_lang.upper()} → {self.target_lang.upper()}"
        self.status_label.setText(f"선택: {page_info} | {lang_info}")
    
    def _start_workflow(self, workflow_type: str):
        """워크플로우 시작"""
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, "알림", "이미 작업이 진행 중입니다.")
            return
        selected_items = self.page_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "알림", "최소 1개 이상의 Notion 페이지를 선택하세요.")
            return
        selected_page_ids = [item.data(Qt.UserRole) for item in selected_items]
        config = {
            "doc_type": "custom",
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "with_translation": (self.source_lang != self.target_lang and workflow_type in ['translate', 'full']),
            "selected_page_ids": selected_page_ids
        }
        self.worker_thread = WorkerThread(config, workflow_type)
        self.worker_thread.progress_updated.connect(self.progress_bar.setValue)
        self.worker_thread.status_updated.connect(lambda msg: (self.status_label.setText(msg), self.result_text.append(self._mask_id(msg))))
        self.worker_thread.finished.connect(self._on_workflow_finished)
        self.worker_thread.error_occurred.connect(self._on_workflow_error)
        self._set_buttons_enabled(False)
        self.progress_bar.setValue(0)
        self.worker_thread.start()
    
    def _on_workflow_finished(self, result: str):
        """워크플로우 완료 처리"""
        self.status_label.setText("✅ 완료!")
        self.result_text.append(f"[{self._get_timestamp()}] {result}")
        self._set_buttons_enabled(True)
        
        QMessageBox.information(self, "완료", f"작업이 완료되었습니다!\n\n{result}")
    
    def _on_workflow_error(self, error_msg: str):
        """워크플로우 에러 처리"""
        self.status_label.setText("❌ 오류 발생")
        self.result_text.append(f"[{self._get_timestamp()}] 오류: {error_msg}")
        self._set_buttons_enabled(True)
        
        QMessageBox.critical(self, "오류", f"작업 중 오류가 발생했습니다:\n\n{error_msg}")
    
    def _set_buttons_enabled(self, enabled: bool):
        """버튼 활성화 상태 설정"""
        self.translate_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)
        self.full_btn.setEnabled(enabled)
    
    def _open_result_folder(self):
        """결과 폴더 열기"""
        result_dir = Path(".etc")
        if result_dir.exists():
            os.startfile(str(result_dir))  # Windows
            # macOS: os.system(f"open {result_dir}")
            # Linux: os.system(f"xdg-open {result_dir}")
        else:
            QMessageBox.information(self, "알림", "결과 폴더가 아직 생성되지 않았습니다.")
    
    def _clear_results(self):
        """결과 텍스트 지우기"""
        self.result_text.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("대기 중...")
    
    def _get_timestamp(self) -> str:
        """현재 시간 스탬프 반환"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def _mask_id(self, msg):
        # page_id 등 ID가 포함된 문자열을 마스킹
        import re
        return re.sub(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{32}|[0-9a-f]{8})', '[ID]', msg)

    def _on_page_selected(self):
        import asyncio
        from notion_client import AsyncClient
        selected_items = self.page_list.selectedItems()
        if selected_items:
            page_id = selected_items[0].data(Qt.UserRole)
            async def fetch_and_render():
                notion = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
                try:
                    page_info = await notion.pages.retrieve(page_id=page_id)
                    from main import extract_page_title, fetch_all_child_blocks, blocks_to_html, get_styles
                    title = extract_page_title(page_info)
                    blocks = await fetch_all_child_blocks(notion, page_id)
                    html = await blocks_to_html(blocks, notion)
                    styles = get_styles()
                    full_html = f"""
                    <html><head><meta charset='utf-8'><style>{styles}</style></head><body><h1>{title}</h1>{html}</body></html>
                    """
                    self.original_preview.setHtml(full_html)
                    # 하위 블록 개수 옵션 자동 입력
                    child_count = len(blocks)
                    self.start_edit.setText('0')
                    self.end_edit.setText(str(max(0, child_count-1)))
                except Exception as e:
                    self.original_preview.setPlainText(f"[오류] {e}")
            asyncio.run(fetch_and_render())
        else:
            self.original_preview.clear()
        self.translated_preview.clear()

    def _on_translate_clicked(self):
        # 실제 번역 대신 더미 텍스트
        orig = self.original_preview.toPlainText()
        if orig:
            self.translated_preview.setPlainText(f"[TRANSLATED]\n\n{orig}")
        else:
            self.translated_preview.setPlainText("")

    def toggle_sync_scroll(self, state):
        if state:
            self.original_preview.verticalScrollBar().valueChanged.connect(
                self.translated_preview.verticalScrollBar().setValue)
            self.translated_preview.verticalScrollBar().valueChanged.connect(
                self.original_preview.verticalScrollBar().setValue)
        else:
            try:
                self.original_preview.verticalScrollBar().valueChanged.disconnect()
                self.translated_preview.verticalScrollBar().valueChanged.disconnect()
            except Exception:
                pass


def extract_page_title(page_info: dict) -> str:
    if not page_info:
        return "페이지 정보 없음"
    try:
        properties = page_info.get('properties', {})
        for prop_name, prop_data in properties.items():
            if prop_data and prop_data.get('type') == 'title':
                arr = prop_data.get('title', [])
                if arr:
                    return ''.join([item.get('plain_text', '') for item in arr if item])
        return "Untitled"
    except Exception as e:
        print(f"제목 추출 중 오류: {e}")
        return "Untitled"


def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    
    # 애플리케이션 설정
    app.setApplicationName("이력서/포폴 자동화 툴")
    app.setApplicationVersion("2.0")
    
    # 다크 모드 지원 (선택사항)
    # app.setStyle("Fusion")
    
    # 메인 윈도우 생성 및 표시
    window = MainWindow()
    window.show()
    
    # 애플리케이션 실행
    sys.exit(app.exec())


if __name__ == "__main__":
    main()