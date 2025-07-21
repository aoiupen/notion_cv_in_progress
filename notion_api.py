import os
from notion_client import AsyncClient

async def get_root_pages():
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    notion = AsyncClient(auth=NOTION_API_KEY)
    all_pages = []
    start_cursor = None
    while True:
        response = await notion.search(filter={"property": "object", "value": "page"}, page_size=100, start_cursor=start_cursor)
        all_pages.extend(response.get("results", []))
        start_cursor = response.get("next_cursor")
        if not start_cursor:
            break
    root_pages = []
    for page in all_pages:
        parent = page.get("parent", {})
        parent_type = parent.get("type", "")
        if parent_type != "database_id" and not (parent_type == "page_id" and parent.get("page_id") in [p['id'] for p in all_pages]):
            root_pages.append(page)
    return root_pages, all_pages

async def get_all_descendant_page_ids(page_id, all_pages):
    ids = [page_id]
    children = [p for p in all_pages if p.get("parent", {}).get("type") == "page_id" and p.get("parent", {}).get("page_id") == page_id]
    for child in children:
        ids.extend(await get_all_descendant_page_ids(child['id'], all_pages))
    return ids

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

async def get_first_child_page_ids(page_id, notion_client):
    # Notion blocks.children.list로 실제 children 순서대로 추출
    children = []
    try:
        response = await notion_client.blocks.children.list(block_id=page_id, page_size=100)
        children = response['results']
        next_cursor = response.get('next_cursor')
        while next_cursor:
            response = await notion_client.blocks.children.list(block_id=page_id, page_size=100, start_cursor=next_cursor)
            children.extend(response['results'])
            next_cursor = response.get('next_cursor')
    except Exception as e:
        print(f"하위 페이지 순서 가져오기 오류: {e}")
        return []
    
    # 빈 줄(empty paragraph)까지만 child_page를 가져오도록 수정
    child_page_ids = []
    for block in children:
        # 내용이 없는 paragraph 블록 (빈 줄)을 만나면 중단
        if block['type'] == 'paragraph' and not block['paragraph'].get('rich_text'):
            break 
        if block['type'] == 'child_page':
            child_page_ids.append(block['id'])
            
    return child_page_ids 