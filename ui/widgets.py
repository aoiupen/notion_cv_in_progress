from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

class ModernButton(QPushButton):
    """현대적인 스타일의 커스텀 버튼"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(45)
        self.setFont(QFont("Arial", 11, QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def set_primary_style(self):
        """주요 버튼 스타일 적용"""
        self.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton:disabled {
                background-color: #94a3b8;
            }
        """)
    
    def set_toggle_style(self, is_active: bool = False):
        """토글 버튼 스타일 적용"""
        if is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: white;
                    border: 2px solid #059669;
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #047857;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #374151;
                    border: 2px solid #d1d5db;
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    border-color: #9ca3af;
                    background-color: #f9fafb;
                }
            """) 