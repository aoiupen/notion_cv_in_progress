import sys
import os
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                             QLabel, QProgressBar, QTextEdit, QTextBrowser, QGroupBox, 
                             QMessageBox, QListWidget, QListWidgetItem, QLineEdit, 
                             QSplitter, QCheckBox, QAbstractItemView)
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtCore import Qt, QTimer, Slot, Signal
import threading

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
        
        # 초기 페이지 로드 요청
        threading.Thread(target=self.vm.load_pages, daemon=True).start()

    def _init_ui(self):
        main_hbox = QHBoxLayout()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setLayout(main_hbox)
        
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
        self.original_preview = QTextBrowser()
        self.translated_preview = QTextEdit()
        self.translated_preview.setReadOnly(True)
        self.splitter.addWidget(self.original_preview)
        self.splitter.addWidget(self.translated_preview)
        preview_layout.addWidget(self.splitter)
        return preview_widget

    def _connect_signals(self):
        # ViewModel의 시그널 -> View의 슬롯
        self.vm.pages_changed.connect(self.update_page_list)
        self.vm.status_updated.connect(self.status_label.setText)
        self.vm.progress_updated.connect(self.progress_bar.setValue)
        self.vm.preview_updated.connect(self.original_preview.setHtml)
        self.vm.result_updated.connect(self.result_text.append)
        self.vm.child_count_updated.connect(self.update_option_ranges)

        # View의 시그널 -> ViewModel의 슬롯
        self.page_list.itemSelectionChanged.connect(self.on_page_selection_changed)
        self.start_edit.editingFinished.connect(self.on_option_changed)
        self.end_edit.editingFinished.connect(self.on_option_changed)
        self.export_btn.clicked.connect(lambda: self.vm.start_export("pdf"))
        
    @Slot(list)
    def update_page_list(self, pages):
        self.page_list.clear()
        if not pages:
            self.page_list.addItem("검색된 루트 페이지가 없습니다.")
            return
        for page in pages:
            title = extract_page_title(page)
            item = QListWidgetItem(f"{title} ({page['id'][:8]})")
            item.setData(Qt.UserRole, page['id'])
            self.page_list.addItem(item)
            
    @Slot()
    def on_page_selection_changed(self):
        selected_items = self.page_list.selectedItems()
        if selected_items:
            page_id = selected_items[0].data(Qt.UserRole)
            # ViewModel에 페이지 선택 알림
            threading.Thread(target=lambda: self.vm.page_selected(page_id), daemon=True).start()

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
            pass # 숫자가 아닐 경우 무시

    # --- UI Group Creation Methods ---
    def _create_page_list_group(self) -> QGroupBox:
        group = QGroupBox("📄 Notion 페이지 선택")
        layout = QVBoxLayout(group)
        self.page_list = QListWidget()
        self.page_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.page_list)
        return group

    def _create_language_group(self) -> QGroupBox:
        group = QGroupBox("🌐 언어")
        # ... (구현 생략)
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