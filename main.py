import sys
import os
import asyncio
import time
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel, QMessageBox, QProgressBar
from PySide6.QtCore import Qt
from notion_client import AsyncClient
from exporter import export_and_merge_pdf
from notion_api import get_root_pages, get_all_descendant_page_ids
from config import FINAL_PDF_NAME
from utils import extract_page_title

async def get_first_child_page_ids(page_id, notion_client):
    # Notion blocks.children.list로 실제 children 순서대로 추출
    children = []
    try:
        response = await notion_client.blocks.children.list(block_id=page_id, page_size=100)
        children = response['results']
        next_cursor = response.get('next_cursor')
        while next_cursor:
            response = await notion_client.blocks.children.list(block_id=page_id, page_size=100, start_cursor=next_cursor)
            children.extend(response['results'])
            next_cursor = response.get('next_cursor')
    except Exception as e:
        print(f"하위 페이지 순서 가져오기 오류: {e}")
        return []
    # type이 'child_page'인 것만 추출
    return [block['id'] for block in children if block['type'] == 'child_page']

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Notion PDF Exporter (Simple UI)")
        self.setMinimumSize(600, 400)
        self.root_pages = []
        self.all_pages = []
        self.init_ui()
        self.load_pages_sync()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.label = QLabel("Notion 루트 페이지 목록:")
        layout.addWidget(self.label)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.list_widget)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.export_btn = QPushButton("PDF로 내보내기")
        self.export_btn.clicked.connect(self.export_pdf)
        layout.addWidget(self.export_btn)

    async def load_pages(self):
        self.label.setText("페이지 불러오는 중...")
        root_pages, all_pages = await get_root_pages()
        self.root_pages = root_pages
        self.all_pages = all_pages
        self.list_widget.clear()
        for page in root_pages:
            title = extract_page_title(page)
            item = QListWidgetItem(f"{title} ({page['id'][:8]})")
            item.setData(Qt.UserRole, page['id'])
            self.list_widget.addItem(item)
        self.label.setText("Notion 루트 페이지 목록:")

    def load_pages_sync(self):
        asyncio.run(self.load_pages())

    def set_exporting_state(self, exporting: bool):
        self.export_btn.setEnabled(not exporting)
        self.progress_bar.setEnabled(exporting)
        if exporting:
            self.label.setText("PDF 생성 중...")
        else:
            self.label.setText("Notion 루트 페이지 목록:")

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

    def export_pdf(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "경고", "최소 하나의 페이지를 선택하세요.")
            return

        page_ids = []
        notion_client = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
        
        for item in selected_items:
            page_id = item.data(Qt.UserRole)
            first_child_ids = asyncio.run(get_first_child_page_ids(page_id, notion_client))
            if first_child_ids:
                page_ids.extend(first_child_ids)
            else:
                # 하위 페이지가 없으면 선택한 페이지 자체를 추가
                page_ids.append(page_id)

        page_ids_unique = list(dict.fromkeys(page_ids))
        total = len(page_ids_unique)
        
        if total == 0:
            QMessageBox.warning(self, "경고", "선택한 페이지에 하위 페이지가 없습니다.")
            return

        self.set_exporting_state(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        start_time = time.time()

        def progress_callback(current, total_pages):
            """진행률 업데이트 콜백 함수"""
            self.progress_bar.setValue(current)
            percent = int((current / total_pages) * 100) if total_pages > 0 else 0
            self.label.setText(f"PDF 생성 중... {percent}% ({current}/{total_pages})")
            QApplication.processEvents()

        # 개선된 export_and_merge_pdf 함수 사용
        result = asyncio.run(export_and_merge_pdf(page_ids_unique, FINAL_PDF_NAME, progress_callback))
        
        elapsed = time.time() - start_time
        self.progress_bar.setValue(total)
        self.label.setText(f"PDF 생성 완료! (100%/{total}) (총 {elapsed:.2f}초)")
        self.set_exporting_state(False)
        self.show_export_result(result, elapsed)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 