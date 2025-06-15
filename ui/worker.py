import asyncio
from typing import Optional

from PySide6.QtCore import QThread, Signal

from core_engine import NotionEngine
from translate_engine import TranslateEngine
from html2pdf_engine import HTML2PDFEngine
from utils.notion_parser import blocks_to_html

class WorkerThread(QThread):
    """백그라운드에서 비동기 작업을 처리하는 워커 스레드"""
    
    progress_updated = Signal(int)
    status_updated = Signal(str)
    finished = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, config, workflow_type: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.workflow_type = workflow_type
        self.notion_engine = NotionEngine()
        self.translate_engine = TranslateEngine()
        self.html2pdf_engine = HTML2PDFEngine()
    
    def run(self):
        """워커 스레드 실행 메인 함수"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 이 부분은 ViewModel과 연동하여 다시 구현해야 합니다.
            # 지금은 구조만 유지합니다.
            result = f"'{self.workflow_type}' 작업 완료 (임시)"
            
            if result:
                self.finished.emit(result)
            else:
                self.error_occurred.emit("작업이 실패했습니다.")
                
        except Exception as e:
            self.error_occurred.emit(f"오류 발생: {str(e)}")
        finally:
            if 'loop' in locals() and loop.is_running():
                loop.close() 