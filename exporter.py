import os
import re
import asyncio
from notion_client import AsyncClient
from playwright.async_api import async_playwright
from PyPDF2 import PdfMerger
from config import TEMP_DIR, FINAL_PDF_PATH
from notion_api import fetch_all_child_blocks, get_synced_block_original_and_top_parent
from utils import extract_page_title

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

def get_styles():
    css_path = os.path.join(os.getcwd(), 'portfolio_style.css')
    try:
        with open(css_path, encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"CSS 파일 읽기 오류: {e}")
        return ""

# extract_page_title 함수는 utils.py로 이동됨

def rich_text_to_html(rich_text_array, process_nested_bullets=False):
    if not rich_text_array:
        return ""
    html = ""
    for chunk in rich_text_array:
        href = chunk.get("href")
        text = chunk.get('plain_text', '').replace('\n', '<br>')
        if href:
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

def estimate_column_widths_with_pixel_heuristic(table_rows):
    if not table_rows:
        return []
    col_lengths = []
    max_cols = max(len(row['table_row']['cells']) for row in table_rows) if table_rows else 0
    if max_cols == 0: return []
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
    if total_estimated_px_width == 0: return [100 / max_cols] * max_cols if max_cols > 0 else []
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
    return percent_widths

async def blocks_to_html(blocks, notion_client):
    if not blocks:
        return ""
    html_parts = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        block_type = block['type']
        if block_type == 'synced_block':
            synced_children = block.get('children')
            synced_block_content = await blocks_to_html(synced_children, notion_client) if synced_children else ""
            html_parts.append(f"<div class='synced-block-container'>{synced_block_content}</div>")
            i += 1
            continue
        if block_type in ['bulleted_list_item', 'numbered_list_item']:
            list_tag = 'ul' if block_type == 'bulleted_list_item' else 'ol'
            list_items = []
            j = i
            while j < len(blocks) and blocks[j]['type'] == block_type:
                current_block = blocks[j]
                item_content = rich_text_to_html(current_block[block_type]['rich_text'])
                if current_block.get('has_children') and current_block.get('children'):
                    item_content += await blocks_to_html(current_block['children'], notion_client)
                list_items.append(f"<li>{item_content}</li>")
                j += 1
            html_parts.append(f"<{list_tag}>{''.join(list_items)}</{list_tag}>")
            i = j
            continue
        block_html = ""
        if block_type == 'heading_1':
            block_html = f"<h1>{rich_text_to_html(block['heading_1']['rich_text'])}</h1>"
        elif block_type == 'heading_2':
            block_html = f"<h2>{rich_text_to_html(block['heading_2']['rich_text'])}</h2>"
        elif block_type == 'heading_3':
            block_html = f"<h3>{rich_text_to_html(block['heading_3']['rich_text'])}</h3>"
        elif block_type == 'paragraph':
            text = rich_text_to_html(block['paragraph']['rich_text'])
            block_html = f"<p>{text if text.strip() else ' '}</p>"
            if block.get('has_children') and block.get('children'):
                block_html += f"<div style='margin-left: 2em;'>{await blocks_to_html(block['children'], notion_client)}</div>"
        elif block_type == 'image':
            image_data = block['image']
            url = image_data.get('file', {}).get('url') or image_data.get('external', {}).get('url', '')
            block_html = f"<img src='{url}' alt='Image' class='notion-block-image' style='max-width: 100%; height: auto;'>"
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
            children_html = await blocks_to_html(block['children'], notion_client) if block.get('has_children') and block.get('children') else ""
            block_html = f"<details open><summary>{summary}</summary>{children_html}</details>"
        elif block_type == 'table':
            width_ratios = estimate_column_widths_with_pixel_heuristic(block.get('children', []))
            colgroup_html = ''.join([f'<col style="width:{ratio:.2f}%">' for ratio in width_ratios]) if width_ratios else ""
            table_html_content = f"<table><colgroup>{colgroup_html}</colgroup>"
            if block.get('children'):
                for i_row, row_block in enumerate(block['children']):
                    if row_block['type'] == 'table_row':
                        cells = row_block['table_row']['cells']
                        row_bg = row_block['table_row'].get('background', 'default')
                        table_html_content += f"<tr style='background:{NOTION_BG_MAP.get(row_bg, '#fff')}'>"
                        for col_idx, cell in enumerate(cells):
                            style = get_cell_style(cell, row_bg=row_bg)
                            tag = 'th' if (block['table'].get('has_column_header') and i_row == 0) or (block['table'].get('has_row_header') and col_idx == 0) else 'td'
                            if tag == 'th':
                                table_html_content += f"<th class='table-header-cell' style='{style}'>{rich_text_to_html(cell)}</th>"
                            else:
                                table_html_content += f"<td style='{style}'>{rich_text_to_html(cell)}</td>"
                        table_html_content += "</tr>"
            table_html_content += "</table>"
            block_html = table_html_content
        elif block_type == 'callout':
            callout = block['callout']
            icon_html = f"{callout['icon']['emoji']} " if callout.get('icon') and callout['icon']['type'] == 'emoji' else ""
            callout_text = rich_text_to_html(callout['rich_text'])
            children_html = await blocks_to_html(block['children'], notion_client) if block.get('has_children') else ''
            block_html = f"<div class='callout'>{icon_html}{callout_text}{children_html}</div>"
        html_parts.append(block_html)
        i += 1
    return '\n'.join(html_parts)

async def export_single_pdf(notion_client, page_id, page_index, temp_dir):
    """단일 페이지의 PDF를 생성합니다."""
    page_info = await notion_client.pages.retrieve(page_id=page_id)
    page_title = extract_page_title(page_info)
    blocks = await fetch_all_child_blocks(notion_client, page_id)
    content_html = await blocks_to_html(blocks, notion_client)
    styles = get_styles()
    
    clean_title = page_title.strip() if page_title else ""
    # 제목이 없거나 'Untitled'면 h1을 출력하지 않음
    if clean_title and clean_title.lower() != "untitled":
        title_section = f'<h1>{clean_title}</h1><div style="height: 0.3em;"></div>'
    else:
        title_section = ""
    
    full_html = f"""
    <!DOCTYPE html>
    <html lang=\"ko\">
    <head>
        <meta charset=\"UTF-8\">
        <title>{clean_title if clean_title else f'Portfolio_{page_index}'}</title>
        <style>{styles}</style>
    </head>
    <body>
        {title_section}
        {content_html}
    </body>
    </html>
    """
    
    pdf_path = os.path.join(temp_dir, f"My_Portfolio_{page_index}.pdf")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(full_html, wait_until="networkidle")
        await page.pdf(path=pdf_path, format="A4", print_background=True)
        await browser.close()
    
    return pdf_path

def merge_pdfs(pdf_paths, output_path):
    """여러 PDF 파일을 하나로 병합합니다."""
    if not pdf_paths:
        return None
    
    merger = PdfMerger()
    for pdf in pdf_paths:
        merger.append(pdf)
    merger.write(output_path)
    merger.close()
    return output_path

async def export_and_merge_pdf(page_ids, output_pdf_path="My_Portfolio_Final.pdf", progress_callback=None):
    """여러 페이지의 PDF를 생성하고 병합합니다. progress_callback은 (current, total) 인수를 받습니다."""
    from dotenv import load_dotenv
    load_dotenv()
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    notion = AsyncClient(auth=NOTION_API_KEY)
    
    temp_dir = TEMP_DIR
    os.makedirs(temp_dir, exist_ok=True)
    temp_pdf_paths = []
    
    total_pages = len(page_ids)
    semaphore = asyncio.Semaphore(4)
    async def export_with_semaphore(page_id, idx):
        async with semaphore:
            if progress_callback:
                progress_callback(idx, total_pages)
            return await export_single_pdf(notion, page_id, idx, temp_dir)
    tasks = [export_with_semaphore(page_id, idx) for idx, page_id in enumerate(page_ids)]
    temp_pdf_paths = await asyncio.gather(*tasks)
    temp_pdf_paths = [path for path in temp_pdf_paths if isinstance(path, str) and os.path.exists(path)]
    
    # 병합 완료 시 진행률 100%
    if progress_callback:
        progress_callback(total_pages, total_pages)
    
    final_pdf_path = FINAL_PDF_PATH if output_pdf_path == "My_Portfolio_Final.pdf" else output_pdf_path
    return merge_pdfs(temp_pdf_paths, final_pdf_path) 