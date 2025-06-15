import asyncio
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot

from core_engine import NotionEngine
from translate_engine import TranslateEngine, TranslationConfig
from html2pdf_engine import HTML2PDFEngine
from utils.helpers import extract_page_title
from utils.notion_parser import blocks_to_html, fetch_all_child_blocks

class MainViewModel(QObject):
    # UI 업데이트를 위한 시그널 정의
    pages_changed = Signal(list)
    status_updated = Signal(str)
    progress_updated = Signal(int)
    preview_updated = Signal(str)
    result_updated = Signal(str)
    child_count_updated = Signal(int)

    def __init__(self):
        super().__init__()
        self._notion_engine = NotionEngine()
        self._translate_engine = TranslateEngine()
        self._html2pdf_engine = HTML2PDFEngine()
        
        self.pages = []
        self.source_lang = "ko"
        self.target_lang = "ko"
        self.selected_page_id = None
        self._temp_dir = Path(".etc/temp")
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    @Slot()
    def load_pages(self):
        """Notion에서 접근 가능한 루트 페이지를 로드하여 UI에 알립니다."""
        self.status_updated.emit("Notion 페이지 목록 로드 중...")
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        self.pages = loop.run_until_complete(self._notion_engine.search_accessible_pages(filter_root_only=True))
        self.pages_changed.emit(self.pages)
        self.status_updated.emit("페이지 목록 로드 완료. 페이지를 선택하세요.")

    @Slot(str)
    def page_selected(self, page_id: str):
        self.selected_page_id = page_id
        self.status_updated.emit(f"페이지 선택됨: {page_id[:8]}... 캐시 확인 중...")
        asyncio.run(self._prepare_and_preview_page())

    async def _prepare_and_preview_page(self):
        """선택된 페이지의 child page들을 캐싱하고 미리보기를 업데이트합니다."""
        json_path = self._temp_dir / f"{self.selected_page_id}_children.json"
        
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                child_ids = json.load(f)
            self.status_updated.emit("캐시된 데이터로 미리보기를 로드합니다.")
        else:
            self.status_updated.emit("페이지 데이터를 Notion에서 가져와 캐싱합니다...")
            page_info = await self._notion_engine.get_page_by_id(self.selected_page_id)
            title = await self._notion_engine.extract_page_title(page_info)
            
            # 자식 페이지들 export 및 캐싱
            children_resp = await self._notion_engine.notion.blocks.children.list(block_id=self.selected_page_id, page_size=100)
            children = children_resp.get('results', [])
            
            # 루트 페이지 자신과 자식 페이지 ID 목록 생성
            child_ids = [self.selected_page_id] + [c['id'] for c in children if c['type'] == 'child_page']

            for i, cid in enumerate(child_ids):
                self.progress_updated.emit(int((i + 1) / len(child_ids) * 100))
                page_info = await self._notion_engine.get_page_by_id(cid)
                ctitle = await self._notion_engine.extract_page_title(page_info)
                blocks = await fetch_all_child_blocks(self._notion_engine.notion, cid)
                html_content = await blocks_to_html(blocks, self._notion_engine.notion)
                
                # HTML 파일 저장
                html_path = self._temp_dir / f"{cid}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(self._html2pdf_engine.generate_full_html(ctitle, html_content))
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(child_ids, f)
            self.status_updated.emit("캐싱 완료.")

        self.child_count_updated.emit(len(child_ids))
        await self.update_preview(0, len(child_ids) -1)
        self.progress_updated.emit(0)

    @Slot(int, int)
    def update_preview(self, start_idx: int, end_idx: int):
        asyncio.run(self._update_preview_async(start_idx, end_idx))

    async def _update_preview_async(self, start_idx: int, end_idx: int):
        """지정된 범위의 캐시된 HTML 파일을 조합하여 미리보기를 업데이트합니다."""
        if not self.selected_page_id:
            return

        json_path = self._temp_dir / f"{self.selected_page_id}_children.json"
        if not json_path.exists():
            self.preview_updated.emit("미리보기할 데이터가 없습니다. 먼저 페이지를 선택하여 캐시를 생성해주세요.")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            child_ids = json.load(f)

        htmls = []
        
        start = max(0, start_idx)
        end = min(len(child_ids) - 1, end_idx)

        for i in range(start, end + 1):
            cid = child_ids[i]
            html_path = self._temp_dir / f"{cid}.html"
            if html_path.exists():
                with open(html_path, "r", encoding="utf-8") as f:
                    htmls.append(f.read())
        
        self.preview_updated.emit("\n<hr>\n".join(htmls))
    
    @Slot(str)
    def start_export(self, export_type: str):
        # 이 부분은 WorkerThread로 분리되어야 함
        # 지금은 간단한 시나리오만 구현
        self.status_updated.emit("PDF/HTML export 시작...")
        asyncio.run(self._export_async())

    async def _export_async(self):
        json_path = self._temp_dir / f"{self.selected_page_id}_children.json"
        if not json_path.exists():
            self.result_updated.emit("Error: No cached data to export.")
            return

        with open(json_path, "r") as f:
            child_ids = json.load(f)
        
        for i, cid in enumerate(child_ids):
            html_path = self._temp_dir / f"{cid}.html"
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            
            await self._html2pdf_engine.html_to_pdf(html_content, f"{cid}.pdf")
            self.progress_updated.emit(int((i+1)/len(child_ids) * 100))

        self.status_updated.emit("Export complete.")
        self.result_updated.emit(f"Successfully exported {len(child_ids)} PDF file(s).")
        self.progress_updated.emit(0) 