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
                print(f"     ID: {page_id[:8]}")
                print(f"     Parent Type: {parent_type}")
                print(f"     Full Parent: {parent}")
                
                # parent 정보 저장
                page_hierarchy[page_id] = {
                    'title': title,
                    'parent_type': parent_type,
                    'parent_info': parent
                }
                
                # 🔍 하위 페이지가 있는지 확인
                try:
                    children_resp = await self.notion.blocks.children.list(
                        block_id=page_id, 
                        page_size=10
                    )
                    child_pages = [c for c in children_resp.get('results', []) 
                                 if c['type'] == 'child_page']
                    if child_pages:
                        print(f"     ➥ 하위 페이지 {len(child_pages)}개 보유")
                        for child in child_pages[:3]:  # 최대 3개 표시
                            child_title = child.get('child_page', {}).get('title', 'Untitled')
                            print(f"        - {child_title}")
                except Exception as e:
                    print(f"     ➥ 하위 페이지 조회 실패: {e}")
                
                print()
            
            if not filter_root_only:
                return all_pages
            
            # 🎯 개별 페이지 권한 상황에 맞춘 필터링 로직
            return await self._filter_pages_for_individual_permissions(all_pages, page_hierarchy)
            
        except Exception as e:
            print(f"페이지 검색 중 오류: {e}")
            return []

    async def _filter_pages_for_individual_permissions(self, all_pages: List[dict], hierarchy: Dict) -> List[dict]:
        """개별 페이지 권한 상황에 맞춘 개선된 필터링"""
        
        print("🎯 개별 페이지 권한 상황 분석 중...")
        
        # 방법 1 개선: parent_type 별로 정확히 분류
        true_child_pages = set()  # parent_type="page_id" (진짜 하위 페이지)
        database_pages = set()    # parent_type="database_id" (리스트뷰/갤러리뷰 페이지)
        
        print(f"\n📊 Parent Type 별 상세 분석:")
        for page in all_pages:
            parent = page.get("parent", {})
            parent_type = parent.get("type", "")
            page_id = page['id']
            title = hierarchy[page_id]['title']
            
            if parent_type == "page_id":
                parent_id = parent.get("page_id", "")
                true_child_pages.add(page_id)
                print(f"  📄 진짜 하위 페이지: {title} (부모: {parent_id[:8]})")
            elif parent_type == "database_id":
                database_id = parent.get("database_id", "")
                database_pages.add(page_id)
                print(f"  🗃️  데이터베이스 페이지: {title} (DB: {database_id[:8]})")
            else:
                print(f"  🌐 최상위 페이지: {title} (Parent: {parent_type})")
        
        print(f"\n🔍 방법1 개선 결과:")
        print(f"  - 진짜 하위 페이지 (page_id): {len(true_child_pages)}개")
        print(f"  - 데이터베이스 페이지 (database_id): {len(database_pages)}개 ← 제외 대상")
        
        # 방법 2: 실제 하위 페이지 존재 여부로 부모 페이지 식별 (신뢰도 높음)
        confirmed_parent_pages = set()
        child_page_titles_found = {}
        
        for page in all_pages:
            page_id = page['id']
            title = hierarchy[page_id]['title']
            try:
                children_resp = await self.notion.blocks.children.list(block_id=page_id, page_size=20)
                child_pages = [c for c in children_resp.get('results', []) if c['type'] == 'child_page']
                if child_pages:
                    confirmed_parent_pages.add(page_id)
                    child_titles = [c.get('child_page', {}).get('title', 'Untitled') for c in child_pages]
                    child_page_titles_found[title] = child_titles
                    print(f"  📁 확실한 부모 페이지: {title} (하위: {len(child_pages)}개)")
            except Exception as e:
                print(f"  ⚠️  {title} 하위 페이지 조회 실패: {e}")
        
        print(f"🔍 방법2 (하위 페이지 보유): {len(confirmed_parent_pages)}개 확실한 부모 페이지 식별")
        
        # 방법 3 개선: 진짜 하위 페이지만 엄격하게 식별
        confirmed_child_pages = set()
        
        for page in all_pages:
            parent = page.get("parent", {})
            parent_type = parent.get("type", "")
            page_id = page['id']
            title = hierarchy[page_id]['title']
            
            # 🎯 핵심: parent_type="page_id"인 것만 진짜 하위 페이지로 인정
            if parent_type == "page_id":
                parent_id = parent.get("page_id", "")
                # 부모가 현재 접근 가능한 페이지 목록에 있고, 실제로 하위 페이지를 보유하는지 확인
                parent_exists_in_list = any(p['id'] == parent_id for p in all_pages)
                parent_has_children = parent_id in confirmed_parent_pages
                
                if parent_exists_in_list and parent_has_children:
                    confirmed_child_pages.add(page_id)
                    print(f"  📄 확실한 하위 페이지: {title} (부모: {parent_id[:8]})")
                elif parent_exists_in_list:
                    print(f"  ❓ 애매한 페이지: {title} (부모 존재하지만 하위 페이지 미확인)")
                else:
                    print(f"  ❓ 부모 미접근: {title} (부모 {parent_id[:8]} 접근 불가)")
        
        print(f"🔍 방법3 개선 (관계 분석): {len(confirmed_child_pages)}개 확실한 하위 페이지 식별")
        
        # 🎯 최종 전략: 
        # 1. 확실한 부모 페이지들은 무조건 포함 (A, B 같은)
        # 2. 확실한 하위 페이지들은 무조건 제외 (a, b, c 같은)
        # 3. 데이터베이스 페이지들도 무조건 제외 (A의 리스트뷰/갤러리뷰 페이지들)
        # 4. 나머지는 독립 페이지로 간주하여 포함 (C 같은)
        
        excluded_pages = confirmed_child_pages | database_pages  # 제외할 페이지들
        root_pages = []
        
        print(f"\n🎯 최종 판정:")
        for page in all_pages:
            page_id = page['id']
            title = hierarchy[page_id]['title']
            
            if page_id in confirmed_child_pages:
                # 확실한 하위 페이지 → 제외
                print(f"  ❌ 하위 페이지: {title}")
            elif page_id in database_pages:
                # 데이터베이스 페이지 → 제외
                print(f"  ❌ 데이터베이스 페이지: {title} (리스트뷰/갤러리뷰)")
            elif page_id in confirmed_parent_pages:
                # 확실한 부모 페이지 → 포함
                root_pages.append(page)
                children = child_page_titles_found.get(title, [])
                print(f"  ✅ 부모 페이지: {title} (하위: {', '.join(children[:3])}{'...' if len(children) > 3 else ''})")
            else:
                # 독립 페이지 → 포함
                root_pages.append(page)
                print(f"  ✅ 독립 페이지: {title}")
        
        print(f"\n🎉 최종 루트 페이지: {len(root_pages)}개")
        print(f"  - 부모 페이지: {len(confirmed_parent_pages)}개")
        print(f"  - 독립 페이지: {len(root_pages) - len(confirmed_parent_pages)}개")
        print(f"  - 제외된 하위 페이지: {len(confirmed_child_pages)}개")
        print(f"  - 제외된 데이터베이스 페이지: {len(database_pages)}개")
        
        return root_pages

    # 기존 메서드들 유지
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