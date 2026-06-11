@echo off
cd /d "C:\Users\Matheus\Desktop\Claude\Projetinho Félas"

tasklist /FI "IMAGENAME eq pythonw.exe" 2>NUL | find /I "pythonw.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    exit
)

start "" "C:\Users\Matheus\AppData\Local\Programs\Python\Python314\pythonw.exe" automacao.py
