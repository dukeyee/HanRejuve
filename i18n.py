"""中文 → English 介面翻譯。

切換為英文時，頁面送出前會經過 translate_html()：
  1. 先整句比對 EXACT
  2. 再套用 PATTERNS（含數字、名稱的句子）
  3. 最後以 PHRASES 由長到短替換剩下的詞
表單欄位的值（input value、textarea）不會被翻譯，避免英文被存回資料庫。
新增中文介面文字時，請在這裡加上對應的英文。
"""
import html
import re

WEEKDAYS = {"一": "Mon", "二": "Tue", "三": "Wed", "四": "Thu", "五": "Fri", "六": "Sat", "日": "Sun"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ---------------------------------------------------------------- 詞彙（也用於部分比對，由長到短替換）
PHRASES = {
    # ---- 服務項目與優惠券（目前資料庫中的名稱）
    "鑽石嬰兒肌水光煥膚": "Diamond Baby Skin Glow",
    "9D黃金炮 新人體驗": "9D Golden Probe New Customer Exclusive Price",
    "新粉·體驗卡": "New Customer Experience Card",
    "外泌體生髮": "Exosome Hair Regrowth",
    "穴位瘦全身": "Acu-Point Weight Loss",
    "雙下巴溶脂": "Double Chin Fat Dissolving",
    "嬰兒水光針": "Baby Hydra Injection",
    "愛馬仕水光": "Hermès Hydra Glow",
    "Serena緊緻提升": "Serena Firming Lift",
    "9D黃金炮": "9D Golden Probe",
    "AI量子儀": "AI Quantum Device",
    "輕抗衰": "Light Anti-Aging",
    "膠原支架": "Collagen Scaffold",
    "祛抬頭紋": "Forehead Wrinkle Removal",
    "祛魚尾紋": "Crow's Feet Removal",
    "祛川字紋": "Frown Line Removal",
    "淚溝激活": "Tear Trough Rejuvenation",
    "額頭精雕": "Forehead Contouring",
    "V臉": "V-Face",
    "臉部提升": "Face Lift",
    "祛法令紋": "Smile Line Removal",
    "祛嘴角肉": "Mouth Corner Contouring",
    "皮膚管理": "Skin Management",
    "凹凸洞": "Acne Scar Repair",
    "淡化疤印": "Scar Fading",
    "淡化黑斑": "Dark Spot Fading",
    "身材管理": "Body Contouring",
    "局部溶脂": "Targeted Fat Dissolving",
    "十八穴位": "18-Acupoint Therapy",
    "減啤酒肚": "Belly Slimming",
    "躺瘦三寶": "Lie-Down Slimming Trio",
    "家醫美": "Home Aesthetics",
    "七日白": "7-Day Whitening",
    "貴婦霜": "Luxury Cream",
    "潔臉凝膠": "Cleansing Gel",
    "醫用面膜": "Medical Face Mask",
    "其他": "Others",

    # ---- 狀態
    "待確認": "Pending",
    "已確認": "Confirmed",
    "已完成": "Completed",
    "已取消": "Cancelled",
    "未到店": "No-show",

    # ---- 導覽
    "服務項目": "Treatments",
    "立即預約": "Book Now",
    "我的預約": "My Bookings",
    "收件箱": "Inbox",
    "優惠券": "Coupons",
    "我的優惠券": "My Coupons",
    "我的帳號": "My Account",
    "管理後台": "Admin",
    "登出": "Log out",
    "會員登入": "Log in",
    "註冊": "Sign up",
    "總覽": "Dashboard",
    "預約管理": "Bookings",
    "會員": "Members",
    "公告信件": "Messages",
    "營業設定": "Settings",
    "前台網站": "Public site",
    "選單": "Menu",

    # ---- 首頁
    "輕醫美 · 抗衰老 · 煥活新生": "Aesthetics · Anti-Aging · Rejuvenation",
    "科技煥膚 · 定制之美 · 由內而外": "Tech Skin Renewal · Tailored Beauty · From Within",
    "立即線上預約": "Book Online Now",
    "專業團隊": "Expert Team",
    "經驗豐富 · 一對一定制": "Experienced · One-to-one tailored care",
    "安全有效": "Safe and Effective",
    "正規儀器 · 安心變美": "Certified equipment · Peace of mind",
    "品質服務": "Quality Service",
    "貼心服務 · 全程陪護": "Caring service · With you all the way",
    "效果保障": "Proven Results",
    "科學方案 · 效果看得見": "Science-based plans · Visible results",
    "目前沒有開放預約的服務項目。": "No treatments are open for booking right now.",
    "營業時間": "Opening hours",
    "預約專線": "Booking hotline",
    "價格洽詢": "Price on request",
    "預約": "Book",

    # ---- 登入 / 註冊 / 帳號
    "註冊會員": "Sign Up",
    "還不是會員？": "Not a member yet?",
    "立即註冊": "Sign up now",
    "已經是會員？": "Already a member?",
    "登入": "Log in",
    "密碼": "Password",
    "確認密碼": "Confirm password",
    "姓名": "Name",
    "手機號碼（馬來西亞）": "Mobile number (Malaysia)",
    "手機號碼": "Mobile number",
    "註冊並開始預約": "Sign up and start booking",
    "個人資料": "Profile",
    "儲存": "Save",
    "修改密碼": "Change Password",
    "目前密碼": "Current password",
    "新密碼": "New password",
    "確認新密碼": "Confirm new password",
    "更新密碼": "Update password",

    # ---- 預約
    "線上預約": "Online Booking",
    "選擇服務": "Choose a treatment",
    "點選主項目展開，再選擇想做的子項目": "Tap a category to expand it, then choose a treatment",
    "使用優惠券（選填）": "Use a coupon (optional)",
    "不使用優惠券": "No coupon",
    "此券不適用於目前選擇的項目": "This coupon does not apply to the selected treatment",
    "選擇日期": "Choose a date",
    "其他日期：": "Other date:",
    "選擇時間": "Choose a time",
    "備註（選填）": "Notes (optional)",
    "例如：肌膚狀況、過敏史、想指定的美容師…": "e.g. skin condition, allergies, preferred beautician…",
    "確認預約": "Confirm booking",
    "尚未選擇服務": "No treatment selected",
    "預約須知": "Booking Notice",
    "新山區以外的客戶，最少要提前兩個星期預約": "Customers outside the Johor Bahru area must book at least two weeks in advance",
    "我已閱讀並確認以上內容": "I have read and confirm the above",
    "返回修改": "Go back",
    "＋ 新增預約": "+ New booking",
    "即將到來": "Upcoming",
    "目前沒有預約。": "You have no bookings.",
    "馬上預約一次放鬆時光 →": "Book some me-time now →",
    "歷史紀錄": "History",
    "取消": "Cancel",
    "確定要取消這筆預約嗎？": "Cancel this booking?",
    "分鐘": "min",

    # ---- 收件箱 / 優惠券
    "全部標示已讀": "Mark all as read",
    "目前沒有信件": "No messages yet",
    "公告": "Announcement",
    "← 收件箱": "← Inbox",
    "隨信附上的優惠券": "Coupons included",
    "感謝你註冊成為會員，以下是專屬新人體驗券。預約時選擇優惠券即可享有體驗價。":
        "Thank you for joining! Here are your exclusive new-member trial coupons. Choose a coupon when booking to get the trial price.",
    "體驗價": "Trial price",
    "適用項目：": "Valid for: ",
    "適用項目": "Valid for",
    "適用：": "Valid for: ",
    "立即使用": "Use now",
    "已使用": "Used",
    "已過期": "Expired",
    "永久有效": "No expiry",
    "可使用": "Available",
    "打造媽生幼態臉，以下項目任選其中一個：淚溝激活、抬頭紋去皺、激活印堂凹陷、魚尾紋去皺、雙下巴脂肪剝離術。雙人行 RM788。":
        "Create A Natural \"Baby Face\". Single Session RM499 / For Two RM788. Tear Trough Rejuvenation, Activates Sunken Glabella, Forehead Wrinkle Removal, Crow's Feet Removal, Double Chin Fat Dissolving.",
    "新客專享・多重功效體驗卡。雙重高效補水美肌護理，煥發水光透亮肌。每人僅限體驗一次。":
        "New Customer Exclusive • Benefits • Trial Card. Dual High-Efficiency Hydration Glow Treatment. Reverse Aging Glow. Limited to one per person.",
    "黑科技煥膚・重塑年輕肌。去皺抗衰、補水嫩膚、緊緻提拉。":
        "World's First 9D Golden Probe. Black-Tech Skin Rejuvenation for Younger, Firmer Skin. Anti-Aging & Repair, Deep Hydration, Firming & Lifting, Needle-Free, Pain-Free, No Downtime.",

    # ---- 錯誤頁
    "回到首頁": "Back to home",
    "找不到此頁面": "Page not found",
    "您沒有權限瀏覽此頁面": "You do not have permission to view this page",
    "表單已過期，請重新整理頁面後再試": "This form has expired. Please refresh the page and try again.",
    "請求有誤": "Bad request",
    "發生錯誤": "Something went wrong",

    # ---- flash 訊息
    "請先登入會員": "Please log in first",
    "已登出": "You have logged out",
    "Email 或密碼錯誤": "Incorrect email or password",
    "請填寫所有欄位": "Please fill in all fields",
    "Email 格式不正確，例如 name@gmail.com": "Invalid email address, e.g. name@gmail.com",
    "手機號碼格式不正確，請輸入馬來西亞手機號碼，例如 12-345 6789": "Invalid mobile number. Please enter a Malaysian mobile number, e.g. 12-345 6789",
    "請輸入馬來西亞手機號碼，例如 12-345 6789": "Please enter a Malaysian mobile number, e.g. 12-345 6789",
    "此手機號碼已註冊，請直接登入": "This mobile number is already registered. Please log in.",
    "密碼至少需要 6 個字元": "Password must be at least 6 characters",
    "兩次輸入的密碼不一致": "Passwords do not match",
    "此 Email 已註冊，請直接登入": "This email is already registered. Please log in.",
    "請選擇服務、日期與時間": "Please choose a treatment, date and time",
    "請先閱讀預約須知並勾選確認": "Please read the booking notice and tick to confirm",
    "預約成功！": "Booking received! ",
    "已為您確認時段。": "Your time slot is confirmed.",
    "我們確認後會再與您聯繫。": "We will contact you once it is confirmed.",
    "此時段已無法預約，請選擇其他時間": "This time slot is no longer available. Please choose another time.",
    "此優惠券無法用於這個項目，或已使用／已過期": "This coupon cannot be used for this treatment, or it has been used or has expired",
    "找不到此服務項目": "Treatment not found",
    "此預約無法取消": "This booking cannot be cancelled",
    "預約已取消": "Booking cancelled",
    "，優惠券已退回「我的優惠券」": ". Your coupon has been returned to My Coupons",
    "姓名不能空白": "Name cannot be empty",
    "資料已更新": "Profile updated",
    "目前密碼不正確": "Current password is incorrect",
    "新密碼至少需要 6 個字元": "New password must be at least 6 characters",
    "兩次輸入的新密碼不一致": "New passwords do not match",
    "密碼已更新": "Password updated",
    "參數錯誤": "Invalid parameters",
    "店休日": "Closed",

    # ---- 後台：總覽 / 預約
    "＋ 新增預約（電話/現場）": "+ New booking (phone / walk-in)",
    "今日預約": "Today",
    "待確認": "Pending",
    "未來 7 天": "Next 7 days",
    "會員人數": "Members",
    "本月已完成營收": "Revenue this month (completed)",
    "今日行程": "Today's schedule",
    "查看全部 →": "View all →",
    "待確認預約": "Pending bookings",
    "沒有符合條件的預約": "No matching bookings",
    "今天": "Today",
    "全部": "All",
    "日期": "Date",
    "狀態": "Status",
    "全部狀態": "All statuses",
    "搜尋顧客": "Search customer",
    "姓名 / 電話 / Email": "Name / phone / email",
    "篩選": "Filter",
    "← 前一天": "← Previous day",
    "後一天 →": "Next day →",
    "編號": "No.",
    "時間": "Time",
    "顧客": "Customer",
    "電話": "Phone",
    "服務": "Treatment",
    "操作": "Actions",
    "確認": "Confirm",
    "完成": "Complete",
    "(非會員)": "(guest)",
    "預約內容": "Booking details",
    "價格": "Price",
    "顧客備註": "Customer notes",
    "建立時間": "Created",
    "查看會員紀錄 →": "View member record →",
    "變更狀態": "Change status",
    "內部備註": "Internal notes",
    "只有管理員看得到，例如：使用產品、肌膚狀況、負責美容師…": "Only admins can see this, e.g. products used, skin condition, beautician…",
    "儲存備註": "Save notes",
    "新增預約": "New Booking",
    "適用於電話或現場預約。若電話號碼與已註冊會員相同，會自動連結到該會員。後台可選擇任何有空位的時段（不受提前預約限制）。":
        "For phone or walk-in bookings. If the phone number matches a registered member, the booking is linked to that member. Admins can pick any free slot (advance-booking limits do not apply).",
    "顧客姓名": "Customer name",
    "服務項目": "Treatments",
    "建立預約（直接確認）": "Create booking (confirmed)",
    "備註": "Notes",
    "請完整填寫顧客姓名、電話、服務、日期與時間": "Please fill in the customer name, phone, treatment, date and time",
    "（已連結到會員）": " (linked to member)",
    "該時段已額滿，無法恢復此預約": "That time slot is full. The booking cannot be restored.",
    "已將此預約使用的優惠券退回給會員": "The coupon used for this booking has been returned to the member",
    "此預約原本的優惠券已被使用，恢復後改以原價計算": "The original coupon has already been used elsewhere, so this booking is now at full price",
    "優惠券": "Coupon",
    "原價": "list price",

    # ---- 後台：服務項目
    "＋ 新增子項目": "+ Add treatment",
    "＋ 新增主項目": "+ Add category",
    "主項目名稱": "Category name",
    "排序（數字小的排前面）": "Order (lower numbers first)",
    "簡介（選填）": "Description (optional)",
    "新增主項目": "Add category",
    "編輯主項目": "Edit category",
    "名稱": "Name",
    "排序": "Order",
    "簡介": "Description",
    "開放線上預約": "Open for online booking",
    "刪除主項目": "Delete category",
    "子項目": "Treatment",
    "時長": "Duration",
    "預約數": "Bookings",
    "開放": "Open",
    "停用": "Disabled",
    "編輯": "Edit",
    "尚無子項目": "No treatments yet",
    "← 服務項目": "← Treatments",
    "編輯服務": "Edit Treatment",
    "新增服務": "Add Treatment",
    "所屬主項目": "Category",
    "（無主項目）": "(no category)",
    "子項目名稱": "Treatment name",
    "介紹": "Description",
    "時長（分鐘）": "Duration (minutes)",
    "價格（0 = 顯示「價格洽詢」）": "Price (0 = show Price on request)",
    "刪除": "Delete",
    "服務項目已儲存": "Treatment saved",
    "服務已刪除": "Treatment deleted",
    "此服務已有預約紀錄，已改為「停用」而非刪除": "This treatment has bookings, so it was disabled instead of deleted",
    "請先刪除或移走這個主項目下的子項目": "Please delete or move the treatments in this category first",
    "主項目已刪除": "Category deleted",
    "主項目已更新": "Category updated",
    "服務分成「主項目」和「子項目」。客人點開主項目後選擇子項目預約。主項目下只有一個同名子項目時，客人可以直接選擇，不用展開。價格設為 0 會顯示「價格洽詢」。":
        "Treatments are grouped into categories. Customers open a category, then pick a treatment. A category with a single treatment of the same name can be picked directly. A price of 0 shows Price on request.",

    # ---- 後台：會員
    "會員列表": "Members",
    "← 會員列表": "← Members",
    "搜尋姓名 / 電話 / Email": "Search name / phone / email",
    "搜尋": "Search",
    "預約次數": "Bookings",
    "最近預約": "Last booking",
    "加入日期": "Joined",
    "沒有符合的會員": "No matching members",
    "累計消費": "Total spent",
    "（已完成）": " (completed)",
    "帳號操作": "Account actions",
    "重設密碼": "Reset password",
    "確定要重設此會員的密碼？": "Reset the password for this member?",
    "設為管理員": "Make admin",
    "移除管理員權限": "Remove admin rights",
    "確定要變更管理員權限？": "Change admin rights?",
    "管理員": "Admin",
    "預約紀錄": "Booking history",
    "領取日": "Issued",
    "到期日": "Expires",
    "永久": "No expiry",
    "尚未領取優惠券": "No coupons yet",
    "不能變更自己的管理員權限": "You cannot change your own admin rights",
    "權限已更新": "Permissions updated",

    # ---- 後台：設定
    "店家資訊": "Shop information",
    "店名": "Shop name",
    "標語": "Tagline",
    "預約電話": "Booking phone",
    "貨幣符號": "Currency symbol",
    "地址": "Address",
    "營業時間與預約規則": "Hours and booking rules",
    "開店時間": "Opening time",
    "打烊時間": "Closing time",
    "療程須在打烊前結束": "Treatments must end before closing",
    "時段間隔（分鐘）": "Slot interval (minutes)",
    "同時段可服務人數": "Customers per time slot",
    "通常等於美容師或床位數": "Usually the number of beauticians or beds",
    "可預約未來天數": "Days bookable in advance",
    "0 = 不限制，任何日期都可以預約": "0 = no limit, any date can be booked",
    "最少提前預約（小時）": "Minimum notice (hours)",
    "會員可取消期限（預約前幾小時）": "Member cancellation deadline (hours before)",
    "新預約自動確認": "Auto-confirm new bookings",
    "預約須知（客人按「確認預約」時跳出，需勾選確認）": "Booking notice (shown when customers confirm, must be ticked)",
    "留白則不跳出": "Leave empty to disable",
    "每週固定公休": "Weekly closing days",
    "儲存設定": "Save settings",
    "特定店休日": "Special closing days",
    "原因（顧客會看到）": "Reason (shown to customers)",
    "例如：春節休息": "e.g. Chinese New Year",
    "新增": "Add",
    "移除": "Remove",
    "尚未設定店休日": "No special closing days",
    "設定已儲存": "Settings saved",
    "已移除店休日": "Closing day removed",
    "打烊時間必須晚於開店時間": "Closing time must be after opening time",
    "可預約天數不能為負數": "Days in advance cannot be negative",
    "時數不能為負數": "Hours cannot be negative",

    # ---- 後台：公告與優惠券
    "＋ 發佈活動公告": "+ Post announcement",
    "🎫 發送優惠券": "🎫 Send coupons",
    "發送優惠券": "Send Coupons",
    "活動公告": "Announcements",
    "發佈時間": "Posted",
    "標題": "Title",
    "圖片": "Image",
    "已讀人數": "Read by",
    "確定刪除這則公告？會員將不再看到。": "Delete this announcement? Members will no longer see it.",
    "尚未發佈公告": "No announcements yet",
    "個人信件": "Personal messages",
    "收件會員": "Recipient",
    "附券": "Coupons",
    "已讀": "Read",
    "未讀": "Unread",
    "尚無個人信件": "No personal messages yet",
    "← 公告信件": "← Messages",
    "發佈活動公告": "Post Announcement",
    "公告會出現在所有會員的收件箱（包含之後才註冊的新會員）。簡體字會自動轉成繁體。":
        "Announcements appear in every member's inbox, including members who join later. Simplified Chinese is converted to Traditional automatically.",
    "例如：12 月聖誕限定優惠": "e.g. December Christmas special",
    "內容": "Content",
    "活動內容、日期、注意事項…": "Details, dates, terms…",
    "活動海報（選填）": "Poster (optional)",
    "發佈公告": "Post announcement",
    "請填寫標題": "Please enter a title",
    "公告已發佈，所有會員都會在收件箱看到": "Announcement posted. All members will see it in their inbox.",
    "信件已刪除（已發出的優惠券仍保留在會員帳戶中）": "Message deleted (coupons already sent stay in member accounts)",
    "＋ 新增優惠券": "+ New coupon",
    "勾選「新人禮」的優惠券，會在會員註冊時自動放進他的收件箱。會員預約時選擇優惠券，就以體驗價計算；預約取消時優惠券自動退回。":
        "Coupons marked Welcome Gift are sent automatically to new members. Members choose a coupon when booking to get the trial price; cancelling the booking returns the coupon.",
    "海報": "Poster",
    "有效期": "Validity",
    "設定": "Options",
    "已發 / 已用": "Sent / Used",
    "新人禮": "Welcome gift",
    "每人限一次": "Once per member",
    "發送": "Send",
    "尚無優惠券": "No coupons yet",
    "← 優惠券": "← Coupons",
    "新增優惠券": "New Coupon",
    "編輯優惠券": "Edit Coupon",
    "例如：新粉·體驗卡": "e.g. New Customer Experience Card",
    "說明": "Description",
    "有效天數（領取後幾天內可用）": "Valid for (days after issue)",
    "0 = 永久有效": "0 = never expires",
    "可使用此券的項目（客人選擇其中一個）": "Treatments this coupon can be used for (customer picks one)",
    "海報圖片": "Poster image",
    "移除目前圖片": "Remove current image",
    "上傳新圖片會取代原本的圖片": "Uploading a new image replaces the current one",
    "新人禮：新會員註冊時自動贈送": "Welcome gift: sent automatically when a member signs up",
    "每人限領一次": "Limit one per member",
    "啟用（停用後不能再發送，已發出的券仍可使用）": "Active (when disabled it cannot be sent, but coupons already sent stay valid)",
    "優惠券已儲存": "Coupon saved",
    "請填寫名稱、體驗價與有效天數": "Please enter a name, trial price and validity",
    "請至少選擇一個可使用此券的項目": "Please choose at least one treatment for this coupon",
    "優惠券會隨一封信寄到會員的收件箱，並存入他的「我的優惠券」。": "The coupon is sent with a message to the member's inbox and saved in My Coupons.",
    "請選擇": "Please choose",
    "還沒有啟用中的優惠券，請先到「優惠券」新增。": "There are no active coupons. Please create one under Coupons first.",
    "收件人": "Recipients",
    "指定會員": "Selected members",
    "信件標題": "Message title",
    "留白則自動使用「送你一張優惠券：券名」": "Leave empty to use: A coupon for you: coupon name",
    "信件內容（選填）": "Message (optional)",
    "請選擇要發送的優惠券": "Please choose a coupon to send",
    "請選擇收件會員": "Please choose recipients",
    "圖片只接受 JPG、PNG、WEBP、GIF 格式": "Images must be JPG, PNG, WEBP or GIF",
    "檔案太大，圖片請小於 10MB": "File too large. Images must be under 10MB",
    "JPG / PNG / WEBP，10MB 以內": "JPG / PNG / WEBP, up to 10MB",
    "我的優惠券": "My Coupons",
    "預約前": "before",
    "非會員": "guest",
    # 無創穴位瘦身（依英文海報）
    "無創穴位瘦身": "Acu-Point Weight Loss",
    "精準科技・安全溶脂・塑造自信曲線。一次體驗 RM788｜四次療程 RM2688（一個療程）。送價值 RM988 一次雙下巴溶脂。":
        "Precision Tech · Safe Fat Dissolving · Sculpt Confident Curves. One-Time Trial RM788 / 4-Session Course RM2688 (One Course). FREE: Worth RM988 One Double Chin Fat Dissolving.",
    "服務分成「主項目」和「子項目」。客人點開主項目後選擇子項目預約。主項目下只有一個同名子項目時，客人可以直接選擇，不用展開。價格不會顯示給客人，只用於營收統計。":
        "Treatments are grouped into categories. Customers open a category, then pick a treatment. A category with a single treatment of the same name can be picked directly. Prices are not shown to customers and are only used for revenue reports.",
    "刪除優惠券": "Delete coupon",
    # 線上客服
    "線上客服": "Live Chat",
    "營業時間內我們會盡快回覆您": "We will reply as soon as possible during opening hours",
    "您好！有任何關於療程、預約或優惠券的問題，都可以在這裡留言給我們。":
        "Hello! Leave us a message here about treatments, bookings or coupons.",
    "輸入訊息…": "Type a message…",
    "輸入訊息": "Type a message",
    "傳送": "Send",
    "關閉": "Close",
    "客服訊息": "Live Chat",
    "新訊息每幾秒自動更新": "New messages appear automatically every few seconds",
    "載入中…": "Loading…",
    "請從左邊選擇一位會員": "Choose a member on the left",
    "選擇對話後，訊息會顯示在這裡。": "Messages appear here after you choose a conversation.",
    "回覆訊息…（Enter 送出，Shift+Enter 換行）": "Reply… (Enter to send, Shift+Enter for a new line)",
    "回覆訊息": "Reply",
    "💬 傳訊息": "💬 Message",
    "傳送失敗，請再試一次": "Could not send. Please try again.",
    "還沒有客服訊息": "No chat messages yet",
    "你：": "You: ",
    "會員資料": "Member profile",
    "還沒有訊息，可以直接傳訊息給這位會員。": "No messages yet. You can message this member directly.",
    "請輸入訊息": "Please type a message",
    "訊息太長，請在 1000 字以內": "Message too long. Please keep it under 1000 characters.",
    "訊息傳送太頻繁，請稍後再試": "You are sending messages too quickly. Please wait a moment.",
    "無法使用客服": "Live chat is not available for this account",
    "沒有權限": "Not allowed",
    "找不到此會員": "Member not found",
    # 服務紀錄
    "服務紀錄": "Service record",
    "（客人在「我的預約」看得到）": "(visible to the customer in My Bookings)",
    "這是非會員預約，客人沒有帳號可以查看服務紀錄。": "This is a guest booking, so the customer has no account to view the record.",
    "給客人的備註": "Notes for the customer",
    "例如：今日療程內容、使用產品、居家保養建議、下次建議回診時間…": "e.g. treatment done today, products used, home care tips, suggested next visit…",
    "新增照片（可一次選多張）": "Add photos (you can select several)",
    "儲存服務紀錄": "Save service record",
    "確定要刪除這張照片？客人將不再看到。": "Delete this photo? The customer will no longer see it.",
    "刪除照片": "Delete photo",
    "照片已刪除": "Photo deleted",
    "服務紀錄已儲存": "Service record saved",
    "單張圖片請小於 15MB": "Each image must be under 15MB",
    "檔案太大，一次上傳的照片合計請小於 60MB，可以分幾次上傳": "Upload too large. Keep each upload under 60MB in total, or upload in several batches.",
    # Email 驗證
    "Email 驗證": "Email Verification",
    "驗證碼已寄到": "We sent a verification code to",
    "沒看到的話，請檢查「垃圾郵件」資料夾。": "If you do not see it, please check your spam folder.",
    "測試模式": "Test mode",
    "：網站尚未設定寄信，所以驗證碼直接顯示在這裡：": ": email sending is not set up yet, so the code is shown here:",
    "驗證碼": "Verification code",
    "完成驗證": "Verify",
    "重新寄送驗證碼": "Resend code",
    "秒後可以重新寄送": "seconds until you can resend",
    "Email 填錯了？": "Wrong email?",
    "正確的 Email": "Correct email",
    "更新並重新寄送": "Update and resend",
    "已驗證": "Verified",
    "未驗證": "Unverified",
    "手動驗證 Email": "Verify email manually",
    "確定要手動驗證這位會員的 Email？（會同時送出新人體驗券）": "Manually verify the email of this member? New-member coupons will also be sent.",
    "驗證信寄送失敗，請稍後按「重新寄送」再試一次": "The verification email could not be sent. Please press Resend later.",
    "驗證碼不正確，請再確認一次": "Incorrect code. Please check and try again.",
    "驗證碼已過期，請按「重新寄送」": "This code has expired. Please press Resend.",
    "輸錯太多次，請按「重新寄送」取得新的驗證碼": "Too many wrong attempts. Please press Resend to get a new code.",
    "驗證信寄送失敗，請稍後再試，或聯絡我們": "The verification email could not be sent. Please try again later or contact us.",
    "已重新寄送驗證碼": "A new code has been sent",
    "這就是目前的 Email": "That is already your current email",
    "Email 已更新，驗證碼已寄到新信箱": "Email updated. A code has been sent to the new address.",
    "Email 已更新，但驗證信寄送失敗，請稍後重新寄送": "Email updated, but the code could not be sent. Please press Resend later.",
    "已手動驗證此會員的 Email": "Email verified manually for this member",
    "中文海報": "Chinese poster",
    "英文海報（網站切換成英文時顯示）": "English poster (shown when the site is in English)",
    "沒有英文海報時，英文介面會顯示中文海報": "Without an English poster, the Chinese poster is shown in English mode",
    "切換到管理後台": "Switch to admin",
    "切換到前台網站": "Switch to public site",
    # 確認視窗（dialog.js）
    "請確認": "Please confirm",
    "返回": "Back",
    "上一張": "Previous",
    "下一張": "Next",
    "提示": "Notice",
    "確定": "OK",
    "確定要刪除此服務？（若已有預約紀錄，會改為停用）": "Delete this treatment? If it has bookings, it will be disabled instead.",
    # booking.js 的訊息
    "請先選擇服務項目": "Please choose a treatment first",
    "請選擇日期": "Please choose a date",
    "載入可預約時段…": "Loading available times…",
    "請選擇其他日期": "please choose another date",
    "這天已無可預約時段，請選擇其他日期": "No times left on this day. Please choose another date.",
    "無法載入時段，請重新整理頁面": "Could not load times. Please refresh the page.",
    "請選擇時間": "choose a time",
    "請選擇預約時間": "Please choose a time",
    "預計時長": "Est. duration",
    "預計時長（分鐘）": "Est. duration (minutes)",
    "參考價格": "Reference price",
    "不會顯示給客人，只用來計算這段時間是否還有空位": "Not shown to customers; only used to check whether a time slot is free",
    "不會顯示給客人，只用於後台營收統計（實際價格依現場而定）": "Not shown to customers; only used for revenue reports (actual price is decided in store)",
    "return confirm('確定要刪除此服務？（若已有預約紀錄，會改為停用）')": "return confirm('Delete this treatment? If it has bookings, it will be disabled instead.')",
    "服務分成「主項目」和「子項目」。客人點開主項目後選擇子項目預約。主項目下只有一個同名子項目時，客人可以直接選擇，不用展開。時長與價格不會顯示給客人：時長用來計算時段是否有空位，價格只用於營收統計。":
        "Treatments are grouped into categories. Customers open a category, then pick a treatment. A category with a single treatment of the same name can be picked directly. Duration and price are not shown to customers: duration is used to check free time slots, and price is only used for revenue reports.",
}

# ---------------------------------------------------------------- 含變數的句子
PATTERNS = [
    (r"確定要刪除優惠券「(.+?)」？(?:目前有 (\d+) 位會員持有還沒使用的這張券，會一併移除。)?已用在預約上的紀錄會保留。此操作無法復原。",
     lambda m: f"Delete coupon {m.group(1)}? "
               + (f"{m.group(2)} members hold an unused copy, which will also be removed. " if m.group(2) else "")
               + "Records already used for bookings are kept. This cannot be undone."),
    (r"優惠券「(.+?)」已刪除", r"Coupon \1 deleted"),
    (r"，並移除 (\d+) 位會員未使用的券", r"; \1 unused copies removed from members"),
    (r"例如療程前後對比照。每筆預約最多 (\d+) 張，目前 (\d+) 張。照片只有這位客人和管理員看得到。",
     r"e.g. before-and-after photos. Up to \1 photos per booking, currently \2. Only this customer and admins can see them."),
    (r"，新增 (\d+) 張照片", r", \1 photos added"),
    (r"每筆預約最多 (\d+) 張照片，目前已有 (\d+) 張", r"Up to \1 photos per booking; this booking already has \2"),
    (r"請到信箱查看 6 位數驗證碼（(\d+) 分鐘內有效）。", r"Check your inbox for the 6-digit code (valid for \1 minutes)."),
    (r"Email 驗證成功，歡迎加入 (.+?)，(.+?)！", r"Email verified. Welcome to \1, \2! "),
    (r"請等 (\d+) 秒後再重新寄送", r"Please wait \1 seconds before resending"),
    (r"請等 (\d+) 秒後再修改", r"Please wait \1 seconds before changing it"),
    (r"，並送出 (\d+) 張新人體驗券", r" and \1 new-member coupons were sent"),
    (r"（發給所有會員，共 (\d+) 位）", r"(sent to all \1 members)"),
    (r"設為「(.+?)」", r"Set to \1"),
    (r"← 回到 (\S+) 的預約", r"← Back to bookings on \1"),
    (r"^嗨，(.+?)！選擇想要的療程與時間，三步驟完成預約。$", r"Hi \1! Choose a treatment and time to book in 3 easy steps."),
    (r"歡迎加入 (.+?)！送你 (\d+) 張新人體驗券", r"Welcome to \1! Here are \2 new-member trial coupons"),
    (r"歡迎加入 (.+?)，(.+?)！", r"Welcome to \1, \2! "),
    (r"已送你 (\d+) 張新人體驗券，請到「收件箱」查看。", r"We have sent you \1 new-member trial coupons. Check your Inbox."),
    (r"送你一張優惠券：", r"A coupon for you: "),
    (r"已新增預約 #(\d+)", r"Booking #\1 created"),
    (r"預約 #(\d+) 已更新", r"Booking #\1 updated"),
    (r"^預約 #(\d+)$", r"Booking #\1"),
    (r"已發送給 (\d+) 位會員", r"Sent to \1 members"),
    (r"，(\d+) 位已領過此券（每人限領一次）而略過", r"; \1 skipped (already received, one per member)"),
    (r"確定要發送給 (\d+) 位會員嗎？", r"Send to \1 members?"),
    (r"預約前 (\S+) 小時內無法線上取消，請直接來電", r"Bookings cannot be cancelled online within \1 hours. Please call us."),
    (r"如需取消，請於預約時間 (\S+) 小時前操作；之後請來電", r"To cancel, please do so at least \1 hours before your appointment; after that, please call"),
    (r"已重設密碼，臨時密碼：(\S+)（請轉告會員登入後自行修改）", r"Password reset. Temporary password: \1 (ask the member to change it after logging in)"),
    (r"已新增主項目「(.+?)」，接著可以為它新增子項目", r"Category \1 added. You can now add treatments to it."),
    (r"確定刪除主項目「(.+?)」？（需先清空子項目）", r"Delete category \1? (it must have no treatments)"),
    (r"已新增店休日 (\S+)", r"Closing day \1 added"),
    (r"設定有誤：", r"Invalid settings: "),
    (r"數值必須大於 0", r"Values must be greater than 0"),
    (r"請填寫名稱、時長（至少 5 分鐘）與價格", r"Please enter a name, duration (at least 5 minutes) and price"),
    (r"共 (\d+) 筆", r"\1 bookings"),
    (r"（只顯示前 300 筆，請縮小篩選範圍）", r" (showing the first 300, please narrow the filter)"),
    (r"共 (\d+) 位", r"\1 members"),
    (r"（(\d+) 個子項目）", r"(\1 treatments)"),
    (r"（優惠券、新人禮，最近 100 封）", r"(coupons and welcome gifts, latest 100)"),
    (r"所有會員（(\d+) 位）", r"All members (\1)"),
    (r"（可用 (\d+) / 共 (\d+) 張）", r"(\1 available / \2 total)"),
    (r"可使用（(\d+)）", r"Available (\1)"),
    (r"已使用（(\d+)）", r"Used (\1)"),
    (r"已過期（(\d+)）", r"Expired (\1)"),
    (r"沒有(可使用|已使用|已過期)的優惠券",
     lambda m: "No " + {"可使用": "available", "已使用": "used", "已過期": "expired"}[m.group(1)] + " coupons"),
    (r"已使用優惠券：", r"Coupon used: "),
    (r"優惠券已存入「我的優惠券」，預約時選擇即可使用。", r"Coupons are saved in My Coupons. Choose one when booking."),
    (r"優惠券已存入「", r"Coupons are saved in "),
    (r"」，預約時選擇即可使用。", r". Choose one when booking."),
    (r"有效期限至 (\S+)", r"Valid until \1"),
    (r"已於 (\S+) 過期", r"Expired on \1"),
    (r"領取後 (\d+) 天", r"\1 days after issue"),
    (r"(\d+) 張", r"\1"),
    (r"(\d+) 項", r"\1 options"),
    (r"(\d+) 分鐘", r"\1 min"),
    (r"(\d+) 分(?=[ ·）)])", r"\1 min"),
    (r"剩餘 (\d+) 位", r"\1 left"),
    (r"（原價 ", r"(list price "),
]

# 最後處理：日期、標點
FINAL_PATTERNS = [
    (r"（([一二三四五六日])）", lambda m: f" ({WEEKDAYS[m.group(1)]})"),
    (r"每週([一二三四五六日])公休", lambda m: f"Closed every {WEEKDAYS[m.group(1)]}"),
    (r"（週([一二三四五六日])）", lambda m: f" ({WEEKDAYS[m.group(1)]})"),
    (r"週([一二三四五六日])", lambda m: WEEKDAYS[m.group(1)]),
    (r"(\d{1,2})月", lambda m: MONTHS[int(m.group(1)) - 1] if 1 <= int(m.group(1)) <= 12 else m.group(0)),
    (r" · 至 ", r" · until "),
    (r"（", r" ("), (r"）", r")"), (r"：", r": "), (r"，", r", "), (r"。", r". "), (r"！", r"! "), (r"？", r"? "),
    (r"、", r", "), (r"；", r"; "), (r"「", r""), (r"」", r""),
]

_CJK = re.compile(r"[一-鿿]")
_phrase_keys = sorted((k for k in PHRASES if len(k) >= 2), key=len, reverse=True)
_phrase_re = re.compile("|".join(re.escape(k) for k in _phrase_keys))
_patterns = [(re.compile(p), r) for p, r in PATTERNS]
_final = [(re.compile(p), r) for p, r in FINAL_PATTERNS]


def translate_text(s):
    if not s or not _CJK.search(s):
        return s
    lead = s[: len(s) - len(s.lstrip())]
    trail = s[len(s.rstrip()):]
    core = " ".join(s.split())
    if core in PHRASES:
        return lead + PHRASES[core] + trail
    out = core
    for rx, rep in _patterns:      # 含數字/名稱的句型
        out = rx.sub(rep, out)
    out = _phrase_re.sub(lambda m: PHRASES[m.group(0)], out)
    for rx, rep in _final:         # 日期、標點
        out = rx.sub(rep, out)
    return lead + " ".join(out.split()) + trail


_TOKEN = re.compile(r"(<!--.*?-->|<[^>]+>)", re.S)
_ATTR = re.compile(r'(\s(?:placeholder|title|alt|aria-label|data-name|data-confirm|onsubmit|onclick)=")([^"]*)(")')
_SKIP_OPEN = re.compile(r"<(script|style|textarea)\b", re.I)


def _translate_attr(m):
    val = html.unescape(m.group(2))
    return m.group(1) + html.escape(translate_text(val), quote=True) + m.group(3)


def translate_html(page):
    parts = _TOKEN.split(page)
    skip = None
    for i, part in enumerate(parts):
        if not part:
            continue
        if part.startswith("<"):
            if skip:
                if re.match(rf"</{skip}\b", part, re.I):
                    skip = None
                continue
            m = _SKIP_OPEN.match(part)
            if m:
                skip = m.group(1).lower()
            if _CJK.search(part):
                parts[i] = _ATTR.sub(_translate_attr, part)
        elif not skip and _CJK.search(part):
            parts[i] = html.escape(translate_text(html.unescape(part)), quote=False)
    return "".join(parts)


# booking.js / forms.js 用到的字串
JS_STRINGS = [
    "請選擇預約時間", "請先選擇服務項目", "請選擇日期", "載入可預約時段…", "請選擇其他日期",
    "這天已無可預約時段，請選擇其他日期", "無法載入時段，請重新整理頁面", "尚未選擇服務", "分鐘",
    "請選擇時間", "體驗價", "請確認", "提示", "確定", "取消", "返回", "上一張", "下一張",
    "傳送失敗，請再試一次", "還沒有客服訊息", "你：", "會員資料", "還沒有訊息，可以直接傳訊息給這位會員。",
    "請輸入訊息", "訊息太長，請在 1000 字以內", "訊息傳送太頻繁，請稍後再試", "請先登入會員", "無法使用客服",
    "沒有權限", "找不到此會員", "Email 格式不正確，例如 name@gmail.com", "請輸入馬來西亞手機號碼，例如 12-345 6789",
]


def js_dict():
    d = {}
    for s in JS_STRINGS:
        t = translate_text(s)
        if t != s:
            d[s] = t
    return d
