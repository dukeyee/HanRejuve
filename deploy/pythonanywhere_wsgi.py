# PythonAnywhere 的 WSGI 設定檔範本
#
# 用法：PythonAnywhere「Web」頁面 → 點 WSGI configuration file 的連結，
#       把裡面原本的內容全部刪掉，貼上這個檔案的內容，
#       再把下面的 YOUR_USERNAME 換成你的 PythonAnywhere 帳號名稱，存檔後按 Reload。

import os
import sys

PROJECT_DIR = "/home/YOUR_USERNAME/HanRejuve"

os.environ["TZ"] = "Asia/Kuala_Lumpur"   # 馬來西亞時間（預約時段用）
os.environ["HAN_HTTPS"] = "1"            # 網站使用 HTTPS：登入狀態只走加密連線

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

from app import app as application  # noqa: E402
