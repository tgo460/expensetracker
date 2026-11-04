# 💸 FinChat AI - Smart Natural Language Expense Tracker

> A free, smart, chat-based expense tracker built with **Python**, **Streamlit**, **Google Gemini API**, and **SQLite / Google Sheets**.

Log your expenses naturally like you would in a quick text message (e.g. *"grocessory 450 upi bob"* or *"atm withdraw 2000 sbi"*). The AI automatically fixes spelling mistakes, understands bank short forms, categorizes spending, and updates your visual financial dashboard in real time.

---

## ✨ Key Features

- 💬 **Natural Language Chat Parsing:** Type or speak expenses without filling tedious forms.
- 🤖 **Gemini AI Intelligence:** Powered by Google Gemini (`gemini-2.5-flash` / `gemini-1.5-flash`) with structured JSON output and typo correction.
- 🏦 **Smart Bank & Mode Detection:** Automatically expands bank abbreviations (`bob` ➔ Bank of Baroda, `sbi` ➔ State Bank of India, `hdfc` ➔ HDFC Bank, `icici` ➔ ICICI Bank) and payment modes (UPI, ATM, Credit Card, Debit Card, Cash, Net Banking).
- 📅 **Relative Date Comprehension:** Recognizes *"yesterday 400 dinner"*, *"last night 120 auto fare"*, or defaults to the current timestamp.
- 📊 **Interactive Analytics Dashboard:** Real-time KPI summary cards, bank-wise spending bars, category distribution donut charts, and spending trend lines.
- 💾 **Dual Storage Architecture:**
  - **Zero-Config Local SQLite:** Works instantly out of the box with zero setup and persists across app restarts.
  - **Google Sheets & CSV Export:** One-click CSV export ready to open in Microsoft Excel or Google Sheets.
- ⚡ **Offline Fallback Engine:** Features a smart regex/rule-based parser so you can test the app immediately even before generating your Gemini API key.
- 📱 **Mobile Ready (PWA):** Responsive design that can be saved directly to your phone's home screen.
- 🆓 **100% Free Stack:** Free AI (Google AI Studio Free Tier), Free hosting (Streamlit Community Cloud), and Free storage.

---

## 🛠️ The 100% Free Tech Stack

| Component | Technology | Why It's Used | Cost |
| :--- | :--- | :--- | :--- |
| **Frontend & UI** | [Streamlit](https://streamlit.io/) | Pure Python web app framework with chat & reactive charts | **Free** |
| **AI Parser** | [Google Gemini API](https://aistudio.google.com/) | Typo correction, entity extraction & structured JSON | **Free Tier** (15 RPM) |
| **Data Visualization**| [Altair](https://altair-viz.github.io/) | Interactive responsive charts | **Free** |
| **Database** | SQLite & Google Sheets | Permanent storage for transactions | **Free** |
| **Cloud Hosting** | [Streamlit Community Cloud](https://share.streamlit.io/) | One-click deployment directly from GitHub | **Free** |

---

## 🚀 Quickstart Guide (Run Locally)

### 1. Clone or Open the Workspace
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

### 4. Configure Your Free Gemini API Key (Optional for Local Run)
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

*The Google AI Studio free tier provides up to 15 requests per minute, which is more than enough for daily personal expense tracking.*

---

## 💬 Example Messages You Can Try

| What You Type | Extracted Item | Amount | Category | Payment Mode | Bank / Source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `grocessory 450 upi bob` | Grocery | ₹450.00 | Groceries | UPI | Bank of Baroda |
| `atm withdraw 2000 sbi` | Cash Withdrawal | ₹2,000.00 | ATM & Cash | ATM Withdrawal | State Bank of India |
| `zomato dinner 680 hdfc cc` | Zomato Dinner | ₹680.00 | Food & Dining | Credit Card | HDFC Bank |
| `petrol 500 cash` | Petrol Refill | ₹500.00 | Travel & Fuel | Cash | Cash / Wallet |
| `electricity 1250 icici netbanking` | Electricity Bill | ₹1,250.00 | Bills & Utilities | Net Banking | ICICI Bank |
| `yesterday 150 coffee gpay` | Coffee | ₹150.00 | Food & Dining | UPI | Other / Not Specified |

---

## 🌐 Deploying to Streamlit Cloud for Free

You can host your tracker online 24/7 at no cost:

### Step 1: Push Code to GitHub
1. Create a new repository on [GitHub](https://github.com/new) (e.g., `my-expense-tracker`).
2. Make it **Private** if you want to keep your expense tracker private.
3. Push your repository:
   ```bash
   git init
   git add app.py requirements.txt README.md .gitignore .streamlit/config.toml
   git commit -m "Initial commit of FinChat AI expense tracker"
   git branch -M main
   git remote add origin https://github.com/<your-username>/my-expense-tracker.git
   git push -u origin main
   ```

### Step 2: Deploy on Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io/) and log in with GitHub.
2. Click **"Create app"** -> **"Deploy a public/private app from GitHub"**.
3. Select your repository: `<your-username>/my-expense-tracker`.
4. Branch: `main`, Main file path: `app.py`.
5. Click **"Deploy"**.

### Step 3: Add Your Secrets
1. In your deployed app's dashboard, click the **Settings (gear icon)** at the bottom right.
2. Select **"Secrets"**.
3. Paste:
   ```toml
   GEMINI_API_KEY = "your_actual_api_key_here"
   CURRENCY = "₹"
   ```
4. Click **Save**. Your app will automatically reload and be live worldwide!

---

## 📱 Use on Mobile Like a Native App

Once deployed, you will get a permanent URL (such as `https://my-expense-tracker.streamlit.app`).

1. Open the URL in **Chrome** (Android) or **Safari** (iPhone).
2. Tap the browser menu:
   - **Android Chrome:** Tap the 3 dots (⋮) ➔ **"Add to Home screen"** or **"Install app"**.
   - **iOS Safari:** Tap the Share button (square with arrow up) ➔ **"Add to Home Screen"**.
3. An icon named **FinChat AI** will now appear on your home screen. Tap it anytime to quickly log an expense in 5 seconds!

---

## 📂 Project Structure

```
expensetracker/
├── app.py                      # Complete Streamlit application with UI, DB & AI parser
├── requirements.txt            # Python dependencies (streamlit, google-genai, altair, pandas)
├── README.md                   # Complete documentation & deployment guide
├── .gitignore                  # Keeps local database, cache & secrets private
├── .env.example                # Example environment variables file
└── .streamlit/
    ├── config.toml             # Custom theme colors & server configurations
    └── secrets.toml.example    # Example secrets template for Streamlit Cloud
```

---

## 🔒 Security & Privacy

- Your Gemini API Key is never committed to GitHub or exposed to the client.
- Expenses are stored in your own private database (`expenses.db` locally or your private Streamlit Cloud storage).
- `.gitignore` is pre-configured to keep credentials and local databases out of version control.

