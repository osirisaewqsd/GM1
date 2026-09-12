# gui/ui_mainwindow.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QListWidget,
    QLineEdit, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


def setup_ui(main_window):
    central = QWidget()
    central.setStyleSheet("background: #2d2d2d;")
    main_window.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(6, 6, 6, 6)
    main_layout.setSpacing(4)

    # ===== 第一行 =====
    row1 = QHBoxLayout()
    row1.setSpacing(4)
    btn_select_win = QPushButton("🎯")
    btn_select_win.setFixedSize(28, 26)
    btn_select_win.setToolTip("选择游戏进程")
    btn_select_win.setStyleSheet("border: 1px solid #4a4a4a; border-radius: 4px;")
    edit_target_win = QLineEdit("请选择游戏进程")
    edit_target_win.setFixedHeight(26)
    edit_target_win.setReadOnly(True)
    edit_target_win.setStyleSheet("background: #3a3a3a; color: #888888; border: 1px solid #4a4a4a; border-radius: 4px;")
    btn_folder = QPushButton("📁")
    btn_folder.setFixedSize(28, 26)
    btn_folder.setToolTip("选择乐谱目录")
    btn_folder.setStyleSheet("border: 1px solid #4a4a4a; border-radius: 4px;")
    edit_music_dir = QLineEdit("")
    edit_music_dir.setFixedHeight(26)
    edit_music_dir.setReadOnly(True)
    edit_music_dir.setPlaceholderText("乐谱目录")
    edit_music_dir.setToolTip("点击打开已选乐谱目录")
    edit_music_dir.setStyleSheet("background: #3a3a3a; color: #888888; border: 1px solid #4a4a4a; border-radius: 4px; padding-left: 2px;")
    row1.addWidget(btn_select_win)
    row1.addWidget(edit_target_win, 1)
    row1.addWidget(btn_folder)
    row1.addWidget(edit_music_dir, 1)
    main_layout.addLayout(row1)

    # ===== 第二行 =====
    row2 = QHBoxLayout()
    row2.setSpacing(4)
    btn_speed_down = QPushButton("◀")
    btn_speed_down.setFixedSize(26, 26)
    btn_speed_down.setFixedWidth(20)
    btn_speed_down.setToolTip("← 减速")
    btn_speed_down.setStyleSheet("font-size:8pt; border: 1px solid #4a4a4a; border-radius: 4px;")
    btn_speed_down.setFocusPolicy(Qt.NoFocus)

    label_speed = QLabel("1.00x")
    label_speed.setFixedWidth(30)
    label_speed.setAlignment(Qt.AlignCenter)
    label_speed.setStyleSheet("font-size:9pt;color:#88ccff;")

    btn_speed_up = QPushButton("▶")
    btn_speed_up.setFixedSize(26, 26)
    btn_speed_up.setFixedWidth(20)
    btn_speed_up.setToolTip("加速 →")
    btn_speed_up.setStyleSheet("font-size:8pt; border: 1px solid #4a4a4a; border-radius: 4px;")
    btn_speed_up.setFocusPolicy(Qt.NoFocus)

    slider_progress = QSlider(Qt.Horizontal)
    slider_progress.setRange(0, 100)
    slider_progress.setEnabled(False)
    slider_progress.setFixedHeight(20)

    label_time = QLabel("00:00 / 00:00")
    label_time.setMinimumWidth(70)
    label_time.setAlignment(Qt.AlignCenter)
    label_time.setStyleSheet("font-size:8pt;color:#777777;")

    row2.addWidget(btn_speed_down)
    row2.addWidget(label_speed)
    row2.addWidget(btn_speed_up)
    row2.addSpacing(4)
    row2.addWidget(slider_progress, 1)
    row2.addWidget(label_time)
    main_layout.addLayout(row2)

    # ===== 第三行：状态 =====
    row3_status = QHBoxLayout()
    row3_status.setSpacing(4)
    label_status_title = QLabel("状态：")
    label_status_title.setStyleSheet("font-size:9pt;color:#777777;")
    label_status_title.setFixedWidth(28)
    label_status = QLabel("就绪")
    label_status.setStyleSheet("font-size:9pt;color:#88ccff;")
    label_status.setMinimumHeight(26)
    label_current = QLabel("")
    label_current.setMinimumHeight(26)
    label_current.setStyleSheet("font-size:9pt;color:#88ccff;")
    label_current.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    row3_status.addWidget(label_status_title)
    row3_status.addWidget(label_status)
    row3_status.addWidget(label_current)
    row3_status.addStretch()
    main_layout.addLayout(row3_status)

    # ===== 第四行 =====
    row4_controls = QHBoxLayout()
    row4_controls.setSpacing(4)

    chk_loop_single = QCheckBox("单循")
    chk_loop_single.setToolTip("单曲循环")
    chk_loop_single.setFocusPolicy(Qt.NoFocus)
    chk_loop_single.setEnabled(True)
    chk_loop_single.setStyleSheet("""
        QCheckBox {
            color: #a9b7c6;
            font-size: 9pt;
            spacing: 2px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            background: #313131;
            border: 1px solid #aaaaaa;
            border-radius: 5px;
        }
        QCheckBox::indicator:checked {
            background: #8baed4;
            border-color: #4b6eb9;
            border: 1px solid #aaaaaa;
        }
    """)

    chk_loop_all = QCheckBox("列循")
    chk_loop_all.setToolTip("列表循环")
    chk_loop_all.setFocusPolicy(Qt.NoFocus)
    chk_loop_all.setEnabled(True)
    chk_loop_all.setStyleSheet("""
        QCheckBox {
            color: #a9b7c6;
            font-size: 9pt;
            spacing: 2px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            background: #313131;
            border: 1px solid #aaaaaa;
            border-radius: 5px;
        }
        QCheckBox::indicator:checked {
            background: #8baed4;
            border-color: #4b6eb9;
            border: 1px solid #aaaaaa;
        }
    """)

    # 模式下拉框
    combo_mode = QComboBox()
    combo_mode.addItems(["完整", "模式1", "模式2"])
    combo_mode.setFixedWidth(48)
    combo_mode.setFocusPolicy(Qt.NoFocus)
    combo_mode.setToolTip("切换弹奏模式：完整=全部弹奏，模式1=和弦只留最高音，模式2=只弹主旋律不弹伴奏")
    combo_mode.setStyleSheet("""
        QComboBox {
            background: #3b3b3b;
            color: #a9b7c6;
            border: 0px solid #4a4a4a;
            border-radius: 4px;
            padding: 0px 0px 0px 7px;
            font-size: 9pt;
            height: 24px;
        }
        QComboBox QLineEdit {
            background: transparent;
            border: none;
            color: #a9b7c6;
            padding: 0px;
            text-align: center;
        }
        QComboBox::drop-down {
            width: 0px;
            border: none;
        }
        QComboBox::down-arrow {
            width: 0px;
            height: 0px;
        }
        QComboBox QAbstractItemView {
            background: #2a2a2a;
            color: #d0d0d0;
            border: 1px solid #4a4a4a;
            border-radius: 4px;
            padding: 0px;
            outline: none;
            selection-background-color: #5a8ab5;
            selection-color: white;
        }
        QComboBox QAbstractItemView::item {
            border: none;
            padding: 3px 4px;
            min-height: 20px;
        }
        QComboBox QAbstractItemView::item:hover {
            background: #3a3a3a;
            border: none;
        }
    """)

    # 输出模式按钮
    btn_output_mode = QPushButton("PC")
    btn_output_mode.setFixedWidth(44)
    btn_output_mode.setFocusPolicy(Qt.NoFocus)
    btn_output_mode.setStyleSheet("""
        QPushButton {
            background: #3b3b3b;
            color: #a9b7c6;
            border: 0px solid #4a4a4a;
            border-radius: 4px;
            padding: 0px;
            text-align: center;
            font-size: 9pt;
            height: 24px;
        }
        QPushButton:hover {
            background: #4b4b4b;
            border-color: #5a5a5a;
        }
        QPushButton:pressed {
            background: #2b2b2b;
        }
    """)

    btn_stop = QPushButton("🛑")
    btn_stop.setFixedSize(36, 26)
    btn_stop.setToolTip("终止 (ESC)")
    btn_stop.setEnabled(False)
    btn_stop.setFocusPolicy(Qt.NoFocus)
    btn_stop.setStyleSheet("""
        QPushButton {
            background: #7a1a1a;
            color: #ff4444;
            border: none;
            border-radius: 4px;
            padding: 0px;
            height: 26px;
        }
        QPushButton:hover {
            background: #9a2a2a;
            color: #ff6666;
        }
        QPushButton:pressed {
            background: #5a0a0a;
            color: #ff2222;
        }
        QPushButton:disabled {
            background: #3a3a44;
            color: #555555;
            border: none;
            padding: 0px;
            height: 26px;
        }
    """)

    btn_pause = QPushButton("〢")
    btn_pause.setFixedSize(36, 26)
    btn_pause.setToolTip("暂停 (空格)")
    btn_pause.setEnabled(False)
    btn_pause.setFocusPolicy(Qt.NoFocus)
    btn_pause.setStyleSheet("""
        QPushButton {
            background: #b8860b;
            color: #ffdd44;
            border: none;
            border-radius: 4px;
            padding: 0px;
            height: 26px;
        }
        QPushButton:hover {
            background: #d4a017;
            color: #ffee66;
        }
        QPushButton:pressed {
            background: #8b6908;
            color: #ffcc22;
        }
        QPushButton:disabled {
            background: #3a3a44;
            color: #555555;
            border: none;
            padding: 0px;
            height: 26px;
        }
    """)

    btn_play = QPushButton("▶")
    btn_play.setFixedSize(36, 26)
    btn_play.setToolTip("播放")
    btn_play.setFocusPolicy(Qt.NoFocus)
    btn_play.setStyleSheet("""
        QPushButton {
            background: #1a7a1a;
            color: #44ff44;
            border: none;
            border-radius: 4px;
            padding: 0px;
            height: 26px;
        }
        QPushButton:hover {
            background: #2a9a2a;
            color: #66ff66;
        }
        QPushButton:pressed {
            background: #0a5a0a;
            color: #22ff22;
        }
        QPushButton:disabled {
            background: #1a3a1a;
            color: #446644;
            border: none;
            padding: 0px;
            height: 26px;
        }
    """)

    row4_controls.addWidget(chk_loop_single)
    row4_controls.addWidget(chk_loop_all)
    row4_controls.addWidget(combo_mode)
    row4_controls.addWidget(btn_output_mode)
    row4_controls.addStretch()
    row4_controls.addWidget(btn_stop)
    row4_controls.addWidget(btn_pause)
    row4_controls.addWidget(btn_play)
    main_layout.addLayout(row4_controls)

    # ===== 第五行 =====
    row5 = QHBoxLayout()
    row5.setSpacing(4)
    label_list_title = QLabel("🎵0首")
    label_list_title.setStyleSheet("""
        font-weight:bold;
        font-size:9pt;
        color:#88ccff;
        background: #3b3b3b;
        border: 0px solid #4a4a4a;
        border-radius: 4px;
        padding: 2px 2px;
        min-width: 40px;
    """)

    btn_del = QPushButton("🗑")
    btn_del.setFixedSize(26, 26)
    btn_del.setToolTip("删除")
    btn_del.setStyleSheet("""
        font-size:6pt;
        border: 0px solid #4a4a4a;
        border-radius: 4px;
        background: #3b3b3b;
        color: #a9b7c6;
    """)
    btn_del.setFocusPolicy(Qt.NoFocus)

    btn_rename = QPushButton("🖉")
    btn_rename.setFixedSize(26, 26)
    btn_rename.setToolTip("重命名乐谱")
    btn_rename.setStyleSheet("""
        font-size:9pt;
        border: 0px solid #4a4a4a;
        border-radius: 4px;
        background: #3b3b3b;
        color: #a9b7c6;
    """)
    btn_rename.setFocusPolicy(Qt.NoFocus)

    edit_search = QLineEdit()
    edit_search.setPlaceholderText("搜索乐谱")
    edit_search.setFixedHeight(26)
    edit_search.setMinimumWidth(120)
    edit_search.setFocusPolicy(Qt.StrongFocus)
    edit_search.setClearButtonEnabled(True)

    btn_search = QPushButton("🔍")
    btn_search.setToolTip("刷新和搜索")
    btn_search.setFixedSize(26, 26)
    btn_search.setFocusPolicy(Qt.NoFocus)
    btn_search.setStyleSheet("""
        border: 0px solid #4a4a4a;
        border-radius: 4px;
        background: #3b3b3b;
        color: #a9b7c6;
    """)

    row5.addWidget(label_list_title)
    row5.addStretch()
    row5.addSpacing(4)
    row5.addWidget(btn_del)
    row5.addWidget(btn_rename)
    row5.addWidget(edit_search, 1)
    row5.addWidget(btn_search)
    main_layout.addLayout(row5)

    # ===== 曲目列表 =====
    list_music = QListWidget()
    list_music.setSelectionMode(QListWidget.SingleSelection)
    list_music.setFont(QFont("Microsoft YaHei", 8))
    list_music.setFocusPolicy(Qt.StrongFocus)
    list_music.setStyleSheet("""
        QListWidget { 
            background: #252525; 
            border: 1px solid #3a3a3a; 
            border-radius: 4px; 
            outline: none;
            font-size: 8pt;
        }
        QListWidget::item { 
            padding: 2px 4px; 
            border-radius: 2px;
            height: 18px;
        }
        QListWidget::item:selected { background: #4b6eb9; color: #ffffff; }
        QListWidget::item:hover { background: #3a3a3a; }
        QScrollBar:horizontal {
            height: 0px;
            background: transparent;
        }
        QScrollBar::handle:horizontal {
            height: 0px;
            background: transparent;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            height: 0px;
        }
        QScrollBar:vertical {
            background: #3a3a3a;
            width: 10px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #6a6a6a;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #8a8a8a;
        }
        QScrollBar::handle:vertical:pressed {
            background: #4a4a4a;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: transparent;
        }
    """)
    main_layout.addWidget(list_music, 1)

    # ===== 底部提示 =====
    label_hint = QLabel("双击播放 | 空格：播放/暂停 | ESC终止 | ←→ 调速 | 切曲 ↑↓ | 切模式0/1/2")
    label_hint.setAlignment(Qt.AlignCenter)
    label_hint.setStyleSheet("font-size:7pt;color:#666666;padding-top:4px;")
    main_layout.addWidget(label_hint)

    # ---- 设置控件的手型光标 ----
    for w in [
        btn_select_win, btn_folder,
        btn_speed_down, btn_speed_up,
        btn_stop, btn_pause, btn_play,
        btn_del, btn_rename, btn_search,
        chk_loop_single, chk_loop_all,
        btn_output_mode,
        edit_music_dir,
        # label_list_title 已移除手型光标，所以不在这里包含
    ]:
        w.setCursor(Qt.PointingHandCursor)

    # ---- 绑定控件 ----
    main_window.btn_select_win = btn_select_win
    main_window.edit_target_win = edit_target_win
    main_window.btn_folder = btn_folder
    main_window.edit_music_dir = edit_music_dir

    main_window.btn_speed_down = btn_speed_down
    main_window.label_speed = label_speed
    main_window.btn_speed_up = btn_speed_up
    main_window.slider_progress = slider_progress
    main_window.label_time = label_time

    main_window.chk_loop_single = chk_loop_single
    main_window.chk_loop_all = chk_loop_all
    main_window.combo_mode = combo_mode
    main_window.btn_output_mode = btn_output_mode

    main_window.label_status = label_status
    main_window.label_current = label_current
    main_window.btn_stop = btn_stop
    main_window.btn_pause = btn_pause
    main_window.btn_play = btn_play

    main_window.label_list_title = label_list_title
    main_window.btn_del = btn_del
    main_window.btn_rename = btn_rename
    main_window.edit_search = edit_search
    main_window.btn_search = btn_search

    main_window.list_music = list_music
    main_window.label_hint = label_hint
