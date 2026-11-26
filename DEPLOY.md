# HAN REJUVE 上線教學（PythonAnywhere）

網站程式和 SQLite 資料庫放在同一台主機上，檔案會永久保存。
整個過程大約 30 分鐘，**不需要會寫程式**，照著做即可。

> 下面所有的 `YOUR_USERNAME` 都要換成你在 PythonAnywhere 註冊的帳號名稱。

---

## 第 0 步：選方案

| 方案 | 費用 | 網址 | 適合 |
|---|---|---|---|
| Beginner（免費） | 0 | `YOUR_USERNAME.pythonanywhere.com` | 先試用、給朋友看 |
| Hacker（付費） | 約 USD 5／月 | 可用自己的網址，例如 `www.hanrejuve.com` | **正式營業** |

免費方案的限制：
- 每 3 個月要登入一次、按「Run until 3 months from today」延長，不然網站會暫停。
- 對外連線有限制，若驗證信寄不出去，就需要升級付費方案。

建議先用免費方案練習一次，確定沒問題再升級。升級後資料都會保留。

---

## 第 1 步：註冊帳號
1. 打開 https://www.pythonanywhere.com/ ，按 **Pricing & signup**。
2. 選方案，註冊帳號（記住你的帳號名稱 = `YOUR_USERNAME`）。

---

## 第 2 步：下載程式到主機
1. 登入後，點上方的 **Consoles** → **Bash**，會打開一個黑色的指令視窗。
2. 依序貼上下面兩行，每貼一行按 Enter，等它跑完再貼下一行：
   ```
   git clone https://github.com/dukeyee/HanRejuve.git
   ```
   ```
   cd HanRejuve && python3.11 -m pip install --user -r requirements.txt
   ```
   看到 `Successfully installed ...` 就完成了。

> 如果專案在 GitHub 上是 **Private**，第一行會要求登入 GitHub：
> 帳號輸入 GitHub 帳號，密碼要用 GitHub 的「Personal access token」（不是登入密碼）。

---

## 第 3 步：建立網站
1. 點上方的 **Web** → **Add a new web app** → **Next**。
2. 選 **Manual configuration**（不要選 Flask）。
3. 選 **Python 3.11**（要和第 2 步指令裡的 `python3.11` 一樣），按 **Next**。
4. 建好後，在 Web 頁面設定：
   - **Source code**：`/home/YOUR_USERNAME/HanRejuve`
   - **Working directory**：`/home/YOUR_USERNAME/HanRejuve`
   - **Static files**：按 *Enter URL*，URL 填 `/static/`，Directory 填 `/home/YOUR_USERNAME/HanRejuve/static`
   - **Force HTTPS**：打開（Enabled）

---

## 第 4 步：設定啟動檔（WSGI）
1. 在 Web 頁面找到 **WSGI configuration file**，點那個連結。
2. 把裡面**全部刪掉**，貼上專案裡 `deploy/pythonanywhere_wsgi.py` 的內容。
3. 把 `YOUR_USERNAME` 換成你的帳號名稱。
4. 按右上角 **Save**。

這個檔案已經幫你設定好：**馬來西亞時區**、**HTTPS 安全登入**。

---

## 第 5 步：上傳你的資料（重要）
GitHub 上只有程式，**沒有**你的會員、預約、密碼等資料。這些要從你的電腦上傳：

點上方 **Files** → 進入 `HanRejuve` 資料夾 → 用 **Upload a file** 上傳：

| 檔案 | 內容 | 沒上傳會怎樣 |
|---|---|---|
| `hanrejuve.db` | 會員、預約、優惠券、客服訊息 | 網站會變成全新、空的 |
| `email_settings.txt` | Gmail 寄信密碼 | 驗證信寄不出去（變成測試模式） |
| `secret_key.txt` | 登入加密金鑰 | 會員需要重新登入（不影響資料） |

另外兩個資料夾裡的圖片也要上傳到主機上**相同的位置**：
- `static/uploads/` 裡的檔案（你在後台上傳的海報）
- `private_uploads/booking_photos/` 裡的檔案（服務紀錄照片，沒有的話可以跳過）

> 上傳 `hanrejuve.db` 之前，請先**關掉自己電腦上的網站**，確保資料是最新的。
> 上線之後，請**只用雲端的網站**，不要再用電腦上的版本，避免兩邊資料不一致。

---

## 第 6 步：啟動網站
1. 回到 **Web** 頁面，按最上面綠色的 **Reload**。
2. 打開 `https://YOUR_USERNAME.pythonanywhere.com`，看到網站就成功了！🎉
3. 用管理員帳號登入，檢查會員、預約、優惠券是否都在。
4. 用另一個信箱註冊一次，確認驗證信有寄到。

**如果出現錯誤畫面：** Web 頁面下方有 **Error log**，點開把最後幾行複製下來，就能找出原因。

---

## 之後：更新網站
程式有更新、推到 GitHub 之後，在 PythonAnywhere 的 Bash 執行：
```
cd ~/HanRejuve && git pull
```
再到 **Web** 頁面按 **Reload**。資料庫和上傳的圖片不會被影響。

---

## 之後：每天自動備份資料庫
點上方 **Tasks**，在 *Scheduled tasks* 新增一個每天執行的工作（時間是 UTC，例如 `16:00` = 馬來西亞凌晨 0 點），指令貼上：
```
mkdir -p ~/backups && sqlite3 ~/HanRejuve/hanrejuve.db ".backup '/home/YOUR_USERNAME/backups/hanrejuve-$(date +%F).db'" && find ~/backups -name 'hanrejuve-*.db' -mtime +30 -delete
```
每天會在 `backups` 資料夾留一份，保留 30 天。
也建議每個月到 **Files** 把最新的備份**下載到自己電腦**一份。

---

## 之後：使用自己的網址（需要付費方案）
1. 在網域商（例如 Exabytes、Namecheap、GoDaddy）購買網址，例如 `hanrejuve.com`。
2. 在 PythonAnywhere **Web** 頁面新增網站時，網址填 `www.hanrejuve.com`（或把現有網站改成這個網址）。
3. Web 頁面會顯示一個 **CNAME**（例如 `webapp-123456.pythonanywhere.com`），
   到網域商的 DNS 設定新增一筆：名稱 `www`、類型 `CNAME`、內容填這個值。
4. 等 DNS 生效（幾分鐘到幾小時），在 Web 頁面的 **HTTPS certificate** 選 **Let's Encrypt**，自動取得免費的 HTTPS 憑證。

---

## 上線前的安全檢查
- [ ] 管理員密碼換成**長一點、不規則**的密碼（到「我的帳號」修改）
- [ ] `email_settings.txt`、`secret_key.txt`、`hanrejuve.db` **不要**放到 GitHub 或傳給別人
- [ ] GitHub 專案建議改成 **Private**
- [ ] 已設定每日備份
