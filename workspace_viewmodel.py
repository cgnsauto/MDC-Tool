# Copyright (c) Capgemini. All rights reserved.
import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt

from common import Workspace
from logger import logger
from parsers.config_parser import ConfigParser

class WorkspaceViewModel(QObject):
    data_loaded = Signal()  # Signal emitted when data is loaded
    no_tag_selected = Signal()
    reset_buttons = Signal()
    reset_testsuite_tab_buttons = Signal()
    reset_reports_tab_buttons = Signal()
    enable_add_to_testhub_button = Signal(bool)
    def __init__(self, model, signal_manager):
        super().__init__()
        self.model = model
        self.signal_manager = signal_manager
        self.selected_items = {}  # Dictionary storing the items selected from the tree view
        self.tags = ['Select Tag','Sanity','Fullft','Stress','Regression']
        self.selected_tag = None
        self.variant = None
        self.subvariant = None
        self.workspace = None
        self.testresult_path = None
        self.testsuite_path = None
        self.connect_signals_to_slots()

    def _get_relative_path(self, model, item_text, item_parent):
        parents = []
        root_node_index = model.index(0, 0, model.invisibleRootItem().index())
        parent = item_parent
        while parent is not None:
            #if parent is not model.invisibleRootItem():  # and parent.text() != self.testsuite_folder:
            if parent.index() != root_node_index:
                parents.append(parent.text())
            parent = parent.parent()
        item_relative_path = "/".join(reversed(parents)) + "/" + item_text
        return item_relative_path

    def connect_signals_to_slots(self):
        self.signal_manager.open_workspace.connect(self.on_open_workspace)
        self.signal_manager.test_execution_started.connect(self.on_test_execution_started)
        self.signal_manager.test_execution_stopped.connect(self.on_test_execution_stopped)
        self.signal_manager.test_reports_generated.connect(self.on_test_reports_generated)

    def on_test_execution_started(self, num_cycles):
        self.enable_add_to_testhub_button.emit(False)

    def on_test_execution_stopped(self):
        self.enable_add_to_testhub_button.emit(True)

    def on_open_workspace(self, workspace_path, subvariant):
        #clear testsuite and reports tree
        self.workspace = None
        self.model.testsuite_model.clear()
        self.model.reports_model.clear()
        self.selected_items.clear() # clear any previously selected test plans
        self.reset_buttons.emit()
        self.signal_manager.reset_test_execution_view.emit()

        #workspace_name = workspace_path[workspace_path.rfind('/')+1:len(workspace_path)]
        self.variant = Path(workspace_path).name
        config_path = os.path.join(workspace_path, f"{self.variant}.ini")
        config = ConfigParser(config_path)

        # Read testsuite and testresult directory name from .ini file
        testsuite_folder_name = config.get_value('WORKSPACE', 'testsuitefolder')
        testresult_folder_name = config.get_value('WORKSPACE', 'testresultfolder')
        client_code = config.get_value('WORKSPACE', 'clientcode')
        evidence_folder = config.get_value('WORKSPACE', 'evidencefolder')
        report_folder = config.get_value('WORKSPACE', 'reportfolder')
        self.workspace = Workspace(workspace_path, client_code, self.variant, subvariant, testsuite_folder_name, testresult_folder_name,
                                   evidence_folder, report_folder)

        # Populate test plans
        self.testsuite_path = os.path.join(workspace_path, testsuite_folder_name)

        relative_paths = []
        test_file_types = []
        root = Path(str(self.testsuite_path))
        excel_files = [
            file for file in root.rglob("*")
            if file.suffix in [".xlsx", ".xlsm"] and not file.name.startswith("~$")
        ]
        for file in excel_files:
            relative_paths.append(str(file.relative_to(root)))
            test_file_types.append(file.suffix)
        self.model.populate_model(self.variant, subvariant, self.model.testsuite_model, testsuite_folder_name, relative_paths, test_file_types)

        # Populate html test reports
        self.testresult_path = os.path.join(workspace_path, testresult_folder_name)
        html_root = Path(str(self.testresult_path))
        html_files = list(html_root.rglob("*.html"))
        relative_html_paths = []
        report_file_types = []
        for file in html_files:
            relative_html_paths.append(str(file.relative_to(html_root)))
            report_file_types.append(file.suffix)
        self.model.populate_model(self.variant, subvariant, self.model.reports_model, testresult_folder_name, relative_html_paths, report_file_types)
        self.subvariant = subvariant
        # self.model.setHorizontalHeaderLabels(
        #     ['Name'])

    def on_tag_selection_changed(self, text):
        self.selected_tag = text

    def on_reports_tree_item_selection_changed(self, index):
        try:
            if index:
                model = self.model.reports_model
                item = model.itemFromIndex(index)
                if item.rowCount() == 0: # Select only leaf items
                    item_text = item.text()
                    parent = item.parent()
                    item_relative_path = self._get_relative_path(model,item_text, parent)
                    item_abs_path = self.workspace.workspace_path + '/'+ item_relative_path
                    self.signal_manager.report_file_selected.emit(item_abs_path)
        except Exception as e:
            logger.critical(f"Exception Caught : {e}")

    # Handle item selection events
    def on_testsuite_tree_item_selection_changed(self,selected, deselected):
        try:
            selected_indices = selected.indexes()
            deselected_indices = deselected.indexes()
            if selected_indices:
                item = self.model.testsuite_model.itemFromIndex(selected_indices[0])
                if item.rowCount() == 0: # Select only leaf items
                    item_text = item.text()
                    parent = item.parent()
                    item_relative_path = self._get_relative_path(self.model.testsuite_model,item_text, parent)
                    item_abs_path = self.workspace.workspace_path + '/'+ item_relative_path
                    self.selected_items[item_relative_path] = item_abs_path
            if deselected_indices:
                item = self.model.testsuite_model.itemFromIndex(deselected_indices[0])
                if item.rowCount() == 0: # Deselect only leaf items
                    item_text = item.text()
                    parent = item.parent()
                    item_relative_path = self._get_relative_path(self.model.testsuite_model, item_text, parent)
                    if item_relative_path in self.selected_items.keys():
                        self.selected_items.pop(item_relative_path)
        except Exception as e:
            logger.critical(f"Exception Caught: {str(e)}")

    def on_add_to_testhub_button_clicked(self):
        if self.selected_tag != 'Select Tag':
            if self.selected_items:
                self.signal_manager.push_items_to_execution_queue.emit(self.workspace, list(self.selected_items.values()), self.selected_tag)
        else:
            self.no_tag_selected.emit()

    def on_test_reports_generated(self):
        self.model.reports_model.clear()
        self.reset_reports_tab_buttons.emit()
        html_root = Path(str(self.testresult_path))
        html_files = list(html_root.rglob("*.html"))
        relative_html_paths = []
        report_file_types = []
        # Print the relative paths of the found files
        for file in html_files:
            relative_html_paths.append(str(file.relative_to(html_root)))
            report_file_types.append(file.suffix)
        self.model.populate_model(self.variant, self.subvariant, self.model.reports_model, html_root.name,
                                  relative_html_paths, report_file_types)

    def close_document(self):
        pass

    def on_refresh_reports_button_clicked(self):
        if not self.model.reports_model.rowCount() == 0:
            self.model.reports_model.clear()
            self.reset_reports_tab_buttons.emit()
            html_root = Path(str(self.testresult_path))
            html_files = list(html_root.rglob("*.html"))
            relative_html_paths = []
            report_file_types = []
            # Print the relative paths of the found files
            for file in html_files:
                relative_html_paths.append(str(file.relative_to(html_root)))
                report_file_types.append(file.suffix)
            self.model.populate_model(self.variant, self.subvariant, self.model.reports_model, html_root.name,
                                      relative_html_paths, report_file_types)

    def on_refresh_testsuites_button_clicked(self):
        if not self.model.testsuite_model.rowCount() == 0:
            self.model.testsuite_model.clear()

            self.selected_items.clear()
            self.reset_testsuite_tab_buttons.emit()

            relative_paths = []
            extensions = []
            root = Path(str(self.testsuite_path))
            excel_files = [
                file for file in root.rglob("*")
                if file.suffix in [".xlsx", ".xlsm"] and not file.name.startswith("~$")
            ]
            for file in excel_files:
                relative_paths.append(str(file.relative_to(root)))
                extensions.append(file.suffix)
            self.model.populate_model(self.variant, self.subvariant, self.model.testsuite_model, root.name, relative_paths, extensions)
