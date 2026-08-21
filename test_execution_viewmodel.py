# Copyright (c) Capgemini. All rights reserved.
import copy
import logging
import os
import queue
import time

from concurrent.futures.process import ProcessPoolExecutor
from datetime import datetime, timedelta

from PyConfigManager.report_config import ReportConfig
from PyConfigManager.variant_config import VariantConfig
import cv2
from PyInstruments.types import DeviceType, get_device_class, get_device_type
from PyReportGenerator.report_manager import generate_test_reports
from PySide6.QtCore import QObject, Signal, QModelIndex, Qt, QDateTime, QTimer, QUrl
from PySide6.QtGui import QStandardItem, QBrush, QColor, QImage, QDesktopServices
from logger import logger, TraceLogHandler, TraceLogLevelFilter, TRACE_LOG_LEVEL
from test_execution_thread import TestSuiteExecutionThread, Result, Status

class TestExecutionViewModel(QObject):
    """
    The ViewModel connects the view and the model, managing the business logic and data flow.
    """
    set_current_index = Signal(QModelIndex)
    start_animation = Signal(QStandardItem)
    stop_animation = Signal(QStandardItem)
    highlight_and_expand_testplan = Signal(QStandardItem, bool)
    highlight_and_expand_testcase = Signal(QStandardItem, bool)
    unhighlight_tree_items = Signal()
    test_progress_updated = Signal(int)
    overall_progress_updated = Signal(int)
    reset_progress = Signal()
    update_execution_data_labels = Signal(int,int,int,int)
    append_log = Signal(str)
    display_image = Signal(QImage)
    show_start_execution_dialog = Signal(bool,str,str,str)
    close_execution_dialog = Signal()
    close_reset_dialog = Signal()
    execution_dialog_error = Signal(str)
    reset_schedule_error = Signal(str)
    toggle_execution_menu= Signal(bool)
    toggle_pause_button = Signal(bool)
    tree_view_cleared = Signal()
    tag_not_found = Signal(str)
    device_not_found = Signal(list)
    show_schedule_indicator = Signal(bool, QDateTime)
    refresh_tree_view = Signal()

    def __init__(self, model, service_manager, signal_manager, device_manager):
        super().__init__()
        self.model = model
        self.signal_manager = signal_manager
        self.service_manager = service_manager
        self.device_manager = device_manager
        self.step_logs = []
        self.selected_items = [] # List storing the item indexes selected from the list view
        self.execution_thread = None
        self.execution_paused = False
        self.execution_cycle = 1 # Cycle count storing number of loops
        self.fail_count = 0 # Total test case fail count
        self.pass_count = 0 # Total test case pass count
        self.test_artifacts_dir = None
        self.trace_log_handler = None
        self._scheduled_execution_data = []
        self.timer = None
        self.subvariant_config_path = None
        self.model.setHorizontalHeaderLabels(
            ['Test Step', 'Test Procedure', 'Input Commands', 'Output Commands', 'Status', 'Result'])
        self.connect_slots_to_signals()
        self.executor = ProcessPoolExecutor(max_workers=2)
        self.report_futures = {}

    def connect_slots_to_signals(self):
        self.signal_manager.execution_status.connect(self.on_receive_execution_status)
        self.signal_manager.execution_thread_exited.connect(self.on_execution_thread_exit)
        self.signal_manager.execution_cycle_completed.connect(self.on_execution_cycle_completed)
        self.signal_manager.push_items_to_execution_queue.connect(self.on_add_items_to_tree)
        self.signal_manager.reset_test_execution_view.connect(lambda : self.on_remove_all_button_clicked())
        self.signal_manager.create_report.connect(self.on_create_report)


    def __clear_column(self, column):
        try:
            for top_level_row in range(self.model.rowCount()):
                tag_item = self.model.item(top_level_row, 0)
                for row in range(tag_item.rowCount()):
                    feature_item = tag_item.child(row)
                    for row_ in range(feature_item.rowCount()):
                        test_plan_item = feature_item.child(row_)
                        test_plan_column_item = feature_item.child(row_, column)
                        if test_plan_column_item:
                            test_plan_column_item.setText("")
                            test_plan_column_item.setBackground(QBrush(QColor("white")))

                        if test_plan_item.hasChildren():
                            for testcase_row in range(test_plan_item.rowCount()):
                                testcase_column_item = test_plan_item.child(testcase_row, column)
                                if testcase_column_item:
                                    testcase_column_item.setText("")
                                    testcase_column_item.setBackground(QBrush(QColor("white")))

                                testcase_item = test_plan_item.child(testcase_row, 0)  # Get the test case Id
                                if testcase_item.hasChildren():
                                    for test_step_row in range(testcase_item.rowCount()):
                                        test_step_column_item = testcase_item.child(test_step_row, column)
                                        if test_step_column_item:
                                            test_step_column_item.setText("")
                                            test_step_column_item.setBackground(QBrush(QColor("white")))
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def __filter_unconnected_devices(self, devices):
        filtered_device_types = []
        for abbr in devices:
            device_type = get_device_type(abbr)
            if not self.device_manager.is_device_connected(device_type):
                filtered_device_types.append(get_device_class(device_type))
        return filtered_device_types

    def __start_execution(self, user_input, num_cycles):
        test_plans, devices = self.model.fetch_test_data_for_execution()
        if test_plans:
            # Verify if devices needed for execution are connected
            filtered_device_types = self.__filter_unconnected_devices(devices)
            if filtered_device_types:
                # Show Devices not found error pop up
                self.device_not_found.emit(filtered_device_types)
                return

            # Create directory for saving execution artifacts
            time_stamp = datetime.now().strftime('%Y-%m-%d_%H.%M.%S')
            testresult_folder = self.model.workspace.workspace_path + '/' + self.model.workspace.testresult_folder
            self.test_artifacts_dir = testresult_folder + '/' + time_stamp
            os.makedirs(self.test_artifacts_dir, exist_ok=True)

            status_column = self.model.get_column_index("Status")
            result_column = self.model.get_column_index("Result")
            self.__clear_column(status_column)  # Clear status column
            self.__clear_column(result_column)  # clear result column
            self.reset_progress.emit() # Reset overall progress bar
            self.model.execution_results.clear()

            # Add handler for appending execution logs to the step log area
            file_path = self.test_artifacts_dir + '/'+ 'trace.log'
            self.trace_log_handler = TraceLogHandler(self.append_log, file_path, TRACE_LOG_LEVEL)
            self.trace_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self.trace_log_handler.addFilter(TraceLogLevelFilter(TRACE_LOG_LEVEL))
            logger.addHandler(self.trace_log_handler)

            # Reset execution data counters
            self.execution_cycle = 0
            self.fail_count = 0
            self.pass_count = 0

            # start capturing video
            camera_device = self.device_manager.get_device(DeviceType.Camera.value)
            if camera_device:
                camera_device.start_video_capture(self.on_receive_frame)
            self.signal_manager.test_execution_started.emit(num_cycles)
            #self.update_execution_data_labels.emit(self.execution_cycle,self.fail_count,self.pass_count,self.model.total_test_case_count)
            logger.trace('Test Execution started')
            self.execution_thread = TestSuiteExecutionThread(test_plans, user_input, self.device_manager, self.service_manager, self.signal_manager, num_cycles,
                                                             self.on_receive_execution_status,copy.deepcopy(self.model.workspace), self.test_artifacts_dir)
            self.execution_thread.start()

    def _delete_schedule(self):
        if self.timer:
            self.timer.stop()
            self.timer = None
            self._scheduled_execution_data.clear()
            return True
        return False

    def _remove_item(self, item):
        parent = item.parent()
        if parent:
            logger.info(f'parent : {parent.text()}')
            parent.removeRow(item.row())
            # Remove parent node if all children are removed
            if parent.rowCount() == 0:
                logger.info(f'Removing parent : {parent.text()}')
                self._remove_item(parent)
        else:
            self.model.removeRow(item.row())

    def on_start_execution_clicked(self):
        client_code = self.model.workspace.client_code
        variant = self.model.workspace.variant
        subvariant = self.model.workspace.subvariant
        self.show_start_execution_dialog.emit(False,client_code,variant,subvariant)

    def on_schedule_execution_clicked(self):
        if not self._scheduled_execution_data:
            client_code = self.model.workspace.client_code
            variant = self.model.workspace.variant
            subvariant = self.model.workspace.subvariant
            self.show_start_execution_dialog.emit(True, client_code,variant,subvariant)
        else:
            error = f'Execution already scheduled at {self._scheduled_execution_data[0][0]}'
            self.execution_dialog_error.emit(error)

    def on_add_items_to_tree(self, workspace , items, tag):
        try:
            ret = self.model.add_items_to_execution_tree(workspace, items, tag)
            if ret:
                self.toggle_execution_menu.emit(True)
            else:
                self.tag_not_found.emit(tag)

        except Exception as e:
            logger.critical(f'Failed to add items to execution tree: {e}')

    def on_move_up_button_click(self):
        """
        Move an item up in the execution queue.
        :return: None
        """
        try:
            if self.selected_items:
                item = self.selected_items[0]
                selected_index = self.model.move_item_up(item)
                if selected_index:
                    self.set_current_index.emit(selected_index)
        except Exception as e:
            logger.critical(f'Failed to move item up : {e}')

    def on_move_down_button_click(self):
        """
        Move an item down in the execution queue.
        :return: None
        """
        try:
            if self.selected_items:
                item = self.selected_items[0]
                selected_index = self.model.move_item_down(item)
                if selected_index:
                    self.set_current_index.emit(selected_index)
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def on_tree_item_selection_changed(self, selected, deselected):
        try:
            selected_indices = selected.indexes()
            deselected_indices = deselected.indexes()
            if selected_indices:
                select_item = self.model.itemFromIndex(selected_indices[0])
                if select_item.rowCount() != 0 and 'TestcaseID' not in select_item.text(): # Select only non-leaf items
                    self.selected_items.append(select_item)
            if deselected_indices:
                deselect_item = self.model.itemFromIndex(deselected_indices[0])
                if deselect_item in self.selected_items:
                    #self.selected_items.remove(deselect_item)
                    self.selected_items.remove(deselect_item)
        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def on_stop_button_click(self):
        try:
            if self.execution_thread:
                self.execution_thread.stop()
        except Exception as e:
            logger.error(f'Failed to stop execution : {e}')

    def on_pause_button_click(self):
        if self.execution_paused:
            if self.execution_thread:
                if self.execution_thread.isRunning():
                    logger.trace('Test Execution resumed')
                    self.execution_thread.resume_execution()
                    self.execution_paused = False
                    self.toggle_pause_button.emit(self.execution_paused)
        else:
            if self.execution_thread:
                if self.execution_thread.isRunning():
                    logger.trace('Test Execution paused')
                    self.execution_thread.pause_execution()
                    self.execution_paused = True
                    self.toggle_pause_button.emit(self.execution_paused)

    def on_remove_all_button_clicked(self):
        self.selected_items.clear()
        self.model.clear()
        self.model.setHorizontalHeaderLabels(
            ['Test Step', 'Test Procedure', 'Input Commands', 'Output Commands', 'Status', 'Result'])
        self._delete_schedule()  # delete any schedule test executions
        self.tree_view_cleared.emit()

    def on_remove_button_clicked(self):
        try:
            if self.selected_items:
                item = self.selected_items[0]
                logger.info(f'remove:{item.text()}')
                self._remove_item(item)
                if self.model.rowCount() == 0:  # Tree is empty
                    self._delete_schedule()  # delete any schedule test executions
                    self.tree_view_cleared.emit()
        except Exception as e:
            logger.critical(f'failed to remove item: {e}')

    def on_receive_execution_status(self, execution_status):
        testcase_id = f"TestcaseID: {execution_status.testcase_id}"
        status_column = self.model.get_column_index("Status")
        result_column = self.model.get_column_index("Result")
        step_column = self.model.get_column_index("Test Step")
        tag_item = self.model.find_item_by_text(execution_status.tag_name)
        feature_item = self.model.find_item_by_text(execution_status.feature_name, tag_item)
        testplan_item = self.model.find_item_by_text(execution_status.testplan_name, feature_item)
        testcase_item = self.model.find_item_by_text(testcase_id, testplan_item)
        step_row = self.model.find_row_by_text(execution_status.step_number,
                                               step_column, testcase_item)
        status_item = testcase_item.child(step_row, status_column)

        # Toggle highlight
        self.highlight_and_expand_testplan.emit(testplan_item,True)
        self.highlight_and_expand_testcase.emit(testcase_item, True)

        if execution_status.step_status == Status.Progress.name:
            self.start_animation.emit(status_item)
        else:
            if execution_status.step_status == Status.Complete.name:
                self.stop_animation.emit(status_item)
            status_item.setText(execution_status.step_status)
            status_item.setBackground(QBrush(QColor(213, 241, 126)))
            self.model.save_execution_result(execution_status.tag_name, execution_status.testplan_name, execution_status.testcase_id,
                                             execution_status.step_number, execution_status.step_result,
                                             execution_status.measured_value,
                                             execution_status.comments, execution_status.step_start_time, execution_status.step_end_time)
            if execution_status.testcase_status == Status.Complete.name:
                self.highlight_and_expand_testcase.emit(testcase_item, False)

                # Update the testcase result in the model
                testcase_row = self.model.find_row_by_text(testcase_item.text(), step_column, testplan_item)
                testcase_result_item = testplan_item.child(testcase_row, result_column)
                if execution_status.testcase_result == Result.Passed.name:
                    brush = QBrush(QColor(213, 241, 126))
                    self.pass_count += 1
                else:
                    brush = QBrush(QColor(255, 115, 115))
                    self.fail_count += 1
                testcase_result_item.setText(execution_status.testcase_result)
                testcase_result_item.setBackground(brush)
                # Update execution data labels
                self.update_execution_data_labels.emit(execution_status.cycle+1, self.fail_count, self.pass_count,
                                                       self.model.total_test_case_count)
                self.test_progress_updated.emit(execution_status.testplan_progress)

                # Update the test plan result in the model
            if execution_status.testplan_status == Status.Complete.name:
                self.highlight_and_expand_testplan.emit(testplan_item, False)
                testplan_row = self.model.find_row_by_text(testplan_item.text(), step_column, feature_item)
                testplan_result_item = feature_item.child(testplan_row, result_column)
                testplan_result_item.setText(execution_status.testplan_result)
                if execution_status.testplan_result == Result.Passed.name:
                    brush = QBrush(QColor(213, 241, 126))
                else:
                    brush = QBrush(QColor(244, 121, 128))
                testplan_result_item.setBackground(brush)
                overall_test_progress = int((execution_status.executed_testplan_count / self.model.total_test_plans) * 100)
                self.overall_progress_updated.emit(overall_test_progress)

    def on_execution_thread_exit(self):
        """
        Slot to handle execution thread exit signal emitted from execution thread when it exits
        :return: None
        """
        try:
            camera_device = self.device_manager.get_device(DeviceType.Camera.value)
            if camera_device:
                camera_device.stop_video_capture()
            self.signal_manager.test_execution_stopped.emit()
            if self.execution_paused:
                self.execution_paused = False
                self.toggle_pause_button.emit(self.execution_paused)

            self.execution_thread = None
            self.trace_log_handler.close()
            logger.removeHandler(self.trace_log_handler)
            del self.trace_log_handler
            self.trace_log_handler = None

            # this is needed to unhighlight the testplan and test case if execution is stopped
            # by the user
            self.unhighlight_tree_items.emit()

        except Exception as e:
            logger.critical(f"Exception Caught: {e}")

    def on_execution_cycle_completed(self, cycle, num_cycles):
        """
        Slot to handle execution_cycle_completed completed signal emitted from execution thread
        when an execution cycle is completed during loop execution
        :return: None
        """
        self.execution_cycle = cycle+1

        # Reset execution data counters
        self.fail_count = 0
        self.pass_count = 0
        # In case of loop execution reset the UI only when it is not the last loop cycle
        if cycle != num_cycles-1:
            self.reset_progress.emit()
            status_column = self.model.get_column_index("Status")
            result_column = self.model.get_column_index("Result")
            self.__clear_column(status_column)
            self.__clear_column(result_column)
            self.model.execution_results.clear()

    def on_receive_frame(self, frame):
        # Convert the frame from BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert to QImage
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.display_image.emit(image)

    def on_start_execution(self, user_input, num_cycles):
        try:
            self.close_execution_dialog.emit()
            self.__start_execution(user_input,num_cycles)
        except ValueError as e:
            self.execution_dialog_error.emit(str(e))
        except Exception as e:
            logger.critical(f'Failed to start execution: {e}')
            self.execution_dialog_error.emit(str(e))

    def on_schedule_execution(self, user_input, date_time, num_cycles):
        """
        Method to schedule testing when valid Date and time is set from Scheduler Dialog
        """
        try:
            datetime_str = date_time.toString("yyyy-MM-dd HH:mm:ss")
            self._scheduled_execution_data.append((datetime_str,user_input,num_cycles))
            event_time = date_time.toSecsSinceEpoch()
            current_time = QDateTime.currentDateTime().toSecsSinceEpoch()
            delay = (event_time - current_time) * 1000 #Converting delay in milliseconds
            if delay > 0:
                self.timer = QTimer()
                self.timer.setSingleShot(True)
                self.timer.timeout.connect(self.on_timer_timeout)
                self.timer.start(delay)
                self.close_execution_dialog.emit()
                self.show_schedule_indicator.emit(True, date_time)
            else:
                raise ValueError('Invalid date time selected. Scheduled time should be greater than current time.')
        except ValueError as e:
            self.execution_dialog_error.emit(str(e))
        except Exception as e:
            logger.critical(f'Failed to Schedule execution: {e}', exc_info=True)
            self.execution_dialog_error.emit(str(e))

    def on_reset_schedule_button_clicked(self, date_time):
        if self.timer:
            self.timer.stop()
            datetime_str = date_time.toString("yyyy-MM-dd HH:mm:ss")

            # Reset date time string in stored scheduled execution data
            item = self._scheduled_execution_data.pop(0)
            updated_item = list(item)
            updated_item[0] = datetime_str
            updated_item = tuple(updated_item)
            self._scheduled_execution_data.append(updated_item)

            event_time = date_time.toSecsSinceEpoch()
            current_time = QDateTime.currentDateTime().toSecsSinceEpoch()
            delay = (event_time - current_time) * 1000  # Converting delay in milliseconds
            if delay > 0:
                self.timer = QTimer()
                self.timer.setSingleShot(True)
                self.timer.timeout.connect(self.on_timer_timeout)
                self.timer.start(delay)
                self.show_schedule_indicator.emit(True,date_time)
                self.close_reset_dialog.emit()
            else:
                self.reset_schedule_error.emit('Invalid date time selected. Scheduled time should be greater than current time.')
        else:
            logger.error('No Scheduled execution found.')

    def on_delete_schedule(self):
        ret = self._delete_schedule()
        if not ret:
            logger.error('No Scheduled execution found.')
        else:
            self.show_schedule_indicator.emit(False,'')

    def on_timer_timeout(self):
        try:
            execution_data = self._scheduled_execution_data[0]
            user_input = copy.deepcopy(execution_data[1])
            num_cycles = execution_data[2]
            if self.execution_thread and self.execution_thread.isRunning():
                logger.error('Failed to start scheduled execution.Execution already in progress.')
            else:
                self.__start_execution(user_input, num_cycles)
        except Exception as e:
            logger.critical(f'Failed to start execution : {e}')
        finally:
            self.timer = None
            self._scheduled_execution_data.clear()
            self.show_schedule_indicator.emit(False, '')

    def on_open_log_button_clicked(self):
        if self.test_artifacts_dir:
            url = QUrl.fromLocalFile(os.path.abspath(self.test_artifacts_dir))
            QDesktopServices.openUrl(url)

    def close_document(self):
        self.executor.shutdown(True)
        if self.execution_thread:
            if self.execution_thread.isRunning():
                self.execution_thread.stop()
                self.execution_thread.wait()

    def handle_report_generation(self, future, test_plan):
        logger.trace(f"Test Reports generated for test plan: {test_plan}")
        try:
            report_path = future.result()
            self.signal_manager.test_reports_generated.emit()
        except Exception as e:
            logger.critical(f'Failed to generate HTML report for test id {test_plan}:{e}', exc_info=True)

    def on_create_report(self, workspace, test_plan_name:str, report_dir:str, evidence_dir:str, test_tag:str, start_time:float, end_time:float, devices:list, user_input:dict):
        test_plan_abs_path = os.path.join(workspace.workspace_path, workspace.testsuite_folder, test_plan_name)
        # create a copy as self.model.execution_results may get cleared
        variant_info = VariantConfig.variant_info(workspace.client_code, workspace.variant, workspace.subvariant)
        device_ids = []
        for abbr in devices:
            device_id = self.device_manager.get_device_id(abbr)
            device_ids.append(device_id)
        execution_results = copy.deepcopy(self.model.execution_results[test_tag][test_plan_name])
        execution_time = end_time - start_time
        execution_time = timedelta(seconds=execution_time)

        total_seconds = execution_time.total_seconds()
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Format with milliseconds (3 digits)
        formatted_time = f"{int(hours):01}:{int(minutes):02}:{int(seconds):02}.{int((seconds % 1) * 1000):03}"
        report_config = ReportConfig.report_generation_config(workspace.client_code, workspace.variant, workspace.subvariant)

        # Wait for all tasks to complete
        logger.trace(f"Generating Test Reports for test plan: {test_plan_abs_path}")
        future = self.executor.submit(generate_test_reports, test_tag, workspace.client_code, workspace.variant, workspace.subvariant,
                                      variant_info, device_ids, report_config, str(test_plan_abs_path), report_dir, evidence_dir, user_input, execution_results, formatted_time)
        future.add_done_callback(lambda f: self.handle_report_generation(f, test_plan_abs_path))

    def on_refresh_button_click(self):
        try:
            execution_data_list = self.model.fetch_tags_and_testplans_from_execution_tree()
            if execution_data_list:
                self.selected_items.clear()
                self.model.clear()
                self.model.setHorizontalHeaderLabels(
                    ['Test Step', 'Test Procedure', 'Input Commands', 'Output Commands', 'Status', 'Result'])
                for tag, test_plans in execution_data_list:
                    test_plan_path_list = []
                    for plan in test_plans:
                        test_plan_path_list.append(self.model.workspace.workspace_path + "/" + self.model.workspace.testsuite_folder + "/" + plan)
                    ret = self.model.add_items_to_execution_tree(self.model.workspace, test_plan_path_list, tag)
                    if ret:
                        self.toggle_execution_menu.emit(True)
                self.refresh_tree_view.emit()

        except Exception as e:
            logger.critical(f'Failed to add items to execution tree: {e}')
