# core_engine.py - 개별 페이지 권한 상황에 맞춘 로직

import os
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
from notion_client import AsyncClient
from config import NOTION_API_KEY

@dataclass
class NotionConfig:
    doc_type: str
    source_lang: str
    target_lang: str
    with_translation: bool = True
    output_dir: str = ".etc"

class NotionEngine:
    def __init__(self):
        self.notion = AsyncClient(auth=NOTION_API_KEY)

    async def search_accessible_pages(self, filter_root_only: bool = True) -> List[dict]:
        try:
            all_pages = []
            start_cursor = None
            
            # 1단계: 모든 페이지 가져오기
            while True:
                search_params = {
                    "filter": {"property": "object", "value": "page"},
                    "page_size": 100
                }
                if start_cursor:
                    search_params["start_cursor"] = start_cursor
                    
                response = await self.notion.search(**search_params)
                pages = response.get("results", [])
                all_pages.extend(pages)
                
                start_cursor = response.get("next_cursor")
                if not start_cursor:
                    break
            
            print(f"🔍 총 {len(all_pages)}개 페이지 발견")
            
            # 🔍 중요: 개별 페이지 권한 상황에서의 parent 정보 분석
            print("\n📊 페이지별 상세 분석:")
            page_hierarchy = {}
            
            for page in all_pages:
                title = await self.extract_page_title(page)
                parent = page.get("parent", {})
                parent_type = parent.get("type", "")
                page_id = page['id']
                
                print(f"  📄 {title}")
                # print(f"     ID: {page_id[:8]}")
                print(f"     Parent Type: {parent_type}")
                print(f"     Full Parent: {parent}")
                
                # parent 정보 저장
                page_hierarchy[page_id] = {
                    'title': title,
                    'parent_type': parent_type,
                    'parent_info': parent
                }
                
                print()
            
            if not filter_root_only:
                return all_pages, all_pages
            
            # 🎯 개별 페이지 권한 상황에 맞춘 필터링 로직
            root_pages = await self._filter_pages_for_individual_permissions(all_pages, page_hierarchy)
            return root_pages, all_pages
            
        except Exception as e:
            print(f"페이지 검색 중 오류: {e}")
            return [], []

    async def _filter_pages_for_individual_permissions(self, all_pages: List[dict], hierarchy: Dict) -> List[dict]:
        """[개선] 개별 페이지 권한에 맞춰 상위 페이지만 필터링하는 간소화된 로직"""
        
        # print("🎯 간소화된 필터링 로직 실행 중...")
        
        # 1. 접근 가능한 모든 페이지의 ID를 집합으로 만듭니다. (빠른 조회를 위해)
        accessible_page_ids = {page['id'] for page in all_pages}
        
        root_pages = []
        
        # print("\n📊 최종 루트 페이지 판별:")
        for page in all_pages:
            page_id = page['id']
            title = hierarchy[page_id]['title']
            parent = page.get("parent", {})
            parent_type = parent.get("type", "")

            # 2. 데이터베이스에 속한 페이지는 제외합니다.
            if parent_type == "database_id":
                # print(f"  ❌ 데이터베이스 페이지: {title}")
                continue

            # 3. 부모가 페이지인 경우, 그 부모가 접근 가능한 페이지 목록에 있는지 확인합니다.
            if parent_type == "page_id":
                parent_id = parent.get("page_id")
                if parent_id in accessible_page_ids:
                    # 부모가 함께 조회된 페이지 목록에 있으므로, 이 페이지는 하위 페이지입니다. 제외합니다.
                    # parent_title = hierarchy.get(parent_id, {}).get('title', 'Untitled')
                    # print(f"  ❌ 하위 페이지: {title} (부모: '{parent_title}')")
                    continue
            
            # 4. 위 조건에 걸리지 않은 페이지는 루트 페이지로 간주합니다.
            # (부모가 workspace이거나, 부모 페이지에 접근 권한이 없는 경우)
            # print(f"  ✅ 루트 페이지: {title}")
            root_pages.append(page)
            
        print(f"🎉 최종 루트 페이지 {len(root_pages)}개를 찾았습니다.")
        return root_pages

    # 기존 메서드들 유지
    async def get_page_by_id(self, page_id: str) -> Optional[dict]:
        try:
            return await self.notion.pages.retrieve(page_id=page_id)
        except Exception as e:
            print(f"페이지 조회 실패: {e}") # (ID: {page_id})
            return None

    async def extract_page_title(self, page_info: dict) -> str:
        try:
            properties = page_info.get('properties', {})
            for prop_name, prop_data in properties.items():
                if prop_data.get('type') == 'title':
                    title_array = prop_data.get('title', [])
                    if title_array:
                        return ''.join([item['plain_text'] for item in title_array])
            return "Untitled"
        except Exception as e:
            print(f"제목 추출 중 오류: {e}")
            return "Untitled"

    async def get_synced_block_original(self, block: dict) -> Optional[dict]:
        """동기화 블록의 원본 블록을 재귀적으로 찾습니다."""
        if block.get('type') == 'synced_block':
            synced_from = block['synced_block'].get('synced_from')
            if synced_from and 'block_id' in synced_from:
                try:
                    original_block = await self.notion.blocks.retrieve(synced_from['block_id'])
                    return await self.get_synced_block_original(original_block)
                except Exception as e:
                    print(f"동기화 원본 블록({synced_from.get('block_id')}) 접근 실패: {e}")
                    return None
        return block

    async def get_synced_block_original_and_top_parent(self, notion, block):
        current_block = block
        # 1. synced_block 사본이면 원본을 재귀적으로 추적
        if current_block.get('type') == 'synced_block':
            synced_from = current_block['synced_block'].get('synced_from')
            if synced_from and 'block_id' in synced_from:
                try:
                    original_block = await notion.blocks.retrieve(synced_from['block_id'])
                    # 재귀 호출하여 원본 블록의 원본 및 최상위 부모를 찾습니다.
                    return await self.get_synced_block_original_and_top_parent(notion, original_block)
                except Exception as e:
                    print(f"[get_synced_block] 원본 블록 접근 실패 (ID: {synced_from.get('block_id', '알 수 없음')}): 코드={getattr(e, 'code', 'N/A')}, 상세={e}")
                    print(f"[get_synced_block] 원본 블록을 찾을 수 없거나 접근 권한이 없습니다. (ID: {synced_from.get('block_id', '알 수 없음')})")
                    return None, None, None
        # 2. 최상위 부모 추적 (여기서는 필요없지만 레거시와 동일하게 반환)
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
            return current_block, parent.get('page_id'), 'page'
        elif parent_type == 'database_id':
            return current_block, parent.get('database_id'), 'database'
        elif parent_type == 'workspace':
            return current_block, block_id_to_find_parent, 'page'
        else:
            return current_block, None, None

    async def fetch_all_child_blocks(self, block_id: str) -> List[dict]:
        blocks = []
        try:
            response = await self.notion.blocks.children.list(block_id=block_id, page_size=100)
            blocks.extend(response['results'])
            next_cursor = response.get('next_cursor')
            while next_cursor:
                response = await self.notion.blocks.children.list(
                    block_id=block_id, page_size=100, start_cursor=next_cursor
                )
                blocks.extend(response['results'])
                next_cursor = response.get('next_cursor')
        except Exception as e:
            print(f"블록 가져오기 오류: {e}")
            return []

        processed_blocks = []
        for block in blocks:
            if block.get('type') == 'synced_block':
                orig_block, _, _ = await self.get_synced_block_original_and_top_parent(self.notion, block)
                if orig_block is None:
                    print(f"경고: 동기화 블록 {block.get('id')}의 원본을 찾지 못해 건너뜁니다.")
                    continue
                if orig_block.get('has_children'):
                    orig_block['children'] = await self.fetch_all_child_blocks(orig_block['id'])
                processed_blocks.append(orig_block)
            elif block.get('has_children'):
                block['children'] = await self.fetch_all_child_blocks(block['id'])
                processed_blocks.append(block)
            else:
                processed_blocks.append(block)
        return processed_blocks


# 🧪 개별 페이지 권한 상황 테스트
async def test_individual_page_permissions():
    engine = NotionEngine()
    
    print("🔍 개별 페이지 권한 상황 분석 중...")
    pages = await engine.search_accessible_pages(filter_root_only=True)
    
    print(f"\n📋 최종 결과: {len(pages)}개 루트 페이지")
    for page in pages:
        title = await engine.extract_page_title(page)
        print(f"  📄 {title}")

if __name__ == "__main__":
    asyncio.run(test_individual_page_permissions())