@echo off
setlocal
rem ==========================================================================================
rem  GigBid - run everything that is left (Windows). Double-click this file.
rem  Needs: Git for Windows (gives Git Bash) and Python 3.12 from python.org.
rem  Works from anywhere: if it is not inside the gigbid repo it clones the repo next to itself.
rem  Your Groq key goes into a .env file that this script opens in Notepad (never typed in the console).
rem ==========================================================================================
title GigBid - run everything

where git >nul 2>nul || (echo Git is not installed. Install "Git for Windows" from https://git-scm.com and run this again. & pause & exit /b 1)

set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%BASH%" set "BASH=%ProgramFiles(x86)%\Git\bin\bash.exe"
if not exist "%BASH%" set "BASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if not exist "%BASH%" (echo Could not find Git Bash. Reinstall Git for Windows with default options. & pause & exit /b 1)

rem ---- find or get the repository
set "HERE=%~dp0"
if exist "%HERE%scripts\run_everything.sh" (
  set "REPO=%HERE%"
) else (
  set "REPO=%HERE%gigbid"
  if not exist "%HERE%gigbid\.git" (
    echo Cloning the repository into %HERE%gigbid ...
    git clone https://github.com/MuhammadHasan-04/gigbid.git "%HERE%gigbid" || (echo Clone failed. & pause & exit /b 1)
  )
)
cd /d "%REPO%"
git config core.autocrlf false
echo Getting the latest version ...
git pull --ff-only

rem ---- the Groq key, in .env (git-ignored)
findstr /b /c:"GROQ_API_KEY=gsk_" .env >nul 2>nul
if errorlevel 1 (
  > .env echo GROQ_API_KEY=gsk_PASTE_YOUR_KEY_HERE
  >> .env echo MODEL_PROFILE=open
  echo.
  echo Notepad will open .env: replace gsk_PASTE_YOUR_KEY_HERE with your Groq key, save, close Notepad.
  notepad .env
  findstr /b /c:"GROQ_API_KEY=gsk_" .env | findstr /v "PASTE_YOUR_KEY" >nul || (echo No Groq key in .env. Run this file again after adding it. & pause & exit /b 1)
)

echo.
echo Starting. This takes a few hours on the free Groq tier; leave the window open.
echo A full log is written to data\runtime\laptop_*.log
"%BASH%" -lc "cd \"$(cygpath -u '%REPO%')\" && bash scripts/run_everything.sh"
echo.
echo Finished. Scroll up for the summary.
pause
