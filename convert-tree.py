#!/usr/bin/env python

"""
    Bulk file copy and AVI conversion utility for AMOS.
    Requires a YAML configuration file (can be overridden with arguments).
    Ⓒ Kvík & Mözg, 2021-2024

    For use in production you should create an EXE file with `pyinstaller.exe --onefile convert-tree.py`,
    see pyinstaller documentation.
"""

import os
from classes.tree import TreeConvertor

os.system("") # you can't have colourful console output from compiled .exe without this little hack
TreeConvertor().run()
