# Copyright (c) Capgemini. All rights reserved.
import os
import queue

from PySide6.QtCore import Qt, QItemSelectionModel, QUrl, Signal, QDateTime
from PySide6.QtGui import QMovie, QPixmap, QAction, QIcon, QImage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QStyledItemDelegate, QWidget, QVBoxLayout, QFrame, QSizePolicy, QHBoxLayout, QPushButton, \
    QLabel, QTreeView, QAbstractItemView, QProgressBar, QTextEdit, QSplitter, \
    QSpacerItem, QTabWidget, QMenu, QToolButton, QMessageBox, QDialog, QDateTimeEdit, QStyle, QDialogButtonBox

from custom_widgets import CustomSplitter, ClosableTabWidget
from icons import base64_to_icon, test_stop, move_up, move_down, remove, remove_all, excel_open, excel_close, \
    collapse_widget, expand_widget, base64_to_pixmap, overall_progress, open_log, \
    test_plan_progress, test_start, base64_to_gif, spin, schedule, loop, pause_execution, resume_execution, \
    refresh_test_execution, back_button
from logger import logger
from view.reset_schedule_dialog_view import ResetScheduleDialog
from view.start_execution_dialog_view import StartTestExecutionDialogView


class AnimatedDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.animations = {}
        self.parent = parent
        self.movie = QMovie('spin.gif')
        self.movies = []

    def paint(self, painter, option, index):
        try:
            # Draw the item
            super().paint(painter, option, index)

            # Start the animation if it exists for this index
            if index in self.movies:
                #movie = self.movies[index]
                #frame = movie.currentPixmap()
                frame = self.movie.currentPixmap().scaled(option.rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
                x = option.rect.x() + (option.rect.width() - frame.width()) // 2
                y = option.rect.y() + (option.rect.height() - frame.height()) // 2
                painter.drawPixmap(x, y, frame)
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def start_animation(self, index):
        try:
            # Store the movie to prevent it from being garbage collected
            self.movie.frameChanged.connect(lambda: self.update_index(index))
            self.movie.start()
            #self.movies[index] = movie
            self.movies.append(index)
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def stop_animation(self, index):
        try:
            if index in self.movies:
                #movie = self.movies[index]
                self.movie.frameChanged.disconnect()
                self.movie.stateChanged.connect(self.on_state_changed)
                self.movie.stop()
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def on_state_changed(self, state):
        if state == QMovie.MovieState.NotRunning:
            self.update_index(self.movies[0])
            self.movies.clear()
            self.movie.stateChanged.disconnect()

    def update_index(self, index):
        # Update the specific index to trigger a repaint
        self.parent.viewport().update(self.parent.visualRect(index))

class TestExecutionView(QWidget):
    def __init__(self, view_model):
        super().__init__()
        self.view_model = view_model
        self.contents_tab = None
        self.tree_view = None
        self.delegate = None
        self.move_up_button = None
        self.move_down_button = None
        self.remove_button = None
        self.remove_all_button = None
        self.start_button = None
        self.stop_button = None
        self.pause_button = None
        self.refresh_button = None
        self.open_log_button = None
        self.test_execution_progress = None
        self.overall_execution_progress = None
        self.graphics_view = None
        self.scene = None
        self.pixmap_item = None  # Create a pixmap item
        self.start_execution_action = None
        self.schedule_execution_action = None
        self.schedule_test_indicator = None
        self.loop_indicator_label = None
        self.execution_menu = None
        self.current_schedule = None
        self.web = None
        self.history = []
        self.test_report_tab_area = None
        self.test_report_tab_layout = None
        self._highlighted_testplan = None
        self._highlighted_testcase = None

        #self.label_captured_frame = None
        self.is_data_loaded = False  # Prevents redundant loading
        self.capture_in_progress = False
        base64_to_gif(spin,'spin.gif')
        self.init_layout()
        self.connect_slots_to_signals()

    def __create_buttons_layout(self):
        """
        Create layout for buttons
        :return: layout
        """
        separator_1 = QFrame()
        separator_1.setStyleSheet("QFrame { background-color: #A5A5A5; }")
        separator_1.setFrameShape(QFrame.Shape.VLine)
        separator_1.setFrameShadow(QFrame.Shadow.Sunken)
        #separator_2.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        separator_1.setFixedHeight(20)
        separator_1.setFixedWidth(2)
        # separator_2.setLineWidth(1)

        separator_2 = QFrame()
        separator_2.setStyleSheet("QFrame { background-color: #A5A5A5; }")
        separator_2.setFrameShape(QFrame.Shape.VLine)
        separator_2.setFrameShadow(QFrame.Shadow.Sunken)
        #separator_3.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        separator_2.setFixedHeight(20)
        separator_2.setFixedWidth(2)

        separator_3 = QFrame()
        separator_3.setStyleSheet("QFrame { background-color: #A5A5A5; }")
        separator_3.setFrameShape(QFrame.Shape.VLine)
        separator_3.setFrameShadow(QFrame.Shadow.Sunken)
        #separator_4.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        separator_3.setFixedHeight(20)
        separator_3.setFixedWidth(2)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(5,0,3,0)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.start_button = QToolButton(self)
        self.start_button.setToolTip('Start Execution')
        self.start_button.setStyleSheet("border: none")
        self.start_button.setIcon(base64_to_icon(test_start))
        # self.start_button.setFixedWidth(25)
        # self.start_button.setFixedHeight(25)
        self.start_button.setStyleSheet("""
            QToolButton {
                border: none; /* Remove borders */
                padding: 10px; /* Remove padding */
                margin: 0px; /* Remove margin */
                text-align: left; /* Align text to the left */
            }
            QToolButton::menu-indicator {
                subcontrol-position: right center; /* Position the menu arrow */
                subcontrol-origin: padding; /* Ensure it appears within the button */
            }
        """)

        self.execution_menu = QMenu(self)
        self.start_execution_action = QAction("Start Execution",self)
        self.start_execution_action.setEnabled(False)
        self.schedule_execution_action = QAction("Schedule Execution", self)
        self.schedule_execution_action.setEnabled(False)

        self.execution_menu.addAction(self.start_execution_action)
        self.execution_menu.addAction(self.schedule_execution_action)

        self.start_button.setMenu(self.execution_menu)
        self.start_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self.stop_button = QPushButton("")
        self.stop_button.setToolTip('Stop Execution')
        self.stop_button.setStyleSheet("border: none")
        self.stop_button.setIcon(base64_to_icon(test_stop))
        self.stop_button.setFixedWidth(20)
        self.stop_button.setFixedHeight(20)
        self.pause_button = QPushButton("")
        self.pause_button.setToolTip('Pause Execution')
        self.pause_button.setStyleSheet("border: none")
        self.pause_button.setIcon(base64_to_icon(pause_execution))
        self.pause_button.setFixedWidth(20)
        self.pause_button.setFixedHeight(20)

        self.move_up_button = QPushButton("")
        self.move_up_button.setStyleSheet("border: none")
        self.move_up_button.setToolTip('Move item up')
        self.move_up_button.setIcon(base64_to_icon(move_up))
        self.move_up_button.setFixedWidth(20)
        self.move_up_button.setFixedHeight(20)
        self.move_down_button = QPushButton(" ")
        self.move_down_button.setToolTip('Move item down')
        self.move_down_button.setStyleSheet("border: none")
        self.move_down_button.setIcon(base64_to_icon(move_down))
        self.move_down_button.setFixedWidth(20)
        self.move_down_button.setFixedHeight(20)
        self.remove_button = QPushButton(" ")
        self.remove_button.setToolTip('Remove item')
        self.remove_button.setStyleSheet("border: none")
        self.remove_button.setIcon(base64_to_icon(remove))
        self.remove_button.setFixedWidth(20)
        self.remove_button.setFixedHeight(20)
        self.remove_all_button = QPushButton(" ")
        self.remove_all_button.setToolTip('Remove all items')
        self.remove_all_button.setStyleSheet("border: none")
        self.remove_all_button.setIcon(base64_to_icon(remove_all))
        self.remove_all_button.setFixedWidth(20)
        self.remove_all_button.setFixedHeight(20)
        self.refresh_button = QPushButton(" ")
        self.refresh_button.setToolTip('Refresh All Items')
        self.refresh_button.setStyleSheet("border: none")
        self.refresh_button.setIcon(base64_to_icon(refresh_test_execution))
        self.refresh_button.setFixedWidth(30)
        self.refresh_button.setFixedHeight(30)

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.pause_button)
        buttons_layout.addWidget(separator_1)
        buttons_layout.addWidget(self.move_up_button)
        buttons_layout.addWidget(self.move_down_button)
        buttons_layout.addWidget(separator_2)
        buttons_layout.addWidget(self.remove_button)
        buttons_layout.addWidget(self.remove_all_button)
        buttons_layout.addWidget(separator_3)
        buttons_layout.addWidget(self.refresh_button)
        return buttons_layout

    def __create_execution_data_label_layout(self):
        execution_data_layout = QHBoxLayout()
        execution_data_layout.setContentsMargins(50, 0, 50, 0)
        self.cycle_count_label = QLabel('CYCLE#:')
        self.cycle_count_label.setStyleSheet("color: #7489C4;font-weight: bold")
        self.test_pass_count = QLabel('PASS#:')
        self.test_pass_count.setStyleSheet("color: green;font-weight: bold")
        self.test_fail_count = QLabel('FAIL#:')
        self.test_fail_count.setStyleSheet("color: #EE3E6F;font-weight: bold")
        self.total_count = QLabel('TOTAL#:')
        self.total_count.setStyleSheet("font-weight: bold")

        execution_data_layout.addWidget(self.cycle_count_label)
        execution_data_layout.addWidget(self.test_pass_count, alignment=Qt.AlignmentFlag.AlignCenter)
        execution_data_layout.addWidget(self.test_fail_count,alignment=Qt.AlignmentFlag.AlignCenter)
        execution_data_layout.addWidget(self.total_count, alignment=Qt.AlignmentFlag.AlignRight)
        return execution_data_layout

    def __create_top_frame_layout(self):
        top_frame = QFrame()
        top_pane_layout = QHBoxLayout()
        top_frame.setLayout(top_pane_layout)

        indicator_layout = QVBoxLayout()
        indicator_layout.setContentsMargins(0,0,0,0)
        indicator_layout.setSpacing(0)
        indicator_container = QWidget()
        indicator_container.setLayout(indicator_layout)
        indicator_container.setFixedWidth(25)
        indicator_container.setFixedHeight(50)
        schedule_menu = QMenu(self)
        self.schedule_test_indicator = QToolButton(self)
        self.schedule_test_indicator.setStyleSheet("border: none")
        self.schedule_test_indicator.setFixedWidth(25)
        self.schedule_test_indicator.setFixedHeight(25)
        self.schedule_test_indicator.setIcon(QIcon(base64_to_icon(schedule)))
        self.reset_schedule_action = QAction("Reset", self)
        self.delete_schedule_action = QAction("Delete", self)
        schedule_menu.addAction(self.reset_schedule_action)
        schedule_menu.addAction(self.delete_schedule_action)
        self.schedule_test_indicator.setMenu(schedule_menu)
        self.schedule_test_indicator.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.schedule_test_indicator.setVisible(False)

        self.loop_indicator_label = QLabel("")
        self.loop_indicator_label.setToolTip("Loop execution in progress")
        pixmap = QPixmap(base64_to_pixmap(loop))
        self.loop_indicator_label.setPixmap(pixmap)
        self.loop_indicator_label.setVisible(False)
        indicator_layout.addWidget(self.schedule_test_indicator)
        indicator_layout.addWidget(self.loop_indicator_label)
        top_pane_layout.addWidget(indicator_container)

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.view_model.model)
        # self.execution_tree.setAlternatingRowColors(True)
        self.tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Make the tree read only
        self.tree_view.setStyleSheet("border: 2px solid #d3d3d3")
        self.tree_view.header().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        #self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree_view.setRootIsDecorated(True)
        # self.tree_view.setStyleSheet("""
        #             QTreeView::item {
        #                 border: 1px solid lightgrey;
        #             }
        #         """)
        self.tree_view.header().setStyleSheet("""
                                        QHeaderView::section {
                                            background-color: white;
                                            border: none;
                                            border-right: 1px  solid lightgrey;
                                            text-align: center;
                                        }
                                        QHeaderView::section:last {
                                            border-right: none;  # Remove the right border from the last section
                                        }
                                    """)
        self.delegate = AnimatedDelegate(self.tree_view)
        self.tree_view.setItemDelegate(self.delegate)

        top_pane_layout.addWidget(self.tree_view)
        return top_frame

    def __create_bottom_frame_layout(self):
        bottom_frame = QFrame()
        bottom_frame.setContentsMargins(0, 0, 0, 0)
        bottom_pane_layout = QVBoxLayout()
        bottom_frame.setLayout(bottom_pane_layout)

        test_plan_progress_layout = QHBoxLayout()
        # Test Suite Execution Progress Bar
        test_plan_progress_label = QLabel("")
        test_plan_progress_label.setToolTip("Test plan execution progress")
        # Load an icon and set it in the label
        pixmap = base64_to_pixmap(test_plan_progress)  # Replace with the path to your icon
        test_plan_progress_label.setPixmap(pixmap)
        test_plan_progress_label.setFixedWidth(25)
        test_plan_progress_layout.addWidget(test_plan_progress_label)
        self.test_execution_progress = QProgressBar()
        self.test_execution_progress.setStyleSheet("""
                                    QProgressBar::chunk {
                                        background-color: #05B8CC;
                                    }
                                """)
        self.test_execution_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        test_plan_progress_layout.addWidget(self.test_execution_progress)
        bottom_pane_layout.addLayout(test_plan_progress_layout)
        # test_execution_frame_layout.addLayout(test_plan_progress_layout)

        open_log_layout = QHBoxLayout()
        self.open_log_button = QPushButton("")
        self.open_log_button.setToolTip('Open log folder')
        self.open_log_button.setStyleSheet("border: none")
        self.open_log_button.setIcon(base64_to_icon(open_log))
        self.open_log_button.setFixedWidth(25)
        self.open_log_button.setFixedHeight(25)
        open_log_layout.addWidget(self.open_log_button)

        self.step_log_area = QTextEdit()
        self.step_log_area.setReadOnly(True)
        self.step_log_area.setPlaceholderText("Test Suite Step Log")
        open_log_layout.addWidget(self.step_log_area)
        bottom_pane_layout.addLayout(open_log_layout)
        # test_execution_frame_layout.addLayout(open_log_layout)

        overall_progress_layout = QHBoxLayout()
        # Overall Execution Progress Bar
        overall_execution_label = QLabel("")
        overall_execution_label.setToolTip('Overall Execution Progress')
        # Load an icon and set it in the label
        pixmap = base64_to_pixmap(overall_progress)  # Replace with the path to your icon
        overall_execution_label.setPixmap(pixmap)
        overall_execution_label.setFixedWidth(25)
        overall_progress_layout.addWidget(overall_execution_label)
        self.overall_execution_progress = QProgressBar()
        self.overall_execution_progress.setStyleSheet("""
                                    QProgressBar::chunk {
                                        background-color: #05B8CC;
                                    }
                                """)
        self.overall_execution_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overall_progress_layout.addWidget(self.overall_execution_progress)
        bottom_pane_layout.addLayout(overall_progress_layout)
        return bottom_frame

    def __create_test_execution_layout(self):
        try:
            test_execution_frame = QFrame()
            test_execution_frame.setObjectName("ExecutionFrame")
            # test_execution_frame.setStyleSheet("border: 2px solid #d3d3d3")
            # test_execution_frame.setStyleSheet("""
            #         QFrame#ExecutionFrame {
            #             border: 1px solid #d3d3d3;
            #         }
            # """)
            # test_execution_frame.setFrameShape(QFrame.Panel)
            # test_execution_frame.setFrameShadow(QFrame.Sunken)
            test_execution_frame_layout = QVBoxLayout()
            test_execution_frame_layout.setContentsMargins(0, 15, 15, 15)
            test_execution_frame.setLayout(test_execution_frame_layout)

            execution_data_layout = self.__create_execution_data_label_layout()
            test_execution_frame_layout.addLayout(execution_data_layout)

            top_frame = self.__create_top_frame_layout()
            bottom_frame = self.__create_bottom_frame_layout()
            bottom_splitter = QSplitter(Qt.Orientation.Vertical)
            bottom_splitter.setHandleWidth(15)
            # bottom_splitter.setStyleSheet("""
            #             QSplitter::handle {
            #                 background-color: #cccccc;
            #                 border: 2px sunken #888888;
            #                 width: 10px; /* Adjust the width for vertical splitter */
            #                 height: 10px; /* Adjust the height for horizontal splitter */
            #             }
            #         """)
            bottom_splitter.setStyleSheet("""
                                      QSplitter::handle {
                                          background-color: #E3E3E3;
                                          border: 1px #E3E3E3;
                                          border-top: 1px solid #696969;
                                          border-bottom: 1px solid #696969;
                                      }
                                  """)
            # bottom_splitter.s
            bottom_splitter.addWidget(top_frame)
            bottom_splitter.addWidget(bottom_frame)
            # test_execution_frame_layout.addLayout(overall_progress_layout)
            test_execution_frame_layout.addWidget(bottom_splitter)
            return test_execution_frame
        except Exception as e:
            logger.error(e)

        #test_execution_frame_layout.addWidget(top_frame)

    def init_layout(self):
        """
        Initialize view layout
        :return: None
        """
        parent_layout = QVBoxLayout()
        parent_layout.setContentsMargins(0, 6, 0, 0)
        parent_layout.setSpacing(0)
        #self.contents_tab = QTabWidget()
        self.contents_tab = ClosableTabWidget()
        test_execution_tab_area = QFrame()
        test_execution_tab_layout = QVBoxLayout()
        test_execution_tab_area.setLayout(test_execution_tab_layout)

        self.test_report_tab_area = QFrame()
        self.test_report_tab_layout = QVBoxLayout()
        self.test_report_tab_area.setLayout(self.test_report_tab_layout)

        main_frame = QFrame()
        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        main_frame.setLayout(layout)

        buttons_layout = self.__create_buttons_layout()
        # parent_layout.addLayout(buttons_layout)
        # parent_layout.addWidget(main_frame)
        test_execution_tab_layout.addLayout(buttons_layout)
        test_execution_tab_layout.addWidget(main_frame)

        test_execution_frame = self.__create_test_execution_layout()

        splitter = CustomSplitter(Qt.Orientation.Horizontal,base64_to_icon(collapse_widget), base64_to_icon(expand_widget))
        splitter.setHandleWidth(25)
        splitter.setStyleSheet("""
                           QSplitter::handle {
                               background-color: #E3E3E3;
                               border: 1px #E3E3E3;
                               border-left: 2px solid #696969;
                               border-right: 1px solid #CCCCCC;
                           }
                       """)

        splitter.addWidget(test_execution_frame)

        media_frame = QFrame()
        #media_frame.setFrameShape(QFrame.Panel)
        # media_frame.setStyleSheet("""
        #                 QFrame {
        #                     border: 1px solid #d3d3d3;
        #                 }
        #         """)
        #media_frame.setFrameShadow(QFrame.NoFrame)
        media_layout = QVBoxLayout()
        media_frame.setLayout(media_layout)
        record_button = QPushButton()
        record_button.setStyleSheet("border: none")
        media_layout.addWidget(record_button)

        # self.graphics_view = QGraphicsView()
        # self.graphics_view.setMinimumWidth(640)
        # self.graphics_view.setMinimumHeight(480)
        # self.scene = QGraphicsScene()
        # self.pixmap_item = QGraphicsPixmapItem(base64_to_pixmap(default_image_base64))  # Create a pixmap item
        # self.scene.addItem(self.pixmap_item)
        # self.graphics_view.setScene(self.scene)
        self.label_captured_frame = QLabel()
        #pixmap = base64_to_pixmap(default_image_base64)  # Replace with the path to your icon
        #self.label_captured_frame.setPixmap(pixmap)
        self.label_captured_frame.setStyleSheet("background-color: black")
        self.label_captured_frame.setMinimumHeight(350)
        media_layout.addWidget(self.label_captured_frame)
        #media_layout.addWidget(self.graphics_view)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setLineWidth(1)
        media_layout.addWidget(separator)

        spacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        media_layout.addItem(spacer)
        # frame.setStyleSheet("""
        #     QFrame {
        #         border: 1px solid #EEEEEE;
        #     }
        # """)

        splitter.addWidget(media_frame)
        total_width = splitter.width()
        # Keep left and right widget to 70-30 ratio
        splitter.setSizes([int(total_width * 0.7), int(total_width * 0.3)])
        layout.addWidget(splitter)

        self.contents_tab.addTab(test_execution_tab_area, "TestExecution")
        # self.contents_tab.add_closable_tab(test_result_tab_area, "TestResult")
        # self.contents_tab.setTabVisible(1, False)
        parent_layout.addWidget(self.contents_tab)

        self.setLayout(parent_layout)

    def connect_slots_to_signals(self):
        """
        Connect signals to respective slots
        :return: None
        """
        # Connect signals
        self.remove_button.clicked.connect(self.view_model.on_remove_button_clicked)
        self.move_up_button.clicked.connect(self.view_model.on_move_up_button_click)
        self.move_down_button.clicked.connect(self.view_model.on_move_down_button_click)
        self.remove_all_button.clicked.connect(self.view_model.on_remove_all_button_clicked)
        self.stop_button.clicked.connect(self.view_model.on_stop_button_click)
        self.pause_button.clicked.connect(self.view_model.on_pause_button_click)
        self.refresh_button.clicked.connect(self.view_model.on_refresh_button_click)
        self.open_log_button.clicked.connect(self.view_model.on_open_log_button_clicked)
        self.tree_view.selectionModel().selectionChanged.connect(
            self.view_model.on_tree_item_selection_changed)

        self.start_execution_action.triggered.connect(self.view_model.on_start_execution_clicked)
        self.schedule_execution_action.triggered.connect(self.view_model.on_schedule_execution_clicked)
        self.reset_schedule_action.triggered.connect(self.on_reset_schedule)
        self.delete_schedule_action.triggered.connect(self.view_model.on_delete_schedule)

        #self.view_model.data_loaded.connect(self.load_data)
        self.view_model.show_start_execution_dialog.connect(self.on_show_start_execution_dialog)
        self.view_model.test_progress_updated.connect(self.update_test_execution_progress)
        self.view_model.signal_manager.test_execution_started.connect(self.on_test_execution_started)
        self.view_model.signal_manager.test_execution_stopped.connect(self.on_test_execution_stopped)
        self.view_model.start_animation.connect(self.on_start_animation)
        self.view_model.stop_animation.connect(self.on_stop_animation)
        self.view_model.highlight_and_expand_testplan.connect(self.on_highlight_expand_testplan)
        self.view_model.highlight_and_expand_testcase.connect(self.on_highlight_expand_testcase)
        self.view_model.unhighlight_tree_items.connect(self.on_unhighlight_tree_items)
        self.view_model.overall_progress_updated.connect(self.update_overall_execution_progress)
        self.view_model.reset_progress.connect(self.on_reset_progress)
        self.view_model.append_log.connect(self.on_append_logs)
        self.view_model.display_image.connect(self.on_display_image)
        self.view_model.set_current_index.connect(self.on_set_current_index)
        self.view_model.toggle_execution_menu.connect(self.on_toggle_execution_menu)
        self.view_model.show_schedule_indicator.connect(self.on_show_schedule_indicator)
        self.view_model.update_execution_data_labels.connect(self.on_update_execution_data_labels)
        self.view_model.tree_view_cleared.connect(self.on_tree_view_cleared)
        self.view_model.toggle_pause_button.connect(self.on_toggle_pause_button)
        self.view_model.signal_manager.report_file_selected.connect(self.open_report_in_tab)
        self.view_model.tag_not_found.connect(self.on_tag_not_found_error)
        self.view_model.device_not_found.connect(self.on_device_not_found_error)
        self.view_model.refresh_tree_view.connect(self.on_refresh_tree_view)

    def update_test_execution_progress(self, progress):
        self.test_execution_progress.setMaximum(100)
        self.test_execution_progress.setValue(progress)

    def on_reset_progress(self):
        self.test_execution_progress.reset()
        self.overall_execution_progress.reset()

    def on_refresh_tree_view(self):
        # Reset tree data and controls when tree becomes empty
        self.overall_execution_progress.reset()
        self.test_execution_progress.reset()
        self.on_update_execution_data_labels('', '', '', '')
        self.step_log_area.clear()

    def on_tree_view_cleared(self):
        # Reset tree data and controls when tree becomes empty
        self.overall_execution_progress.reset()
        self.test_execution_progress.reset()
        self.start_execution_action.setEnabled(False)
        self.schedule_execution_action.setEnabled(False)
        self.on_update_execution_data_labels('','','','')
        self.schedule_test_indicator.setVisible(False)
        self.step_log_area.clear()

    def on_update_execution_data_labels(self,cycle,failed,passed,total):
        self.cycle_count_label.setText(f"CYCLE#:{str(cycle)}")
        self.cycle_count_label.setStyleSheet("color: #7489C4;font-weight: bold")
        self.test_pass_count.setText(f"PASS#:{str(passed)}")
        self.test_pass_count.setStyleSheet("color: green;font-weight: bold")
        self.test_fail_count.setText(f"FAIL#:{str(failed)}")
        self.test_fail_count.setStyleSheet("color: #EE3E6F;font-weight: bold")
        self.total_count.setText(f"TOTAL#:{str(total)}")
        self.total_count.setStyleSheet("font-weight: bold")

    def  on_test_execution_started(self, num_cycles):
        """
        Slot to handle test_execution_started signal emitted from the view model
        when test execution is started.
        :return: None
        """
        self.capture_in_progress = True
        self.step_log_area.clear()
        self.move_up_button.setEnabled(False)
        self.move_down_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.remove_all_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        if num_cycles > 1:
            self.loop_indicator_label.setVisible(True)

    def on_start_animation(self, item):
        """
        Start animation on receiving start_animation signal from the view model
        :param item: QStandardItem instance representing the cell item where animation needs to be shown
        :return: None
        """
        try:
            #self.delegate.start_animation(item.index(), 'C:/Workspace/NS_Automation/icons/spin.gif')
            self.delegate.start_animation(item.index())
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def on_stop_animation(self, item):
        """
        Stop animation on receiving stop_animation signal from the view model
        :param item: QStandardItem instance representing the cell item where animation is running
        :return: None
        """
        try:
            self.delegate.stop_animation(item.index())
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def _toggle_highlight_and_expand(self, item, highlight=True):
        """
        Toggle text highlight and expand the item on receiving toggle_highlight_and_expand signal
        from the view model
        :param item: QStandardItem instance representing the item to highlight and expand
        :param highlight: Boolean flag , highlight the item if True else remove the highlight
        :return: None
        """
        try:
            font = item.font()
            font.setBold(highlight)
            item.setFont(font)
            feature_index = self.tree_view.model().indexFromItem(item.parent()) # feature Node
            feature_item = self.tree_view.model().itemFromIndex(feature_index)
            tag_index = self.tree_view.model().indexFromItem(feature_item.parent()) # Tag Node
            if not self.tree_view.isExpanded(tag_index):
                self.tree_view.expand(tag_index) # Expand tag node
            if not self.tree_view.isExpanded(feature_index):
                self.tree_view.expand(feature_index) # Expand feature node

            # Expand the item
            index = self.tree_view.model().indexFromItem(item)
            self.tree_view.expand(index)
        except Exception as e:
            logger.critical(f"Exception Caught: {e}", exc_info=True)

    def on_highlight_expand_testplan(self, item, highlight):
        self._highlighted_testplan = item
        self._toggle_highlight_and_expand(item, highlight)

    def on_highlight_expand_testcase(self, item, highlight):
        self._highlighted_testcase = item
        self._toggle_highlight_and_expand(item, highlight)

    def on_unhighlight_tree_items(self):
        if self._highlighted_testplan:
            self._toggle_highlight_and_expand(self._highlighted_testplan, False)
        if self._highlighted_testcase:
            self._toggle_highlight_and_expand(self._highlighted_testcase, False)

    def on_test_execution_stopped(self):
        """
        Slot to handle test_execution_stopped signal emitted from the view model
        when test execution is stopped.
        :return: None
        """
        self.capture_in_progress = False
        self.move_up_button.setEnabled(True)
        self.move_down_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        self.remove_all_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.label_captured_frame.clear()
        self.label_captured_frame.setStyleSheet("background-color:black")
        self.label_captured_frame.setMinimumHeight(350)
        #self.schedule_execution_action.setEnabled(True)
        self.loop_indicator_label.setVisible(False)

    def update_overall_execution_progress(self, progress):
        """
        Update the overall execution progress bar on receiving the overall_progress_updated signal
        from the view model
        :param progress: Integer representing the execution progress
        :return: None
        """
        self.overall_execution_progress.setMaximum(100)
        self.overall_execution_progress.setValue(progress)

    def on_append_logs(self, text):
        self.step_log_area.append(text)

    def on_display_image(self, image):
        if self.capture_in_progress:

            #self.pixmap_item.setPixmap(QPixmap.fromImage(image))
            self.label_captured_frame.setPixmap(QPixmap.fromImage(image))
        else:
            self.label_captured_frame.clear()
            self.label_captured_frame.setStyleSheet("background-color:black")
            self.label_captured_frame.setMinimumHeight(350)

    def on_set_current_index(self, index):
        try:
            self.tree_view.setCurrentIndex(index)
            self.tree_view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        except Exception as e:
            print(e)

    def __clear_layout(self,layout):
        """Removes all items (widgets and nested layouts) from a given layout."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()  # Schedule widget for deletion
                else:
                    # If it's a nested layout, recursively clear it
                    self.__clear_layout(item.layout())

    def open_report_in_tab(self, file_path: str):
        """
            Given an absolute HTML path, clear out the TestResult tab,
            place a small 'Viewing: <filename>' label, and load it into QWebEngineView.
        """
        logger.info(file_path)
        self.history.clear()
        try:
            is_tab_already_added = False
            tab_index = -1
            for i in range(self.contents_tab.count()): # find if the tab is already added
                if self.contents_tab.tabText(i) == "TestResult":
                    is_tab_already_added = True
                    tab_index = i
                    break
            self.__clear_layout(self.test_report_tab_layout)
            if not is_tab_already_added: # Add the tab if it is not already added

                tab_index = self.contents_tab.add_closable_tab(self.test_report_tab_area, "TestResult")

            # 3) Put a small "Viewing: <file name>" label on top:
            report_name = os.path.basename(file_path)
            self.back_button = QPushButton("")
            self.back_button.setToolTip('Back')
            self.back_button.setStyleSheet("border: none")
            self.back_button.setIcon(base64_to_icon(back_button))
            self.back_button.setFixedWidth(30)
            self.back_button.setFixedHeight(30)
            self.test_report_tab_layout.addWidget(self.back_button)

            # 4) Create and load the QWebEngineView:
            self.web = QWebEngineView()
            self.test_report_tab_layout.addWidget(self.web)
            self.web.setUrl(QUrl.fromLocalFile(file_path))
            self.history.append(file_path)
            self.contents_tab.setCurrentIndex(tab_index)
            # Track URL changes
            self.back_button.clicked.connect(self.go_back)
            self.web.urlChanged.connect(self.track_history)


        except Exception as e:
            # If anything goes wrong, print or log—do not crash
            logger.error(f"[TestExecutionView.open_report_in_tab] Error loading {file_path}: {e}")

    def track_history(self, url):
        if not self.history or self.history[-1] != url:
            self.history.append(url)

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()  # Remove current
            previous_url = self.history[-1]
            self.web.setUrl(previous_url)

    def on_show_start_execution_dialog(self, enable_date_time:bool, client_code:str, variant:str, subvariant:str):
        start_execution_dialog = StartTestExecutionDialogView(self.view_model, enable_date_time, client_code, variant, subvariant)
        start_execution_dialog.exec()

    def on_show_schedule_indicator(self, show_indicator, date_time):
        if show_indicator:
            self.schedule_test_indicator.setVisible(True)
            self.current_schedule = date_time
            self.schedule_test_indicator.setToolTip(f'Execution scheduled at: {date_time.toString()}')
        else:
            self.current_schedule = None
            self.schedule_test_indicator.setVisible(False)

    def on_reset_schedule(self):
        reset_schedule_dialog = ResetScheduleDialog(self.view_model)
        reset_schedule_dialog.exec()

    def on_tag_not_found_error(self, tag):
        QMessageBox.warning(self, "MDCAutoTestClient: Tag not found", f"Tag {tag} not found in selected test plan.")

    def on_device_not_found_error(self, device_types: list):
        msg = "Connect below devices to proceed:"
        devices = ''
        for types_ in device_types:
            devices = devices + '\n' + "\u2022 " + types_
        msg = msg + devices
        QMessageBox.warning(self, "MDCAutoTestClient: Device not found", msg)

    def on_toggle_execution_menu(self, toggle):
        self.start_execution_action.setEnabled(toggle)
        self.schedule_execution_action.setEnabled(toggle)

    def on_toggle_pause_button(self, execution_paused):
        if execution_paused:
            # change button icon and tool tip to resume
            self.pause_button.setToolTip('Resume Execution')
            self.pause_button.setIcon(base64_to_icon(resume_execution))
        else:
            # change button icon and tool tip to pause
            self.pause_button.setToolTip('Pause Execution')
            self.pause_button.setIcon(base64_to_icon(pause_execution))

