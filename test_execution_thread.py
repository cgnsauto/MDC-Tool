# Copyright (c) Capgemini. All rights reserved.
import os
import threading
import re
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread

from command_dispatcher import CommandDispatcher
from common import Status, Result, ExecutionStatus
from logger import logger


class PlaceholderResolver:
    def __init__(self, command_results):
        self.command_results = command_results

    def replacer(self, match):
        try:
            step_number, key = match.groups()
            step_result = self.command_results.get(step_number)
            return str(step_result.get(key))
        except Exception as e:
            logger.critical(f"Exception Caught:{e}", exc_info=True)

    def resolve_placeholders(self, step_no, command_str):
        try:
            pattern = re.compile(r'\$(\d+):(\w+)')  # e.g. $1:key
            pattern2 = re.compile(r'\$(\w+)') # e.g. $key
            ret = re.sub(pattern, self.replacer, command_str)
            if ret == command_str:
                match = re.search(pattern2, command_str)
                if match:
                    key = match.group(1)
                    key = key.strip()
                    step_result = self.command_results.get(step_no)
                    ret = re.sub(pattern2, str(step_result.get(key)), command_str)
            if not ret:
                ret = command_str
            return ret
        except Exception as e:
            logger.critical(f"Exception Caught:{e}", exc_info=True)

class TestSuiteExecutionThread(QThread):
    """
    Thread class handling the execution of test plans
    """
    def __init__(self, test_tags, user_input, device_manager , service_manager, signal_manager, num_cycles, callback, workspace, test_artifacts_dir):
        super().__init__()
        self.signal_manager = signal_manager
        self.test_tags = test_tags

        self.user_input = user_input
        self.receive_status = callback
        self.stop_execution_event = threading.Event()
        self.pause_execution_event = threading.Event()
        self.num_cycles = num_cycles
        self.test_artifacts_dir = test_artifacts_dir
        self.workspace = workspace
        self.device_manager = device_manager
        self.service_manager = service_manager
        #self.command_dispatcher = CommandDispatcher(device_manager, service_manager, self.stop_execution_event, workspace.client_code, workspace.variant, workspace.subvariant)

    def __send_execution_status(self, cycle, tag_name, feature_name, testplan_name, test_id, testcase_status, testplan_status, step_no, step_status, testplan_progress, executed_testplan_count, step_result, testcase_result, testplan_result, comments, measured_value, test_step_start_time="0", test_step_end_time="0"):
        try:
            execution_status = ExecutionStatus(cycle=cycle, tag_name=tag_name,feature_name=feature_name,testplan_name=testplan_name, testcase_id=test_id, testcase_status=testcase_status, testplan_status=testplan_status,
                                               step_number=step_no, step_status=step_status, testplan_progress=testplan_progress, executed_testplan_count=executed_testplan_count, step_result=step_result, testcase_result=testcase_result,
                                               testplan_result=testplan_result, comments=comments, measured_value=measured_value, step_start_time=test_step_start_time, step_end_time=test_step_end_time)
            #self.receive_status(execution_status)
            self.signal_manager.execution_status.emit(execution_status)
        except Exception as e:
            logger.critical(f"Exception caught: {e}")

    def __extract_device_abbr(self, command_str):
            abbr = None
            if 'device' in command_str:
                start_index =  command_str.index('device') + len('device')
                end_index = command_str.index(';',start_index)
                abbr = command_str[start_index+1:end_index]
            return abbr

    def run(self):
        command_results = {}
        start_time = None
        device_abbr = []
        command_dispatcher = CommandDispatcher(self.device_manager, self.service_manager, self.stop_execution_event,
                                               self.workspace.client_code, self.workspace.variant, self.workspace.subvariant)
        try:
            for cycle in range(self.num_cycles):
                if self.stop_execution_event.is_set():
                    break
                logger.trace(f'---Cycle#: {cycle}----')
                cycle_dir = f'{self.test_artifacts_dir}/Cycle_{cycle}'
                os.makedirs(cycle_dir, exist_ok=True)
                executed_testplan_count = 0
                for tag_name, features in self.test_tags:
                    if self.stop_execution_event.is_set():
                        break
                    tag_dir = cycle_dir + '/' + tag_name
                    os.makedirs(tag_dir, exist_ok=True)
                    for feature_name, test_plans in features:
                        if self.stop_execution_event.is_set():
                            break
                        # Create directories for storing execution artifacts
                        feature_dir = tag_dir + '/' + feature_name
                        os.makedirs(feature_dir, exist_ok=True)
                        #executed_testplan_count = 0
                        for test_plan_name, testcases in test_plans:
                            testplan_result = Result.NA.name
                            device_abbr.clear()
                            # pause execution
                            while self.pause_execution_event.is_set():
                                pass
                            if self.stop_execution_event.is_set():
                                break
                            start_time = time.time()
                            testplan_dir = feature_dir + '/' + Path(
                                test_plan_name).stem  # TODO: Make it work for other file extensions
                            evidence_dir = testplan_dir + '/' + self.workspace.evidence_folder
                            report_dir = testplan_dir + '/' + self.workspace.report_folder
                            os.makedirs(testplan_dir, exist_ok=True)
                            os.makedirs(evidence_dir, exist_ok=True)
                            os.makedirs(report_dir, exist_ok=True)

                            logger.trace(f'Executing test Plan: {test_plan_name}')
                            # Get all the test steps for the test plan
                            total_testcase_count = len(testcases)
                            executed_testcase_count = 0
                            testplan_status = Status.Progress.name
                            for testcase_id, test_steps in testcases:
                                testcase_result = Result.NA.name
                                testcase_id = testcase_id.replace("TestcaseID:", '').strip()
                                # pause execution
                                while self.pause_execution_event.is_set():
                                    pass
                                if self.stop_execution_event.is_set():
                                    logger.trace(f'Execution stopped by user')
                                    break
                                testcase_evidence_dir = evidence_dir + "/" + testcase_id
                                os.makedirs(testcase_evidence_dir, exist_ok=True)
                                # clear the command results of previous test case
                                command_results.clear()

                                # Start executing commands for the test case
                                testcase_status = Status.Progress.name
                                testplan_progress = int((executed_testcase_count / total_testcase_count) * 100)
                                abort = False
                                total_step_count = len(test_steps)
                                executed_step_count = 0
                                for test_step in test_steps:
                                    test_step_start_epoch = time.time()
                                    test_step_start_time = datetime.fromtimestamp(test_step_start_epoch).strftime("%H:%M:%S.%f")
                                    step_number = test_step[0]
                                    command_str = test_step[2]
                                    validation_str = test_step[3]
                                    # pause execution
                                    while self.pause_execution_event.is_set():
                                        pass
                                    if self.stop_execution_event.is_set():
                                        logger.trace(f'Execution stopped by user')
                                        break

                                    # Abort execution of remaining test steps if a test step fails for a test case
                                    if abort:
                                        executed_step_count += 1
                                        if executed_step_count == total_step_count:
                                            # Test case execution complete
                                            testcase_status = Status.Complete.name
                                            executed_testcase_count += 1
                                            testplan_progress = int((executed_testcase_count / total_testcase_count) * 100)
                                            if executed_testcase_count == total_testcase_count:
                                                # Test plan execution finished
                                                testplan_status = Status.Complete.name
                                                executed_testplan_count += 1
                                        test_step_end_epoch = time.time()
                                        test_step_end_time = datetime.fromtimestamp(test_step_end_epoch).strftime(
                                            "%H:%M:%S.%f")

                                        self.__send_execution_status(cycle,tag_name, feature_name, test_plan_name,
                                                                     testcase_id, testcase_status, testplan_status,
                                                                     step_number, Status.Skipped.name,
                                                                     testplan_progress,
                                                                     executed_testplan_count, Result.Aborted.name,
                                                                     testcase_result, testplan_result, 'Ok', 'NA', test_step_start_time, test_step_end_time)
                                        continue

                                    logger.info(f"Sending in progress testcase_id {testcase_id} step_no: {step_number}")
                                    self.__send_execution_status(cycle,tag_name, feature_name, test_plan_name,
                                                                 testcase_id, testcase_status, testplan_status,
                                                                 step_number, Status.Progress.name,
                                                                 testplan_progress, executed_testplan_count, Result.NA.name, testcase_result, testplan_result,'NA', "NA",
                                                                 test_step_start_time)
                                    step_result = Result.Passed.name
                                    step_status = Status.Complete.name
                                    comments = 'Ok'
                                    measured_value = 'NA'
                                    if '<' in command_str and '>' in command_str:
                                        abbr = self.__extract_device_abbr(command_str)
                                        if abbr and abbr not in device_abbr:
                                            device_abbr.append(abbr)
                                        logger.trace(f'Executing {testcase_id}-{step_number}: {command_str}')

                                        # Replace any variables with actual values
                                        resolved_cmd = PlaceholderResolver(command_results).resolve_placeholders(step_number, command_str)

                                        # Dispatch test commands
                                        logger.info(resolved_cmd)
                                        result = command_dispatcher.dispatch(resolved_cmd,save_dir=testcase_evidence_dir,
                                                                                  test_identifier=step_number)
                                        command_results[step_number] = result
                                        logger.info(command_results)

                                        # Validate result
                                        if '<' in validation_str and '>' in validation_str:
                                            logger.trace(f'Executing test step validation command: {validation_str}')
                                            resolved_validation = PlaceholderResolver(command_results).resolve_placeholders(step_number, validation_str)
                                            logger.trace(f'Resolved validation command : {resolved_validation}')
                                            validation_result = None
                                            # Dispatch validation command
                                            if resolved_validation:
                                                validation_result = command_dispatcher.dispatch(resolved_validation)
                                            else:
                                                validation_result = command_dispatcher.dispatch(validation_str)

                                            if not validation_result.get('success'):
                                                step_result = Result.Failed.name
                                                testcase_result = Result.Failed.name
                                                testplan_result = Result.Failed.name
                                                abort = True
                                            comments = validation_result.get('reason')
                                            measured_value = validation_result.get("measured_value")
                                            logger.trace(f'{testcase_id}-{step_number} validation status: {step_result}')
                                        else: # No validation command present for test step
                                            step_result = Result.Ok.name
                                    else: # No command present for test step
                                        step_result = Result.Ok.name
                                    logger.info(f'Finished Executing test step:{step_number}')
                                    test_step_end_epoch = time.time()
                                    test_step_end_time = datetime.fromtimestamp(test_step_end_epoch).strftime(
                                        "%H:%M:%S.%f")
                                    executed_step_count += 1
                                    if executed_step_count == total_step_count:
                                        # Test case execution complete
                                        logger.trace(f'Finished Executing test case:{testcase_id}')
                                        #command_dispatcher.cleanup_can_tasks()
                                        testcase_status = Status.Complete.name
                                        if testcase_result != Result.Failed.name:
                                            testcase_result = Result.Passed.name
                                        executed_testcase_count += 1
                                        testplan_progress = int((executed_testcase_count / total_testcase_count) * 100)
                                        if executed_testcase_count == total_testcase_count:
                                            # Test plan execution finished
                                            logger.trace(f'Finished Executing test plan: {test_plan_name}')
                                            command_dispatcher.cleanup_can_tasks()
                                            testplan_status = Status.Complete.name
                                            if testplan_result != Result.Failed.name:
                                                testplan_result = Result.Passed.name
                                            executed_testplan_count += 1
                                    self.__send_execution_status(cycle,tag_name, feature_name, test_plan_name,
                                                                 testcase_id, testcase_status, testplan_status,
                                                                 step_number, step_status, testplan_progress,
                                                                 executed_testplan_count, step_result, testcase_result,
                                                                 testplan_result, comments,measured_value, test_step_start_time, test_step_end_time)
                            if not self.stop_execution_event.is_set():
                                end_time = time.time()
                                self.signal_manager.create_report.emit(self.workspace, test_plan_name, report_dir,
                                                                       evidence_dir, tag_name, start_time, end_time,
                                                                       device_abbr, self.user_input)
                if self.num_cycles > 1 and not self.stop_execution_event.is_set():
                    # send a loop cycle complete signal
                    self.signal_manager.execution_cycle_completed.emit(cycle, self.num_cycles)
        except ValueError as e:
            logger.critical(f"Exception Caught:{e}", exc_info=True)
        except RuntimeError as e:
            logger.critical(f"Exception Caught:{e}", exc_info=True)
        except Exception as e:
            logger.critical(f"Exception Caught:{e}", exc_info=True)
        finally:
            logger.info("Exiting Test Suite Execution thread.")
            self.stop_execution_event.clear()
            # Send execution thread exit signal to view model
            self.signal_manager.execution_thread_exited.emit()

    def stop(self):
        self.stop_execution_event.set()
        self.pause_execution_event.clear()

    def pause_execution(self):
        self.pause_execution_event.set()

    def resume_execution(self):
        self.pause_execution_event.clear()

