# HAN REJUVE 上線教學（Render）

網站放在 Render 的新加坡主機，資料庫與照片存在「永久硬碟」上。
之後只要把程式推到 GitHub，網站就會**自動更新**，不用登入主機操作。

**費用**：約 USD 7.25／月（主機 Starter USD 7 ＋ 1GB 硬碟 USD 0.25），以 https://render.com/pricing 為準。
免費方案不能掛硬碟、也不能寄 Gmail 驗證信，所以要用付費的 Starter。

整個過程大約 20 分鐘，照著做即可。

---

## 第 1 步：在舊網站下載備份（把資料搬過去用）
1. 在自己電腦上打開網站，用管理員登入。
2. 後台 →「營業設定」→ 最下面「資料備份與還原」→ 按 **下載備份**。
3. 會下載一個 `hanrejuve-backup-日期.zip`，先存好。

> 從這一刻起，請不要再用電腦上的網站接受預約，避免資料沒搬到。

---

## 第 2 步：註冊 Render
1. 打開 https://render.com/ ，按 **Get Started**。
2. 選 **GitHub** 登入（用你放專案的 GitHub 帳號），照畫面授權。
3. 依指示加入付款方式（信用卡），Starter 方案需要付費。

---

## 第 3 步：建立網站（Blueprint 一次設定好）
1. Render 後台右上角按 **New** → **Blueprint**。
2. 選擇 **dukeyee/HanRejuve** 專案（看不到的話，按 *Configure account* 讓 Render 存取這個專案）。
3. Render 會讀取專案裡的 `render.yaml`，自動設定：新加坡主機、馬來西亞時區、HTTPS、1GB 永久硬碟。
4. 畫面會要你填兩個值：
   | 欄位 | 填什麼 |
   |---|---|
   | `HAN_ADMIN_PASSWORD` | 第一次登入用的管理員密碼（自己想一組，長一點） |
   | `SMTP_PASSWORD` | Gmail 應用程式密碼（就是 `email_settings.txt` 裡那 16 個字母） |
5. 按 **Apply**，等它建置，約 3～5 分鐘。看到 **Live** 就完成了。

網址會是 `https://hanrejuve.onrender.com`（或 Render 顯示的網址）。

---

## 第 4 步：把資料還原到新網站
1. 打開新網址，用管理員登入：
   - Email：`hanrejuve2026@gmail.com`
   - 密碼：第 3 步填的 `HAN_ADMIN_PASSWORD`
2. 後台 →「營業設定」→「資料備份與還原」→ 選第 1 步下載的 `.zip` → 按 **還原備份** → 確定。
3. 還原後會自動登出。用**你原本的管理員帳號密碼**重新登入（備份裡的那組）。
4. 檢查會員、預約、優惠券、海報、客服訊息是否都在。
5. 用另一個信箱註冊一次，確認驗證信有寄到。

---

## 之後：更新網站
程式推到 GitHub 的 `main` 之後，Render 會自動重新部署（約 3 分鐘），資料不受影響。
在 Render 網站頁面的 **Events** 可以看到進度。

## 之後：備份
- Render 會替永久硬碟做每日快照（可在 Disk 頁面查看）。
- 另外建議**每個月**到「營業設定」按 **下載備份**，存在自己的電腦或雲端硬碟。

## 之後：使用自己的網址
1. 在網域商（例如 Exabytes、Namecheap、GoDaddy）購買網址，例如 `hanrejuve.com`。
2. Render 網站頁面 → **Settings** → **Custom Domains** → 新增 `www.hanrejuve.com`。
3. 照 Render 顯示的說明，到網域商的 DNS 設定新增一筆 **CNAME**（名稱 `www`，內容是 Render 給的網址）。
4. 等 DNS 生效後，Render 會自動提供免費 HTTPS。

## 需要修改設定時
Render 網站頁面 → **Environment**：
- 換 Gmail 應用程式密碼：改 `SMTP_PASSWORD`
- `HAN_ADMIN_PASSWORD` 只在**資料庫還沒有管理員時**使用一次；之後改密碼請到網站的「我的帳號」。

修改後按 **Save Changes**，網站會自動重新啟動。

## 出問題時
- 網站頁面 → **Logs** 可以看到錯誤訊息，把最後幾行複製下來就能找出原因。
- 網站打不開：先看 **Events** 是不是還在部署中。

---

## 上線前的安全檢查
- [ ] 管理員密碼換成**長一點、不規則**的密碼
- [ ] 備份檔含有客人個資，請妥善保管，不要傳給別人
- [ ] GitHub 專案建議改成 **Private**（Render 一樣可以讀取）

---

### 附錄：用 PythonAnywhere
如果之後想改用 PythonAnywhere（USD 10／月），啟動檔範本在 `deploy/pythonanywhere_wsgi.py`，
資料一樣用「下載備份／還原備份」搬移。
