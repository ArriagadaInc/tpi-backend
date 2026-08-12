@echo off
cd /d "%~dp0"
set PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

set STREAMLIT_PORT=8501
set STREAMLIT_ADDRESS=0.0.0.0
set URL=http://localhost:%STREAMLIT_PORT%

echo Iniciando Streamlit...
echo URL: %URL%
start "" "%URL%"
"%PYTHON_EXE%" -m streamlit run app/streamlit_app.py --server.address=%STREAMLIT_ADDRESS% --server.port=%STREAMLIT_PORT% --server.headless=true
