# Copyright (c) Capgemini. All rights reserved.

from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon, Qt

from icons import base64_to_icon, excel_close, testcase, test_plan, test_tag, feature
from logger import logger
from parsers.excel_parser import ExcelParser
from test_execution_thread import Result


class TestExecutionModel(QStandardItemModel):
    """
    The model represents the data shown in the tree view
    """
    def __init__(self):
        super().__init__()
        self.workspace = None
        self.total_test_plans = 0
        self.total_test_case_count = 0
        self.event_name = None
        self.meter_number = None
        self.cm0_boot = None
        self.tester_name = None
        self.cm0_appl = None
        self.revision_sw_version = None
        #self.eeprom_data_version = None
        self.eeprom_map_version = None
        #self.target_variation = None
        self.cm7_boot = None
        self.cm7_appl = None
        self.jpeg_decoder = None
        self.graphics_data = None
        self.execution_results = {}  # dictionary storing the execution results of test plans

    def __get_test_steps(self, test_case):
        test_steps = []
        for row in range(test_case.rowCount()):
            test_step = []
            for column in range(test_case.columnCount()):
                child_item = test_case.child(row, column)
                test_step.append(child_item.text())
            test_steps.append(test_step)
        return test_steps

    def __update_device_types(self, test_steps, device_types):
        for test_step in test_steps:
            input_cmd = test_step[2]
            if 'device' in input_cmd:
                start_index =  input_cmd.index('device') + len('device')
                end_index = input_cmd.index(';',start_index)
                device_type = input_cmd[start_index+1:end_index]
                if device_type not in device_types:
                    device_types.append(device_type)

    def find_item_by_text(self, text, parent=None):
        """
        Find a tree model item using the item text
        :param text: string representing the item text
        :param parent: Parent of the item
        :return: QStandardItem instance representing the item
        """
        if parent is None:
            parent = self.invisibleRootItem()
        for row in range(parent.rowCount()):
            item = parent.child(row)
            if item.text() == text:
                return item
        return None

    def get_column_index(self, column_name):
        """
        Get index of column using the column name
        :param column_name: string representing column name
        :return: column index if found else -1
        """
        for column in range(self.columnCount()):
            if self.horizontalHeaderItem(column).text() == column_name:
                return column
        return -1  # Return -1 if the column name is not found

    def find_row_by_text(self, text, column, parent=None):
        """
        Find a row index using the text and column index
        :param text: string containing the text of the row item
        :param column: column index corresponding to the row item
        :param parent: parent of the row item
        :return: Row index
        """
        if parent is None:
            parent = self.invisibleRootItem()
        for row in range(parent.rowCount()):
            child_item = parent.child(row, column)
            if child_item.text() == text:
                return row
        return -1  # Return -1 if the row is not found

    def _create_node(self,text='', text_alignment=None, set_italic_font=False):
        node = QStandardItem(text)
        if text_alignment:
            node.setTextAlignment(text_alignment)
        if set_italic_font:
            font = node.font()
            font.setItalic(True)
            node.setFont(font)
        return node

    def add_items_to_execution_tree(self,workspace, items, tag):
        """
        Add items to execution tree
        :param workspace: object of class Workspace
        :param items: list of items
        :param tag: string representing the tag
        :return: None
        """
        self.workspace = workspace
        target_variant = self.workspace.variant
        if self.workspace.subvariant:
            target_variant = f'{self.workspace.variant}_{self.workspace.subvariant}'
        items_added = False
        parser = ExcelParser()
        # Add tag as parent node in the tree if it is not already added
        tag_node = self.find_item_by_text(tag)
        for item in items:
            test_plan_abs_path = item
            testplan_name = test_plan_abs_path[test_plan_abs_path.rfind('/') + 1:len(test_plan_abs_path)]
            parser.parse_file(test_plan_abs_path,2)
            feature_name = parser.get_feature_name(test_plan_abs_path, 2)
            test_data = parser.get_test_data_by_tag_and_variant(tag, target_variant)
            if not test_data:
                return False
            if not tag_node:
                tag_node = QStandardItem(base64_to_icon(test_tag), tag)  # Create Tag node
                self.appendRow(tag_node)
            feature_node = self.find_item_by_text(feature_name, tag_node)
            if not feature_node:
                feature_node = QStandardItem(base64_to_icon(feature), feature_name)  # Create Feature Node
                tag_node.appendRow(feature_node) # Add Feature Node

            if not self.find_item_by_text(testplan_name, feature_node):
                testplan = QStandardItem(base64_to_icon(test_plan), testplan_name) # Create test plan Node

                testplan_result = self._create_node(text_alignment=Qt.AlignmentFlag.AlignCenter,set_italic_font=True)
                feature_node.appendRow([testplan,QStandardItem(),QStandardItem(),QStandardItem(),QStandardItem(),testplan_result])
                testcase_id = None
                testcase_id_column_index = parser.get_column_index()
                teststep_col_idx = parser.get_column_index('Test Step')
                for data in test_data:
                    if not testcase_id:
                        testcase_id = QStandardItem(f"TestcaseID: {str(data[testcase_id_column_index])}")  # Create Testcase node
                        testcase_id.setIcon(QIcon(base64_to_icon(testcase)))
                        testcase_result = self._create_node(text_alignment=Qt.AlignmentFlag.AlignCenter,set_italic_font=True)
                        testplan.appendRow([testcase_id, QStandardItem(), QStandardItem(), QStandardItem(), QStandardItem(),testcase_result])
                    else:
                        #print(str(data[testcase_id_column_index]))
                        #print(testcase_id.text().replace("TestcaseID:",'').strip())
                        if str(data[testcase_id_column_index]) != testcase_id.text().replace("TestcaseID:",'').strip():
                            testcase_id = QStandardItem(f"TestcaseID: {str(data[testcase_id_column_index])}") #Create Testcase node
                            testcase_id.setIcon(QIcon(base64_to_icon(testcase)))
                            testcase_result = self._create_node(text_alignment=Qt.AlignmentFlag.AlignCenter, set_italic_font=True)
                            testplan.appendRow([testcase_id,QStandardItem(),QStandardItem(),QStandardItem(),QStandardItem(),testcase_result])
                    step_no = self._create_node(str(data[teststep_col_idx]),Qt.AlignmentFlag.AlignCenter)
                    description = self._create_node(str(data[testcase_id_column_index+4]),Qt.AlignmentFlag.AlignCenter)
                    input_task = self._create_node(str(data[testcase_id_column_index+5]),Qt.AlignmentFlag.AlignCenter)
                    output_task = self._create_node(str(data[testcase_id_column_index+6]),Qt.AlignmentFlag.AlignCenter)
                    status = self._create_node(text_alignment=Qt.AlignmentFlag.AlignCenter, set_italic_font=True)
                    testcase_id.appendRow([step_no, description, input_task, output_task, status])
                #testcase_id = None
        return True

    def fetch_test_data_for_execution(self):
        """
        Traverse the tree and append the test plans in the list
        :return: list containing the test plans
        """
        data = []
        device_types = []
        self.total_test_plans = 0
        self.total_test_case_count = 0
        for row in range(self.rowCount()):
            index = self.index(row, 0)  # Get the QModel Index of top level item
            tag = self.itemFromIndex(index)
            if tag.hasChildren():
                features = []
                for feature_row in range(tag.rowCount()):
                    feature = tag.child(feature_row, 0)  # Get the feature name
                    if feature.hasChildren():
                        testplans = []
                        for testplan_row in range(feature.rowCount()):
                            testplan = feature.child(testplan_row, 0)
                            self.total_test_plans += 1
                            logger.info(f'Total test plans : {self.total_test_plans}')
                            if testplan.hasChildren():
                                testcases = []
                                self.total_test_case_count += testplan.rowCount() # Updated total test cases count
                                for testcase_row in range(testplan.rowCount()):
                                    testcase_id = testplan.child(testcase_row, 0)
                                    if testcase_id.hasChildren():
                                        test_steps = self.__get_test_steps(testcase_id)
                                        self.__update_device_types(test_steps, device_types)
                                        testcases.append((testcase_id.text(), test_steps))
                                testplans.append((testplan.text(), testcases))
                        features.append((feature.text(), testplans))
                data.append((tag.text(), features))
        return data, device_types

    def move_item_up(self, item):
        """
        Move an item up in the execution queue.
        :param item: Item to move
        :return:
        """
        if not item:
            return None
        current_index = self.indexFromItem(item)
        parent_item = item.parent()
        if not parent_item:
            parent_item = self.invisibleRootItem()
        parent_index = self.indexFromItem(parent_item)

        row = item.row()
        if row <= 0:
            return  None # Can't move up if it's already at the top

        target_row = row - 1 # move one row up

        # Take the item out of the model
        item_row = parent_item.takeRow(row)

        # Insert the item at the new position (one row up)
        parent_item.insertRow(target_row, item_row)
        return self.index(target_row, current_index.column(),parent_index)

    def move_item_down(self, item):
        """
        Move an item down in the execution queue.
        :param item: Item to move
        :return:
        """
        if not item:
            return None
        current_index = self.indexFromItem(item)
        parent_item = item.parent()
        if not parent_item:
            parent_item = self.invisibleRootItem()
        parent_index = self.indexFromItem(parent_item)

        row = item.row()
        if row >= parent_item.rowCount() - 1:
            return None # Can't move down if it's already at the bottom
        target_row = row + 1  # move one row down

        # Take the item out of the model
        item_row = parent_item.takeRow(row)

        # Insert the item at the new position (one row down)
        parent_item.insertRow(row + 1, item_row)
        return self.index(target_row, current_index.column(), parent_index)

    def get_testcase_result(self, testplan_name, testcase_id):
        """
        Get execution result of the test case
        :param testplan_name: string representing the test plan file name
        :param testcase_id: string representing the test case id
        :return: Enum value representing Pass, Fail or NA
        """
        if "TestcaseID:" in testcase_id:
            testcase_id = testcase_id.replace("TestcaseID:", '').strip()
        testcase_results =  self.execution_results[testplan_name][testcase_id]
        testcase_result = Result.Ok.name
        for result in testcase_results.values():
            if result['result'] == Result.Passed.name:
                testcase_result = Result.Passed.name
            if result['result'] == Result.Ok.name:
                testcase_result = Result.Passed.name
            if result['result'] == Result.Failed.name:
                return Result.Failed.name
        return testcase_result

    def get_testplan_result(self, testplan_name):
        """
        Get execution result of the test plan
        :param testplan_name: string representing the test plan file name
        :return: Enum value representing Pass, Fail or NA
        """
        test_case_results = self.execution_results[testplan_name]
        testplan_result = Result.Ok.name
        for testcase_id in test_case_results:
            testcase_result = self.get_testcase_result(testplan_name, testcase_id)
            if testcase_result == Result.Failed.name:
                return Result.Failed.name
            if testcase_result == Result.Passed.name:
                testplan_result = Result.Passed.name
            if testcase_result == Result.Ok.name:
                testplan_result = Result.Passed.name
        return testplan_result

    def save_execution_result(self, tag_name, testplan_name, testcase_id, step_no, step_result, measured_value, comments, step_start_time, step_end_time):
        """
        Save test execution results
        :param tag_name: Test tag name
        :param testplan_name: Test plan file name string
        :param testcase_id: Test case id string
        :param step_no: Test step number
        :param step_result: Execution result for the test step
        :return:
        """
        testsuite_entry = self.execution_results.get(tag_name)
        if testsuite_entry:
            #testcase_result = testsuite_entry.get(testcase_id)
            testplan_result = testsuite_entry.get(testplan_name)
            if testplan_result:
                testcase_result = testplan_result.get(testcase_id)
                if testcase_result:
                    testcase_result.update({step_no:{"result":step_result, "measured_value":measured_value, "comments":comments,
                                                     "step_start_timestamp":step_start_time, "step_end_timestamp":step_end_time}})
                else:
                    testcase_result = {step_no:{"result":step_result, "measured_value":measured_value, "comments":comments,
                                                "step_start_timestamp":step_start_time, "step_end_timestamp":step_end_time}}
                    self.execution_results[tag_name][testplan_name][testcase_id] = testcase_result
            else:
                test_step_result = {step_no: {"result": step_result, "measured_value": measured_value, "comments": comments,
                                              "step_start_timestamp":step_start_time, "step_end_timestamp":step_end_time}}
                testcase_result = {testcase_id: test_step_result}
                self.execution_results[tag_name][testplan_name] = testcase_result

        else:
            test_step_result = {step_no:{"result":step_result, "measured_value":measured_value, "comments":comments,
                                         "step_start_timestamp":step_start_time, "step_end_timestamp":step_end_time}}
            testcase_result = {testcase_id:test_step_result}
            #self.execution_results[testplan_name] = {testcase_id:testcase_result}
            self.execution_results[tag_name] = {testplan_name: testcase_result}

    def fetch_tags_and_testplans_from_execution_tree(self):
        """
        Traverse the tree and extract tags and testplans from execution tree
        :return: list containing the test plans and tags
        """
        execution_data_list = []
        self.total_test_plans = 0
        for row in range(self.rowCount()):
            index = self.index(row, 0)  # Get the QModel Index of top level item
            tag = self.itemFromIndex(index)
            test_plan_list = []
            if tag.hasChildren():
                for feature_row in range(tag.rowCount()):
                    feature = tag.child(feature_row, 0)  # Get the feature name
                    if feature.hasChildren():
                        for testplan_row in range(feature.rowCount()):
                            testplan = feature.child(testplan_row, 0)
                            self.total_test_plans += 1
                            test_plan_list.append(testplan.text())
            execution_data_list.append((tag.text(), test_plan_list))
        return execution_data_list

