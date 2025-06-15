import asyncio
import json
import sys
import re
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot

from core_engine import NotionEngine
from translate_engine import TranslateEngine, TranslationConfig
from html2pdf_engine import HTML2PDFEngine
from utils.helpers import extract_page_title
from utils.notion_parser import blocks_to_html, fetch_all_child_blocks
from ui.worker import WorkerThread
from playwright.async_api import async_playwright

class QtSignalStream(QObject):
    """STDOUT 출력을 Qt 시그널로 보내는 스트림 객체"""
    text_written = Signal(str)
    def write(self, text):
        self.text_written.emit(str(text))
    def flush(self):
        pass

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
        self.selected_page_title = None
        self._temp_dir = Path(".etc/temp")
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self.worker: WorkerThread = None

        # STDOUT 리디렉션
        self._stdout_stream = QtSignalStream()
        self._stdout_stream.text_written.connect(self.result_updated.emit)
        sys.stdout = self._stdout_stream
        sys.stderr = self._stdout_stream

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

    @Slot(str, str)
    def page_selected(self, page_id: str, page_title: str):
        self.selected_page_id = page_id
        self.selected_page_title = page_title
        self.status_updated.emit(f"페이지 선택됨: {page_title}...")
        worker = self._start_worker(self._prepare_and_preview_page_async, page_id)
        if worker:
            worker.finished.connect(self._on_prepare_and_preview_finished)
            worker.start()

    @Slot(int, int)
    def update_preview(self, start_idx: int, end_idx: int):
        if not self.selected_page_id: return
        # 새로운 미리보기 요청 시, 기존 작업이 있으면 취소(이번에는 구현하지 않지만, 향후 개선 가능)
        # 현재는 단순히 새 작업을 시작하게 합니다. _start_worker에서 중복 실행을 막습니다.
        worker = self._start_worker(self._update_preview_async, start_idx, end_idx)
        if worker:
            worker.finished.connect(self._on_preview_updated)
            worker.start()

    # --- Private Async Logic for Worker ---
    async def _load_pages_async(self, worker: WorkerThread):
        worker.status_updated.emit("페이지 구조 분석 중...")
        root_pages, all_pages = await self._notion_engine.search_accessible_pages(filter_root_only=True)
        
        # 전체 페이지를 ID 기반으로 빠르게 찾을 수 있도록 딕셔너리로 변환
        all_pages_dict = {p['id']: p for p in all_pages}
        
        # 부모-자식 관계를 딕셔너리로 구성
        parent_to_children = {}
        for page in all_pages:
            parent = page.get('parent')
            if parent and parent.get('type') == 'page_id':
                parent_id = parent.get('page_id')
                if parent_id not in parent_to_children:
                    parent_to_children[parent_id] = []
                parent_to_children[parent_id].append(page)

        # 최종적으로 트리에 표시할 데이터를 구성
        pages_with_children = []
        total = len(root_pages)
        for i, page in enumerate(root_pages):
            worker.progress_updated.emit(int((i + 1) / total * 100))
            page_id = page['id']
            children = parent_to_children.get(page_id, [])
            
            pages_with_children.append({
                "page_info": page,
                "children": children
            })
            
        return pages_with_children

    async def _prepare_and_preview_page_async(self, worker: WorkerThread, page_id: str):
        json_path = self._temp_dir / f"{page_id}_children.json"
        
        if json_path.exists():
            worker.status_updated.emit("캐시된 데이터 확인 완료.")
            with open(json_path, "r", encoding="utf-8") as f:
                child_ids = json.load(f)
        else:
            worker.status_updated.emit("페이지 데이터를 Notion에서 가져와 캐싱합니다...")
            
            # 하위 페이지 목록을 먼저 가져옵니다.
            child_page_ids = []
            try:
                children_resp = await self._notion_engine.notion.blocks.children.list(block_id=page_id, page_size=100)
                children = children_resp.get('results', [])
                child_page_ids = [c['id'] for c in children if c['type'] == 'child_page']
            except Exception as e:
                worker.status_updated.emit(f"하위 페이지 조회 중 경고: {e}")

            # 하위 페이지가 있으면 하위 페이지만, 없으면 현재 페이지만 목록에 포함
            if child_page_ids:
                child_ids = child_page_ids
                worker.status_updated.emit(f"하위 페이지가 있어, {len(child_ids)}개의 하위 페이지만 처리합니다.")
            else:
                child_ids = [page_id]
                worker.status_updated.emit("단독 페이지를 처리합니다.")

            total_pages = len(child_ids)
            for i, cid in enumerate(child_ids):
                worker.progress_updated.emit(int((i + 1) / total_pages * 100))
                page_info = await self._notion_engine.get_page_by_id(cid)
                if not page_info: # 페이지 정보를 가져오지 못하면 건너뜁니다.
                    worker.status_updated.emit(f"경고: 페이지 정보({cid})를 가져올 수 없습니다.")
                    continue

                ctitle = extract_page_title(page_info)
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
            return "" # 이미지 경로 대신 빈 문자열 반환

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
        
        if not htmls:
            return ""

        # 전체 HTML 구조로 감싸서 Playwright로 렌더링 후 스크린샷
        full_html = self._html2pdf_engine.generate_full_html("", "<hr>".join(htmls))
        preview_image_path = self._temp_dir / "preview.png"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.set_content(full_html, wait_until="networkidle")
                await page.screenshot(path=str(preview_image_path), full_page=True)
                await browser.close()
            return str(preview_image_path)
        except Exception as e:
            print(f"미리보기 이미지 생성 실패: {e}")
            return ""

    # --- Private Slots for Worker Results ---
    @Slot(object)
    def _on_pages_loaded(self, pages):
        self.pages = pages
        self.pages_changed.emit(self.pages)
        self.status_updated.emit(f"페이지 로드 완료. {len(self.pages)}개 페이지를 찾았습니다.")

    @Slot(object)
    def _on_preview_updated(self, image_path):
        if image_path and isinstance(image_path, str):
            self.preview_updated.emit(image_path)
        else:
            self.status_updated.emit("미리보기 컨텐츠 생성에 실패했습니다.")
            self.preview_updated.emit("")

    @Slot(object)
    def _on_prepare_and_preview_finished(self, child_ids):
        if not child_ids:
            self.status_updated.emit("오류: 페이지 데이터를 준비할 수 없습니다.")
            self.progress_updated.emit(0)
            self.child_count_updated.emit(0)
            return

        self.child_count_updated.emit(len(child_ids))
        self.progress_updated.emit(0)
        self.status_updated.emit("데이터 준비 완료. 미리보기를 표시합니다.")
        # 미리보기 업데이트 요청 (결과가 유효할 때만)
        self.update_preview(0, len(child_ids) - 1)

    @Slot(str)
    def start_export(self, export_type: str):
        # 지금은 간단한 시나리오만 구현
        self.status_updated.emit("PDF/HTML export 시작...")
        worker = self._start_worker(self._export_async)
        if worker:
            # 익스포트 완료 후 상태 업데이트를 위한 연결
            worker.finished.connect(lambda result: self.status_updated.emit(result))
            worker.start()

    async def _export_async(self, worker: WorkerThread):
        json_path = self._temp_dir / f"{self.selected_page_id}_children.json"
        if not json_path.exists():
            return "오류: 내보낼 캐시 데이터가 없습니다."

        # 파일명으로 사용할 수 없는 문자 제거/변경
        sanitized_title = re.sub(r'[\\/*?:"<>|]', "", self.selected_page_title)
        output_dir = Path.cwd() / ".etc" # 절대 경로 사용으로 수정
        temp_dir = self._temp_dir

        with open(json_path, "r") as f:
            child_ids = json.load(f)

        all_html_content = []
        for i, cid in enumerate(child_ids):
            worker.progress_updated.emit(int((i + 1) / len(child_ids) * 100))
            html_path = temp_dir / f"{cid}.html"
            if not html_path.exists():
                worker.status_updated.emit(f"경고: 캐시된 HTML 파일({html_path})이 없습니다. 건너뜁니다.")
                continue

            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
                all_html_content.append(html_content)

            # 개별 PDF 저장 (하위 페이지가 있을 경우)
            if len(child_ids) > 1:
                pdf_filename = f"{sanitized_title}_{i:02d}.pdf"
                await self._html2pdf_engine.html_to_pdf(html_content, temp_dir / pdf_filename)
        
        # 최종 합본 PDF 생성
        final_html = self._html2pdf_engine.generate_full_html("", "<hr>".join(all_html_content))
        final_pdf_path = output_dir / f"{sanitized_title}_final.pdf"
        await self._html2pdf_engine.html_to_pdf(final_html, final_pdf_path)

        worker.progress_updated.emit(100)
        return f"내보내기 완료: {final_pdf_path}" 