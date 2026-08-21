import ast
import json
import math
import os
import queue
import re
import threading
import time
from datetime import datetime
from sys import exc_info

import cv2
from PyConfigManager.switch_map_config import SwitchMapConfig
from PyInstruments.types import get_device_type, DeviceType
#from joblib.testing import param
from openpyxl.styles.builtins import total, output

from logger import logger
import utils
import can
import math
import threading

class CanTask:
    def __init__(self, device, channel):
        self.device = device
        self.channel = channel
        self.tasks = {}      # msg_id -> cyclic TX task
        self.messages = {}   # msg_id -> dbc message object
        self.signals = {}    # msg_id -> {signal_name: value}
        self.active_non_blocking_threads = {}


    def _create_msg_data(self, msg_id, signal_name, signal_value):
        # Ensure message and signals dict exist
        if msg_id not in self.messages:
            self.messages[msg_id] = self.device.get_message_from_db(msg_id)
            self.signals[msg_id] = {sig.name: 0 for sig in self.messages[msg_id].signals}

        # Update signal dictionary
        self.signals[msg_id][signal_name] = signal_value
        data = list(self.messages[msg_id].encode(self.signals[msg_id]))
        # Apply alive counter and checksum updates
        #self.device.update_alive_status(data)
        #self.device.update_checksum(msg_id, data)
        return data

    def send_periodic_tx(self, msg_id, signal_name, signal_value, periodicity):
        data = self._create_msg_data(msg_id, signal_name, signal_value)
        self.device.send_periodic(msg_id, data, periodicity)
        logger.info(f"Can message corresponding to {signal_name}:{signal_value} sent")

    def increment_tx_loop(self, msg_id, signal_name, value, max_value, increment,
                          increment_period, rollover_value, signal_factor,
                          message_periodicity, stop_event):
        """
        Increment signal value periodically while cyclic TX is active.
        Preserves rollover and repetition logic from your original design.
        """
        #self.periods[msg_id] = message_periodicity
        max_value_rep = math.floor(max_value / rollover_value)
        max_rollover_value = (max_value % rollover_value) - (max_value_rep * signal_factor)
        #max_rollover_value = (max_value % rollover_value)
        repetitions = math.ceil(max_value / rollover_value)
        total_value = value
        count_interval = 0
        for count in range(repetitions):
            # Reset signal value after each repetition
            if count == 0:
                signal_value_rep = math.floor(value / rollover_value)
                signal_value = (value % rollover_value) - (signal_value_rep * signal_factor)
                #signal_value = (value % rollover_value)
            else:
                signal_value = signal_value - (rollover_value + signal_factor)
                # = signal_value - (rollover_value)
            while signal_value <= rollover_value and not stop_event.is_set():
                # Build CAN payload with alive + checksum
                data = self._create_msg_data(msg_id, signal_name, signal_value)
                self.device.send_periodic(msg_id, data, message_periodicity, is_incremental=True)
                count_interval+=1
                logger.info(f"Can message corresponding to {signal_name}:{signal_value} sent")
                #logger.info(f"Can message corresponding to {signal_name}:{signal_value} sent")
                # Wait until next increment (or break early if stop_event set)
                if increment_period == message_periodicity:
                    if stop_event.wait(0.0005):
                        logger.info("Woke up early from increment tx loop due to stop event!")
                        break
                else:
                    if signal_value != max_rollover_value:
                        if stop_event.wait(increment_period):
                            logger.info("Woke up early from increment tx loop due to stop event!")
                            break
                    else:
                        logger.info("Didn't wait for last iteration")

                # Increment value
                signal_value += increment
                decimal_places = str(increment)[::-1].find('.')
                signal_value = round(signal_value, decimal_places)
                total_value += increment
                total_value = round(total_value, decimal_places)

                if total_value > max_value:
                    break

            if total_value > max_value:
                break

        self.device.wait_until_incremental_queue_finishes(msg_id)
        logger.info("Exiting Loop/Thread")
        if msg_id in self.active_non_blocking_threads:
            del self.active_non_blocking_threads[msg_id]

    def stop(self, msg_id: str):
        """
        Stop a periodic transmission for a specific msg_id.
        Delegates to device.stop_periodic().
        """
        try:
            self.device.stop_periodic(msg_id)
            logger.info(f"Stopped cyclic TX for msg_id: {msg_id}")
        except Exception as e:
            logger.error(f"Error stopping cyclic TX for msg_id {msg_id}: {e}")

    def stop_all(self):
        """
        Stop all periodic transmissions.
        Delegates to device.stop_all_periodic().
        """
        try:
            self.device.stop_all_periodic()
            self.device.last_msg_dict.clear()
            logger.info("Stopped all cyclic TX tasks.")
        except Exception as e:
            logger.error(f"Error stopping all cyclic TX tasks: {e}")


class CommandDispatcher:
    def __init__(self, device_manager, service_manager, stop_event, client_code, variant, sub_variant = None):
        self.device_manager = device_manager
        self.service_manager = service_manager
        self.stop_event = stop_event
        self.client_code = client_code
        self.variant = variant
        self.sub_variant = sub_variant
        target_variant = variant
        if sub_variant:
            target_variant = f'{variant}_{sub_variant}'
        self.model_path = f'resources/models/ml/object_detection/{client_code}/{target_variant}/yolox_s_objects_640x640.pth'
        self.class_file_path = f'resources/models/ml/object_detection/{client_code}/{target_variant}/classes.txt'
        self.can_tasks = {}
        self.active_non_blocking_threads = {}

    def __del__(self):
        logger.info('Destroying command dispatcher')
        for task in self.can_tasks.values():
            task.stop_all()

    def _get_class_names(self):
        with open(self.class_file_path, "r") as f:
            class_names = [line.strip() for line in f if line.strip()]
        return class_names

    def _split_pairs(self, command_args):
        parts=[]
        current=[]
        depth=0
        in_single_quote = False
        in_double_quote = False

        for ch in command_args:
            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote

            if not in_single_quote and not in_double_quote:
                if ch =='[':
                    depth+=1
                elif ch ==']':
                    depth-=1

            if ch == ';' and depth == 0 and not in_double_quote and not in_single_quote:
                parts.append("".join(current).strip())
                current= []
            else:
                current.append(ch)
        if current:
            parts.append(''.join(current).strip())
        return parts

    def _parse_command(self, raw_command: str):
        try:
            command_name, command_args = raw_command.split('<')
            command_name = command_name.strip()
            command_args = command_args.split('>')[0].strip()
            commands_pair = self._split_pairs(command_args)
            params = {}
            for pair in commands_pair:
                if pair.strip():
                    key,value = pair.split('=', 1)
                    params[key] = value
            return command_name,{k.strip(): v.strip() for k, v in params.items()}
        except Exception as e:
            msg = f'Error parsing command {raw_command}: {e}'
            logger.trace(msg)
            raise ValueError(msg)

    def _handle_exception(self, cmd_name, cmd_params, e):
        service_name = None
        if cmd_name == 'execute':
            service_name = cmd_params.get('service')

        if cmd_name == 'write':
            return {"success": False, "reason": str(e), "measured_value": 'NA'}

        if service_name == 'validate':
            return {"success": False, "reason": str(e), "measured_value": 'NA'}
        else:
            output = cmd_params.get('output')
            cmd_result = {}
            if output:
                if ',' in output:
                    output = output.split(",")
                    for item in output:
                        cmd_result.update({item: str(e)})
                else:
                    cmd_result[output] = str(e)
                return cmd_result
            else:
                return None

    # Manager method
    def _can_send_periodic(self, device, msg_id, signal_name, signal_value, periodicity, channel):
        if msg_id not in self.can_tasks:
            self.can_tasks[msg_id] = CanTask(device, channel)
            self.can_tasks[msg_id].send_periodic_tx(msg_id, signal_name, signal_value, periodicity)
            logger.trace(f"Started cyclic TX for msg_id: {msg_id}")
        else:
            logger.info(f"Cyclic TX for msg_id: {msg_id} already running, updating signal values")
            self.can_tasks[msg_id].send_periodic_tx(msg_id, signal_name, signal_value, periodicity)

    def _daq_control_digital_switch(
            self, switch_config, state, device, press_duration_s, reset_delay_s, skip_reset_delay=False):
        physical_line = switch_config["physical_line"]
        active_state = True if switch_config["active_state"] == 'high' else False
        reset_to_default = switch_config["reset_to_default"]

        if state == 'on':
            device.write_digital_output(physical_line, active_state)
            logger.info("Pressed")
            if reset_to_default:
                time.sleep(press_duration_s)
                device.write_digital_output(physical_line, not active_state)
                if not skip_reset_delay:  # <-- only apply delay if not last press
                    time.sleep(reset_delay_s)
                    logger.info("after reset delay")
        elif state == 'off':
            device.write_digital_output(physical_line, not active_state)
        else:
            raise ValueError(f"Invalid state {state}")

    def _daq_control_analog_switch(self, switch_config, state, device, press_duration_s, reset_voltage, reset_delay_s):
        channel = switch_config["channel"]
        output_voltage = switch_config["voltage_to_output"]
        reset_to_default = switch_config["reset_to_default"]
        if state == 'on':
            device.write_analog_output(channel, output_voltage, reset_voltage)
            if reset_to_default:
                time.sleep(press_duration_s)
                device.write_analog_output(channel, reset_voltage)
                time.sleep(reset_delay_s)
        elif state == 'off':
            device.write_analog_output(channel, reset_voltage, reset_voltage)
        else:
            raise ValueError(f"Invalid state {state}")

    def _camera_handler(self, device, command_name, cmd_params, **kwargs):
        save_dir = kwargs.get("save_dir")
        testcase_identifier = kwargs.get("test_identifier")
        if command_name == 'write':
            filename = cmd_params.get('filename')
            if cmd_params['action'] == 'capture_image':
                if filename:
                    filename = save_dir + '/' + filename
                else:
                    filename = save_dir + '/' + f'{testcase_identifier}_image.jpg'
                device.capture_image(filename)

                # Wait until file is visible
                max_checks = 1000  # 500 × 0.01s = 5 seconds
                for _ in range(max_checks):
                    if os.path.exists(filename):
                        logger.trace(f'Image Captured.Saved to file :{filename}')
                        break
                    time.sleep(0.01)
                else:
                    raise TimeoutError("File did not appear in time")
                return {'image': filename}
            elif cmd_params['action'] == 'start_recording':
                if filename:
                    filename = save_dir + '/' + filename
                else:
                    filename = save_dir + '/' + f'{testcase_identifier}_video.mp4'
                fps = cmd_params.get('fps')
                if fps:
                    fps = int(fps)
                device.start_recording(filename, 'mp4v', fps)
                # Wait until file is visible
                max_checks = 1000  # 500 × 0.01s = 5 seconds
                for _ in range(max_checks):
                    if os.path.exists(filename):
                        logger.trace('Recording started.Saving to file :{filename}')
                        break
                    time.sleep(0.01)
                else:
                    raise TimeoutError("File did not appear in time")
                return {'video': filename}
            elif cmd_params['action'] == 'stop_recording':
               device.stop_recording()
               return None
            else:
                raise ValueError(f"CameraHandler:Invalid command parameter:{cmd_params['action']}")
        else:
            raise ValueError(f"CameraHandler:Invalid command name:{command_name}")

    def _parse_can_command(self, value: str):
        value = value.strip()

        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [item.strip() for item in inner.split(",")]
        return value

    def _can_handler(self, device, command_name, cmd_params, **kwargs):
        response = {}
        parsed_can_commands = {key: self._parse_can_command(value) for key, value in cmd_params.items()}
        protocol = parsed_can_commands.get("proto")
        if not protocol:
            raise ValueError("Invalid CAN command, 'proto' key not found.")
        msg_id = parsed_can_commands.get("msg_id")
        channel = cmd_params.get("channel")
        if channel:
            channel = channel.strip()
        if not msg_id:
            raise ValueError("Invalid CAN command, 'msg_id' key not found.")
        data = cmd_params.get("data")
        if command_name == 'read':
            signal_name = cmd_params.get("sig")
            if not signal_name:
                raise ValueError("Invalid CAN command, 'sig' key found.")
            if "[" in signal_name:
                signals_list = signal_name.strip("[]").split(",")
                msg_dict = device.read(msg_id)
                print("msg_dict", msg_dict)
                response_list = []
                for signal in signals_list:
                    print("signal", signal)
                    ret = msg_dict[signal.strip()]
                    response_list.append(ret)
                response[cmd_params["output"]] = str(response_list).strip("[]")
            else:
                signal_name = signal_name.strip()
                ret = device.read(msg_id, signal_name, channel)
                response[cmd_params["output"]] = ret
        else:
            if protocol == 'uds':
                if not data:
                    raise ValueError("Invalid CAN command, 'data' key not found.")
                hex_data = data.split(',')
                ret = device.send_diagnostic(hex_data, channel)
                response[cmd_params["output"]] = ret
            else:
                stop_msg = cmd_params.get("stop_msg")
                if stop_msg:
                    can_task = self.can_tasks.get(msg_id)
                    if can_task:
                        can_task.stop(msg_id)
                        del self.can_tasks[msg_id]
                    else:
                        logger.error("No Can task to stop")
                    return response

                periodicity = parsed_can_commands.get("periodicity")
                if type(periodicity) == str:
                    periodicity = float(periodicity)
                elif type(periodicity) == list:
                    periodicity = [float(item) for item in periodicity]

                repetitions = cmd_params.get("repetitions")
                if repetitions:
                    repetitions = int(repetitions)

                rollover_value = parsed_can_commands.get("rollover_value")
                if type(rollover_value) == str:
                    rollover_value = float(rollover_value)
                elif type(rollover_value) == list:
                    rollover_value = [float(item) for item in rollover_value]

                interval = cmd_params.get("interval")
                if interval:
                    interval = float(interval)
                increment_period = parsed_can_commands.get("increment_period")
                if type(increment_period) == str:
                    increment_period = float(increment_period)
                elif type(increment_period) == list:
                    increment_period = [float(item) for item in increment_period]
                unit = cmd_params.get("unit")
                if unit == 'ms':
                    if increment_period:
                        if type(increment_period) == list:
                            increment_period = [(item/1000) for item in increment_period]
                        else:
                            increment_period = increment_period / 1000
                    if periodicity:
                        if type(periodicity) == list:
                            periodicity = [(item / 1000) for item in periodicity]
                        else:
                            periodicity = periodicity / 1000
                    if interval:
                        interval = interval/1000
                signal_name = None
                if data:
                    hex_data_list = data.split(',')
                    data_bytes = bytearray()
                    for hex_byte in hex_data_list:
                        hex_byte = hex_byte.strip()
                        if hex_byte.startswith('0x'):
                            hex_byte = hex_byte[2:]  # Remove '0x' prefix
                            data_bytes.append(int(hex_byte, 16))
                    data = data_bytes
                else:
                    signal_name = parsed_can_commands.get("sig")
                    if type(signal_name) == str:
                        signal_name = signal_name.strip()
                if not data and not signal_name:
                    raise ValueError("Invalid CAN command, Neither 'data' nor 'sig' keys found.")
                if not periodicity and not repetitions: # Send Can once
                    device.send(msg_id, data, channel)
                    response[cmd_params["output"]] = device.receive(msg_id, channel, timeout_s=7)
                    logger.info(f"Response received {response}")
                elif repetitions and not periodicity: # Send Can n times
                    for i in range(repetitions):
                        device.send(msg_id, data, channel)
                        timestamp = time.time()
                        # Convert to human-readable format
                        readable = datetime.fromtimestamp(timestamp)
                        logger.info(f"Readable:  {readable.strftime("%Y-%m-%d %H:%M:%S")}")
                        if i == repetitions-1:
                            break
                        time.sleep(interval)
                    response[cmd_params["output"]] = device.receive(msg_id, channel, timeout_s=7)
                    logger.info(f"Response received {response}")
                elif periodicity and not rollover_value: # Send can periodically
                    signal_value = cmd_params.get("value")
                    if signal_value:
                        signal_value = float(signal_value)
                    self._can_send_periodic(device, msg_id, signal_name, signal_value, periodicity, channel)
                elif periodicity and rollover_value:
                    if type(msg_id) is not list:# Send can periodically and incrementally
                        signal_value = float(cmd_params.get("value"))
                        max_value = float(cmd_params.get("max_value"))
                        increment = float(cmd_params.get("increment"))
                        signal_factor = cmd_params.get("signal_factor")
                        if signal_factor:
                            signal_factor = float(signal_factor)
                        if increment_period < periodicity:
                            raise ValueError(" Increment period must be greater than message periodicity.")
                        can_task = self.can_tasks.get(msg_id)
                        if not can_task:
                            print("Creating can ntask")
                            can_task = CanTask(device, channel)
                            self.can_tasks[msg_id] = can_task
                        can_task.increment_tx_loop(msg_id, signal_name, signal_value, max_value, increment,
                                                   increment_period, rollover_value, signal_factor, periodicity,
                                                   self.stop_event)
                    else:
                        signal_value = [float(item) for item in parsed_can_commands.get("value")]
                        max_value = [float(item) for item in parsed_can_commands.get("max_value")]
                        increment = [float(item) for item in parsed_can_commands.get("increment")]
                        signal_factor = [float(item) for item in parsed_can_commands.get("signal_factor")]
                        for msg, signal_name, signal_value, max_value, increment, increment_period, \
                                rollover_value, signal_factor, periodicity in zip(msg_id, signal_name, signal_value, max_value, increment,
                                                   increment_period, rollover_value, signal_factor, periodicity):
                            can_task = self.can_tasks.get(msg)
                            if not can_task:
                                can_task = CanTask(device, channel)
                                self.can_tasks[msg] = can_task
                                print("CAN Task Created")
                            if msg not in can_task.active_non_blocking_threads:
                                can_non_blocking_thread = threading.Thread(
                                    target=can_task.increment_tx_loop,
                                    args=(msg, signal_name, signal_value, max_value, increment, increment_period,
                                          rollover_value, signal_factor, periodicity, self.stop_event,),
                                    daemon=True
                                )
                                can_task.active_non_blocking_threads[msg] = can_non_blocking_thread
                                print(f"Starting thread for {msg}")
                                can_non_blocking_thread.start()

                else:
                    raise ValueError("Invalid can command.")
        # Additional delay is added to account for cases where Meter HMI takes time
        # to update and HMI image is captured immediately after sending CAN signal
        time.sleep(1.8)
        return response

    def _daq_handler(self, device, command_name, cmd_params, **kwargs):
        if command_name == "write":
            action = cmd_params.get("action")
            if not action:
                raise ValueError("Invalid Daq command, 'action' key not found.")
            if action == "press":
                switch_name = cmd_params.get("key")
                key_sequence = cmd_params.get("sequence")
                repeat = cmd_params.get("repeat")
                if not switch_name and not key_sequence:
                    raise ValueError("Invalid Daq command, Neither 'key' nor 'sequence' keys found.")
                press_duration_s = float(SwitchMapConfig.press_duration(self.client_code,self.variant, self.sub_variant))
                reset_voltage = float(SwitchMapConfig.reset_voltage(self.client_code,self.variant, self.sub_variant))
                reset_delay_s = float(SwitchMapConfig.reset_delay(self.client_code,self.variant, self.sub_variant))
                if switch_name and repeat is None:

                    state = cmd_params.get("state")
                    switch_config = SwitchMapConfig.switch_config(switch_name, self.client_code,
                                                                self.variant, self.sub_variant)
                    channel_type = switch_config["type"]
                    if channel_type == "DIO":
                        self._daq_control_digital_switch(switch_config, state, device, press_duration_s, reset_delay_s)
                    elif channel_type == 'AO':
                        self._daq_control_analog_switch(switch_config, state, device, press_duration_s, reset_voltage, reset_delay_s)
                    else:
                        raise ValueError(f"Invalid channel type for key:{switch_name}")

                elif switch_name and repeat:
                    on_time = float(cmd_params.get("on_time"))
                    off_time = float(cmd_params.get("off_time"))
                    unit = cmd_params.get("unit")
                    switch_config = SwitchMapConfig.switch_config(switch_name, self.client_code,
                                                                  self.variant, self.sub_variant)
                    channel_type = switch_config["type"]

                    if unit == 'ms':
                        on_time = on_time / 1000
                        off_time = off_time / 1000

                    #device.toggle_relay(relay_index, False)
                    time.sleep(0.2)
                    for i in range(int(repeat)):
                        logger.info(f"\n {switch_name} Cycle {i + 1} of {repeat}")
                        if channel_type == "DIO":
                            self._daq_control_digital_switch(switch_config, "on", device, press_duration_s,
                                                             reset_delay_s)
                        elif channel_type == 'AO':
                            self._daq_control_analog_switch(switch_config, "on", device, press_duration_s,
                                                            reset_voltage,
                                                            reset_delay_s)
                        time.sleep(on_time)
                        if channel_type == "DIO":
                            self._daq_control_digital_switch(switch_config, "off", device, press_duration_s,
                                                             reset_delay_s)
                        elif channel_type == 'AO':
                            self._daq_control_analog_switch(switch_config, "off", device, press_duration_s,
                                                            reset_voltage,
                                                            reset_delay_s)
                        time.sleep(off_time)
                    logger.info(f"[{switch_name}] cycles complete.")
                elif key_sequence:
                    skip_last_delay = cmd_params.get("skip_last_delay")
                    if skip_last_delay:
                        skip_last_delay = skip_last_delay.lower()
                    print("Skip", skip_last_delay)
                    print(type(skip_last_delay))
                    switches = key_sequence.split(':')
                    num_switches = len(switches)

                    for i, switch in enumerate(switches):
                        switch_abbreviation, press_count = re.match(r"([A-Za-z]+)(\d+)", switch).groups()
                        switch_config = SwitchMapConfig.switch_config_abbr(
                            switch_abbreviation, self.client_code, self.variant, self.sub_variant)
                        channel_type = switch_config["type"]

                        for repeat in range(int(press_count)):
                            if skip_last_delay == "true":
                                is_last_switch = (i == num_switches - 1)
                                is_last_repeat = (repeat == int(press_count) - 1)
                                skip_delay = is_last_switch and is_last_repeat
                            else:
                                skip_delay=False

                            if channel_type == "DIO":
                                self._daq_control_digital_switch(
                                    switch_config, 'on', device, press_duration_s, reset_delay_s,
                                    skip_reset_delay=skip_delay)
                            elif channel_type == 'AO':
                                self._daq_control_analog_switch(
                                    switch_config, 'on', device, press_duration_s, reset_voltage, reset_delay_s)
                            else:
                                raise ValueError(f"Invalid channel type key {switch_abbreviation}")

        return {}

    def _fg_handler(self, device, command_name, cmd_params, **kwargs):
        result = {}
        if command_name == "write":
            output = cmd_params.get('output')
            if "pulse" in cmd_params.keys():
                device.set_pulse(cmd_params["pulse"])
                time.sleep(2)
                pulse = device.get_pulse()
                logger.trace(f'Pulse set to: {pulse}')
                if output:
                    result.update({output: pulse})
            elif "freq" in cmd_params.keys():
                device.set_frequency(cmd_params["freq"])
                time.sleep(2)
                freq = device.get_frequency()
                logger.trace(f'Frequency set to: {freq}')
                if output:
                    result.update({output: freq})
            else:
                raise ValueError(f"Invalid command arguments passed for command: {command_name}")
        else:
            raise ValueError(f"Invalid command name: {command_name}")
        return result

    def _osc_handler(self,  device, command_name, cmd_params, **kwargs):
        save_dir = kwargs.get("save_dir")
        testcase_identifier = kwargs.get("test_identifier")
        file_path = save_dir + '/' + f'{testcase_identifier}_osc_screenshot.jpg'
        result = {}
        if command_name == "read":
            output = cmd_params['output']
            if cmd_params["measurement"] == "frequency":
                freq = device.measure_frequency(device.channel)
                logger.trace(f'Measured Frequency: {freq}')
                result.update({output: freq})
                device.take_screenshot(file_path)
                logger.trace(f'screenshot save to : {file_path}')
            elif cmd_params["measurement"] == "amplitude":
                amp = device.measure_amplitude(device.channel)
                result.update({output: amp})
                device.take_screenshot(file_path)
                logger.trace(f'Measured amplitude: {amp}')
            elif cmd_params["measurement"] == "dutycycle":
                duty_cycle = device.measure_duty_cycle(device.channel)
                logger.trace(f'Measured Duty Cycle: {duty_cycle}')
                device.take_screenshot(file_path)
                result.update({output: duty_cycle})
            else:
                raise ValueError(f"Invalid command arguments passed for command: {command_name}")
        else:
            raise ValueError(f"Invalid command name: {command_name}")
        return result

    def _psu_handler(self,  device, command_name, cmd_params, **kwargs):
        result = {}
        output = cmd_params.get('output')
        if command_name == "write":
            if "volt" in cmd_params.keys() and "curr" not in cmd_params.keys():
                device.set_voltage(cmd_params["volt"])
                time.sleep(1.5)
                voltage = device.get_voltage()
                if output:
                    result.update({output: voltage})
            elif "curr" in cmd_params.keys() and "volt" not in cmd_params.keys():
                device.set_current(cmd_params["curr"])
                time.sleep(1.5)
                current = device.get_current()
                if output:
                    result.update({output: current})
            elif "volt" and "curr" in cmd_params.keys():
                device.set_voltage(cmd_params["volt"])
                device.set_current(cmd_params["curr"])
                if cmd_params["volt"] == "0":
                    time.sleep(10)
                else:
                    time.sleep(1.5)
                voltage = device.get_voltage()
                current = device.get_current()
                if output:
                    output = output.split(",")
                    result.update({output[0]: voltage,
                                   output[1]: current})
        elif command_name == "read":
            output_list = cmd_params["measurement"].split(",")
            if len(output_list) == 1 and "curr" not in output_list:
                voltage = device.get_voltage()
                result.update({output: voltage})
            elif len(output_list) == 1 and "volt" not in output_list:
                current = device.get_current()
                result.update({output: current})
            elif len(output_list) > 1:
                voltage = device.get_voltage()
                current = device.get_current()
                output = output.split(",")
                result.update({output[0]: voltage,
                               output[1]: current})
        else:
            raise ValueError(f"Invalid command name: {command_name}")
        return result

    def _relay_handler(self, device, command_name, cmd_params, **kwargs):
        if command_name == "write":
            switch_name = cmd_params.get("action")
            if not switch_name:
                raise ValueError("Invalid Relay command, 'key' key not found.")
            switch_config = SwitchMapConfig.switch_config(switch_name, self.client_code,
                                                                self.variant, self.sub_variant)
            relay_index = switch_config.get("relay_number")
            if not relay_index:
                raise ValueError(f"Relay number not found in {switch_name} configuration.")
            relay_index = int(relay_index)
            if "state" in cmd_params.keys():
                state = True if cmd_params.get("state") == 'on' else False
                device.toggle_relay(relay_index, state)
            else:
                on_time = float(cmd_params.get("on_time"))
                off_time = float(cmd_params.get("off_time"))
                num_cycles = cmd_params.get("repeat")
                unit = cmd_params.get("unit")
                if unit == 'ms':
                    on_time = on_time/1000
                    off_time = off_time/1000
                device.toggle_relay(relay_index, False)
                time.sleep(0.2)
                for i in range(num_cycles):
                    logger.info(f"\n[Relay {relay_index}] Cycle {i + 1} of {num_cycles}")
                    device.toggle_relay(relay_index, True)
                    time.sleep(on_time)
                    device.toggle_relay(relay_index, True)
                    time.sleep(off_time)
                logger.info(f"[Relay {relay_index}] cycles complete.")
        return {}

    def _rc_handler(self, device, command_name, cmd_params, **kwargs):
        if command_name == "write":
            if "resistance" in cmd_params:
                device.apply_resistance(int(cmd_params["resistance"]))
            else:
                raise ValueError(
                    f"Invalid command arguments {cmd_params} passed for command: {command_name}")
        else:
            raise Exception(f"Invalid command name: {command_name}")
        return {}

    def _validate_handler(self, service, cmd_params, **kwargs):
        actual_value = cmd_params.get('actual')
        if not actual_value:
            raise ValueError('Invalid validation command, actual value not present')
        #actual_value = actual_value.lower()
        expected = cmd_params.get('expected')
        expected_min = None
        expected_max = None
        if expected:
            expected = expected.lower()
            return service.validate_absolute(actual_value, expected)
        else:
            evaluated_value = ast.literal_eval(actual_value)
            expected_min = cmd_params.get('expected_min')
            expected_max = cmd_params.get('expected_max')
            actual_value_numeric_part = None
            expected_min_numeric_part, expected_min_alpha_part = utils.split_alnum_value(expected_min)
            expected_max_numeric_part, expected_max_alpha_part = utils.split_alnum_value(expected_max)
            if isinstance(evaluated_value, list) and len(evaluated_value)>0:
                for item in evaluated_value:
                    if not item.isalpha():
                        actual_value_numeric_part, actual_value_alpha_part = utils.split_alnum_value(item)
                        result = service.validate_range(actual_value_numeric_part, expected_min_numeric_part,
                                               expected_max_numeric_part)
                        # Replace measured_value in result with actual
                        # value from test case as alphanumeric strings will be stripped
                        # of the alphabet part in validate range for validation
                        result["measured_value"] = item
                        return result
                # Only strings were present in the actual result
                raise ValueError("Numeric value not found in actual value")
            elif isinstance(evaluated_value, list) and len(evaluated_value)==0:
                raise ValueError("Actual Value is empty")
            else:
                return service.validate_range(float(actual_value), float(expected_min), float(expected_max))

    def _delay_handler(self, service, cmd_params):
        period = int(cmd_params.get('time'))
        unit = cmd_params.get('unit')
        camera = self.device_manager.get_device(DeviceType.Camera.value)
        suspend_capture = False
        if unit == 'ms':
            period = period / 1000

        # suspend video capture if delay is more than equal 10 minutes
        if period >= 600 and camera:
            camera.suspend_capture()
            suspend_capture = True
        #service.delay(period)
        event_set = self.stop_event.wait(period)
        if event_set:
            logger.info("Woken up early from delay handler due to an event signal!")
        if suspend_capture and camera:
            camera.resume_capture()
        return {}

    def _compute_handler(self, service, cmd_params, **kwargs):
        expr = cmd_params.get('expr')
        if not expr:
            raise ValueError('Invalid compute command, no compute expression present')
        _, expr = expr.split('(')
        expr, _ = expr.split(')')
        type_ = cmd_params.get('type')
        unit = cmd_params.get('unit')
        output = cmd_params.get('output')
        result = service.evaluate(expr, type_, unit)
        if unit == "msec":
            result = result.total_seconds() * 1000
        elif unit == "sec":
            result = result.total_seconds()
        else:
            raise ValueError(f"Invalid unit {unit}")
        return {output: result}

    def _vision_handler(self, service, cmd_params, **kwargs):
        action = cmd_params.get("action")
        input_source = cmd_params.get("input")
        if input_source == 'None':
            raise ValueError("No input source provided")
        last_dot_index = input_source.rfind('.')
        file_type = input_source[last_dot_index + 1:]
        if file_type == 'jpg':
            input_type = 'image'
        else:
            input_type = 'video'
        evidence_dir = kwargs.get("save_dir")
        test_identifier = kwargs.get("test_identifier")
        confidence = cmd_params.get("confidence")
        if not confidence:
            confidence = 0.3
        else:
            confidence = float(confidence)
        output = cmd_params.get('output')
        class_names = self._get_class_names()
        result = {}
        if action == 'detect':
            object_label = cmd_params.get("object")
            if input_type == 'image':
                found, img = service.detect_in_image(input_source, object_label, confidence,
                                                 self.model_path, class_names)
                result[output]= found
                if found:
                    file_path = evidence_dir + '/' + f'{test_identifier}_detect_img.jpg'
                    cv2.imwrite(file_path, img)
            elif input_type == 'video':
                match = cmd_params.get("match")
                seek = cmd_params.get('seek')
                output = output.split(',')
                found, found_timestamp, found_frame = service.detect_in_video(self.stop_event, input_source, object_label, self.model_path, class_names, confidence, match, seek)
                if 'found' in output:
                    result['found'] = found
                if 'timestamp' in output:
                    result['timestamp'] = found_timestamp
                if found:
                    file_path = evidence_dir + '/' + f'{test_identifier}_{found_timestamp}.jpg'
                    cv2.imwrite(file_path, found_frame)
            else:
                raise ValueError('Unsupported input type')
        elif action == "ocr":
            region = cmd_params.get('region')
            expected_text = cmd_params.get('text')
            textcolor = cmd_params.get('textcolor')
            background_color = cmd_params.get('bgcolor')
            language = cmd_params.get("lang")
            if not language:
                language = 'en'
            if input_type == 'image':
                if region:
                    found_text, cropped_img = service.extract_text_from_region(input_source, self.model_path,
                                                                  class_names, region, confidence, language)
                    if cropped_img is not None and cropped_img.any():
                        cropped_img_path = evidence_dir + '/' + f'{test_identifier}_cropped_img.jpg'
                        cv2.imwrite(cropped_img_path, cropped_img)
                else:
                    found_text = service.extract_text_from_image(input_source, language)
                result[output] = found_text
                logger.trace(f'Found Texts {found_text}')

                # Dump result to JSON file
                with open(f'{evidence_dir}/{test_identifier}_ocr_result.json', "a",
                          encoding='utf-8') as f:
                    f.write("\n---------------------------------------\n\n")
                    json.dump(found_text, f, indent=4, ensure_ascii=False)
            elif input_type == 'video':
                match = cmd_params.get("match")
                seek = cmd_params.get('seek')
                if not match:
                    match = 'first'
                output = output.split(',')
                found, found_timestamp, found_frame = service.ocr_from_video(self.stop_event, input_source, self.model_path, class_names, region, confidence,
                                                                language, expected_text, match, seek)
                if 'found' in output:
                    result['found'] = found
                if 'timestamp' in output:
                    result['timestamp'] = found_timestamp
                if found:
                    file_path = evidence_dir + '/' + f'{test_identifier}_{found_timestamp}.jpg'
                    cv2.imwrite(file_path, found_frame)
            else:
                raise ValueError('Unsupported input type')
        else:
            raise ValueError(f"Unsupported action: {action}")
        return result

    def cleanup_can_tasks(self):
        for task in self.can_tasks.values():
            task.stop_all()
        self.can_tasks.clear()

    def dispatch(self, command: str, **kwargs):
        command_name, cmd_params = self._parse_command(command)
        try:
            if command_name == 'write' or command_name == 'read': # devices command
                device_abbreviation = cmd_params.get('device')
                device_type = get_device_type(device_abbreviation)
                device_instance = self.device_manager.get_device(device_type)
                if device_type == DeviceType.Can.value:
                    return self._can_handler(device_instance, command_name, cmd_params, **kwargs)
                elif device_type == DeviceType.Camera.value:
                    return self._camera_handler(device_instance, command_name, cmd_params, **kwargs)
                elif device_type == DeviceType.Relay.value:
                    return self._relay_handler(device_instance, command_name, cmd_params, **kwargs)
                elif device_type == DeviceType.Daq.value:
                    return self._daq_handler(device_instance, command_name, cmd_params, **kwargs)
                elif device_type == DeviceType.ResistanceCard.value:
                    return self._rc_handler(device_instance, command_name, cmd_params, **kwargs)
                elif device_type == DeviceType.Powersupply.value:
                    return self._psu_handler(device_instance, command_name, cmd_params, **kwargs)
                elif device_type == DeviceType.FunctionGenerator.value:
                    return self._fg_handler(device_instance, command_name, cmd_params, **kwargs)
                elif device_type == DeviceType.Oscilloscope.value:
                    return self._osc_handler(device_instance, command_name, cmd_params, **kwargs)
                else:
                    raise ValueError(f'Unsupported device type :{device_type}')
            elif command_name == 'execute': # service command
                service_name = cmd_params.get('service')
                service_instance = self.service_manager.get_service(service_name)
                if service_name == "validate":
                    return self._validate_handler(service_instance, cmd_params, **kwargs)
                elif service_name == "vision":
                    return self._vision_handler(service_instance, cmd_params, **kwargs)
                elif service_name == "compute":
                    return self._compute_handler(service_instance, cmd_params, **kwargs)
                elif service_name == "delay":
                    return self._delay_handler(service_instance, cmd_params)
                else:
                    raise ValueError(f'Unsupported service :{service_name}')
            else:
                return None
        except Exception as e:
            logger.critical(f"[Dispatcher] Command {command} failed, Reason: {e}",exc_info=True)
            return self._handle_exception(command_name, cmd_params, "Exception")
