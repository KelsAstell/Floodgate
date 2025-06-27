@echo off
:: 设置项目根目录和虚拟环境路径（使用相对路径）
set PROJECT_DIR=..\Floodgate
set VENV_DIR=%PROJECT_DIR%\venv

:: 检查是否存在虚拟环境
if not exist "%VENV_DIR%" (
    echo 正在创建虚拟环境...
    python -m venv "%VENV_DIR%"
)

:: 激活虚拟环境
call "%VENV_DIR%\Scripts\activate.bat"

:: 切换到项目目录
cd /d "%PROJECT_DIR%"

:: 启动程序
echo 正在启动 Floodgate...
python run.py

:: 保持窗口不关闭，方便查看错误信息
echo.
echo 程序已退出。
pause
