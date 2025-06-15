import sys
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from viewmodels.main_viewmodel import MainViewModel

def main():
    """애플리케이션 메인 함수"""
    # .env 파일 체크 및 생성

    # Qt 애플리케이션 생성
    app = QApplication(sys.argv)
    
    # ViewModel 인스턴스 생성
    # ViewModel이 애플리케이션의 모든 상태와 로직을 관리합니다.
    view_model = MainViewModel()
    
    # View(MainWindow) 인스턴스 생성 및 ViewModel 주입
    # View는 ViewModel의 데이터 변경을 감지하고 UI를 업데이트합니다.
    window = MainWindow(view_model)
    
    # 윈도우 표시
    window.show()
    
    # 이벤트 루프 시작
    sys.exit(app.exec())

if __name__ == '__main__':
    main()