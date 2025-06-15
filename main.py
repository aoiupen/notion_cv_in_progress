# main.py - 수정된 버전 (주요 기능 복원)

import os
import asyncio
import sys
import re
import requests
import base64
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from notion_client import AsyncClient
from notion_client.errors import APIResponseError
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from config import NOTION_API_KEY, CLAUDE_API_KEY
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

# 표 스타일 매핑 딕셔너리 - 원본과 동일하게 복원
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

CELL_PADDING_PX = 16
TABLE_TOTAL_WIDTH = 100

# --- CSS 파일 분리: get_styles()는 CSS 파일을 읽어 반환 (원본 방식 복원) ---
def get_styles():
    """루트(최상위) 경로의 portfolio_style.css 파일 내용을 반환합니다."""
    css_path = os.path.join(os.getcwd(), 'portfolio_style.css')
    try:
        with open(css_path, encoding='utf-8') as f:
            css = f.read()
        return css
    except Exception as e:
        print(f"CSS 파일 읽기 오류: {e}")
        # 백업용 기본 CSS 반환
        return """
        @page { size: A4; margin: 2cm; }
        body { font-family: 'Pretendard', sans-serif; line-height: 1.6; color: #333; }
        h1 { font-size: 2.5em; margin: 1.2em 0 0.1em 0; }
        h2 { font-size: 1.8em; margin: 1.1em 0 0.4em 0; }
        h3 { font-size: 1.2em; margin: 0.9em 0 0.3em 0; }
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

# --- 원본의 rich_text_to_html 함수 복원 ---
def rich_text_to_html(rich_text_array, process_nested_bullets=False):
    """미니멀한 스타일의 rich_text 변환"""
    if not rich_text_array:
        return ""
    html = ""
    for chunk in rich_text_array:
        href = chunk.get("href")
        text = chunk.get('plain_text', '').replace('\n', '<br>')
        
        if href:
            # 파비콘 없이 텍스트만 표시
             html += f'<a href="{href}" target="_blank">{text}</a>'
        else:
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

# --- 원본의 정교한 테이블 너비 계산 함수 복원 ---
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
    PIXEL_PER_CHAR = 4
    MIN_COL_WIDTH_PX = 65
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

# --- 원본의 동기화 블록 처리 함수들 복원 ---
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
                print(f"[get_synced_block] 원본 블록 접근 실패 (ID: {synced_from.get('block_id', '알 수 없음')}): 코드={getattr(e, 'code', 'N/A')}, 상세={e}")
                print(f"[get_synced_block] 원본 블록을 찾을 수 없거나 접근 권한이 없습니다. (ID: {synced_from.get('block_id', '알 수 없음')})")
                return None, None, None

    # 2. 최상위 부모 추적
    block_id_to_find_parent = current_block['id']
    parent = current_block.get('parent', {})
    parent_type = parent.get('type')

    while parent_type == 'block_id':
        next_id = parent.get('block_id')
        try:
            parent_block = await notion.blocks.retrieve(next_id)
            parent = parent_block.get('parent', {})
            parent_type = parent.get('type')
            block_id_to_find_parent = parent_block['id']
        except Exception as e:
            print(f"[get_synced_block] 부모 블록 추적 실패 (ID: {next_id}): {e}")
            return current_block, None, None

    if parent_type == 'page_id':
        print(f"[get_synced_block] 최상위 부모: page_id={parent.get('page_id')}")
        return current_block, parent.get('page_id'), 'page'
    elif parent_type == 'database_id':
        print(f"[get_synced_block] 최상위 부모: database_id={parent.get('database_id')}")
        return current_block, parent.get('database_id'), 'database'
    elif parent_type == 'workspace':
        print(f"[get_synced_block] 최상위 부모: workspace (page로 간주) id={block_id_to_find_parent}")
        return current_block, block_id_to_find_parent, 'page'
    else:
        print(f"[get_synced_block] 최상위 부모 타입 알 수 없음: {parent_type}. 블록 ID: {current_block.get('id')}")
        return current_block, None, None

# --- 원본의 blocks_to_html 함수 복원 (동기화 블록 처리 포함) ---
async def blocks_to_html(blocks, notion_client):
    """Notion 블록 리스트를 HTML로 변환합니다."""
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
            continue

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

        # --- 기타 블록 타입 처리 ---
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
        # --- 이미지 블록 처리 복원 ---
        elif block_type == 'image':
            image_data = block['image']
            url = ''
            if image_data.get('file'):
                url = image_data['file']['url']
            elif image_data.get('external'):
                url = image_data['external']['url']
            # class="notion-block-image" 추가 (원본과 동일)
            block_html = f"<img src='{url}' alt='Image' class='notion-block-image'>"
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
            has_row_header = table_info.get('has_row_header', False)
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
                        row_bg = row_block['table_row'].get('background', 'default')
                        table_html_content += f"<tr style='background:{NOTION_BG_MAP.get(row_bg, '#fff')}'>"
                        for col_idx, cell in enumerate(cells):
                            style = get_cell_style(cell, row_bg=row_bg)
                            width_style = f"width:{width_ratios[col_idx]:.2f}%;" if col_idx < len(width_ratios) else ''
                            # 제목 행/열에만 <th class="table-header-cell"> 적용
                            if (has_column_header and i_row == 0) or (has_row_header and col_idx == 0):
                                table_html_content += f"<th class='table-header-cell' style='{style}{width_style}'>{rich_text_to_html(cell)}</th>"
                            else:
                                table_html_content += f"<td style='{style}{width_style}'>{rich_text_to_html(cell)}</td>"
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
            
            # class 사용으로 변경 (원본과 동일)
            block_html = (
                f"<div class='callout'>"
                f"{icon_html}{callout_text}{children_html}</div>"
            )
        elif 'type' in block:
            print(f"경고: 알 수 없거나 지원되지 않는 블록 타입: {block_type}. 블록 ID: {block.get('id')}")
            block_html = f"<p><em>[Unsupported Block Type: {block_type}]</em></p>"

        html_parts.append(block_html)
        i += 1
    return '\n'.join(html_parts)

# --- 원본의 fetch_all_child_blocks 함수 복원 (동기화 블록 처리 포함) ---
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

    processed_blocks = []
    for block in blocks:
        # 동기화된 블록이면 항상 원본을 따라가고, 최상위 부모도 추적
        if block.get('type') == 'synced_block':
            orig_block, top_parent_id, top_parent_type = await get_synced_block_original_and_top_parent(notion, block)
            if orig_block is None:
                print(f"경고: 동기화 블록 {block.get('id')}의 원본을 찾거나 접근할 수 없어 건너뜀.")
                continue

            if orig_block.get('has_children'):
                orig_block['children'] = await fetch_all_child_blocks(notion, orig_block['id'])

            processed_blocks.append(orig_block)
            print(f"[fetch_all_child_blocks] 동기화 블록의 최상위 부모: {top_parent_id} (타입: {top_parent_type})")
        elif block.get('has_children'):
            block['children'] = await fetch_all_child_blocks(notion, block['id'])
            processed_blocks.append(block)
        else:
            processed_blocks.append(block)

    return processed_blocks

# --- 원본의 메인 함수 복원 ---
async def main():
    print("--- Notion to PDF (여러 PAGE_ID 순회) ---")
    notion = AsyncClient(auth=NOTION_API_KEY)
    page_ids = []
    for i in range(0,1):
        pid = os.getenv(f"PAGE_ID_{i}")
        if pid:
            page_ids.append(pid)
    
    page_ids = list(dict.fromkeys(page_ids))
    if not page_ids:
        print(".env에 PAGE_ID_0 ~ PAGE_ID_9 중 최소 1개가 필요합니다.")
        return

    temp_dir = os.path.join(".etc", "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_pdf_paths = []
    temp_html_paths = []

    for idx, PAGE_ID in enumerate(page_ids):
        try:
            page_info = await notion.pages.retrieve(page_id=PAGE_ID)
            page_title = extract_page_title(page_info)
            print(f"   [{idx}] 페이지 제목: {page_title}")
        except Exception as e:
            print(f"   [{idx}] 페이지 제목을 가져오지 못했습니다: {e}")
            page_title = f"Page_{idx}"
        
        print(f"[{idx}] 페이지({PAGE_ID}) 전체 블록을 가져오는 중...")
        blocks = await fetch_all_child_blocks(notion, PAGE_ID)
        print(f"[{idx}] HTML 변환 중...")
        content_html = await blocks_to_html(blocks, notion)
        styles = get_styles()
        
        def generate_html_with_conditional_title(page_title, content_html, styles):
            clean_title = page_title.strip() if page_title else ""
            if clean_title:
                title_section = f'<h1>{clean_title}</h1><div style="height: 0.3em;"></div>'
                body_class = ""
                html_title = clean_title
            else:
                title_section = ""
                body_class = ' class="no-title"'
                html_title = f"Portfolio_{idx}"
            return f"""
            <!DOCTYPE html>
            <html lang=\"ko\">
            <head>
                <meta charset=\"UTF-8\">
                <title>{html_title}</title>
                <style>{styles}</style>
            </head>
            <body{body_class}>
                {title_section}
                {content_html}
            </body>
            </html>
            """
        
        full_html = generate_html_with_conditional_title(page_title, content_html, styles)
        html_path = os.path.join(temp_dir, f"My_Portfolio_{idx}.html")
        pdf_path = os.path.join(temp_dir, f"My_Portfolio_{idx}.pdf")
        
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        
        print(f"[{idx}] PDF 변환 중...")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(full_html, wait_until="networkidle")
                await page.pdf(path=pdf_path, format="A4", print_background=True)
                await browser.close()
            print(f"   🎉 [{idx}] '{os.path.abspath(pdf_path)}' 파일이 생성되었습니다.")
            temp_pdf_paths.append(pdf_path)
            temp_html_paths.append(html_path)
        except Exception as e:
            print(f"   ❌ [{idx}] PDF 생성 중 오류 발생: {e}")
            print("   - playwright install 명령어를 실행했는지 확인하세요.")

    # PDF 병합
    if temp_pdf_paths:
        from PyPDF2 import PdfMerger
        merger = PdfMerger()
        for pdf in temp_pdf_paths:
            merger.append(pdf)
        final_pdf_path = os.path.join(".etc", "My_Portfolio_Final.pdf")
        merger.write(final_pdf_path)
        merger.close()
        print(f"\n🎉 최종 병합 PDF: '{os.path.abspath(final_pdf_path)}' 파일이 생성되었습니다.")
        
        final_html_path = os.path.join(".etc", "My_Portfolio_Final.html")
        with open(final_html_path, "w", encoding="utf-8") as f:
            for html_file in temp_html_paths:
                with open(html_file, "r", encoding="utf-8") as hf:
                    f.write(hf.read())
        print(f"최종 HTML: '{os.path.abspath(final_html_path)}' 파일이 생성되었습니다.")
    else:
        print("PDF 병합할 파일이 없습니다.")

# GUI 클래스들은 기존과 동일하게 유지...
# (WorkerThread, ModernButton, MainWindow 등은 변경 없음)

class WorkerThread(QThread):
    """백그라운드에서 비동기 작업을 처리하는 워커 스레드"""
    
    progress_updated = Signal(int)
    status_updated = Signal(str)
    finished = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, config, workflow_type: str):
        super().__init__()
        self.config = config
        self.workflow_type = workflow_type
        self.notion_engine = NotionEngine()
        self.translate_engine = TranslateEngine()
        self.html2pdf_engine = HTML2PDFEngine()
    
    def run(self):
        """워커 스레드 실행 메인 함수"""
        try:
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
        
        page_id = self.config["selected_page_ids"][0]
        page_info = await self.notion_engine.notion.pages.retrieve(page_id=page_id)
        title = await self.notion_engine.extract_page_title(page_info)
        # 직속 children만 가져오기
        children_resp = await self.notion_engine.notion.blocks.children.list(block_id=page_id, page_size=100)
        children = children_resp.get('results', [])
        # 시작/끝 범위 적용
        try:
            start = int(self.parent().start_edit.text())
            end = int(self.parent().end_edit.text())
        except Exception:
            start, end = 0, len(children)-1
        blocks_to_use = children[start:end+1]
        content_html = await blocks_to_html(blocks_to_use, self.notion_engine.notion)
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

# GUI 클래스들은 기존과 동일... (ModernButton, MainWindow 등)

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
        
        self.doc_type = "resume"
        self.source_lang = "ko"
        self.target_lang = "en"
        self.worker_thread = None
        
        self._init_ui()
        self._check_environment()
        
    def _init_ui(self):
        """UI 구성요소 초기화"""
        main_hbox = QHBoxLayout()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setLayout(main_hbox)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(20)
        left_layout.setContentsMargins(30, 30, 30, 30)
        
        title_label = QLabel("이력서/포폴 자동화 툴")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #1f2937; margin-bottom: 10px;")
        left_layout.addWidget(title_label)
        
        page_group = self._create_page_list_group()
        left_layout.addWidget(page_group)
        
        row_layout = QHBoxLayout()
        lang_group = self._create_language_group()
        action_group, full_btn = self._create_action_group_with_full_btn()
        option_group = self._create_option_group()
        row_layout.addWidget(lang_group, 2)
        row_layout.addWidget(action_group, 2)
        row_layout.addWidget(option_group, 2)
        row_layout.addWidget(full_btn, 1)
        left_layout.addLayout(row_layout)
        
        progress_group = self._create_progress_group()
        left_layout.addWidget(progress_group)
        
        result_group = self._create_result_group()
        left_layout.addWidget(result_group)
        left_layout.addStretch()
        
        self._set_language("ko", "ko")
        self.export_btn.setEnabled(True)
        self.export_btn.set_primary_style()
        self.translate_btn.setEnabled(False)
        self.translate_btn.setStyleSheet("")
        main_hbox.addWidget(left_widget, 2)
        
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
        
        self.page_list.itemSelectionChanged.connect(self._on_page_selected)
        self.translate_btn.clicked.connect(self._on_translate_clicked)
    
    def _create_page_list_group(self) -> QGroupBox:
        """Notion 페이지 목록 그룹 생성"""
        group = QGroupBox("📄 Notion 페이지 선택 (단일 선택)")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        self.page_list = QListWidget()
        self.page_list.setFont(QFont("Arial", 12))
        self.page_list.setFixedHeight(400)
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
            async def fetch_root_pages():
                result = await notion.search(filter={"property": "object", "value": "page"})
                pages = []
                for page in result["results"]:
                    parent = page.get("parent", {})
                    if parent.get("type") in ("workspace", "user"):
                        pages.append(page)
                return pages
            pages = asyncio.run(fetch_root_pages())
            self.page_list.clear()
            for page in pages:
                title = extract_title(page)
                item = QListWidgetItem(f"{title} ({page['id'][:8]})")
                item.setData(Qt.UserRole, page['id'])
                self.page_list.addItem(item)
        except Exception as e:
            self.page_list.addItem(f"페이지 목록 불러오기 실패: {e}")
    
    def _create_language_group(self) -> QGroupBox:
        """언어 방향 선택 그룹 생성"""
        group = QGroupBox("🌐 언어 설정")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        grid = QHBoxLayout(group)
        
        left_col = QVBoxLayout()
        self.ko_to_en_btn = ModernButton("한→영")
        self.en_to_ko_btn = ModernButton("영→한")
        self.ko_to_en_btn.setCheckable(True)
        self.en_to_ko_btn.setCheckable(True)
        self.ko_to_en_btn.clicked.connect(lambda: self._set_language("ko", "en"))
        self.en_to_ko_btn.clicked.connect(lambda: self._set_language("en", "ko"))
        left_col.addWidget(self.ko_to_en_btn)
        left_col.addWidget(self.en_to_ko_btn)
        
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
        """실행 버튼 그룹 생성"""
        group = QGroupBox("⚡ 실행")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        self.translate_btn = ModernButton("번역")
        self.export_btn = ModernButton("PDF")
        self.translate_btn.clicked.connect(lambda: self._start_workflow("translate"))
        self.export_btn.clicked.connect(lambda: self._start_workflow("export"))
        layout.addWidget(self.translate_btn)
        layout.addWidget(self.export_btn)
        
        self.full_btn = ModernButton("실행")
        self.full_btn.set_primary_style()
        self.full_btn.setMinimumHeight(90)
        self.full_btn.clicked.connect(lambda: self._start_workflow("full"))
        return group, self.full_btn
    
    def _create_option_group(self) -> QGroupBox:
        """옵션 박스 생성"""
        group = QGroupBox("옵션")
        group.setFont(QFont("Arial", 12, QFont.Weight.Medium))
        layout = QVBoxLayout(group)
        
        row = QHBoxLayout()
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("시작")
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("끝")
        row.addWidget(self.start_edit)
        row.addWidget(self.end_edit)
        layout.addLayout(row)
        
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
        
        for btn in [self.ko_to_en_btn, self.en_to_ko_btn, self.ko_only_btn, self.en_only_btn]:
            btn.set_toggle_style(False)
        
        if source == "ko" and target == "en":
            self.ko_to_en_btn.set_toggle_style(True)
        elif source == "en" and target == "ko":
            self.en_to_ko_btn.set_toggle_style(True)
        elif source == "ko" and target == "ko":
            self.ko_only_btn.set_toggle_style(True)
        elif source == "en" and target == "en":
            self.en_only_btn.set_toggle_style(True)
        
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
        """상태 표시 업데이트"""
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
            os.startfile(str(result_dir))
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
                    # 직속 children만 가져오기
                    children_resp = await notion.blocks.children.list(block_id=page_id, page_size=100)
                    children = children_resp.get('results', [])
                    child_count = len(children)
                    self.start_edit.setText('0')
                    self.end_edit.setText(str(max(0, child_count-1)))
                    # 미리보기 등 기존 코드
                    from main import extract_page_title, blocks_to_html, get_styles
                    page_info = await notion.pages.retrieve(page_id=page_id)
                    title = extract_page_title(page_info)
                    html = await blocks_to_html(children, notion)
                    styles = get_styles()
                    full_html = f"""
                    <html><head><meta charset='utf-8'><style>{styles}</style></head><body><h1>{title}</h1>{html}</body></html>
                    """
                    self.original_preview.setHtml(full_html)
                except Exception as e:
                    self.original_preview.setPlainText(f"[오류] {e}")
            asyncio.run(fetch_and_render())
        else:
            self.original_preview.clear()
        self.translated_preview.clear()

    def _on_translate_clicked(self):
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

def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    
    app.setApplicationName("이력서/포폴 자동화 툴")
    app.setApplicationVersion("2.0")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()