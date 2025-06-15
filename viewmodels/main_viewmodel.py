import asyncio
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot

from core_engine import NotionEngine
from translate_engine import TranslateEngine, TranslationConfig
from html2pdf_engine import HTML2PDFEngine
from utils.helpers import extract_page_title
from utils.notion_parser import blocks_to_html, fetch_all_child_blocks
from ui.worker import WorkerThread

class MainViewModel(QObject):
    # UI 업데이트를 위한 시그널 정의
    pages_changed = Signal(list)
    status_updated = Signal(str)
    progress_updated = Signal(int)
    preview_updated = Signal(str)
    result_updated = Signal(str)
    child_count_updated = Signal(int)
    worker_error = Signal(str)

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
        self.worker: WorkerThread = None

    def _start_worker(self, async_func, *args):
        if self.worker and self.worker.isRunning():
            self.status_updated.emit("이전 작업이 진행 중입니다. 잠시 후 다시 시도하세요.")
            return
        
        self.worker = WorkerThread(async_func, *args)
        self.worker.status_updated.connect(self.status_updated)
        self.worker.progress_updated.connect(self.progress_updated)
        self.worker.error_occurred.connect(self.worker_error)
        return self.worker

    # --- Public Slots for View ---
    @Slot()
    def load_pages(self):
        self.status_updated.emit("Notion 페이지 목록 로드 중...")
        worker = self._start_worker(self._load_pages_async)
        if worker:
            worker.finished.connect(self._on_pages_loaded)
            worker.start()

    @Slot(str)
    def page_selected(self, page_id: str):
        self.selected_page_id = page_id
        self.status_updated.emit(f"페이지 선택됨: {page_id[:8]}... 캐시 확인 중...")
        worker = self._start_worker(self._prepare_and_preview_page_async, page_id)
        if worker:
            worker.finished.connect(self._on_prepare_and_preview_finished)
            worker.start()

    @Slot(int, int)
    def update_preview(self, start_idx: int, end_idx: int):
        if not self.selected_page_id: return
        worker = self._start_worker(self._update_preview_async, start_idx, end_idx)
        if worker:
            worker.finished.connect(self.preview_updated) # preview_updated 시그널에 직접 연결
            worker.start()

    # --- Private Async Logic for Worker ---
    async def _load_pages_async(self, worker: WorkerThread):
        pages = await self._notion_engine.search_accessible_pages(filter_root_only=True)
        return pages

    async def _prepare_and_preview_page_async(self, worker: WorkerThread, page_id: str):
        json_path = self._temp_dir / f"{page_id}_children.json"
        
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                child_ids = json.load(f)
            worker.status_updated.emit("캐시된 데이터 확인 완료.")
        else:
            worker.status_updated.emit("페이지 데이터를 Notion에서 가져와 캐싱합니다...")
            children_resp = await self._notion_engine.notion.blocks.children.list(block_id=page_id, page_size=100)
            children = children_resp.get('results', [])
            child_ids = [page_id] + [c['id'] for c in children if c['type'] == 'child_page']

            for i, cid in enumerate(child_ids):
                worker.progress_updated.emit(int((i + 1) / len(child_ids) * 100))
                page_info = await self._notion_engine.get_page_by_id(cid)
                ctitle = await self._notion_engine.extract_page_title(page_info)
                blocks = await fetch_all_child_blocks(self._notion_engine.notion, cid)
                html_content = await blocks_to_html(blocks, self._notion_engine.notion)
                
                html_path = self._temp_dir / f"{cid}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(self._html2pdf_engine.generate_full_html(ctitle, html_content))
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(child_ids, f)
            worker.status_updated.emit("캐싱 완료.")
        return child_ids

    async def _update_preview_async(self, worker: WorkerThread, start_idx: int, end_idx: int):
        json_path = self._temp_dir / f"{self.selected_page_id}_children.json"
        if not json_path.exists():
            return "미리보기할 데이터가 없습니다. 먼저 페이지를 선택하여 캐시를 생성해주세요."

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
                    # 각 HTML에서 body 내용만 추출
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(f.read(), 'html.parser')
                    body_content = soup.body.decode_contents() if soup.body else ''
                    htmls.append(body_content)
        
        # 전체 HTML 구조로 감싸서 반환
        full_html = self._html2pdf_engine.generate_full_html("통합 미리보기", "<hr>".join(htmls))
        return full_html

    # --- Private Slots for Worker Results ---
    @Slot(object)
    def _on_pages_loaded(self, pages):
        self.pages = pages
        self.pages_changed.emit(self.pages)
        self.status_updated.emit(f"페이지 로드 완료. {len(self.pages)}개 페이지를 찾았습니다.")

    @Slot(object)
    def _on_prepare_and_preview_finished(self, child_ids):
        self.child_count_updated.emit(len(child_ids))
        self.progress_updated.emit(0)
        self.status_updated.emit("데이터 준비 완료. 미리보기를 표시합니다.")
        # 미리보기 업데이트 요청
        self.update_preview(0, len(child_ids) - 1)

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