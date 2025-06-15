import os
import asyncio
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# Third-party imports
import requests
from notion_client import AsyncClient
from notion_client.errors import APIResponseError
from playwright.async_api import async_playwright
from PyPDF2 import PdfMerger

# Local imports
from config import NOTION_API_KEY, CLAUDE_API_KEY, PAGE_ID_MAP


@dataclass
class ProcessingConfig:
    """처리 설정을 담는 데이터 클래스"""
    doc_type: str  # 'resume' or 'portfolio'
    source_lang: str  # 'ko' or 'en'
    target_lang: str  # 'ko' or 'en'
    with_translation: bool = True
    output_dir: str = ".etc"


class NotionPortfolioEngine:
    """Notion 포트폴리오/이력서 통합 처리 엔진"""
    
    def __init__(self):
        self.notion = AsyncClient(auth=NOTION_API_KEY)
        self.claude_api_key = CLAUDE_API_KEY
        self.output_dir = Path(".etc")
        self.temp_dir = self.output_dir / "temp"
        
        # 디렉토리 생성
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        # CSS 스타일 로드
        self._load_css_styles()
    
    def _load_css_styles(self) -> str:
        """CSS 스타일을 로드합니다."""
        css_path = Path("portfolio_style.css")
        try:
            with open(css_path, encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"CSS 파일 읽기 오류: {e}")
            return self._get_default_css()
    
    def _get_default_css(self) -> str:
        """기본 CSS 스타일을 반환합니다."""
        return """
        @page { size: A4; margin: 2cm; }
        body { font-family: 'Pretendard', sans-serif; line-height: 1.6; }
        h1 { font-size: 2.5em; margin: 1.2em 0 0.1em 0; }
        h2 { font-size: 1.8em; margin: 1.1em 0 0.4em 0; }
        h3 { font-size: 1.2em; margin: 0.9em 0 0.3em 0; }
        """
    
    def _get_page_id(self, config: ProcessingConfig) -> Optional[str]:
        """설정에 따라 적절한 페이지 ID를 반환합니다."""
        try:
            if config.doc_type == "resume":
                return PAGE_ID_MAP.get(f"{config.source_lang}_cv_b_none")
            else:  # portfolio
                return PAGE_ID_MAP.get(f"{config.source_lang}_pf_b_none")
        except KeyError:
            print(f"페이지 ID를 찾을 수 없습니다: {config}")
            return None
    
    # ============================================================================
    # 기능 1: 번역 및 내용 개선
    # ============================================================================
    
    async def translate_content_with_claude(self, text: str, source_lang: str, target_lang: str) -> str:
        """Claude API를 사용하여 텍스트를 번역합니다."""
        if source_lang == target_lang:
            return text
            
        try:
            # Claude API 호출
            headers = {
                "x-api-key": self.claude_api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            
            prompt = self._create_translation_prompt(text, source_lang, target_lang)
            
            data = {
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 2000,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["content"][0]["text"]
            else:
                print(f"번역 API 오류: {response.status_code}")
                return text
                
        except Exception as e:
            print(f"번역 중 오류 발생: {e}")
            return text
    
    def _create_translation_prompt(self, text: str, source_lang: str, target_lang: str) -> str:
        """번역을 위한 프롬프트를 생성합니다."""
        lang_map = {
            "ko": "Korean",
            "en": "English"
        }
        
        source = lang_map.get(source_lang, "Korean")
        target = lang_map.get(target_lang, "English")
        
        return f"""
Please translate the following {source} text to {target}. 
Maintain the professional tone and technical terminology appropriately.
Keep the original formatting and structure.

Text to translate:
{text}

Translation:
"""
    
    async def translate_and_enhance(self, config: ProcessingConfig) -> Optional[str]:
        """번역 및 내용 개선을 수행합니다."""
        print(f"🔄 번역 및 개선 시작: {config.doc_type} ({config.source_lang} → {config.target_lang})")
        
        page_id = self._get_page_id(config)
        if not page_id:
            print("❌ 페이지 ID를 찾을 수 없습니다.")
            return None
        
        try:
            # 1. Notion 페이지 추출
            page_info = await self.notion.pages.retrieve(page_id=page_id)
            page_title = self._extract_page_title(page_info)
            
            # 2. 번역이 필요한 경우 번역 수행
            if config.with_translation and config.source_lang != config.target_lang:
                translated_title = await self.translate_content_with_claude(
                    page_title, config.source_lang, config.target_lang
                )
                print(f"✅ 제목 번역 완료: {page_title} → {translated_title}")
                return translated_title
            
            return page_title
            
        except Exception as e:
            print(f"❌ 번역 및 개선 중 오류: {e}")
            return None
    
    # ============================================================================
    # 기능 2: PDF 출력 및 변환 (mainsub.py 로직 통합)
    # ============================================================================
    
    async def export_to_pdf(self, config: ProcessingConfig, output_filename: Optional[str] = None) -> Optional[str]:
        """PDF 출력 및 변환을 수행합니다."""
        print(f"📄 PDF 출력 시작: {config.doc_type} ({config.source_lang})")
        
        page_id = self._get_page_id(config)
        if not page_id:
            print("❌ 페이지 ID를 찾을 수 없습니다.")
            return None
        
        try:
            # 1. 페이지 정보 및 제목 추출
            page_info = await self.notion.pages.retrieve(page_id=page_id)
            page_title = self._extract_page_title(page_info)
            
            # 2. 모든 블록 가져오기
            blocks = await self._fetch_all_child_blocks(page_id)
            
            # 3. HTML 변환
            content_html = await self._blocks_to_html(blocks)
            
            # 4. 완전한 HTML 문서 생성
            full_html = self._generate_full_html(page_title, content_html)
            
            # 5. PDF 생성
            if not output_filename:
                output_filename = f"{config.doc_type}_{config.source_lang}.pdf"
            
            pdf_path = self.output_dir / output_filename
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(full_html, wait_until="networkidle")
                await page.pdf(path=str(pdf_path), format="A4", print_background=True)
                await browser.close()
            
            print(f"✅ PDF 생성 완료: {pdf_path}")
            return str(pdf_path)
            
        except Exception as e:
            print(f"❌ PDF 생성 중 오류: {e}")
            return None
    
    # ============================================================================
    # 통합 워크플로우
    # ============================================================================
    
    async def full_workflow(self, config: ProcessingConfig) -> Optional[str]:
        """전체 워크플로우를 실행합니다."""
        print(f"🚀 전체 워크플로우 시작: {config}")
        
        # 1. 번역 및 개선 (필요한 경우)
        if config.with_translation:
            translated_title = await self.translate_and_enhance(config)
            if translated_title:
                print(f"✅ 번역 완료: {translated_title}")
        
        # 2. PDF 출력
        result_path = await self.export_to_pdf(config)
        
        if result_path:
            print(f"🎉 전체 프로세스 완료! 결과: {result_path}")
            return result_path
        else:
            print("❌ 프로세스 실패")
            return None
    
    # ============================================================================
    # Helper Methods (mainsub.py에서 이전된 핵심 함수들)
    # ============================================================================
    
    def _extract_page_title(self, page_info: dict) -> str:
        """페이지 제목을 추출합니다."""
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
    
    async def _fetch_all_child_blocks(self, block_id: str) -> List[dict]:
        """모든 자식 블록을 재귀적으로 가져옵니다."""
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
        
        # 자식 블록 재귀적으로 처리
        for block in blocks:
            if block.get('has_children'):
                block['children'] = await self._fetch_all_child_blocks(block['id'])
        
        return blocks
    
    async def _blocks_to_html(self, blocks: List[dict]) -> str:
        """블록 리스트를 HTML로 변환합니다."""
        if not blocks:
            return ""
        
        html_parts = []
        for block in blocks:
            block_html = await self._convert_single_block_to_html(block)
            if block_html:
                html_parts.append(block_html)
        
        return '\n'.join(html_parts)
    
    async def _convert_single_block_to_html(self, block: dict) -> str:
        """단일 블록을 HTML로 변환합니다."""
        block_type = block.get('type')
        
        if block_type == 'heading_1':
            return f"<h1>{self._rich_text_to_html(block['heading_1']['rich_text'])}</h1>"
        elif block_type == 'heading_2':
            return f"<h2>{self._rich_text_to_html(block['heading_2']['rich_text'])}</h2>"
        elif block_type == 'heading_3':
            return f"<h3>{self._rich_text_to_html(block['heading_3']['rich_text'])}</h3>"
        elif block_type == 'paragraph':
            text = self._rich_text_to_html(block['paragraph']['rich_text'])
            return f"<p>{text if text.strip() else '&nbsp;'}</p>"
        elif block_type == 'bulleted_list_item':
            return f"<li>{self._rich_text_to_html(block['bulleted_list_item']['rich_text'])}</li>"
        # ... 더 많은 블록 타입 처리
        
        return ""
    
    def _rich_text_to_html(self, rich_text_array: List[dict]) -> str:
        """Rich text를 HTML로 변환합니다."""
        if not rich_text_array:
            return ""
        
        html = ""
        for chunk in rich_text_array:
            text = chunk.get('plain_text', '').replace('\n', '<br>')
            html += self._apply_annotations(text, chunk)
        
        return html
    
    def _apply_annotations(self, text: str, chunk: dict) -> str:
        """텍스트에 주석을 적용합니다."""
        if not text:
            return ""
        
        annotations = chunk.get('annotations', {})
        if annotations.get('bold'):
            text = f'<strong>{text}</strong>'
        if annotations.get('italic'):
            text = f'<em>{text}</em>'
        if annotations.get('code'):
            text = f'<code>{text}</code>'
        
        href = chunk.get('href')
        if href:
            text = f'<a href="{href}" target="_blank">{text}</a>'
        
        return text
    
    def _generate_full_html(self, title: str, content: str) -> str:
        """완전한 HTML 문서를 생성합니다."""
        css_styles = self._load_css_styles()
        
        return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>{css_styles}</style>
</head>
<body>
    <h1>{title}</h1>
    <div style='height: 1.5em;'></div>
    {content}
</body>
</html>
"""


# ============================================================================
# 팩토리 함수들
# ============================================================================

def create_config(doc_type: str, source_lang: str, target_lang: str, with_translation: bool = True) -> ProcessingConfig:
    """ProcessingConfig 객체를 생성합니다."""
    return ProcessingConfig(
        doc_type=doc_type,
        source_lang=source_lang,
        target_lang=target_lang,
        with_translation=with_translation
    )


async def quick_export(doc_type: str, lang: str = "ko") -> Optional[str]:
    """빠른 PDF 출력을 위한 헬퍼 함수"""
    engine = NotionPortfolioEngine()
    config = create_config(doc_type, lang, lang, with_translation=False)
    return await engine.export_to_pdf(config)


if __name__ == "__main__":
    # 테스트 실행
    async def test():
        engine = NotionPortfolioEngine()
        config = create_config("portfolio", "ko", "en", with_translation=True)
        result = await engine.full_workflow(config)
        print(f"Test result: {result}")
    
    asyncio.run(test()) 