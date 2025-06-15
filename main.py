import sys
from PySide6.QtWidgets import QApplication

from config import check_and_create_env
from ui.main_window import MainWindow
from viewmodels.main_viewmodel import MainViewModel

def main():
    """애플리케이션 메인 함수"""
    # .env 파일 체크 및 생성
    if not check_and_create_env():
        # 필수 환경변수가 없어 프로그램을 시작할 수 없는 경우,
        # 사용자에게 알리고 종료합니다.
        # (check_and_create_env 내부에서 이미 메시지 박스를 띄웁니다)
        sys.exit(1)

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