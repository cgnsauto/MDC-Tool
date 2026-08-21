# Copyright (c) Capgemini. All rights reserved.
import os.path
import subprocess
import threading
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMainWindow, QToolBar, QTabWidget, QWidget, QVBoxLayout, QFrame, QMenu, QMessageBox, \
    QToolButton, QFileDialog, QSizePolicy, QLabel

from custom_widgets import ClosableTabWidget, CustomDockWidget
from icons import base64_to_icon, new_workspace_icon, open_workspace_icon, audio_detection_icon, quit_app_icon, \
    base64_to_pixmap, cg_logo_big
from logger import logger
from model.device_model import DeviceModel
from model.new_workspace_model import NewWorkspaceModel
from model.test_execution_model import TestExecutionModel
from model.workspace_model import WorkspaceModel
from utils import Struct, action, add_actions
from view.device_view import DeviceView
from view.new_workspace_view import NewWorkspaceView
from view.test_execution_view import TestExecutionView

from view.open_workspace_dialog_view import OpenWorkspaceDialogView
from view.workspace_view import WorkspaceView
from viewmodel.device_viewmodel import DeviceViewModel
from viewmodel.new_workspace_viewmodel import NewWorkspaceViewModel
from viewmodel.test_execution_viewmodel import TestExecutionViewModel
from viewmodel.open_workspace_dialog_viewmodel import OpenWorkspaceDialogViewModel
from viewmodel.workspace_viewmodel import WorkspaceViewModel

class MainWindow(QMainWindow):
    """
    This class represents the main window of the application.
    """
    def __init__(self, signal_manager, service_manager, device_manager):
        super().__init__()

        self.devices_dock_widget = None
        self.left_dock_widget = None
        self.devices_dock_widget = None
        self.right_dock_widget = None
        self.workspace_tab = None
        self.test_center_tab_widget = None
        self.main_toolbar_style = None
        self.workspace_view_container = None
        self.signal_manager = signal_manager
        self.device_manager = device_manager
        self.service_manager = service_manager
        workspace_model = WorkspaceModel()
        workspace_view_model = WorkspaceViewModel(workspace_model, self.signal_manager)
        self.workspace_view = WorkspaceView(workspace_view_model)
        test_execution_model = TestExecutionModel()
        test_execution_viewmodel = TestExecutionViewModel(test_execution_model, service_manager, signal_manager, device_manager)
        self.test_execution_view = TestExecutionView(test_execution_viewmodel)
        device_model = DeviceModel()
        device_view_model = DeviceViewModel(device_model, signal_manager, device_manager)
        self.device_view = DeviceView(device_view_model, signal_manager)
        self.documents = [test_execution_viewmodel,workspace_view_model,device_view_model]  # list of view models
        self.file_menu_actions = None
        self.devices_actions = None
        self.open_workspace_action = None
        self.__create_menu()
        self.__init_layout()
        self.signal_manager.test_execution_started.connect(self.disable_open_workspace)
        self.signal_manager.test_execution_stopped.connect(self.enable_open_workspace)

    def __create_menu(self):
        try:
            #create file menu
            new_workspace = action(self, 'New Workspace', self.create_new_workspace, icon=base64_to_icon(new_workspace_icon))
            open_workspace = action(self, 'Open Workspace', self.open_workspace, icon=base64_to_icon(open_workspace_icon))
            recent = action(self, 'Recent Workspaces')
            quit_application = action(self, 'Quit', self.close, icon=base64_to_icon(quit_app_icon))
            self.file_menu_actions = Struct(new_workspace=new_workspace, open_workspace=open_workspace,
                                  quit_application=quit_application, recent=recent)
            menu_bar = self.menuBar()
            file_menu = menu_bar.addMenu("File")
            add_actions(file_menu, (new_workspace, open_workspace, recent, quit_application))

        except Exception as e:
            logger.critical(f"Failed to create menus : {e}")

    def __create_tool_bar(self):
        # Toolbar
        toolbar = QToolBar("Toolbar")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        toolbar.setStyleSheet("""
            QToolButton {
                font-size: 16px;
                width: 45px;
                height: 45px;
                padding: 0px;
            }
        """)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        new_workspace = action(self, 'New', self.create_new_workspace, icon=base64_to_icon(new_workspace_icon), tip='New Workspace')
        self.open_workspace_action = action(self, 'Open', self.open_workspace, icon=base64_to_icon(open_workspace_icon), tip='Open Workspace')
        audio_detection = action(self, 'Audio', self.run_audio_detection, icon=base64_to_icon(audio_detection_icon), tip='Audio Detection')
        #audio_detection.setMinimumWidth(120)
        add_actions(toolbar, [new_workspace, self.open_workspace_action])
        toolbar.addSeparator()
        add_actions(toolbar, [audio_detection])

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        toolbar.addSeparator()
        cg_logo_label = QLabel()
        pixmap = QPixmap(base64_to_pixmap(cg_logo_big))
        cg_logo_label.setPixmap(pixmap)
        toolbar.addWidget(cg_logo_label)
        self.main_toolbar_style = toolbar.styleSheet()

    def __create_left_dock_widget(self):
        self.left_dock_widget = CustomDockWidget("Workspace", self)
        self.left_dock_widget.title_bar.setStyleSheet("background-color: #9c9c9c;")  # Selected color
        self.left_dock_widget.title_label.setStyleSheet("color: white;")
        # Create a tab widget
        self.workspace_tab = QTabWidget()
        self.workspace_tab.setStyleSheet("""
                                    QTabBar::tab:selected {
                                        background-color: white; /* Change background color to white when selected */
                                        border: 2px solid #dedede; /* Set a raised border */
                                        border-bottom-color: none;
                                        padding: 2px
                                    }
                                   """)

        workspace_view_container = QWidget()
        workspace_view_layout = QVBoxLayout()
        workspace_view_layout.setContentsMargins(5, 0, 0, 0)
        workspace_view_container.setLayout(workspace_view_layout)
        workspace_view_layout.addWidget(self.workspace_view)

        #self.workspace_tab.addTab(self.workspace_view_container, "Workspace")

        #self.left_dock_widget.setWidget(self.workspace_tab)
        self.left_dock_widget.setWidget(workspace_view_container)
        self.left_dock_widget.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock_widget)

        # Create devices dock widget
        information = "Use context menu to Add,Remove,Connect and Disconnect devices."
        self.devices_dock_widget = CustomDockWidget("Manage Devices", self, True,information)
        self.devices_dock_widget.title_bar.setStyleSheet("background-color: #9c9c9c;")  # Selected color
        self.devices_dock_widget.title_label.setStyleSheet("color: white;")
        #self.devices_dock_widget.setFixedHeight(300)
        #device_frame = QFrame()
        # device_frame.setFrameShape(QFrame.Shape.WinPanel)

        # device_frame.setFixedHeight(400)
        device_view_container = QWidget()
        device_view_layout = QVBoxLayout()
        device_view_layout.setContentsMargins(0, 0, 0, 0)
        device_view_container.setLayout(device_view_layout)
        device_view_layout.addWidget(self.device_view)
        self.devices_dock_widget.setWidget(device_view_container)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.devices_dock_widget)

    def __create_right_dock_widget(self):
        self.right_dock_widget = CustomDockWidget("Explorer", self)
        self.right_dock_widget.title_bar.setStyleSheet("background-color: #0284CA;")  # Selected color
        self.right_dock_widget.title_label.setStyleSheet("color: white;")

        #self.test_center_tab_widget = ClosableTabWidget()
        self.test_center_tab_widget = QTabWidget()
        test_center_tab = QWidget()
        #self.test_center_tab_widget.add_closable_tab(test_center_tab, "Test Hub")
        self.test_center_tab_widget.addTab(test_center_tab, "Test Hub")
        test_center_tab_layout = QVBoxLayout(test_center_tab)

        test_center_tab_layout.addWidget(self.test_execution_view)

        self.right_dock_widget.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.right_dock_widget.setWidget(self.test_center_tab_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock_widget)
        self.setCentralWidget(self.right_dock_widget)

    def __init_layout(self):
        self.__create_tool_bar()
        self.__create_left_dock_widget()
        self.__create_right_dock_widget()

    def create_new_workspace(self):
        new_workspace_model = NewWorkspaceModel()
        new_workspace_viewmodel = NewWorkspaceViewModel(new_workspace_model)
        new_workspace_dialog = NewWorkspaceView(new_workspace_viewmodel)
        new_workspace_dialog.exec()

    def open_workspace(self):
        view_model = OpenWorkspaceDialogViewModel(self.signal_manager)
        dialog = OpenWorkspaceDialogView(view_model, self.signal_manager)
        dialog.exec_()

    @staticmethod
    def run_audio_detection():
        def target():
            try:
                venv_python = os.path.join("MDCAutoTestClient_v1.0.0","venv", "Scripts", "python.exe")
                print(venv_python)
                subprocess.run([venv_python, "audio_gui.py"], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error occurred while running audio_detection.py: {e}")

        audio_detection_thread = threading.Thread(target=target)
        audio_detection_thread.start()

    def enable_open_workspace(self):
        self.open_workspace_action.setEnabled(True)
        self.file_menu_actions.open_workspace.setEnabled(True)

    def disable_open_workspace(self, num_cycles):
        self.open_workspace_action.setEnabled(False)
        self.file_menu_actions.open_workspace.setEnabled(False)

    def confirm_close(self):
        reply = QMessageBox.question(self, 'Confirm Close',
                                     "Are you sure to quit?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes

    def closeEvent(self, event):
        if self.confirm_close():
            self.close_documents()
            event.accept()
        else:
            event.ignore()

    def close_documents(self):
        for doc in self.documents:
            doc.close_document()
        self.documents.clear()
        self.device_manager.shutdown()
        del self.device_manager
        del self.signal_manager

    def resize_dock_widgets(self):
        window_width = self.width()
        left_dock_width = int(window_width * 0.1)
        right_dock_width = int(window_width * 0.9)
        self.resizeDocks([self.left_dock_widget, self.right_dock_widget], [left_dock_width, right_dock_width],
                                Qt.Orientation.Horizontal)

    def select_left_dock_widget(self):
        pass
        #self.right_dock_widget.activateWindow()
        #self.right_dock_widget.setFocus()
        # self.right_dock_widget.raise_()
        # self.right_dock_widget.setFocus()
        #self.left_dock_widget.clearFocus()
        #self.right_dock_widget.raise_()
        #self.left_dock_widget.clearFocus()



