# Copyright (c) Capgemini. All rights reserved.
from pathlib import Path

from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon
from icons import base64_to_icon, folder_close, test_plan, html_file

class WorkspaceModel:
    def __init__(self):
        super().__init__()
        self.testsuite_model = QStandardItemModel()
        self.reports_model = QStandardItemModel()
        self.reports_model.invisibleRootItem().index()

    def find_item_by_text(self, model, text, parent=None):
        if parent is None:
            parent = model.invisibleRootItem()
        for row in range(parent.rowCount()):
            item = parent.child(row)
            if item.text() == text:
                return item
        return None

    def populate_model(self, variant, subvariant, model, folder_path, relative_paths:list, file_types):
        root_node_text = f'{variant}-{subvariant}' if subvariant else variant
        root_node = QStandardItem(root_node_text)
        root_node.setIcon(base64_to_icon(folder_close))
        model.appendRow(root_node)
        folder_name = Path(folder_path).name
        folder_node = QStandardItem(folder_name)
        folder_node.setIcon(base64_to_icon(folder_close))
        root_node.appendRow(folder_node)
        for path, file_type in zip(relative_paths, file_types):
            parent = folder_node
            nodes = path.split('\\')
            for node in nodes:
                # Check if the node is already added
                if parent:
                    child = self.find_item_by_text(model, node, parent)
                    if not child:
                        child = QStandardItem(node)
                        if node.endswith(file_type):
                            if file_type in ['.xlsx', '.xlsm']:
                                child.setIcon(base64_to_icon(test_plan))
                            else:
                                child.setIcon(base64_to_icon(html_file))
                        else:
                            child.setIcon(base64_to_icon(folder_close))
                        parent.appendRow(child) # Add node in the parent
                    parent = child
                else:
                    child = self.find_item_by_text(model,node)
                    if not child:
                        child = QStandardItem(node)
                        child.setIcon(base64_to_icon(folder_close))  # Initial icon
                        model.appendRow(child)
                    parent = child

