import sys
import os
import asyncio
import time
from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel, QMessageBox, QProgressBar, QStyleFactory, QTreeWidget, QTreeWidgetItem, QSplitter, QTreeView, QFileSystemModel, QFileDialog
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer, QDir, QSettings
from PySide6.QtGui import QPalette, QColor, QDesktopServices
from PySide6.QtCore import QUrl
from notion_client import AsyncClient
from exporter import export_and_merge_pdf
from notion_api import get_root_pages, get_first_child_page_ids
from config import FINAL_PDF_NAME, FINAL_PDF_PATH
from utils import extract_page_title, extract_page_title_raw, extract_page_title_for_tree, has_hide_marker

load_dotenv()

class LoadPagesThread(QThread):
    pages_loaded = Signal(list, list)
    error = Signal(str)

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            root_pages, all_pages = loop.run_until_complete(get_root_pages())
            self.pages_loaded.emit(root_pages, all_pages)
        except Exception as e:
            self.error.emit(str(e))

class ExportPDFThread(QThread):
    progress = Signal(int, int)
    finished = Signal(str, float)
    error = Signal(str)

    def __init__(self, page_ids_unique, final_pdf_name):
        super().__init__()
        self.page_ids_unique = page_ids_unique
        self.final_pdf_name = final_pdf_name

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            start_time = time.time()
            def progress_callback(current, total_pages):
                self.progress.emit(current, total_pages)
            result = loop.run_until_complete(export_and_merge_pdf(self.page_ids_unique, self.final_pdf_name, progress_callback))
            elapsed = time.time() - start_time
            self.finished.emit(result, elapsed)
        except Exception as e:
            self.error.emit(str(e))

class LoadChildrenThread(QThread):
    children_loaded = Signal(str, list)
    error = Signal(str)

    def __init__(self, parent_page_id: str):
        super().__init__()
        self.parent_page_id = parent_page_id

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            notion_client = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
            child_ids = loop.run_until_complete(get_first_child_page_ids(self.parent_page_id, notion_client))
            children = []
            for cid in child_ids:
                page_info = loop.run_until_complete(notion_client.pages.retrieve(page_id=cid))
                children.append(page_info)
            self.children_loaded.emit(self.parent_page_id, children)
        except Exception as e:
            self.error.emit(str(e))

class ChildPresenceThread(QThread):
    ready = Signal(list, dict)
    error = Signal(str)

    def __init__(self, pages: list):
        super().__init__()
        self.pages = pages

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            notion_client = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
            flags = {}
            for page in self.pages:
                pid = page.get('id')
                try:
                    child_ids = loop.run_until_complete(get_first_child_page_ids(pid, notion_client))
                    flags[pid] = bool(child_ids)
                except Exception:
                    flags[pid] = False
            self.ready.emit(self.pages, flags)
        except Exception as e:
            self.error.emit(str(e))

class BuildFullTreeThread(QThread):
    tree_ready = Signal(dict)
    progress = Signal(int)
    error = Signal(str)

    def __init__(self, root_pages: list):
        super().__init__()
        self.root_pages = root_pages

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            notion_client = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
            parent_to_children = {}
            visited = set()

            async def crawl(page_id: str):
                if page_id in visited:
                    return
                visited.add(page_id)
                # 진행 보고
                self.progress.emit(len(visited))
                ids = await get_first_child_page_ids(page_id, notion_client)
                children_pages = []
                for cid in ids:
                    page_info = await notion_client.pages.retrieve(page_id=cid)
                    children_pages.append(page_info)
                parent_to_children[page_id] = children_pages
                for child in children_pages:
                    await crawl(child['id'])

            async def run_all():
                for page in self.root_pages:
                    await crawl(page['id'])

            loop.run_until_complete(run_all())
            self.tree_ready.emit(parent_to_children)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self, demo_mode: bool = False, initial_out_dir: str | None = None):
        super().__init__()
        self.setWindowTitle("Notion PDF Exporter")
        self.setMinimumSize(720, 480)
        self.root_pages = []
        self.all_pages = []
        self.demo_mode = demo_mode
        self.initial_out_dir = initial_out_dir
        self.settings = QSettings("notion_cv", "notion_pdf_exporter")
        self.init_ui()
        self.load_pages_thread = None
        self.export_pdf_thread = None
        if self.demo_mode:
            self.setup_demo_ui()
        else:
            self.load_pages()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(8)
        # 상단: 프로그레스바 + PDF 내보내기 + 새로고침
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        header.addWidget(self.progress_bar, 1)
        self.export_btn = QPushButton("PDF로 내보내기")
        self.export_btn.clicked.connect(self.export_pdf)
        self.export_btn.setProperty("type", "primary")
        header.addWidget(self.export_btn)
        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.clicked.connect(self.load_pages)
        self.refresh_btn.setProperty("type", "secondary")
        header.addWidget(self.refresh_btn)
        self.up_btn = QPushButton("상위")
        self.up_btn.clicked.connect(self.go_up_directory)
        self.up_btn.setProperty("type", "secondary")
        header.addWidget(self.up_btn)
        self.outdir_btn = QPushButton("폴더 변경")
        self.outdir_btn.clicked.connect(self.change_output_dir)
        self.outdir_btn.setProperty("type", "secondary")
        header.addWidget(self.outdir_btn)
        layout.addLayout(header)
        splitter = QSplitter(Qt.Vertical)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.itemExpanded.connect(self.on_item_expanded)
        splitter.addWidget(self.tree_widget)
        # 파일 브라우저 (출력 폴더 표시)
        self.fs_model = QFileSystemModel()
        # 출력 폴더: 설정값 > 초기 인자 > 디폴트(.etc)
        if self.initial_out_dir and os.path.isdir(self.initial_out_dir):
            out_dir = self.initial_out_dir
        else:
            out_dir = self.settings.value("output_dir", os.path.abspath(os.path.dirname(FINAL_PDF_PATH)))
            if not out_dir or not os.path.isdir(out_dir):
                out_dir = os.path.abspath(os.path.dirname(FINAL_PDF_PATH))
        # 폴더가 없으면 먼저 생성
        os.makedirs(out_dir, exist_ok=True)
        self.out_dir = out_dir
        idx = self.fs_model.setRootPath(out_dir)
        # 디렉터리와 파일을 모두 표시하고, 숨김/점 항목은 제외
        self.fs_model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot | QDir.Readable)
        # 디렉터리 로드 완료 시 강제 루트 인덱스 갱신 (일부 환경에서 초기 표시가 비어 보이는 문제 대응)
        try:
            self.fs_model.directoryLoaded.connect(self.on_dir_loaded)
        except Exception:
            pass
        self.file_view = QTreeView()
        self.file_view.setModel(self.fs_model)
        self.file_view.setRootIndex(idx)
        self.file_view.setSortingEnabled(True)
        try:
            self.file_view.sortByColumn(3, Qt.DescendingOrder)
        except Exception:
            pass
        self.file_view.doubleClicked.connect(self.on_file_double_clicked)
        splitter.addWidget(self.file_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        # 초기 표시 직후 한 번 더 갱신하여 내용 보장
        QTimer.singleShot(0, self.refresh_file_view)
        
        # 페이지 ID 매핑 캐시
        self.page_item_map = {}

    # --- Demo mode helpers ---
    def setup_demo_ui(self):
        # 더미 데이터로 트리 채우기
        self.tree_widget.clear()
        dummy_items = [
            "프로젝트 Alpha", "프로젝트 Beta", "프로젝트 Gamma",
            "기술 스택 정리", "시스템 설계 노트", "테스트 시나리오",
            "프로토타입 스크린샷", "회고 및 개선안"
        ]
        for idx, name in enumerate(dummy_items):
            root = QTreeWidgetItem([name])
            root.setData(0, Qt.UserRole, "demo-id")
            if idx == 1:
                for j in range(1, 4):
                    child = QTreeWidgetItem([f"Beta 하위 {j}"])
                    child.setData(0, Qt.UserRole, "demo-child-id")
                    root.addChild(child)
            else:
                root.addChild(QTreeWidgetItem(["..."]))
            self.tree_widget.addTopLevelItem(root)
        # 두 번째 최상위 항목만 선택
        for i in range(self.tree_widget.topLevelItemCount()):
            it = self.tree_widget.topLevelItem(i)
            if it:
                it.setSelected(False)
        if self.tree_widget.topLevelItemCount() >= 2:
            self.tree_widget.topLevelItem(1).setSelected(True)
        # 진행률 표시 연출 (예: 10/25 => 40%)
        self.progress_bar.setMaximum(25)
        self.progress_bar.setValue(10)
        self.progress_bar.setFormat("PDF 생성 중... 40% (10/25)")
        # 실행 버튼은 비활성화, 새로고침은 보이되 비활성화
        self.export_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        # 창 표시 이후 캡처를 위해 약간 지연 후 캡처
        QTimer.singleShot(350, self.capture_demo_and_quit)

    def capture_demo_and_quit(self):
        try:
            out_dir = os.path.join(os.getcwd(), "@image")
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, "ui_demo.png")
            pixmap = self.grab()
            pixmap.save(out_path)
        except Exception:
            pass
        QTimer.singleShot(150, QApplication.instance().quit)

    def load_pages(self):
        self.progress_bar.setFormat("페이지 불러오는 중...")
        self.set_buttons_enabled(False)
        self.load_pages_thread = LoadPagesThread()
        self.load_pages_thread.pages_loaded.connect(self.on_pages_loaded)
        self.load_pages_thread.error.connect(self.on_load_pages_error)
        self.load_pages_thread.start()

    # --- Lazy load when expanding a node ---
    def on_item_expanded(self, item: QTreeWidgetItem):
        try:
            if item.childCount() == 1 and item.child(0).text(0) == "...":
                parent_id = item.data(0, Qt.UserRole)
                if isinstance(parent_id, str):
                    self.start_load_children(parent_id)
        except Exception:
            pass

    def start_load_children(self, parent_page_id: str):
        thread = LoadChildrenThread(parent_page_id)
        thread.children_loaded.connect(self.on_children_loaded)
        thread.error.connect(lambda msg: None)
        thread.start()
        if not hasattr(self, "_child_threads"):
            self._child_threads = []
        self._child_threads.append(thread)

    def on_children_loaded(self, parent_page_id: str, children_pages: list):
        parent_item = self.page_item_map.get(parent_page_id)
        if parent_item is None:
            return
        parent_item.takeChildren()
        for page in children_pages:
            title = extract_page_title_for_tree(page)
            child = QTreeWidgetItem([title])
            child.setData(0, Qt.UserRole, page['id'])
            # 말단 노드는 기본적으로 삼각형(더미) 없이
            parent_item.addChild(child)
            self.page_item_map[page['id']] = child

    @Slot(list, dict)
    def on_child_presence_ready(self, pages: list, flags: dict):
        # 루트 항목들의 삼각형 유무 반영
        for page in pages:
            pid = page.get('id')
            item = self.page_item_map.get(pid)
            if not item:
                continue
            # 기존 자식 제거
            item.takeChildren()
            if flags.get(pid):
                # 자식이 있는 경우에만 더미를 넣어 확장 아이콘 표시
                item.addChild(QTreeWidgetItem(["..."]))

    @Slot(dict)
    def on_full_tree_ready(self, parent_to_children: dict):
        # 완전한 트리를 한 번에 반영 (말단에는 더미를 추가하지 않음)
        for pid, item in list(self.page_item_map.items()):
            item.takeChildren()
        for parent_id, children_pages in parent_to_children.items():
            parent_item = self.page_item_map.get(parent_id)
            if not parent_item:
                continue
            for page in children_pages:
                title = extract_page_title_for_tree(page)
                child = QTreeWidgetItem([title])
                child.setData(0, Qt.UserRole, page['id'])
                parent_item.addChild(child)
                self.page_item_map[page['id']] = child
        self.progress_bar.setFormat("")

    @Slot(int)
    def on_full_tree_progress(self, visited_count: int):
        self.progress_bar.setFormat(f"트리 구성 중... {visited_count}개 로드")

    @Slot(list, list)
    def on_pages_loaded(self, root_pages, all_pages):
        self.root_pages = root_pages
        self.all_pages = all_pages
        self.tree_widget.clear()
        self.page_item_map.clear()
        for page in root_pages:
            title = extract_page_title_for_tree(page)
            root_item = QTreeWidgetItem([title])
            root_item.setData(0, Qt.UserRole, page['id'])
            # 일단 자식 더미는 넣지 않고, 존재 여부를 비동기로 판별 후 설정
            self.tree_widget.addTopLevelItem(root_item)
            self.page_item_map[page['id']] = root_item
        # 전체 트리 비동기 사전 구성: 펼칠 때 지연 없이 즉시 표시되도록
        self.full_tree_thread = BuildFullTreeThread(root_pages)
        self.full_tree_thread.tree_ready.connect(self.on_full_tree_ready)
        self.full_tree_thread.progress.connect(self.on_full_tree_progress)
        self.full_tree_thread.error.connect(lambda msg: self.progress_bar.setFormat("트리 구성 실패"))
        self.full_tree_thread.start()
        self.progress_bar.setFormat("")
        self.set_buttons_enabled(True)

    @Slot(str)
    def on_load_pages_error(self, msg):
        QMessageBox.critical(self, "오류", f"페이지 불러오기 실패: {msg}")
        self.progress_bar.setFormat("페이지 불러오기 실패")
        self.set_buttons_enabled(True)

    def set_buttons_enabled(self, enabled: bool):
        self.export_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)

    def set_exporting_state(self, exporting: bool):
        self.set_buttons_enabled(not exporting)
        self.progress_bar.setEnabled(exporting)
        if exporting:
            self.progress_bar.setFormat("PDF 생성 중...")
        else:
            self.progress_bar.setFormat("")

    @Slot(str, float)
    def show_export_result(self, result, elapsed=None):
        msg = ""
        if result:
            msg = f"PDF 생성 완료: {result}"
            if elapsed is not None:
                msg += f"\n(총 소요 시간: {elapsed:.2f}초)"
            QMessageBox.information(self, "완료", msg)
            self.progress_bar.setFormat("PDF 생성 완료!" + (f" (총 {elapsed:.2f}초)" if elapsed is not None else ""))
            # 파일 브라우저 새로고침 (감시가 늦을 수 있어 강제 갱신)
            try:
                if hasattr(self, 'fs_model') and hasattr(self, 'file_view') and hasattr(self, 'out_dir'):
                    idx = self.fs_model.setRootPath(self.out_dir)
                    self.file_view.setRootIndex(idx)
            except Exception:
                pass
        else:
            msg = "PDF 생성 실패"
            if elapsed is not None:
                msg += f"\n(총 소요 시간: {elapsed:.2f}초)"
            QMessageBox.critical(self, "실패", msg)
            self.progress_bar.setFormat("PDF 생성 실패" + (f" (총 {elapsed:.2f}초)" if elapsed is not None else ""))
        self.set_exporting_state(False)

    @Slot(int, int)
    def update_progress(self, current, total_pages):
        self.progress_bar.setValue(current)
        percent = int((current / total_pages) * 100) if total_pages > 0 else 0
        self.progress_bar.setFormat(f"PDF 생성 중... {percent}% ({current}/{total_pages})")
        QApplication.processEvents()

    @Slot(str)
    def on_export_error(self, msg):
        QMessageBox.critical(self, "오류", f"PDF 생성 실패: {msg}")
        self.set_exporting_state(False)
        self.progress_bar.setFormat("PDF 생성 실패")

    def export_pdf(self):
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "경고", "최소 하나의 페이지를 선택하세요.")
            return

        page_ids = []
        notion_client = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for item in selected_items:
            page_id = item.data(0, Qt.UserRole)
            first_child_ids = loop.run_until_complete(get_first_child_page_ids(page_id, notion_client))
            if first_child_ids:
                page_ids.extend(first_child_ids)
            else:
                # 하위 페이지가 없으면 선택한 페이지 자체를 추가
                page_ids.append(page_id)

        page_ids_unique = list(dict.fromkeys(page_ids))
        total = len(page_ids_unique)

        if total == 0:
            QMessageBox.warning(self, "경고", "출력할 페이지가 없습니다.")
            return

        self.set_exporting_state(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        # 선택된 최상위 노드의 이름으로 파일명 구성
        top_selected = [it for it in selected_items if not it.parent()]
        base_name = extract_page_title_for_tree(self.page_item_map_inv(top_selected[0]) if top_selected else {"properties":{}}) if False else None
        # 위 한 줄은 안전을 위해 무시하고, 아래에서 텍스트 그대로 사용
        base_name = top_selected[0].text(0) if top_selected else "My_Portfolio_Final"
        safe_name = ''.join(c for c in base_name if c not in '\\/:*?"<>|').strip() or "My_Portfolio_Final"
        # 현재 보기 중인 폴더에 저장
        current_dir = self.out_dir if hasattr(self, 'out_dir') and self.out_dir else os.path.dirname(FINAL_PDF_PATH)
        output_name = os.path.join(current_dir, f"{safe_name}.pdf")
        # 동일 파일명이 있으면 덮어쓰기, 없으면 새로 생성 (파일명 변경 없이)
        self.export_pdf_thread = ExportPDFThread(page_ids_unique, output_name)
        self.export_pdf_thread.progress.connect(self.update_progress)
        self.export_pdf_thread.finished.connect(self.show_export_result)
        self.export_pdf_thread.error.connect(self.on_export_error)
        self.export_pdf_thread.start()

    def on_file_double_clicked(self, index):
        try:
            path = self.fs_model.filePath(index)
            if self.fs_model.isDir(index):
                # 디렉터리로 이동
                self.out_dir = path
                self.settings.setValue("output_dir", path)
                idx = self.fs_model.setRootPath(path)
                self.file_view.setRootIndex(idx)
            elif os.path.isfile(path):
                # 파일 열기
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            pass

    def change_output_dir(self):
        try:
            start_dir = self.out_dir if hasattr(self, 'out_dir') and self.out_dir else os.getcwd()
            new_dir = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", start_dir)
            if new_dir:
                self.out_dir = new_dir
                self.settings.setValue("output_dir", new_dir)
                idx = self.fs_model.setRootPath(new_dir)
                self.file_view.setRootIndex(idx)
        except Exception:
            pass

    def go_up_directory(self):
        try:
            if not hasattr(self, 'out_dir') or not self.out_dir:
                return
            parent = os.path.dirname(self.out_dir.rstrip("/\\"))
            if parent and os.path.isdir(parent):
                self.out_dir = parent
                self.settings.setValue("output_dir", parent)
                idx = self.fs_model.setRootPath(parent)
                self.file_view.setRootIndex(idx)
        except Exception:
            pass

    def refresh_file_view(self):
        try:
            if hasattr(self, 'out_dir'):
                # 강제 재스캔: 루트를 잠시 시스템 루트로 옮겼다가 되돌림
                self.fs_model.setRootPath(QDir.rootPath())
                idx = self.fs_model.setRootPath(self.out_dir)
                self.file_view.setRootIndex(idx)
        except Exception:
            pass

    def on_dir_loaded(self, path: str):
        try:
            if hasattr(self, 'out_dir') and os.path.abspath(path) == os.path.abspath(self.out_dir):
                idx = self.fs_model.index(self.out_dir)
                self.file_view.setRootIndex(idx)
        except Exception:
            pass

def main():
    app = QApplication(sys.argv)
    is_demo = "--demo" in sys.argv
    out_dir_arg = None
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            out_dir_arg = sys.argv[i + 1]
            break
    try:
        # Fusion 스타일 기반 + 팔레트 + QSS 적용
        app.setStyle(QStyleFactory.create("Fusion"))
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#F6F7FB"))
        palette.setColor(QPalette.WindowText, QColor("#202124"))
        palette.setColor(QPalette.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.AlternateBase, QColor("#F2F4F8"))
        palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
        palette.setColor(QPalette.ToolTipText, QColor("#202124"))
        palette.setColor(QPalette.Text, QColor("#202124"))
        palette.setColor(QPalette.Button, QColor("#FFFFFF"))
        palette.setColor(QPalette.ButtonText, QColor("#202124"))
        palette.setColor(QPalette.Highlight, QColor("#3B82F6"))
        palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        app.setPalette(palette)

        app.setStyleSheet(load_app_stylesheet())
    except Exception:
        # 스타일 적용 실패 시에도 앱은 실행되도록 방어
        pass
    window = MainWindow(demo_mode=is_demo, initial_out_dir=out_dir_arg)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

# --- QSS (앱 전체 테마) ---
def load_app_stylesheet() -> str:
    return """
    QWidget { background: #F6F7FB; color: #202124; }
    QMainWindow { background: #F6F7FB; }

    QLabel#headerLabel {
        font-size: 16px;
        font-weight: 600;
        padding: 2px 0 6px 0;
        color: #111827;
    }

    QListWidget {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 6px;
    }
    QListWidget::item {
        padding: 8px 10px;
        border-radius: 6px;
        margin: 2px 2px;
    }
    QListWidget::item:selected {
        background: #E0EBFF;
        color: #111827;
    }
    QListWidget::item:hover {
        background: #F3F4F6;
    }

    QProgressBar {
        background: #EEF2FF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        text-align: center;
        padding: 3px;
        color: #111827;
    }
    QProgressBar::chunk {
        background-color: #22C55E;
        border-radius: 6px;
    }

    QPushButton {
        border: 1px solid #D1D5DB;
        border-radius: 10px;
        padding: 8px 14px;
        background: #FFFFFF;
        color: #111827;
    }
    QPushButton[type="primary"] {
        background: #3B82F6;
        color: #FFFFFF;
        border: 1px solid #3B82F6;
    }
    QPushButton[type="primary"]:hover { background: #2563EB; border-color: #2563EB; }
    QPushButton[type="primary"]:pressed { background: #1D4ED8; border-color: #1D4ED8; }

    QPushButton[type="secondary"] {
        background: #FFFFFF;
        color: #111827;
        border: 1px solid #D1D5DB;
    }
    QPushButton[type="secondary"]:hover { background: #F3F4F6; }
    QPushButton[type="secondary"]:pressed { background: #E5E7EB; }
    QPushButton:disabled {
        background: #F3F4F6;
        color: #9CA3AF;
        border-color: #E5E7EB;
    }

    /* 스크롤바 (가벼운 스타일) */
    QScrollBar:vertical {
        background: transparent; width: 10px; margin: 2px; border: none;
    }
    QScrollBar::handle:vertical {
        background: #D1D5DB; min-height: 24px; border-radius: 5px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px; background: none; border: none;
    }

    QScrollBar:horizontal {
        background: transparent; height: 10px; margin: 2px; border: none;
    }
    QScrollBar::handle:horizontal {
        background: #D1D5DB; min-width: 24px; border-radius: 5px;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px; background: none; border: none;
    }
    """