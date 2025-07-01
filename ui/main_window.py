import sys
import os
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                             QLabel, QProgressBar, QTextEdit, QTextBrowser, QGroupBox, 
                             QMessageBox, QTreeWidget, QTreeWidgetItem, QLineEdit, 
                             QSplitter, QCheckBox, QAbstractItemView, QHeaderView)
from PySide6.QtGui import QFont, QPalette, QColor, QPixmap
from PySide6.QtCore import Qt, QTimer, Slot, Signal

from ui.widgets import ModernButton
from viewmodels.main_viewmodel import MainViewModel
from utils.helpers import extract_page_title

class MainWindow(QMainWindow):
    """메인 애플리케이션 윈도우 (View)"""
    
    def __init__(self, view_model: MainViewModel):
        super().__init__()
        self.vm = view_model
        self.setWindowTitle("이력서/포폴 자동화 툴 v3.0 (MVVM)")
        self.setMinimumSize(1200, 800)
        
        self._init_ui()
        self._connect_signals()
        
        # ViewModel에 페이지 로드를 직접 요청
        QTimer.singleShot(100, self.vm.load_pages)

    def _init_ui(self):
        main_hbox = QHBoxLayout()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setLayout(main_hbox)
        
        # 미리보기용 QPixmap을 저장할 변수
        self.current_preview_pixmap = None
        
        left_widget = self._create_left_panel()
        main_hbox.addWidget(left_widget, 2)
        
        preview_widget = self._create_right_panel()
        main_hbox.addWidget(preview_widget, 3)

    def _create_left_panel(self):
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(15)
        left_layout.setContentsMargins(20, 20, 20, 20)
        
        title_label = QLabel("Notion 자동화 툴")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        left_layout.addWidget(title_label)
        
        left_layout.addWidget(self._create_page_list_group())
        
        row_layout = QHBoxLayout()
        row_layout.addWidget(self._create_language_group())
        row_layout.addWidget(self._create_option_group())
        left_layout.addLayout(row_layout)
        
        left_layout.addWidget(self._create_action_group())
        left_layout.addWidget(self._create_progress_group())
        left_layout.addWidget(self._create_result_group())
        left_layout.addStretch()
        return left_widget

    def _create_right_panel(self):
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        self.splitter = QSplitter()
        
        # 이미지 미리보기 레이블 설정 개선
        self.preview_label = QLabel("미리볼 페이지를 선택하세요.")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)  # 최소 크기 설정
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                background-color: #f9f9f9;
                color: #666;
                font-size: 14px;
            }
        """)
        # 스케일링 활성화 - 이게 핵심!
        self.preview_label.setScaledContents(True)
        
        self.translated_preview = QTextEdit()
        self.translated_preview.setReadOnly(True)
        
        self.splitter.addWidget(self.preview_label)
        self.splitter.addWidget(self.translated_preview)
        self.splitter.setSizes([2, 1])  # 이미지 영역을 더 크게
        
        preview_layout.addWidget(self.splitter)
        return preview_widget

    def _connect_signals(self):
        # ViewModel의 시그널 -> View의 슬롯
        self.vm.pages_changed.connect(self.update_page_list)
        self.vm.status_updated.connect(self.status_label.setText)
        self.vm.progress_updated.connect(self.progress_bar.setValue)
        self.vm.preview_updated.connect(self.update_preview_image)
        self.vm.result_updated.connect(self.result_text.append)
        self.vm.child_count_updated.connect(self.update_option_ranges)
        self.vm.worker_error.connect(self.show_error_message)

        # View의 시그널 -> ViewModel의 슬롯
        self.page_tree.itemSelectionChanged.connect(self.on_page_selection_changed)
        self.start_edit.editingFinished.connect(self.on_option_changed)
        self.end_edit.editingFinished.connect(self.on_option_changed)
        self.export_btn.clicked.connect(lambda: self.vm.start_export("pdf"))
        
    @Slot(list)
    def update_page_list(self, pages):
        self.page_tree.clear()
        if not pages:
            item = QTreeWidgetItem(self.page_tree, ["검색된 루트 페이지가 없습니다."])
            return
            
        for page_data in pages:
            parent_item = QTreeWidgetItem(self.page_tree)
            parent_item.setText(0, extract_page_title(page_data['page_info'], default_if_empty=True))
            parent_item.setText(1, page_data['page_info']['id'])
            parent_item.setData(0, Qt.UserRole, page_data['page_info']['id'])
            
            for child_page in page_data.get('children', []):
                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, extract_page_title(child_page, default_if_empty=True))
                child_item.setText(1, child_page['id'])
                child_item.setData(0, Qt.UserRole, child_page['id'])
            
    @Slot()
    def on_page_selection_changed(self):
        selected_items = self.page_tree.selectedItems()
        if selected_items:
            page_id = selected_items[0].data(0, Qt.UserRole)
            page_title = selected_items[0].text(0)
            self.vm.page_selected(page_id, page_title)

    @Slot(int)
    def update_option_ranges(self, count):
        self.start_edit.setText("0")
        self.end_edit.setText(str(max(0, count - 1)))

    @Slot()
    def on_option_changed(self):
        try:
            start = int(self.start_edit.text())
            end = int(self.end_edit.text())
            self.vm.update_preview(start, end)
        except ValueError:
            pass

    @Slot(str)
    def show_error_message(self, message):
        QMessageBox.critical(self, "오류 발생", message)

    def resizeEvent(self, event):
        """창 크기 변경 시 미리보기 이미지 리사이즈"""
        super().resizeEvent(event)
        if hasattr(self, 'preview_label') and self.current_preview_pixmap:
            self.resize_preview_image()

    def resize_preview_image(self):
        """현재 QPixmap을 라벨 크기에 맞춰 비율을 유지하며 리사이즈"""
        if self.current_preview_pixmap and not self.current_preview_pixmap.isNull():
            # setScaledContents(True)로 설정했으므로 단순히 pixmap만 설정하면 자동 스케일링됨
            self.preview_label.setPixmap(self.current_preview_pixmap)

    @Slot(str)
    def update_preview_image(self, image_path):
        print(f"🖼️ update_preview_image 호출됨: {image_path}")  # 디버그 로그
        
        if image_path:
            # 파일 존재 확인
            if not os.path.exists(image_path):
                print(f"❌ 이미지 파일이 존재하지 않음: {image_path}")
                self.preview_label.setText("이미지 파일을 찾을 수 없습니다.")
                return
            
            # QPixmap 로드 시도
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                print(f"❌ QPixmap 로드 실패: {image_path}")
                self.preview_label.setText("이미지를 로드할 수 없습니다.")
                return
            
            print(f"✅ 이미지 로드 성공: {pixmap.width()}x{pixmap.height()}")
            
            # 현재 pixmap 저장 및 설정
            self.current_preview_pixmap = pixmap
            self.preview_label.setPixmap(pixmap)
            
            # 텍스트 지우기 (이미지가 있을 때)
            self.preview_label.clear()
            self.preview_label.setPixmap(pixmap)
        else:
            print("❌ 빈 이미지 경로")
            self.current_preview_pixmap = None
            self.preview_label.clear()
            self.preview_label.setText("미리보기를 생성하지 못했습니다.")

    # --- UI Group Creation Methods ---
    def _create_page_list_group(self) -> QGroupBox:
        group = QGroupBox("📄 Notion 페이지 선택")
        layout = QVBoxLayout(group)
        self.page_tree = QTreeWidget()
        self.page_tree.setColumnCount(2)
        self.page_tree.setHeaderLabels(["페이지 제목", "ID"])
        self.page_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.page_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.page_tree)
        return group

    def _create_language_group(self) -> QGroupBox:
        group = QGroupBox("🌐 언어")
        layout = QVBoxLayout(group)
        self.ko_checkbox = QCheckBox("한국어")
        self.en_checkbox = QCheckBox("English")
        self.ko_checkbox.setChecked(True)
        layout.addWidget(self.ko_checkbox)
        layout.addWidget(self.en_checkbox)
        return group

    def _create_option_group(self) -> QGroupBox:
        group = QGroupBox("📑 범위 선택")
        layout = QHBoxLayout(group)
        self.start_edit = QLineEdit("0")
        self.end_edit = QLineEdit("0")
        layout.addWidget(QLabel("시작:"))
        layout.addWidget(self.start_edit)
        layout.addWidget(QLabel("끝:"))
        layout.addWidget(self.end_edit)
        return group

    def _create_action_group(self) -> QGroupBox:
        group = QGroupBox("⚡ 실행")
        layout = QHBoxLayout(group)
        self.export_btn = ModernButton("PDF로 내보내기")
        self.translate_btn = ModernButton("번역하기")
        layout.addWidget(self.export_btn)
        layout.addWidget(self.translate_btn)
        return group

    def _create_progress_group(self) -> QGroupBox:
        group = QGroupBox("📊 진행 상황")
        layout = QVBoxLayout(group)
        self.status_label = QLabel("대기 중...")
        self.progress_bar = QProgressBar()
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        return group

    def _create_result_group(self) -> QGroupBox:
        group = QGroupBox("📋 결과")
        layout = QVBoxLayout(group)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)
        return group