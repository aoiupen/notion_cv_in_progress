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
        # --- 이미지 블록 처리 (mainsub.py와 동일하게 수정) ---
        elif block_type == 'image':
            image_data = block['image']
            url = ''
            if image_data.get('file'):
                url = image_data['file']['url']
            elif image_data.get('external'):
                url = image_data['external']['url']
            # class="notion-block-image" 추가하고 인라인 스타일 제거
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
            
            # class 사용으로 변경 (인라인 스타일 제거)
            block_html = (
                f"<div class='callout'>"
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