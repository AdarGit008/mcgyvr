@rem The door's `docker` for a program that looks `docker` up by PATHEXT on Windows:
@rem the shim beside this file, run on the interpreter the door runs on.
@"%RUN_PYTHON%" "%~dp0docker" %*
@exit /b %ERRORLEVEL%
