# Copyright (c) Capgemini. All rights reserved.
# setup.py
#from distutils.core import setup
#from setuptools import setup
#import py2exe
import os
import sys
from cx_Freeze import setup, Executable

sys.setrecursionlimit(5000)
# Automatically find all Python files in the application directory
def find_python_files(path):
    python_files = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.py'):  #or file.endswith('.ini') :
                python_files.append(os.path.relpath(os.path.join(root, file), path))
    print(python_files)
    return python_files

MAIN_SCRIPT = 'main.py'
base = None
if sys.platform == 'win32':
    base = 'Win32GUI'

BUILD_EXE_OPTIONS = {
    "packages": ["torch", "torch._dynamo", "torch._dynamo.polyfills", "torch.fx", "can", "PyConfigManager","PyReportGenerator","PyTestServices","PyInstruments"],
    'build_exe': "../Build",
     # Include additional files
    'include_files':['resources']
}

setup(
    name="MDCAutoTestClient",
    version="1.0.0",
    description="Test Automation",
    options={"build_exe": BUILD_EXE_OPTIONS},
    executables=[Executable("main.py", target_name="MDCAutoTestClient.exe", base="gui")]
)