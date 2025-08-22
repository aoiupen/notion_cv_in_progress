import sys
import os
import asyncio
import time
from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel, QMessageBox, QProgressBar
from PySide6.QtCore import Qt, QThread, Signal, Slot
from notion_client import AsyncClient
from exporter import export_and_merge_pdf
from notion_api import get_root_pages, get_first_child_page_ids
from config import FINAL_PDF_NAME
from utils import extract_page_title

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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Notion PDF Exporter")
        self.setMinimumSize(600, 400)
        self.root_pages = []
        self.all_pages = []
        self.init_ui()
        self.load_pages_thread = None
        self.export_pdf_thread = None
        self.load_pages()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.label = QLabel("목록:")
        layout.addWidget(self.label)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.list_widget)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        button_layout = QHBoxLayout()
        self.export_btn = QPushButton("PDF로 내보내기")
        self.export_btn.clicked.connect(self.export_pdf)
        button_layout.addWidget(self.export_btn)

        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.clicked.connect(self.load_pages)
        button_layout.addWidget(self.refresh_btn)

        layout.addLayout(button_layout)

    def load_pages(self):
        self.label.setText("페이지 불러오는 중...")
        self.set_buttons_enabled(False)
        self.load_pages_thread = LoadPagesThread()
        self.load_pages_thread.pages_loaded.connect(self.on_pages_loaded)
        self.load_pages_thread.error.connect(self.on_load_pages_error)
        self.load_pages_thread.start()

    @Slot(list, list)
    def on_pages_loaded(self, root_pages, all_pages):
        self.root_pages = root_pages
        self.all_pages = all_pages
        self.list_widget.clear()
        for page in root_pages:
            title = extract_page_title(page)
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, page['id'])
            self.list_widget.addItem(item)
        self.label.setText("목록:")
        self.set_buttons_enabled(True)

    @Slot(str)
    def on_load_pages_error(self, msg):
        QMessageBox.critical(self, "오류", f"페이지 불러오기 실패: {msg}")
        self.label.setText("페이지 불러오기 실패")
        self.set_buttons_enabled(True)

    def set_buttons_enabled(self, enabled: bool):
        self.export_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)

    def set_exporting_state(self, exporting: bool):
        self.set_buttons_enabled(not exporting)
        self.progress_bar.setEnabled(exporting)
        if exporting:
            self.label.setText("PDF 생성 중...")
        else:
            self.label.setText("목록:")

    @Slot(str, float)
    def show_export_result(self, result, elapsed=None):
        msg = ""
        if result:
            msg = f"PDF 생성 완료: {result}"
            if elapsed is not None:
                msg += f"\n(총 소요 시간: {elapsed:.2f}초)"
            QMessageBox.information(self, "완료", msg)
            self.label.setText("PDF 생성 완료!" + (f" (총 {elapsed:.2f}초)" if elapsed is not None else ""))
        else:
            msg = "PDF 생성 실패"
            if elapsed is not None:
                msg += f"\n(총 소요 시간: {elapsed:.2f}초)"
            QMessageBox.critical(self, "실패", msg)
            self.label.setText("PDF 생성 실패" + (f" (총 {elapsed:.2f}초)" if elapsed is not None else ""))
        self.set_exporting_state(False)

    @Slot(int, int)
    def update_progress(self, current, total_pages):
        self.progress_bar.setValue(current)
        percent = int((current / total_pages) * 100) if total_pages > 0 else 0
        self.label.setText(f"PDF 생성 중... {percent}% ({current}/{total_pages})")
        QApplication.processEvents()

    @Slot(str)
    def on_export_error(self, msg):
        QMessageBox.critical(self, "오류", f"PDF 생성 실패: {msg}")
        self.set_exporting_state(False)
        self.label.setText("PDF 생성 실패")

    def export_pdf(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "경고", "최소 하나의 페이지를 선택하세요.")
            return

        page_ids = []
        notion_client = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for item in selected_items:
            page_id = item.data(Qt.UserRole)
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

        self.export_pdf_thread = ExportPDFThread(page_ids_unique, FINAL_PDF_NAME)
        self.export_pdf_thread.progress.connect(self.update_progress)
        self.export_pdf_thread.finished.connect(self.show_export_result)
        self.export_pdf_thread.error.connect(self.on_export_error)
        self.export_pdf_thread.start()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()