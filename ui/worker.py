import asyncio
from typing import Callable, Any
from PySide6.QtCore import QThread, Signal

class WorkerThread(QThread):
    """지정된 비동기 함수를 백그라운드에서 실행하는 범용 워커 스레드"""
    
    # 작업 완료 시 결과 객체를 전달하는 시그널
    finished = Signal(object)
    
    # 오류 발생 시 오류 메시지를 전달하는 시그널
    error_occurred = Signal(str)
    
    # 진행률 업데이트를 위한 시그널
    progress_updated = Signal(int)
    
    # 상태 메시지 업데이트를 위한 시그널
    status_updated = Signal(str)
    
    def __init__(self, async_func: Callable, *args: Any, **kwargs: Any):
        super().__init__()
        self._async_func = async_func
        self._args = args
        self._kwargs = kwargs
    
    def run(self):
        """워커 스레드 실행 메인 함수"""
        try:
            # 새 이벤트 루프를 생성하고 현재 스레드의 기본 루프로 설정
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 워커 인스턴스 자체를 비동기 함수에 전달하여,
            # 실행 중인 함수가 직접 시그널(progress, status)을 발생시킬 수 있도록 함
            result = loop.run_until_complete(self._async_func(self, *self._args, **self._kwargs))
            
            # 작업 완료 시그널 방출
            self.finished.emit(result)
                
        except Exception as e:
            # 오류 발생 시그널 방출
            self.error_occurred.emit(f"백그라운드 작업 오류: {e}")
            
        finally:
            # 이벤트 루프 정리
            if 'loop' in locals() and loop.is_running():
                loop.close() 