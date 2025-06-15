# core_engine.py는 Notion 데이터 추출/블록 파싱 등 Notion 전용 엔진/헬퍼만 남깁니다.
# 번역, HTML->PDF, PDF 출력 관련 함수/클래스는 제거합니다.

import os
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
from notion_client import AsyncClient
from config import NOTION_API_KEY, PAGE_ID

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

    def get_page_id(self, config: NotionConfig) -> Optional[str]:
        try:
            if config.doc_type == "resume":
                return PAGE_ID.get(f"{config.source_lang}_cv_b_none")
            else:
                return PAGE_ID.get(f"{config.source_lang}_pf_b_none")
        except KeyError:
            print(f"페이지 ID를 찾을 수 없습니다: {config}")
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