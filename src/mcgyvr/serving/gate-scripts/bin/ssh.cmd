@rem The door's `ssh` for a program that looks `ssh` up by PATHEXT on Windows:
@rem the shim beside this file, run on the interpreter the door runs on.
@"%RUN_PYTHON%" "%~dp0ssh" %*
@exit /b %ERRORLEVEL%
