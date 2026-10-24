@echo off
:: arena-cleanup, the Windows launcher: put it next to arena-cleanup.py on PATH.
:: Every argument passes through. Exit codes are the script's: 0 ok, 1 error, 7 work found.
setlocal

set "SCRIPT=%~dp0arena-cleanup.py"
if not exist "%SCRIPT%" (
  echo [ERROR] arena-cleanup.py not found next to %~nx0 1>&2
  echo         expected: %SCRIPT% 1>&2
  exit /b 1
)

:: The py launcher first: it selects the right Python when several exist.
:: Then python.exe on PATH.
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3 was not found on PATH. 1>&2
  echo         Install it from https://www.python.org/downloads/ 1>&2
  echo         ^(tick "Add python.exe to PATH" in the installer^) 1>&2
  exit /b 1
)

%PY% "%SCRIPT%" %*
exit /b %ERRORLEVEL%
