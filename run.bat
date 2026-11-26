@echo off
chcp 65001 >nul
title HAN REJUVE 預約網站
cd /d "%~dp0"

echo ============================================
echo   HAN REJUVE 線上預約系統
echo ============================================
echo.

rem --- 1. 檢查是不是在 ZIP 裡面直接執行 ---
if not exist "app.py" (
  echo [錯誤] 找不到 app.py。
  echo.
  echo 你可能是在 ZIP 壓縮檔裡面直接雙擊 run.bat。
  echo 請先在 ZIP 檔上按右鍵，選「解壓縮全部」，
  echo 再打開解壓縮後的資料夾，雙擊裡面的 run.bat。
  goto :fail
)

rem --- 2. 找 Python（優先用 py 啟動器，避免開到 Microsoft Store）---
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
  echo [錯誤] 找不到 Python。
  echo.
  echo 請到 https://www.python.org/downloads/ 下載安裝 Python 3.10 以上版本，
  echo 安裝時第一個畫面要勾選「Add Python to PATH」，
  echo 裝好後重新雙擊 run.bat。
  goto :fail
)
for /f "delims=" %%v in ('%PY% --version') do echo 使用 %%v
echo.

rem --- 3. 安裝需要的套件 ---
echo 正在檢查並安裝需要的套件（第一次會比較久）...
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo [錯誤] 套件安裝失敗。請確認電腦有連上網路，再重新雙擊 run.bat。
  goto :fail
)

rem --- 4. 啟動網站 ---
if "%PORT%"=="" set "PORT=5000"
echo.
echo 網站啟動中：請用瀏覽器打開 http://127.0.0.1:%PORT%
echo 要關閉網站，直接關掉這個黑色視窗即可。
echo.
if not defined HAN_NO_BROWSER start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:%PORT%"
%PY% app.py
echo.
echo [網站已停止] 如果上面有錯誤訊息，請把這個視窗截圖給技術人員。
echo 常見原因：網址 %PORT% 已被其他程式使用（例如已經開了另一個 run.bat）。

:fail
echo.
pause
exit /b 1
