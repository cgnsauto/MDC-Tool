# Copyright (c) Capgemini. All rights reserved.
from pathlib import Path

import numpy as np
from PyInstruments.device import Device
from PySide6.QtCore import QObject, Signal

from common import Workspace, ExecutionStatus


class SignalManager(QObject):
    """
    SignalManager is the central class that defines and manages application-wide signals in a PyQt application.
    This class acts as a signal hub, allowing different components of the application to communicate
    without direct dependencies. By using a shared instance of SignalManager, signals can be emitted
    and received across multiple modules.
    """
    register_commands = Signal(str,str,list)
    register_device = Signal(Device)
    execution_status = Signal(ExecutionStatus)
    execution_thread_exited = Signal()
    execution_cycle_completed = Signal(int,int)
    push_items_to_execution_queue = Signal(Workspace,list, str)
    open_workspace = Signal(str, str)
    add_device = Signal(str,str,str)
    remove_device = Signal(str)
    report_file_selected = Signal(str)
    test_execution_started = Signal(int)
    test_execution_stopped = Signal()
    create_report = Signal(Workspace,str, str, str, str, float, float, list, dict)
    test_reports_generated = Signal()
    reset_test_execution_view = Signal()
    def __init__(self):
        super().__init__()

