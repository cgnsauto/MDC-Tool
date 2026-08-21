# Copyright (c) Capgemini. All rights reserved.
from PySide6 import QtCore
from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QModelIndex
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QHBoxLayout, QPushButton, QComboBox, QTreeView, \
    QAbstractItemView, QMessageBox, QToolButton, QTabWidget

from icons import base64_to_icon, expand, folder_open, folder_close, collapse, move_left, deselect_all, add_queue, \
    base64_to_pixmap, down_arrow, select_all_items, refresh_test_execution, html_file


class WorkspaceView(QWidget):
    def __init__(self, view_model):
        super().__init__()
        self.view_model = view_model
        self.contents_tab = None
        self.toggle_selection_button = None
        self.select_all = True
        self.expand_testsuites_button = None
        self.expand_reports_button = None
        self.refresh_testsuites_button = None
        self.refresh_reports_button = None
        
        self.add_to_testhub_button = None
        self.testsuite_tree = None
        self.reports_tree = None
        self.tags_combo_box = None
        self.expand_testsuite_tree = True
        self.expand_reports_tree = True
        self.is_data_loaded = False  # Prevents redundant loading
        self.init_layout()
        self.connect_slots_to_signals()

    def __select_item(self, item, row, column, select_all):
        if item.rowCount() == 0: # Select/Deselect only test plans
            parent_item = item.parent()
            if parent_item is not None:
                parent_index = self.testsuite_tree.model().indexFromItem(parent_item)
            else:
                parent_index = QtCore.QModelIndex()  # Root index
            index = self.testsuite_tree.model().index(row, column, parent_index)
            if select_all:
                self.testsuite_tree.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select)
            else:
                self.testsuite_tree.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Deselect)
        for row in range(item.rowCount()):
            child_item = item.child(row, 0)
            if child_item:
                self.__select_item(child_item, row, 0,select_all)

    def __create_testsuite_content_layout(self, layout):
        controls_frame = QFrame()
        # controls_frame.setFrameShadow(QFrame.Sunken)
        controls_frame.setStyleSheet("""
                                   QFrame {
                                       background-color: #F0F0F0;
                                       border: 1px #E3E3E3;
                                       border-top: 2px solid #A9A9A9;
                                       border-bottom: 1px solid #F0F0F0;
                                   }
                               """)
        # controls_frame.setFrameShape(QFrame.WinPanel)
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(5)
        controls_frame.setLayout(controls_layout)
        self.toggle_selection_button = QPushButton()
        self.toggle_selection_button.setToolTip('Select/Deselect all')
        self.toggle_selection_button.setStyleSheet("border: none")
        self.toggle_selection_button.setIcon(base64_to_icon(deselect_all))
        self.toggle_selection_button.setFixedWidth(20)
        self.toggle_selection_button.setFixedHeight(20)

        self.expand_testsuites_button = QPushButton("")
        self.expand_testsuites_button.setToolTip('Expand/Collapse all')
        self.expand_testsuites_button.setStyleSheet("border: none")
        self.expand_testsuites_button.setIcon(base64_to_icon(expand))
        self.expand_testsuites_button.setFixedWidth(20)
        self.expand_testsuites_button.setFixedHeight(20)
        separator_1 = QFrame()
        separator_1.setStyleSheet("QFrame { background-color: #A5A5A5; }")
        separator_1.setFrameShape(QFrame.Shape.VLine)
        separator_1.setFrameShadow(QFrame.Shadow.Sunken)
        separator_1.setFixedWidth(1)

        # Convert base64 to QPixmap
        pixmap = base64_to_pixmap(down_arrow)

        # Save the pixmap to a temporary file
        pixmap.save("down_arrow.png")

        self.tags_combo_box = QComboBox()
        self.tags_combo_box.setStyleSheet("""
                    QComboBox {
                        border: 1px solid gray;
                        padding: 1px 15px 1px 1px;
                        min-width: 4.3em;
                    }
                    QComboBox:editable {
                        background: white;
                    }
                    QComboBox:!editable, QComboBox::drop-down:editable {
                        background: white;
                    }
                    QComboBox:!editable:on, QComboBox::drop-down:editable:on {
                        background: white;
                    }
                    QComboBox:on {
                        padding-top: 3px;
                        padding-left: 4px;
                    }
                    QComboBox::drop-down {
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 25px;
                        border-left-width: 1px;
                        border-left-color: darkgray;
                        border-left-style: solid;
                        border-top-right-radius: 3px;
                        border-bottom-right-radius: 3px;
                    }
                    QComboBox::down-arrow {
                        image: url(down_arrow.png);
                    }
                """)
        self.tags_combo_box.setObjectName("Tags")

        self.refresh_testsuites_button = QPushButton(" ")
        self.refresh_testsuites_button.setToolTip('Refresh Testsuites')
        self.refresh_testsuites_button.setStyleSheet("border: none")
        self.refresh_testsuites_button.setIcon(base64_to_icon(refresh_test_execution))
        self.refresh_testsuites_button.setFixedWidth(30)
        self.refresh_testsuites_button.setFixedHeight(30)

        self.add_to_testhub_button = QPushButton("")
        self.add_to_testhub_button.setToolTip('Add to Test Hub')
        self.add_to_testhub_button.setStyleSheet("Border: none;")
        self.add_to_testhub_button.setFixedWidth(20)
        self.add_to_testhub_button.setFixedHeight(20)
        self.add_to_testhub_button.setIcon(base64_to_icon(add_queue))
        self.add_to_testhub_button.setIconSize(QSize(20, 20))

        controls_layout.addWidget(self.toggle_selection_button)

        controls_layout.addWidget(self.expand_testsuites_button)
        controls_layout.addWidget(separator_1)
        controls_layout.addWidget(self.tags_combo_box)
        controls_layout.addWidget(self.refresh_testsuites_button)
        controls_layout.addWidget(self.add_to_testhub_button)

        layout.addWidget(controls_frame)

        # Create the workspace tree view
        self.testsuite_tree = QTreeView()
        self.testsuite_tree.setSelectionMode(QTreeView.SelectionMode.MultiSelection)
        # self.testsuite_tree.setContentsMargins(0,0,0,0)
        self.testsuite_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Make the tree read only
        # Enable lines connecting the root items to their children
        # self.testsuite_tree.setStyleSheet("border: 1px solid #d3d3d3; border-bottom: none;")
        self.testsuite_tree.setStyleSheet("border: none;")
       #self.testsuite_tree.setRootIsDecorated(True)
        # self.testsuite_tree.setStyleSheet("""
        #     QTreeView::item {
        #         border: 1px solid lightgrey;
        #     }
        # """)

        # self.testsuite_tree.header().setStyleSheet("""
        #                         QHeaderView::section {
        #                             background-color: white;
        #                             border: none;
        #                             border-bottom: none;
        #                         }
        #                     """)

        self.testsuite_tree.header().hide()
        self.testsuite_tree.setModel(self.view_model.model.testsuite_model)
        layout.addWidget(self.testsuite_tree)

    def __create_reports_content_layout(self, layout):
        controls_frame = QFrame()
        controls_frame.setStyleSheet("""
                                   QFrame {
                                       background-color: #F0F0F0;
                                       border: 1px #E3E3E3;
                                       border-top: 2px solid #A9A9A9;
                                       border-bottom: 1px solid #F0F0F0;
                                   }
                               """)
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        #controls_layout.setSpacing(5)
        controls_frame.setLayout(controls_layout)
        self.expand_reports_button = QPushButton("")
        self.expand_reports_button.setToolTip('Expand/Collapse all')
        self.expand_reports_button.setStyleSheet("border: none")
        self.expand_reports_button.setIcon(base64_to_icon(expand))
        self.expand_reports_button.setFixedWidth(20)
        self.expand_reports_button.setFixedHeight(20)


        self.refresh_reports_button = QPushButton(" ")
        self.refresh_reports_button.setToolTip('Refresh Reports')
        self.refresh_reports_button.setStyleSheet("border: none")
        self.refresh_reports_button.setIcon(base64_to_icon(refresh_test_execution))
        self.refresh_reports_button.setFixedWidth(30)
        self.refresh_reports_button.setFixedHeight(30)

        controls_layout.addWidget(self.expand_reports_button)
        controls_layout.addWidget(self.refresh_reports_button)
        layout.addWidget(controls_frame)

        # Create the reports tree view
        self.reports_tree = QTreeView()
        self.reports_tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.reports_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Make the tree read only
        self.reports_tree.setStyleSheet("border: none;")
        self.reports_tree.setRootIsDecorated(True)

        # self.reports_tree.header().setStyleSheet("""
        #                         QHeaderView::section {
        #                             background-color: white;
        #                             border: none;
        #                             border-bottom: none;
        #                         }
        #                     """)

        self.reports_tree.header().hide()
        self.reports_tree.setModel(self.view_model.model.reports_model)
        layout.addWidget(self.reports_tree)

    def init_layout(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        self.contents_tab = QTabWidget()
        # self.contents_tab.setStyleSheet("""
        #                                     QTabBar::tab:selected {
        #                                         background-color: white; /* Change background color to white when selected */
        #                                         border: 2px solid #dedede; /* Set a raised border */
        #                                         border-bottom-color: none;
        #                                         padding: 2px
        #                                     }
        #                                 """)

        # Add testsuite tab
        testsuite_content_area = QFrame()
        testsuite_content_layout = QVBoxLayout()
        self.__create_testsuite_content_layout(testsuite_content_layout)
        testsuite_content_area.setLayout(testsuite_content_layout)
        self.contents_tab.addTab(testsuite_content_area, "Testsuites")

        # Add Reports tab
        reports_content_area = QFrame()
        reports_content_layout = QVBoxLayout()
        self.__create_reports_content_layout(reports_content_layout)
        reports_content_area.setLayout(reports_content_layout)
        self.contents_tab.addTab(reports_content_area, "Testreports")

        layout.addWidget(self.contents_tab)
        self.setLayout(layout)

    def connect_slots_to_signals(self):
        self.testsuite_tree.expanded.connect(self.on_testsuite_tree_item_expanded)
        self.testsuite_tree.collapsed.connect(self.on_testsuite_tree_item_collapsed)
        self.reports_tree.expanded.connect(self.on_reports_tree_item_expanded)
        self.reports_tree.collapsed.connect(self.on_reports_tree_item_collapsed)
        self.toggle_selection_button.clicked.connect(self.on_toggle_selection_button_clicked)
        self.expand_testsuites_button.clicked.connect(self.on_expand_testsuites_button_clicked)
        self.expand_reports_button.clicked.connect(self.on_expand_reports_button_clicked)
        self.add_to_testhub_button.clicked.connect(self.view_model.on_add_to_testhub_button_clicked)
        self.refresh_testsuites_button.clicked.connect(self.view_model.on_refresh_testsuites_button_clicked)
        self.refresh_reports_button.clicked.connect(self.view_model.on_refresh_reports_button_clicked)
        self.tags_combo_box.currentTextChanged.connect(self.view_model.on_tag_selection_changed)
        self.reports_tree.clicked.connect(self.view_model.on_reports_tree_item_selection_changed)
        self.testsuite_tree.selectionModel().selectionChanged.connect(self.view_model.on_testsuite_tree_item_selection_changed)

        self.view_model.no_tag_selected.connect(self.on_no_tag_selected)
        self.view_model.reset_buttons.connect(self.on_reset_buttons)
        self.view_model.reset_testsuite_tab_buttons.connect(self.on_reset_testsuite_tab_buttons)
        self.view_model.reset_reports_tab_buttons.connect(self.on_reset_reports_tab_buttons)
        self.view_model.enable_add_to_testhub_button.connect(self.on_enable_add_to_testhub_button)

    def showEvent(self, event):
        """Called whenever the View is shown."""
        super().showEvent(event)
        if not self.is_data_loaded:
            self.is_data_loaded = True
            self.tags_combo_box.addItems(self.view_model.tags)

    def on_testsuite_tree_item_expanded(self, index):
        item = self.testsuite_tree.model().itemFromIndex(index)
        if item.rowCount() > 0:
            item.setIcon(base64_to_icon(folder_open))

    def on_testsuite_tree_item_collapsed(self, index):
        item = self.testsuite_tree.model().itemFromIndex(index)
        if item.rowCount() > 0:
            item.setIcon(base64_to_icon(folder_close))

    def on_reports_tree_item_expanded(self, index):
        item = self.reports_tree.model().itemFromIndex(index)
        if item.rowCount() > 0:
            item.setIcon(base64_to_icon(folder_open))
        else:
            item.setIcon(base64_to_icon(html_file))

    def on_reports_tree_item_collapsed(self, index):
        item = self.reports_tree.model().itemFromIndex(index)
        if item.rowCount() > 0:
            item.setIcon(base64_to_icon(folder_close))
        else:
            item.setIcon(base64_to_icon(html_file))

    def on_toggle_selection_button_clicked(self):
        parent_index = QModelIndex()
        model = self.testsuite_tree.model()
        select_all = self.select_all
        if model.rowCount():
            for row in range(model.rowCount(parent_index)):
                index = model.index(row, 0, parent_index)
                item = model.itemFromIndex(index)
                if item:
                    self.__select_item(item, row,0, select_all)
            self.select_all = not self.select_all  # Toggle the select flag
            if select_all:
                self.toggle_selection_button.setIcon(base64_to_icon(select_all_items))
            else:
                self.toggle_selection_button.setIcon(base64_to_icon(deselect_all))

    def on_expand_testsuites_button_clicked(self):
        """
        Expand or collapse all test suites tree items
        :return: None
        """
        if self.testsuite_tree.model().rowCount()!=0:
            if self.expand_testsuite_tree:
                self.testsuite_tree.expandAll()
                self.expand_testsuite_tree = False
                self.expand_testsuites_button.setIcon(base64_to_icon(collapse))
            else:
                self.testsuite_tree.collapseAll()
                self.expand_testsuite_tree = True
                self.expand_testsuites_button.setIcon(base64_to_icon(expand))

    def on_expand_reports_button_clicked(self):
        """
        Expand or collapse all reports tree items
        :return: None
        """
        if self.reports_tree.model().rowCount()!=0:
            if self.expand_reports_tree:
                self.reports_tree.expandAll()
                self.expand_reports_tree = False
                self.expand_reports_button.setIcon(base64_to_icon(collapse))
            else:
                self.reports_tree.collapseAll()
                self.expand_reports_tree = True
                self.expand_reports_button.setIcon(base64_to_icon(expand))

    def on_no_tag_selected(self):
        QMessageBox.warning(self, "Tag selection error", 'Select a tag')

    def on_reset_buttons(self):
        # Reset testsuite tab buttons
        self.select_all = True
        self.toggle_selection_button.setIcon(base64_to_icon(deselect_all))

        self.expand_testsuite_tree = True
        self.expand_testsuites_button.setIcon(base64_to_icon(expand))

        # Reset report tab buttons
        self.expand_reports_tree = True
        self.expand_reports_button.setIcon(base64_to_icon(expand))

    def on_reset_reports_tab_buttons(self):
        self.expand_reports_tree = True
        self.expand_reports_button.setIcon(base64_to_icon(expand))

    def on_reset_testsuite_tab_buttons(self):
        self.select_all = True
        self.toggle_selection_button.setIcon(base64_to_icon(deselect_all))

        self.expand_testsuite_tree = True
        self.expand_testsuites_button.setIcon(base64_to_icon(expand))

    def on_enable_add_to_testhub_button(self, enable):
        self.add_to_testhub_button.setEnabled(enable)


