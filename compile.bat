@echo Compiling Python file to EXE...
pyinstaller.exe --onefile --icon "NONE" convert-tree.py
pyinstaller.exe --onefile --icon "NONE" convert-single.py
@pause
