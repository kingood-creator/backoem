@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
echo ============================================================
echo    输入法悬浮球 - Windows 绿色版 一键打包
echo ============================================================
echo.

rem ---------- 1) 找 Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo [错误] 没有找到 Python。
    echo        请先安装 Python 3.9 或更高版本，安装时务必勾选
    echo        "Add python.exe to PATH"。
    echo        下载地址： https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)
if not exist "ime_float.py" (
    echo [错误] 请在解压后的程序目录里运行本脚本（找不到 ime_float.py）。
    pause
    exit /b 1
)
if not exist "ime_win.py" (
    echo [错误] 缺少 ime_win.py，请确认压缩包解压完整。
    pause
    exit /b 1
)
echo 使用 Python： %PY%
%PY% -c "import sys; print('Python 版本：', sys.version.split()[0])"

rem ---------- 2) 安装依赖 ----------
echo.
echo [1/3] 安装依赖（PyQt6 / pyinstaller，首次需要联网）...
%PY% -m pip install --disable-pip-version-check -q PyQt6 pyinstaller
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

rem ---------- 3) 打包 ----------
echo.
echo [2/3] 正在打包（首次大约 1~3 分钟，请耐心等待）...
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name InputMethodFloatBall --icon app.ico ^
    --hidden-import ime_win --hidden-import ime_mac ^
    ime_float.py
if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请把上面红色报错发出来。
    pause
    exit /b 1
)

rem ---------- 4) 整理绿色版目录 ----------
echo.
echo [3/3] 整理输出目录 ...
if not exist "绿色版" mkdir "绿色版"
copy /y "dist\InputMethodFloatBall.exe" "绿色版\输入法悬浮球.exe" >nul
copy /y "说明-Windows绿色版.txt" "绿色版\说明.txt" >nul

echo.
echo ============================================================
echo    打包完成
echo ------------------------------------------------------------
echo    绿色版位置： %~dp0绿色版
echo    双击 "输入法悬浮球.exe" 即可运行（无需安装）
echo    配置会自动生成在    绿色版\data\config.json
echo    把整个「绿色版」文件夹拷到任何电脑都能直接用
echo ============================================================
echo.
pause
