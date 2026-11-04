# 💸 FinChat AI - Smart Expense & Account Tracker

> A free, smart financial tracking app built with **Python**, **Streamlit**, **Google Gemini API**, and **SQLite**.

Log expenses, deposit balance, manage bank accounts, and delete transactions naturally using everyday language (e.g. *"grocessory 450 upi bob"*, *"added 5000 in sbi"*, or *"salary 45000 hdfc"*).

---

## ✨ Key Features

- 💬 **Natural Language Chat Parsing:** Type or speak expenses AND balance deposits (Gemini extracts item, amount, bank, category, and distinguishes expenses from income).
- 🏦 **Multi-Account & Live Balance Tracking:**
  - **Create New Accounts:** Set up bank accounts, cash wallets, credit cards, or digital wallets with custom opening balances.
  - **Deposit / Add Balance:** Top-up any account via Chat (*"added 5000 in sbi"*) or via the dedicated deposit form.
  - **Real-Time Balance Formula:** `Current Balance = Initial Balance + Deposits - Expenses`.
- 🗑️ **Foolproof Transaction Deletion:**
  - **1-Click Delete Button:** Tap the red 🗑️ trash icon directly next to any transaction in the **Latest Activity** feed.
  - **Dropdown Selection:** Choose any transaction from a descriptive dropdown list in **History & Manage** to delete it instantly.
  - **Batch Delete:** Multi-select and remove multiple transactions simultaneously.
  - Automatic balance refund: when an expense is deleted, the money is immediately restored to that bank's balance!
- 🤖 **Gemini AI Intelligence:** Powered by Google Gemini (`gemini-2.5-flash` / `gemini-1.5-flash`) with structured JSON output and typo correction.
- 🏦 **Smart Bank & Mode Detection:** Automatically expands bank abbreviations (`bob` ➔ Bank of Baroda, `sbi` ➔ State Bank of India, `hdfc` ➔ HDFC Bank, `icici` ➔ ICICI Bank) and payment modes (UPI, ATM, Credit Card, Debit Card, Cash, Net Banking).
- 📊 **Interactive Analytics Dashboard:** Real-time KPI summary cards, bank-wise spending bars, category distribution donut charts, and spending trend lines.
- 💾 **Local SQLite Storage & CSV Export:** Zero-config database that persists across restarts. One-click CSV export ready to open in Microsoft Excel or Google Sheets.
- ⚡ **Offline Fallback Engine:** Features a smart regex/rule-based parser so you can test sample transactions even without an API key!
- 📱 **Mobile Ready (PWA):** Responsive design that can be saved directly to your phone's home screen.
- 🆓 **100% Free Stack:** Free AI (Google AI Studio Free Tier), Free hosting (Streamlit Community Cloud), and Free storage.

---

## 🛠️ The 100% Free Tech Stack

| Component | Technology | Why It's Used | Cost |
| :--- | :--- | :--- | :--- |
| **Frontend & UI** | [Streamlit](https://streamlit.io/) | Pure Python web app framework with chat & reactive charts | **Free** |
| **AI Parser** | [Google Gemini API](https://aistudio.google.com/) | Typo correction, entity extraction & structured JSON | **Free Tier** (15 RPM) |
| **Data Visualization**| [Altair](https://altair-viz.github.io/) | Interactive responsive charts | **Free** |
| **Database** | SQLite & CSV Export | Permanent local storage for transactions & accounts | **Free** |
| **Cloud Hosting** | [Streamlit Community Cloud](https://share.streamlit.io/) | One-click deployment directly from GitHub | **Free** |

---

## 🚀 Quickstart Guide (Run Locally)

### 1. Open the Workspace
```bash
cd d:\expensetracker
```

### 2. (Optional) Create a Virtual Environment
```bash
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Your Free Gemini API Key (Optional)
You can configure your key in any of these 3 easy ways:
1. **Directly in the App:** Enter it in the sidebar input box on startup.
2. **Via `.env` file:** Copy `.env.example` to `.env` and fill in `GEMINI_API_KEY="your_key"`.
3. **Via Streamlit secrets:** Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in `GEMINI_API_KEY="your_key"`.

> *Note: If no API key is provided, the app will run in **Offline Heuristic Mode**, allowing you to test sample transactions without any errors!*

### 5. Launch the Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🔑 How to Get Your Free Gemini API Key (2 Minutes)

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google / Gmail account.
3. Click **"Get API key"** in the top left.
4. Click **"Create API key"** (in a new project or existing project).
5. Copy your key (starts with `AIzaSy...`).
6. Paste it into the app's sidebar or your `.streamlit/secrets.toml` file.

---

## 💬 Example Messages You Can Try

| What You Type | Action | Extracted Item | Amount | Category | Bank / Account |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `grocessory 450 upi bob` | **Expense** | Grocery | ₹450.00 | Groceries | Bank of Baroda |
| `atm withdraw 2000 sbi` | **Expense** | Cash Withdrawal | ₹2,000.00 | ATM & Cash | State Bank of India |
| `zomato dinner 680 hdfc cc`| **Expense** | Zomato Dinner | ₹680.00 | Food & Dining | HDFC Bank |
| `petrol 500 cash` | **Expense** | Petrol Refill | ₹500.00 | Travel & Fuel | Cash / Wallet |
| `added 5000 in sbi` | **Add Balance** | Account Deposit | ₹5,000.00 | Deposit / Top-up | State Bank of India |
| `salary 45000 hdfc` | **Add Balance** | Monthly Salary | ₹45,000.00 | Salary | HDFC Bank |
| `deposit 2000 in bob` | **Add Balance** | Account Deposit | ₹2,000.00 | Deposit / Top-up | Bank of Baroda |

---

## 🏦 Account & Balance Management

1. **Creating an Account**:
   - Navigate to the **"🏦 Accounts & Balances"** tab.
   - Enter Account Name (e.g., *Kotak Mahindra Bank*, *Axis Bank*, *Emergency Cash*).
   - Select Account Type (*Savings Account, Current, Credit Card, Digital Wallet, Cash*).
   - Enter your initial opening balance (e.g., *₹15,000*).
   - Click **"✨ Create Account"**.

2. **Depositing / Adding Balance**:
   - **Method A (Chat):** Simply type *"added 5000 in sbi"* or *"salary 50000 hdfc"* in the chat!
   - **Method B (UI Form):** Under the **"🏦 Accounts & Balances"** tab or in the left panel's **"💰 Quick Add Balance"** form, pick the account, enter the amount, select category (*Salary, Deposit, Cashback*), and click **"Add Balance Now"**.

3. **Deleting Transactions**:
   - **Quick Delete:** In the **Latest Activity** feed on the left, click the red **🗑️** button next to any transaction.
   - **History & Manage Tab:** Go to the **"📝 History & Manage"** tab, pick any transaction from the dropdown list, and click **"🗑️ Delete Selected Transaction"** (or use **Batch Delete** to remove several at once).
   - Deleted expenses automatically restore that account's live balance!

---

## 🌐 Deploying to Streamlit Cloud for Free

1. Create a GitHub repository (e.g., `my-expense-tracker`).
2. Push your files:
   ```bash
   git init
   git add app.py requirements.txt README.md .gitignore .streamlit/config.toml
   git commit -m "FinChat AI with Account Balance & Delete support"
   git branch -M main
   git remote add origin https://github.com/<your-username>/my-expense-tracker.git
   git push -u origin main
   ```
3. Visit [share.streamlit.io](https://share.streamlit.io/) and click **"Deploy an app"**.
4. In Streamlit Cloud **App Settings -> Secrets**, paste:
   ```toml
   GEMINI_API_KEY = "your_actual_api_key_here"
   ```
5. On mobile, open your app URL and tap **"Add to Home Screen"** to use it like a native app!
