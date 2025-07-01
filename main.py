import sys
import asyncio
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from viewmodels.main_viewmodel import MainViewModel

# --- CLI PDF 직접 출력 엔트리포인트 ---
import argparse
from notion_client import AsyncClient
from utils.notion_parser import fetch_all_child_blocks, blocks_to_html
from utils.helpers import extract_page_title, get_styles
from html2pdf_engine import HTML2PDFEngine

async def export_pdf_direct(page_id, output_pdf_path=None):
    from config import NOTION_API_KEY
    notion = AsyncClient(auth=NOTION_API_KEY)
    page_info = await notion.pages.retrieve(page_id=page_id)
    blocks = await fetch_all_child_blocks(notion, page_id)
    html = await blocks_to_html(blocks, notion)
    styles = get_styles()
    title = extract_page_title(page_info, default_if_empty=True)
    # HTML2PDFEngine의 스타일 적용 방식과 동일하게 HTML 생성
    html2pdf = HTML2PDFEngine()
    full_html = html2pdf.generate_full_html(title, html)
    if not output_pdf_path:
        output_pdf_path = f"Portfolio_{page_id}.pdf"
    await html2pdf.html_to_pdf(full_html, output_pdf_path)
    print(f"PDF가 생성되었습니다: {output_pdf_path}")


def main():
    """애플리케이션 메인 함수 (UI 또는 CLI)"""
    parser = argparse.ArgumentParser(description="Notion PDF Exporter")
    parser.add_argument('--export-pdf', metavar='PAGE_ID', help='지정한 Notion PAGE_ID로 바로 PDF 출력')
    parser.add_argument('--output', metavar='OUTPUT_PDF', help='PDF 출력 경로/파일명')
    args, unknown = parser.parse_known_args()

    if args.export_pdf:
        # CLI: 바로 PDF 출력
        asyncio.run(export_pdf_direct(args.export_pdf, args.output))
        return

    # Qt 애플리케이션 실행 (기존 UI)
    app = QApplication(sys.argv)
    view_model = MainViewModel()
    window = MainWindow(view_model)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()