import asyncio
import json
import sys
import re
import os
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
            return None
        
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
        self.status_updated.emit(f"페이지 선택됨: {page_title}")
        
        # 블록 개수만 가져와서 UI 업데이트 (실제 처리는 export에서)
        worker = self._start_worker(self._count_blocks_async, page_id)
        if worker:
            worker.finished.connect(self._on_blocks_counted)
            worker.start()

    @Slot(int, int)
    def update_preview(self, start_idx: int, end_idx: int):
        if not self.selected_page_id: 
            return
        
        # 간단한 미리보기만 생성
        worker = self._start_worker(self._simple_preview_async)
        if worker:
            worker.finished.connect(self._on_preview_updated)
            worker.start()

    # --- Private Async Logic for Worker ---
    async def _load_pages_async(self, worker: WorkerThread):
        worker.status_updated.emit("페이지 구조 분석 중...")
        root_pages, all_pages = await self._notion_engine.search_accessible_pages(filter_root_only=True)
        
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

    async def _count_blocks_async(self, worker: WorkerThread, page_id: str):
        """블록 개수만 세기 (미리보기용)"""
        try:
            blocks = await fetch_all_child_blocks(self._notion_engine.notion, page_id)
            return len(blocks)
        except Exception as e:
            print(f"블록 개수 세기 실패: {e}")
            return 0

    async def _simple_preview_async(self, worker: WorkerThread):
        """간단한 미리보기 - 실제 출력과는 무관"""
        if not self.selected_page_id:
            return ""
            
        worker.status_updated.emit("미리보기 생성 중...")
        
        try:
            # mainsub.py와 동일한 방식으로 HTML 생성
            blocks = await fetch_all_child_blocks(self._notion_engine.notion, self.selected_page_id)
            content_html = await blocks_to_html(blocks, self._notion_engine.notion)
            
            page_info = await self._notion_engine.get_page_by_id(self.selected_page_id)
            page_title = extract_page_title(page_info) if page_info else ""
            
            # mainsub.py의 get_styles() 함수 사용
            styles = self._get_styles()
            full_html = self._generate_html_with_conditional_title(page_title, content_html, styles)
            
            # 🔍 디버깅 정보 출력
            print(f"🎨 CSS 길이: {len(styles)} 문자")
            print(f"📝 Content HTML 길이: {len(content_html)} 문자")
            print(f"🌐 Full HTML 길이: {len(full_html)} 문자")
            
            # CSS 내용 일부 확인
            if styles:
                print(f"🎨 CSS 시작 부분: {styles[:200]}...")
            else:
                print("❌ CSS가 비어있음!")
            
            # HTML 내용 일부 확인  
            print(f"📝 Content HTML 시작 부분: {content_html[:500]}...")
            
            # 생성된 HTML을 임시 파일로 저장해서 확인
            debug_html_path = self._temp_dir / f"debug_{self.selected_page_id}.html"
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(full_html)
            print(f"🔍 디버그 HTML 저장됨: {debug_html_path}")
            
            # 스크린샷 생성
            preview_image_path = self._temp_dir / f"preview_{self.selected_page_id}.png"
            
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.set_content(full_html, wait_until="networkidle")
                await page.screenshot(path=str(preview_image_path), full_page=True)
                await browser.close()
            
            return str(preview_image_path)
            
        except Exception as e:
            print(f"미리보기 생성 실패: {e}")
            return ""

    def _get_styles(self):
        """mainsub.py의 get_styles() 함수와 완전히 동일하게 수정"""
        css_path = os.path.join(os.getcwd(), 'portfolio_style.css')
        try:
            with open(css_path, encoding='utf-8') as f:
                css = f.read()
            print(f"✅ CSS 파일 로드 성공: {len(css)} 문자")
            return css
        except Exception as e:
            print(f"❌ CSS 파일 읽기 오류: {e}")
            print(f"🔍 찾고 있는 경로: {css_path}")
            print(f"🔍 현재 작업 디렉토리: {os.getcwd()}")
            print(f"🔍 파일 존재 여부: {os.path.exists(css_path)}")
            return ""

    def _generate_html_with_conditional_title(self, page_title, content_html, styles):
        """mainsub.py와 완전히 동일한 포맷으로 수정 (멀티라인 문자열 사용)"""
        clean_title = page_title.strip() if page_title else ""
        if clean_title:
            title_section = f'<h1>{clean_title}</h1><div style="height: 0.3em;"></div>'
            body_class = ""
            html_title = clean_title
        else:
            title_section = ""
            body_class = ' class="no-title"'
            html_title = f"Portfolio"
        
        # mainsub.py와 동일한 멀티라인 포맷 사용
        return f"""
        <!DOCTYPE html>
        <html lang=\"ko\">
        <head>
            <meta charset=\"UTF-8\">
            <title>{html_title}</title>
            <style>{styles}</style>
        </head>
        <body{body_class}>
            {title_section}
            {content_html}
        </body>
        </html>
        """

    # --- Private Slots for Worker Results ---
    @Slot(object)
    def _on_pages_loaded(self, pages):
        self.pages = pages
        self.pages_changed.emit(self.pages)
        self.status_updated.emit(f"페이지 로드 완료. {len(self.pages)}개 페이지를 찾았습니다.")

    @Slot(object)
    def _on_blocks_counted(self, block_count):
        if block_count > 0:
            self.child_count_updated.emit(block_count)
            self.status_updated.emit(f"블록 {block_count}개 확인. 미리보기를 생성합니다.")
            # 자동으로 미리보기 생성
            self.update_preview(0, block_count - 1)
        else:
            self.status_updated.emit("블록을 찾을 수 없습니다.")

    @Slot(object)
    def _on_preview_updated(self, image_path):
        if image_path and isinstance(image_path, str) and os.path.exists(image_path):
            self.preview_updated.emit(image_path)
            self.status_updated.emit("미리보기 준비 완료.")
        else:
            self.status_updated.emit("미리보기 생성에 실패했습니다.")
            self.preview_updated.emit("")

    @Slot(str)
    def start_export(self, export_type: str):
        """실제 내보내기 - mainsub.py 로직 그대로 사용"""
        if not self.selected_page_id:
            self.status_updated.emit("페이지를 먼저 선택해주세요.")
            return
            
        self.status_updated.emit("PDF 내보내기 시작...")
        worker = self._start_worker(self._export_mainsub_async)
        if worker:
            worker.finished.connect(lambda result: self.status_updated.emit(result))
            worker.start()

    async def _export_mainsub_async(self, worker: WorkerThread):
        """mainsub.py의 main() 함수 로직 그대로 복사"""
        try:
            worker.status_updated.emit("Notion 블록 가져오는 중...")
            worker.progress_updated.emit(20)
            
            # mainsub.py와 동일: 전체 블록 가져오기
            blocks = await fetch_all_child_blocks(self._notion_engine.notion, self.selected_page_id)
            
            worker.status_updated.emit("HTML 변환 중...")
            worker.progress_updated.emit(40)
            
            # mainsub.py와 동일: HTML 변환
            content_html = await blocks_to_html(blocks, self._notion_engine.notion)
            
            # 페이지 제목 가져오기
            page_info = await self._notion_engine.get_page_by_id(self.selected_page_id)
            page_title = extract_page_title(page_info) if page_info else "Portfolio"
            
            # mainsub.py와 동일한 HTML 생성
            styles = self._get_styles()
            full_html = self._generate_html_with_conditional_title(page_title, content_html, styles)
            
            # 🔍 내보내기 시에도 디버깅 정보 출력
            print(f"📋 [내보내기] CSS 길이: {len(styles)} 문자")
            print(f"📋 [내보내기] Content HTML 길이: {len(content_html)} 문자")
            
            # 출력 파일명 (특수문자 제거)
            sanitized_title = re.sub(r'[\\/*?:"<>|]', "", page_title)
            output_dir = Path.cwd() / ".etc"
            output_dir.mkdir(exist_ok=True)
            
            # HTML 파일 저장
            html_path = output_dir / f"{sanitized_title}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(full_html)
            print(f"📋 [내보내기] HTML 파일 저장됨: {html_path}")
            
            worker.status_updated.emit("PDF 변환 중...")
            worker.progress_updated.emit(70)
            
            # mainsub.py와 동일한 PDF 생성
            pdf_path = output_dir / f"{sanitized_title}.pdf"
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(full_html, wait_until="networkidle")
                await page.pdf(path=str(pdf_path), format="A4", print_background=True)
                await browser.close()
            
            worker.progress_updated.emit(100)
            
            return f"✅ 생성 완료!\n📄 HTML: {html_path}\n📋 PDF: {pdf_path}"
            
        except Exception as e:
            return f"❌ 오류 발생: {e}"