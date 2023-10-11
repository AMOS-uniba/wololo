@echo Compiling Python file to EXE...
pyinstaller.exe --onefile executables/convert-tree.py
pyinstaller.exe --onefile executables/convert-single.py
@pause