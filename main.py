import sys
import os
import asyncio
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel, QMessageBox
from PySide6.QtCore import Qt
from notion_client import AsyncClient
from mainsub_exporter import export_and_merge_pdf

def extract_page_title(page_info):
    properties = page_info.get('properties', {})
    for prop_name, prop_data in properties.items():
        if prop_data.get('type') == 'title':
            title_array = prop_data.get('title', [])
            if title_array:
                return ''.join([item['plain_text'] for item in title_array])
    return "Untitled"

async def get_root_pages():
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    notion = AsyncClient(auth=NOTION_API_KEY)
    all_pages = []
    start_cursor = None
    while True:
        response = await notion.search(filter={"property": "object", "value": "page"}, page_size=100, start_cursor=start_cursor)
        all_pages.extend(response.get("results", []))
        start_cursor = response.get("next_cursor")
        if not start_cursor:
            break
    # 루트 페이지만 추출
    root_pages = []
    for page in all_pages:
        parent = page.get("parent", {})
        parent_type = parent.get("type", "")
        if parent_type != "database_id" and not (parent_type == "page_id" and parent.get("page_id") in [p['id'] for p in all_pages]):
            root_pages.append(page)
    return root_pages, all_pages

async def get_all_descendant_page_ids(page_id, all_pages):
    # page_id의 모든 하위 페이지 id를 재귀적으로 수집
    ids = [page_id]
    children = [p for p in all_pages if p.get("parent", {}).get("type") == "page_id" and p.get("parent", {}).get("page_id") == page_id]
    for child in children:
        ids.extend(await get_all_descendant_page_ids(child['id'], all_pages))
    return ids

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

    def export_pdf(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "경고", "최소 하나의 페이지를 선택하세요.")
            return
        page_ids = []
        for item in selected_items:
            page_id = item.data(Qt.UserRole)
            # 하위 페이지까지 포함
            ids = asyncio.run(get_all_descendant_page_ids(page_id, self.all_pages))
            page_ids.extend(ids)
        # 중복 제거 및 순서 유지
        seen = set()
        page_ids_unique = [x for x in page_ids if not (x in seen or seen.add(x))]
        self.export_btn.setEnabled(False)
        self.label.setText("PDF 생성 중...")
        QApplication.processEvents()
        result = asyncio.run(export_and_merge_pdf(page_ids_unique, "My_Portfolio_Final.pdf"))
        self.export_btn.setEnabled(True)
        if result:
            QMessageBox.information(self, "완료", f"PDF 생성 완료: {result}")
            self.label.setText("PDF 생성 완료!")
        else:
            QMessageBox.critical(self, "실패", "PDF 생성 실패")
            self.label.setText("PDF 생성 실패")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 