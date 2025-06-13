from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox

class RuleSelectorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.label = QLabel("출력 유형/규칙을 선택하세요:")
        self.combo = QComboBox()
        # (디스플레이 한글, 내부 코드) 쌍으로 관리
        self.rules = [
            ("한 이 기본", "ko_cv_b_none"),
            ("영 이 기본", "en_cv_b_none"),
            ("한 이 Page", "ko_cv_b_rule"),
            ("영 이 Page", "en_cv_b_rule"),
            ("한 포 뷰", "ko_pf_b_none"),
            ("영 포 뷰", "en_pf_b_none"),
            ("한 포 순차", "ko_pf_e_none"),
            ("영 포 순차", "en_pf_e_none")
        ]
        for display, code in self.rules:
            self.combo.addItem(display, code)
        layout.addWidget(self.label)
        layout.addWidget(self.combo)
        self.setLayout(layout)

    def get_selected_rule(self):
        # 내부 코드값 반환
        return self.combo.currentData()
