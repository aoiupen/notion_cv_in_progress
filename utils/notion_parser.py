import asyncio
import base64
import uuid
from pathlib import Path
from utils.helpers import *

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

def rich_text_to_html(rich_text_array, process_nested_bullets=False):
    """미니멀한 스타일의 rich_text 변환"""
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

async def get_synced_block_original_and_top_parent(notion, block):
    current_block = block
    if current_block.get('type') == 'synced_block':
        synced_from = current_block['synced_block'].get('synced_from')
        if synced_from and 'block_id' in synced_from:
            try:
                original_block = await notion.blocks.retrieve(synced_from['block_id'])
                return await get_synced_block_original_and_top_parent(notion, original_block)
            except Exception as e:
                print(f"[get_synced_block] 원본 블록 접근 실패: {e}")
                return None, None, None
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
        except Exception:
            return current_block, None, None
    if parent_type == 'page_id':
        return current_block, parent.get('page_id'), 'page'
    elif parent_type == 'database_id':
        return current_block, parent.get('database_id'), 'database'
    elif parent_type == 'workspace':
        return current_block, block_id_to_find_parent, 'page'
    else:
        return current_block, None, None

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
                            table_html_content += f"<{tag} style='{style}'>{rich_text_to_html(cell)}</{tag}>"
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

async def fetch_all_child_blocks(notion, block_id):
    blocks = []
    try:
        response = await notion.blocks.children.list(block_id=block_id, page_size=100)
        blocks.extend(response['results'])
        next_cursor = response.get('next_cursor')
        while next_cursor:
            response = await notion.blocks.children.list(block_id=block_id, page_size=100, start_cursor=next_cursor)
            blocks.extend(response['results'])
            next_cursor = response.get('next_cursor')
    except Exception as e:
        print(f"블록 가져오기 오류: {e}")
        return []
    processed_blocks = []
    for block in blocks:
        if block.get('type') == 'synced_block':
            orig_block, _, _ = await get_synced_block_original_and_top_parent(notion, block)
            if orig_block:
                if orig_block.get('has_children'):
                    orig_block['children'] = await fetch_all_child_blocks(notion, orig_block['id'])
                processed_blocks.append(orig_block)
        elif block.get('has_children'):
            block['children'] = await fetch_all_child_blocks(notion, block['id'])
            processed_blocks.append(block)
        else:
            processed_blocks.append(block)
    return processed_blocks 