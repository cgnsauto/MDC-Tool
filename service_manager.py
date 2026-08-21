# Copyright (c) Capgemini. All rights reserved.
from PyTestServices.compute import ComputeService
from PyTestServices.delay import DelayService
from PyTestServices.validate import ValidationService
from PyTestServices.vision import VisionService
from logger import logger

class ServiceManager:
    """
    This class provides a centralized interface for registering, monitoring services that handle service during test
    execution
    """
    def __init__(self):
        self.services = {}
        self.register_service()

    def register_service(self):
        """
        Register services with the service manager
        :return: None
        """
        ocr_path = 'resources/models/ml/ocr/easyocr'
        self.services['validate'] = ValidationService()
        self.services['compute'] = ComputeService()
        logger.info("Before Vision")
        self.services['vision'] = VisionService(ocr_path)
        logger.info("after vision")
        self.services['delay'] = DelayService()

    def get_service(self, name):
        return self.services.get(name)


