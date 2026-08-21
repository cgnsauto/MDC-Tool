 # Copyright (c) Capgemini. All rights reserved.
import logging
import os
import sys
import faulthandler
from PySide6.QtCore import QTimer
from PySide6.QtGui import Qt, QIcon, QPixmap, QColor
from PySide6.QtWidgets import QApplication, QStyleFactory, QMainWindow, QSplashScreen
from device_manager import DeviceManager
from icons import base64_to_icon, cg_logo, cg_logo_big, base64_to_pixmap, cg_splash
from logger import init_logger, logger
from service_manager import ServiceManager
from signals import SignalManager
from view.main_view import MainWindow


if __name__ == "__main__":
    # Enable faulthandler to write to a file
    # dump_file = os.path.join(os.getcwd(), 'crash_dump.txt')
    # faulthandler.enable(open(dump_file, 'w'))
    #sys.excepthook = handle_exception
    init_logger('Application', logging.DEBUG, True, 50 * 1024 * 1024, 10)
    try:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-software-rasterizer"
        os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
        os.environ['QT_SCALE_FACTOR'] = '1'

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)
        app = QApplication(sys.argv)
        app.setStyle(QStyleFactory.create('Windows'))
        app.setWindowIcon(base64_to_icon(cg_logo))

        # Setup Splash Screen
        pixmap = QPixmap(base64_to_pixmap(cg_splash))  # Ensure you have an image here
        splash = QSplashScreen(pixmap)
        splash.showMessage("Loading... Please wait", Qt.AlignmentFlag.AlignBottom|
                           Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.black)
        splash.show()
        logger.info("Before Process Events")
        app.processEvents()
        logger.info("Before Signal Events")
        signal = SignalManager()
        logger.info("Before Device Events")
        device_manager = DeviceManager()
        logger.info("Before Service Events")
        service_manager = ServiceManager()

        main_window = MainWindow(signal,service_manager, device_manager)
        main_window.setWindowTitle("MDCAutoTestClient")
        main_window.showMaximized()

        splash.finish(main_window)
        # Resize the dock widgets after the window is shown
        main_window.resizeEvent = lambda event: (QMainWindow.resizeEvent(main_window, event), main_window.resize_dock_widgets())

        # Use QTimer to call resize_dock_widgets after the window is shown
        QTimer.singleShot(0, main_window.select_left_dock_widget)
        sys.exit(app.exec())
    except Exception as e:
        print(str(e))
