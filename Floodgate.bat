@echo off
:: ������Ŀ��Ŀ¼�����⻷��·��
set PROJECT_DIR=D:\Workspace\Floodgate
set VENV_DIR=%PROJECT_DIR%\venv

:: ����Ƿ�������⻷��
if not exist "%VENV_DIR%" (
    echo ���ڴ������⻷��...
    python -m venv "%VENV_DIR%"
)

:: �������⻷��
call "%VENV_DIR%\Scripts\activate.bat"

:: �л�����ĿĿ¼
cd /d "%PROJECT_DIR%"

:: ��������
echo �������� Floodgate...
python run.py

:: ���ִ��ڲ��رգ�����鿴������Ϣ
echo.
echo �������˳���
pause
