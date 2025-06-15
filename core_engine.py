# core_engine.py는 Notion 데이터 추출/블록 파싱 등 Notion 전용 엔진/헬퍼만 남깁니다.
# 번역, HTML->PDF, PDF 출력 관련 함수/클래스는 제거합니다.

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
            if filter_root_only:
                root_pages = []
                for page in all_pages:
                    parent = page.get("parent", {})
                    parent_type = parent.get("type", "")
                    if parent_type in ["workspace", "database_id"]:
                        root_pages.append(page)
                return root_pages
            return all_pages
        except Exception as e:
            print(f"페이지 검색 중 오류: {e}")
            return []

    async def get_page_by_id(self, page_id: str) -> Optional[dict]:
        try:
            return await self.notion.pages.retrieve(page_id=page_id)
        except Exception as e:
            print(f"페이지 조회 실패 (ID: {page_id}): {e}")
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

    async def fetch_all_child_blocks(self, block_id: str) -> List[dict]:
        blocks = []
        try:
            response = await self.notion.blocks.children.list(block_id=block_id, page_size=100)
            blocks.extend(response['results'])
            next_cursor = response.get('next_cursor')
            while next_cursor:
                response = await self.notion.blocks.children.list(
                    block_id=block_id,
                    page_size=100,
                    start_cursor=next_cursor
                )
                blocks.extend(response['results'])
                next_cursor = response.get('next_cursor')
        except Exception as e:
            print(f"블록 가져오기 오류: {e}")
            return []
        for block in blocks:
            if block.get('has_children'):
                block['children'] = await self.fetch_all_child_blocks(block['id'])
        return blocks 