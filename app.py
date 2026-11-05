import os
import json
import re
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import altair as alt

# ==============================================================================
# 0. BANK DATA — loaded once from banks.json (single source of truth)
# ==============================================================================
_BANKS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banks.json")

def _load_bank_data() -> list[dict]:
    """Loads the bank list from banks.json. Returns empty list on failure."""
    try:
        with open(_BANKS_JSON_PATH, encoding="utf-8") as f:
            return json.load(f).get("banks", [])
    except Exception:
        return []

BANK_DATA = _load_bank_data()   # list of {name, type, aliases}

# Flat alias → canonical name dict (used by heuristic parser)
BANK_ALIAS_MAP: dict[str, str] = {
    alias.lower(): bank["name"]
    for bank in BANK_DATA
    for alias in bank["aliases"]
}

# Compact one-liner injected into LLM prompt  (token-efficient: ~350 chars typical)
# Format: "alias=Full Name, alias2=Full Name2, ..."
# Only primary short abbreviations (first alias per bank) to keep prompt small.
def _build_prompt_bank_line() -> str:
    parts = []
    for bank in BANK_DATA:
        if bank["aliases"]:
            parts.append(f"{bank['aliases'][0]}={bank['name']}")
    return ", ".join(parts)

BANK_PROMPT_LINE: str = _build_prompt_bank_line()

# ==============================================================================
# 1. STREAMLIT APP CONFIGURATION & THEMING
# ==============================================================================
st.set_page_config(
    page_title="FinChat AI - Smart Expense & Account Tracker",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    /* Metric Cards */
    div[data-testid="stMetric"] {
        background-color: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="stMetric"]:hover {
        border-color: #10B981;
        transition: border-color 0.2s ease-in-out;
    }
    /* Transaction Card */
    .txn-card {
        background: #1E293B;
        border-left: 4px solid #10B981;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .txn-card-income {
        background: #1E293B;
        border-left: 4px solid #3B82F6;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    /* Account Card */
    .account-card {
        background: #1E293B;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 12px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .account-card:hover {
        border-color: #10B981;
        transform: translateY(-2px);
    }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-bank { background-color: #3B82F6; color: white; }
    .badge-cat { background-color: #8B5CF6; color: white; }
    .badge-mode { background-color: #F59E0B; color: black; }
    .badge-income { background-color: #10B981; color: white; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. DATABASE MANAGEMENT (SQLite Persistence for Expenses, Accounts & Deposits)
# ==============================================================================
DB_PATH = "expenses.db"

def init_db():
    """Initializes local SQLite database with expenses, accounts, and balance_adjustments."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Expenses Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            item TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            mode TEXT NOT NULL,
            bank TEXT NOT NULL,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Accounts Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            account_type TEXT NOT NULL,
            initial_balance REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 3. Balance Adjustments / Deposits Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balance_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            account_name TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    conn.commit()
    conn.close()

# Auto ensure account exists when an expense or balance adjustment is made
def ensure_account_exists(account_name: str, account_type: str = "Savings Account"):
    """Ensures that the given account name is registered in the accounts table."""
    clean_name = account_name.strip()
    if not clean_name:
        clean_name = "Other / Not Specified"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO accounts (name, account_type, initial_balance)
        VALUES (?, ?, 0.0)
    """, (clean_name, account_type))
    conn.commit()
    conn.close()

def create_new_account(name: str, account_type: str, initial_balance: float):
    """Creates a new user account with initial balance."""
    clean_name = name.strip()
    if not clean_name:
        return False, "Account name cannot be empty."
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO accounts (name, account_type, initial_balance)
            VALUES (?, ?, ?)
        """, (clean_name, account_type, float(initial_balance)))
        conn.commit()
        success = True
        msg = f"Account '{clean_name}' created successfully!"
    except sqlite3.IntegrityError:
        success = False
        msg = f"An account with the name '{clean_name}' already exists."
    except Exception as e:
        success = False
        msg = str(e)
    finally:
        conn.close()
    return success, msg

def add_balance_to_account(account_name: str, amount: float, adj_type: str, description: str, date: str = None):
    """Adds balance / deposit to an account and logs the adjustment."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d %H:%M")
    ensure_account_exists(account_name)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO balance_adjustments (date, account_name, amount, type, description)
        VALUES (?, ?, ?, ?, ?)
    """, (date, account_name.strip(), float(amount), adj_type, description))
    conn.commit()
    conn.close()

def add_expense_to_db(date, item, category, amount, mode, bank, raw_text=""):
    """Inserts a new expense record into the SQLite database and ensures the account exists."""
    ensure_account_exists(bank)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (date, item, category, amount, mode, bank, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date, item, category, float(amount), mode, bank, raw_text))
    conn.commit()
    conn.close()

def get_all_expenses():
    """Fetches all expenses as a pandas DataFrame sorted by date descending."""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT id, date, item, category, amount, mode, bank, raw_text FROM expenses ORDER BY date DESC, id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_all_balance_adjustments():
    """Fetches all balance additions / deposits as a DataFrame."""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT id, date, account_name, amount, type, description FROM balance_adjustments ORDER BY date DESC, id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_all_accounts_summary():
    """Returns a DataFrame of all accounts with initial balance, total added, total spent, and current balance."""
    conn = sqlite3.connect(DB_PATH)
    accounts_df = pd.read_sql_query("SELECT id, name, account_type, initial_balance FROM accounts ORDER BY name ASC", conn)
    expenses_df = pd.read_sql_query("SELECT bank, SUM(amount) as total_spent FROM expenses GROUP BY bank", conn)
    deposits_df = pd.read_sql_query("SELECT account_name, SUM(amount) as total_added FROM balance_adjustments GROUP BY account_name", conn)
    conn.close()

    if accounts_df.empty:
        return pd.DataFrame(columns=["id", "name", "account_type", "initial_balance", "total_added", "total_spent", "current_balance"])

    df = accounts_df.merge(expenses_df, left_on="name", right_on="bank", how="left")
    df["total_spent"] = df["total_spent"].fillna(0.0).infer_objects(copy=False).astype(float)
    df = df.merge(deposits_df, left_on="name", right_on="account_name", how="left")
    df["total_added"] = df["total_added"].fillna(0.0).infer_objects(copy=False).astype(float)
    df["current_balance"] = df["initial_balance"] + df["total_added"] - df["total_spent"]
    return df

def delete_expense_from_db(expense_id):
    """Deletes an expense row by its primary key ID and returns True if successful."""
    try:
        clean_id = int(expense_id)
    except (ValueError, TypeError):
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ?", (clean_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def delete_balance_adjustment(adjustment_id):
    """Deletes a balance deposit row by its primary key ID and returns True if successful."""
    try:
        clean_id = int(adjustment_id)
    except (ValueError, TypeError):
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM balance_adjustments WHERE id = ?", (clean_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def delete_account(account_id):
    """Deletes an account from the database."""
    try:
        clean_id = int(account_id)
    except (ValueError, TypeError):
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE id = ?", (clean_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def clear_all_expenses_from_db():
    """Clears all records from the expenses table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses")
    conn.commit()
    conn.close()

# Initialize DB on load
init_db()

# ==============================================================================
# 3. AI PARSER (GEMINI API + SMART OFFLINE HEURISTIC)
# ==============================================================================
def get_gemini_api_key():
    """Retrieves Gemini API key from session state, secrets, or environment."""
    # 1. From Streamlit Session State (Sidebar user input)
    try:
        if st.session_state.get("sidebar_api_key"):
            return st.session_state["sidebar_api_key"].strip()
    except Exception:
        pass

    # 2. From Streamlit secrets
    try:
        if hasattr(st, "secrets"):
            key = st.secrets.get("GEMINI_API_KEY", "")
            if key:
                return str(key).strip()
    except Exception:
        pass

    # 3. From environment variables
    try:
        env_key = os.getenv("GEMINI_API_KEY", "")
        if env_key:
            return env_key.strip()
    except Exception:
        pass

    return ""

def parse_with_gemini(user_message: str, api_key: str):
    """Parses natural language financial message into structured JSON using Google Gemini API."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_date = datetime.now().strftime("%Y-%m-%d")

    # Get user's existing account names to help Gemini match banks accurately
    try:
        acc_df = get_all_accounts_summary()
        known_accounts = acc_df["name"].tolist() if not acc_df.empty else []
    except Exception:
        known_accounts = []
    known_accounts_str = ", ".join(known_accounts) if known_accounts else "Bank of Baroda, State Bank of India, HDFC Bank, ICICI Bank, Cash / Wallet"

    prompt = f"""
    You are an intelligent financial assistant parser.
    Today's date and time is: {now_str} (Reference date: {today_date}).
    User's registered accounts: {known_accounts_str}

    Bank abbreviation map (alias=Full Name): {BANK_PROMPT_LINE}

    User message: "{user_message}"

    Analyze the message and determine if this is an:
    1) "expense" (spending money, buying an item, withdrawing cash, dinner, groceries, bills, etc.) OR
    2) "income" (adding balance to an account, salary, depositing money, transfer received, top up, etc.)

    Return ONLY a valid JSON object with EXACTLY these keys:
    - "type":     (string, either "expense" or "income")
    - "item":     (string, clean descriptive name with typos corrected,
                   e.g. 'Grocery' instead of 'grocessory', 'Monthly Salary', 'Coffee')
    - "amount":   (number/float, positive spend or deposit amount)
    - "mode":     (string, payment method — 'UPI', 'ATM Withdrawal', 'Credit Card',
                   'Debit Card', 'Cash', 'Net Banking', 'Bank Transfer', 'Direct Deposit')
    - "bank":     (string, first try to match the user's registered accounts exactly,
                   then use the bank abbreviation map above. If cash with no bank, use 'Cash / Wallet'.)
    - "category": (for expense: 'Food & Dining', 'Groceries', 'Shopping',
                               'Bills & Utilities', 'Travel & Fuel', 'Entertainment',
                               'Health & Fitness', 'ATM & Cash', 'Education',
                               'Investment', 'Miscellaneous'
                   for income:  'Salary', 'Deposit / Top-up', 'Transfer Received',
                               'Freelance / Business', 'Cashback / Refund', 'Other Income')
    - "date":     (string, format 'YYYY-MM-DD HH:MM'. If 'yesterday', use yesterday's date.
                   If no date mentioned, use '{now_str}'.)
    """

    # Approach 1: Try new official google.genai SDK
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        data["source"] = "Gemini AI (google.genai)"
        return data
    except Exception as e_new:
        # Approach 2: Fallback to google.generativeai (legacy SDK)
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=api_key)
            model = legacy_genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\n", "", raw_text)
                raw_text = re.sub(r"\n```$", "", raw_text)
            data = json.loads(raw_text)
            data["source"] = "Gemini AI (gemini-1.5-flash)"
            return data
        except Exception as e_legacy:
            raise RuntimeError(f"Gemini API Error: {str(e_legacy or e_new)}")

def parse_with_heuristic(user_message: str):
    """Smart offline rule-based parser when Gemini API key is not configured."""
    msg = user_message.lower()

    # 1. Detect if income / deposit / add balance
    income_keywords = [
        "deposit", "deposited", "salary", "credit", "credited", "received", "added", 
        "add balance", "topup", "top up", "cashback", "refund", "bonus", "income", "load money"
    ]
    is_income = any(re.search(rf"\b{kw}\b", msg) for kw in income_keywords)

    # 2. Extract amount
    amount = 0.0
    amount_match = re.search(r'(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d{1,2})?)', msg)
    if amount_match:
        amount = float(amount_match.group(1))

    # 3. Extract Bank — uses BANK_ALIAS_MAP loaded from banks.json
    detected_bank = "Other / Not Specified"
    # Try longest alias first to avoid 'au' matching inside 'audit' etc.
    for alias in sorted(BANK_ALIAS_MAP.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", msg):
            detected_bank = BANK_ALIAS_MAP[alias]
            break

    # 4. Extract Mode
    detected_mode = "Bank Transfer" if is_income else "UPI"
    if "atm" in msg or "withdraw" in msg:
        detected_mode = "ATM Withdrawal"
    elif "cash" in msg:
        detected_mode = "Cash"
        if detected_bank == "Other / Not Specified":
            detected_bank = "Cash / Wallet"
    elif "credit card" in msg or " cc " in f" {msg} ":
        detected_mode = "Credit Card"
    elif "debit card" in msg or " dc " in f" {msg} ":
        detected_mode = "Debit Card"
    elif "netbanking" in msg or "net banking" in msg:
        detected_mode = "Net Banking"
    elif "upi" in msg or "gpay" in msg or "phonepe" in msg:
        detected_mode = "UPI"

    # 5. Extract Category & Item
    if is_income:
        if "salary" in msg:
            cat = "Salary"
            item = "Monthly Salary"
        elif "cashback" in msg or "refund" in msg:
            cat = "Cashback / Refund"
            item = "Cashback / Refund"
        elif "freelance" in msg or "client" in msg or "bonus" in msg:
            cat = "Freelance / Business"
            item = "Bonus / Freelance"
        else:
            cat = "Deposit / Top-up"
            item = "Account Deposit"
    else:
        cat = "Miscellaneous"
        item = "General Expense"
        if any(w in msg for w in ["grocessory", "grocery", "groceries", "milk", "vegetables", "sabzi", "kirana"]):
            cat = "Groceries"
            item = "Groceries"
        elif any(w in msg for w in ["dinner", "lunch", "breakfast", "food", "zomato", "swiggy", "restaurant", "cafe", "coffee", "tea"]):
            cat = "Food & Dining"
            item = "Food & Dining"
        elif any(w in msg for w in ["petrol", "diesel", "fuel", "cab", "uber", "ola", "auto", "metro", "bus", "train", "flight"]):
            cat = "Travel & Fuel"
            item = "Travel / Transport"
        elif any(w in msg for w in ["bill", "electricity", "wifi", "internet", "recharge", "water", "rent", "gas"]):
            cat = "Bills & Utilities"
            item = "Utility Bill"
        elif any(w in msg for w in ["movie", "cinema", "netflix", "spotify", "game", "outing"]):
            cat = "Entertainment"
            item = "Entertainment"
        elif any(w in msg for w in ["medicine", "doctor", "hospital", "pharma", "health"]):
            cat = "Health & Fitness"
            item = "Health & Medical"
        elif "atm" in msg or "withdraw" in msg:
            cat = "ATM & Cash"
            item = "Cash Withdrawal"
        elif any(w in msg for w in ["cloth", "shirt", "pant", "amazon", "flipkart", "shopping"]):
            cat = "Shopping"
            item = "Shopping"

    # 6. Date calculation
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "yesterday" in msg:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")

    return {
        "type": "income" if is_income else "expense",
        "item": item,
        "amount": amount,
        "mode": detected_mode,
        "bank": detected_bank,
        "category": cat,
        "date": date_str,
        "source": "Offline Heuristic (Enter Gemini API Key for full AI parsing)"
    }

def parse_expense(text: str):
    """Main parser dispatch: uses Gemini API when key is available, else offline heuristic."""
    api_key = get_gemini_api_key()
    if api_key:
        try:
            return parse_with_gemini(text, api_key)
        except Exception as e:
            st.warning(f"⚠️ Gemini API error ({str(e)[:120]}...). Falling back to smart offline parser.")
            return parse_with_heuristic(text)
    else:
        return parse_with_heuristic(text)

# ==============================================================================
# 4. SIDEBAR SETTINGS & CONTROLS
# ==============================================================================
with st.sidebar:
    st.markdown("### 💸 FinChat AI Control")

    # API Key Configuration
    active_key = get_gemini_api_key()
    if active_key:
        st.success("🟢 Gemini AI Active")
    else:
        st.warning("🟡 Offline Mode Active")

    with st.expander("🔑 Configure Gemini API Key", expanded=not bool(active_key)):
        st.markdown("""
        Get your free API key at [Google AI Studio](https://aistudio.google.com/).
        Free tier gives 15 requests/minute with zero billing needed!
        """)
        user_key_input = st.text_input(
            "Enter Gemini API Key:",
            type="password",
            value=st.session_state.get("sidebar_api_key", ""),
            placeholder="AIzaSy...",
            help="Your key is kept only in your local session and not stored anywhere else."
        )
        if st.button("Save API Key"):
            st.session_state["sidebar_api_key"] = user_key_input.strip()
            st.rerun()

    # Currency Selection
    currency_options = ["₹", "$", "€", "£", "¥", "AED", "Rs"]
    selected_currency = st.selectbox("Preferred Currency", currency_options, index=0)

    st.divider()

    # Live Accounts Overview in Sidebar
    st.markdown("### 🏦 Live Account Balances")
    acc_summary = get_all_accounts_summary()
    if not acc_summary.empty:
        total_balance_all = acc_summary["current_balance"].sum()
        bal_color = "#10B981" if total_balance_all >= 0 else "#EF4444"
        st.markdown(f"**Total Net Balance:** <span style='font-size:1.15rem; font-weight:700; color:{bal_color};'>{selected_currency}{total_balance_all:,.2f}</span>", unsafe_allow_html=True)
        st.write("")
        for _, acc_row in acc_summary.iterrows():
            row_color = "#10B981" if acc_row['current_balance'] >= 0 else "#EF4444"
            st.markdown(f"**{acc_row['name']}**: <span style='color:{row_color}; font-weight:600;'>{selected_currency}{acc_row['current_balance']:,.2f}</span>", unsafe_allow_html=True)
    else:
        st.info("No accounts set up yet.")

    st.divider()

    # Database Tools
    with st.expander("🛠️ Data Export & Reset"):
        df_all_exp = get_all_expenses()
        st.markdown(f"**Expenses Stored:** `{len(df_all_exp)}` records")
        
        # Download CSV
        if not df_all_exp.empty:
            csv_data = df_all_exp.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Expenses to CSV",
                data=csv_data,
                file_name=f"expenses_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # Download Accounts Summary CSV
        if not acc_summary.empty:
            acc_csv_data = acc_summary.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Accounts to CSV",
                data=acc_csv_data,
                file_name=f"accounts_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # Clear Expenses
        if st.button("🗑️ Clear All Expenses", type="secondary", use_container_width=True):
            clear_all_expenses_from_db()
            st.success("All expense records cleared!")
            st.rerun()

    with st.expander("☁️ Cloud Deployment Guide"):
        st.markdown("""
        1. Push this folder to a GitHub repository.
        2. Go to [share.streamlit.io](https://share.streamlit.io).
        3. Connect GitHub and deploy `app.py`.
        4. Add your `GEMINI_API_KEY` under **App Settings -> Secrets**.
        """)

# ==============================================================================
# 5. MAIN APPLICATION INTERFACE
# ==============================================================================
st.title("💸 FinChat AI - Smart Expense & Account Tracker")
st.caption("Chat naturally to log expenses, deposit balance, and track bank accounts in real time.")

# Top KPI Metric Row
acc_summary = get_all_accounts_summary()
df_all = get_all_expenses()
deposits_all = get_all_balance_adjustments()

total_net_worth = acc_summary["current_balance"].sum() if not acc_summary.empty else 0.0
total_spent = df_all["amount"].sum() if not df_all.empty else 0.0
total_deposited = deposits_all["amount"].sum() if not deposits_all.empty else 0.0

today_str = datetime.now().strftime("%Y-%m-%d")
if not df_all.empty:
    today_spent = df_all[df_all["date"].str.startswith(today_str)]["amount"].sum()
    top_category = df_all.groupby("category")["amount"].sum().idxmax() if len(df_all) > 0 else "N/A"
else:
    today_spent = 0.0
    top_category = "N/A"

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("💳 Total Available Balance", f"{selected_currency}{total_net_worth:,.2f}")
col_m2.metric("💸 Total Spent", f"{selected_currency}{total_spent:,.2f}")
col_m3.metric("💰 Total Balance Added", f"{selected_currency}{total_deposited:,.2f}")
col_m4.metric("📅 Today's Spend", f"{selected_currency}{today_spent:,.2f}")

st.divider()

# Layout: Split Screen into Left (Chat & Inputs) and Right (Dashboard & Accounts)
col_chat, col_dash = st.columns([1, 1.4], gap="large")

# ------------------------------------------------------------------------------
# LEFT COLUMN: CHAT INPUT & QUICK TRANSACTIONS
# ------------------------------------------------------------------------------
with col_chat:
    st.subheader("💬 Natural Language Financial Chat")
    st.write("Type naturally to **log an expense** or **add balance / deposit**:")

    # Quick Prompt Chips
    st.caption("✨ **Quick examples (click to execute):**")
    chip_col1, chip_col2 = st.columns(2)
    sample_to_use = None
    if chip_col1.button("🛒 grocessory 450 upi bob", use_container_width=True):
        sample_to_use = "grocessory 450 upi bob"
    if chip_col2.button("🏧 atm withdraw 2000 sbi", use_container_width=True):
        sample_to_use = "atm withdraw 2000 sbi"
    if chip_col1.button("💰 added 5000 in sbi", use_container_width=True):
        sample_to_use = "added 5000 in sbi"
    if chip_col2.button("💼 salary 45000 hdfc", use_container_width=True):
        sample_to_use = "salary 45000 hdfc"

    # Chat Input Box
    user_input = st.chat_input("e.g. 'petrol 350 cash', 'added 2000 in bob', or 'dinner 550 sbi'...")
    active_prompt = sample_to_use or user_input

    # Process Message
    if active_prompt:
        with st.spinner("🤖 AI is analyzing your entry..."):
            try:
                parsed = parse_expense(active_prompt)
                txn_type = parsed.get("type", "expense").lower()
                amount_val = float(parsed.get("amount", 0.0))
                item_name = str(parsed.get("item", "Transaction")).title()
                cat_name = str(parsed.get("category", "Miscellaneous"))
                mode_name = str(parsed.get("mode", "UPI"))
                bank_name = str(parsed.get("bank", "Other / Not Specified"))
                date_val = str(parsed.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")))
                source_note = parsed.get("source", "")

                if amount_val <= 0:
                    st.warning("⚠️ Could not detect a valid amount. Please include a number like '450' or '₹1000'.")
                elif txn_type in ["income", "deposit"]:
                    # Add balance to account
                    add_balance_to_account(
                        account_name=bank_name,
                        amount=amount_val,
                        adj_type=cat_name,
                        description=f"{item_name} (via chat: '{active_prompt}')",
                        date=date_val
                    )
                    st.toast(f"🎉 Credited {selected_currency}{amount_val:,.2f} to {bank_name}!", icon="💰")
                    st.success(f"💰 **Added {selected_currency}{amount_val:,.2f} balance** to **{bank_name}** ({cat_name})")
                    if "Offline" in source_note:
                        st.caption(f"ℹ️ {source_note}")
                    st.rerun()
                else:
                    # Add expense
                    add_expense_to_db(
                        date=date_val,
                        item=item_name,
                        category=cat_name,
                        amount=amount_val,
                        mode=mode_name,
                        bank=bank_name,
                        raw_text=active_prompt
                    )
                    st.toast(f"💸 Added {item_name}: {selected_currency}{amount_val:,.2f}", icon="✅")
                    st.success(f"🎉 **Added {selected_currency}{amount_val:,.2f}** for **{item_name}** ({bank_name} via {mode_name})")
                    if "Offline" in source_note:
                        st.caption(f"ℹ️ {source_note}")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error processing input: {str(e)}")

    # Manual Forms Accordion
    m_exp1, m_exp2 = st.tabs(["✍️ Manual Expense Form", "💰 Quick Add Balance"])

    with m_exp1:
        with st.form("manual_expense_form", clear_on_submit=True):
            m_col1, m_col2 = st.columns(2)
            m_item = m_col1.text_input("Item Name", placeholder="e.g. Lunch & Drinks")
            m_amount = m_col2.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            
            m_col3, m_col4 = st.columns(2)
            categories = ["Food & Dining", "Groceries", "Shopping", "Bills & Utilities", 
                          "Travel & Fuel", "Entertainment", "Health & Fitness", "ATM & Cash", "Investment", "Miscellaneous"]
            m_cat = m_col3.selectbox("Category", categories)
            modes = ["UPI", "Credit Card", "Debit Card", "Cash", "ATM Withdrawal", "Net Banking", "Other"]
            m_mode = m_col4.selectbox("Payment Mode", modes)
            
            m_col5, m_col6 = st.columns(2)
            # Available accounts for dropdown
            existing_acc_names = acc_summary["name"].tolist() if not acc_summary.empty else ["Bank of Baroda", "State Bank of India", "Cash / Wallet"]
            m_bank = m_col5.selectbox("Select Bank / Account", existing_acc_names)
            m_date = m_col6.date_input("Date", value=datetime.now().date())

            if st.form_submit_button("➕ Record Expense", use_container_width=True):
                if m_amount > 0 and m_item.strip():
                    date_full = f"{m_date.strftime('%Y-%m-%d')} {datetime.now().strftime('%H:%M')}"
                    add_expense_to_db(date_full, m_item.strip(), m_cat, float(m_amount), m_mode, m_bank, "Manual Entry")
                    st.toast(f"Added {m_item} ({selected_currency}{m_amount:,.2f})")
                    st.rerun()
                else:
                    st.warning("Please enter an item name and amount > 0.")

    with m_exp2:
        with st.form("manual_deposit_form", clear_on_submit=True):
            d_col1, d_col2 = st.columns(2)
            existing_acc_names = acc_summary["name"].tolist() if not acc_summary.empty else ["Bank of Baroda", "State Bank of India", "Cash / Wallet"]
            d_acc = d_col1.selectbox("Target Account", existing_acc_names, key="d_acc_select")
            d_amount = d_col2.number_input("Amount to Deposit", min_value=1.0, value=1000.0, step=100.0, format="%.2f")

            d_col3, d_col4 = st.columns(2)
            d_types = ["Deposit / Top-up", "Salary", "Transfer Received", "Bonus / Freelance", "Cashback / Refund", "Other Income"]
            d_type = d_col3.selectbox("Deposit Type", d_types)
            d_desc = d_col4.text_input("Description / Note", placeholder="e.g. Salary, Cash Added")

            if st.form_submit_button("💰 Deposit to Account", use_container_width=True):
                if d_amount > 0:
                    add_balance_to_account(d_acc, float(d_amount), d_type, d_desc.strip() or d_type)
                    st.toast(f"Added {selected_currency}{d_amount:,.2f} to {d_acc}!")
                    st.rerun()

    # Recent Transactions Feed with ONE-CLICK DELETE BUTTONS
    st.markdown("#### 🕒 Latest Activity & Quick Delete")
    st.caption("Click 🗑️ to instantly remove any transaction and restore your balance.")
    df_recent = get_all_expenses().head(6)

    if not df_recent.empty:
        for _, row in df_recent.iterrows():
            c_info, c_action = st.columns([5, 1])
            with c_info:
                st.markdown(f"""
                <div class="txn-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="font-size:0.95rem;">{row['item']}</strong>
                        <span style="font-size:1.05rem; font-weight:700; color:#10B981;">{selected_currency}{row['amount']:,.2f}</span>
                    </div>
                    <div style="margin-top:4px;">
                        <span class="badge badge-cat">{row['category']}</span>
                        <span class="badge badge-bank">{row['bank']}</span>
                        <span class="badge badge-mode">{row['mode']}</span>
                        <span style="color:#94A3B8; font-size:0.75rem;">📅 {row['date']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with c_action:
                st.write("")
                if st.button("🗑️", key=f"quick_del_exp_{row['id']}", help=f"Delete #{row['id']} - {row['item']}"):
                    if delete_expense_from_db(row['id']):
                        st.toast(f"✅ Deleted transaction #{row['id']}!")
                        st.rerun()
    else:
        st.info("No activity logged yet. Use the chat bar above!")

# ------------------------------------------------------------------------------
# RIGHT COLUMN: VISUAL DASHBOARD, ACCOUNTS & TRANSACTION MANAGEMENT
# ------------------------------------------------------------------------------
with col_dash:
    tab_dash, tab_accounts, tab_history = st.tabs(["📊 Analytics", "🏦 Accounts & Balances", "📝 History & Manage"])

    # --------------------------------------------------------------------------
    # TAB 1: VISUAL ANALYTICS
    # --------------------------------------------------------------------------
    with tab_dash:
        st.subheader("📊 Spending Breakdown")
        df_dash = get_all_expenses()

        if not df_dash.empty:
            subtab_bank, subtab_cat, subtab_trend = st.tabs(["🏦 Bank Summary", "🏷️ Categories", "📈 Daily Trend"])

            with subtab_bank:
                bank_summary = df_dash.groupby("bank")["amount"].sum().reset_index()
                bank_chart = alt.Chart(bank_summary).mark_bar(cornerRadius=6, color="#3B82F6").encode(
                    x=alt.X("amount:Q", title=f"Total Spent ({selected_currency})"),
                    y=alt.Y("bank:N", sort="-x", title="Bank / Source"),
                    tooltip=["bank:N", alt.Tooltip("amount:Q", format=",.2f")]
                ).properties(height=260)
                st.altair_chart(bank_chart, use_container_width=True)

            with subtab_cat:
                cat_summary = df_dash.groupby("category")["amount"].sum().reset_index()
                cat_chart = alt.Chart(cat_summary).mark_arc(innerRadius=50).encode(
                    theta=alt.Theta("amount:Q", title="Amount"),
                    color=alt.Color("category:N", legend=alt.Legend(title="Category")),
                    tooltip=["category:N", alt.Tooltip("amount:Q", format=",.2f")]
                ).properties(height=260)
                st.altair_chart(cat_chart, use_container_width=True)

            with subtab_trend:
                df_dash['day'] = df_dash['date'].apply(lambda x: str(x).split()[0] if str(x) else "")
                trend_summary = df_dash.groupby("day")["amount"].sum().reset_index().sort_values("day")
                trend_chart = alt.Chart(trend_summary).mark_area(
                    line={"color": "#10B981"},
                    color=alt.Gradient(
                        gradient='linear',
                        stops=[alt.GradientStop(color='#10B981', offset=0),
                               alt.GradientStop(color='rgba(16, 185, 129, 0)', offset=1)],
                        x1=1, x2=1, y1=1, y2=0
                    )
                ).encode(
                    x=alt.X("day:T", title="Date"),
                    y=alt.Y("amount:Q", title=f"Daily Spend ({selected_currency})"),
                    tooltip=["day:T", alt.Tooltip("amount:Q", format=",.2f")]
                ).properties(height=260)
                st.altair_chart(trend_chart, use_container_width=True)
        else:
            st.info("No expense data available for analytics yet.")

    # --------------------------------------------------------------------------
    # TAB 2: ACCOUNTS & BALANCE MANAGEMENT (Create Account & Add Balance)
    # --------------------------------------------------------------------------
    with tab_accounts:
        st.subheader("🏦 Bank & Wallet Accounts")
        st.caption("Track live balances across all your accounts. Balance = Initial + Deposits - Expenses.")

        # Display Account Cards
        acc_df_live = get_all_accounts_summary()
        if not acc_df_live.empty:
            # 2 Columns grid for account cards
            cols = st.columns(2)
            for i, (_, acc) in enumerate(acc_df_live.iterrows()):
                col = cols[i % 2]
                bal = acc["current_balance"]
                bal_color = "#10B981" if bal >= 0 else "#EF4444"
                with col:
                    st.markdown(f"""
                    <div class="account-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="font-size:1.05rem;">{acc['name']}</strong>
                            <span class="badge badge-bank">{acc['account_type']}</span>
                        </div>
                        <div style="margin: 10px 0;">
                            <span style="font-size:0.85rem; color:#94A3B8;">Current Balance:</span><br/>
                            <span style="font-size:1.6rem; font-weight:800; color:{bal_color};">{selected_currency}{bal:,.2f}</span>
                        </div>
                        <div style="font-size:0.8rem; color:#94A3B8; border-top:1px solid rgba(255,255,255,0.08); padding-top:8px;">
                            <span>Opening: {selected_currency}{acc['initial_balance']:,.0f}</span> | 
                            <span style="color:#10B981;">+Added: {selected_currency}{acc['total_added']:,.0f}</span> | 
                            <span style="color:#F87171;">-Spent: {selected_currency}{acc['total_spent']:,.0f}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        st.divider()

        # Two Actions: Create Account & Add Balance
        act_col1, act_col2 = st.columns(2, gap="medium")

        # ACTION 1: CREATE ACCOUNT
        with act_col1:
            st.markdown("#### ➕ Create New Account")
            with st.form("create_new_account_form", clear_on_submit=True):
                new_acc_name = st.text_input("Account Name", placeholder="e.g. Axis Bank, Kotak Mahindra, Salary Acc")
                acc_type_opts = ["Savings Account", "Current / Checking", "Credit Card", "Digital Wallet", "Cash / Wallet", "Investment Account"]
                new_acc_type = st.selectbox("Account Type", acc_type_opts)
                new_acc_init_bal = st.number_input("Opening / Initial Balance", min_value=0.0, value=10000.0, step=500.0, format="%.2f")

                if st.form_submit_button("✨ Create Account", use_container_width=True):
                    success, msg = create_new_account(new_acc_name, new_acc_type, new_acc_init_bal)
                    if success:
                        st.toast(msg, icon="🎉")
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        # ACTION 2: ADD BALANCE / DEPOSIT
        with act_col2:
            st.markdown("#### 💰 Deposit / Add Balance")
            with st.form("add_balance_action_form", clear_on_submit=True):
                all_account_names = acc_df_live["name"].tolist() if not acc_df_live.empty else ["Bank of Baroda"]
                target_account = st.selectbox("Select Account", all_account_names, key="target_acc_select")
                deposit_amt = st.number_input("Deposit Amount", min_value=1.0, value=5000.0, step=500.0, format="%.2f")
                deposit_cat = st.selectbox("Category / Source", ["Deposit / Top-up", "Salary", "Transfer Received", "Bonus / Freelance", "Cashback / Refund", "Other Income"])
                deposit_note = st.text_input("Note / Memo", placeholder="e.g. Monthly Salary, ATM deposit")

                if st.form_submit_button("💳 Add Balance Now", use_container_width=True):
                    add_balance_to_account(target_account, float(deposit_amt), deposit_cat, deposit_note.strip() or deposit_cat)
                    st.toast(f"Deposited {selected_currency}{deposit_amt:,.2f} to {target_account}!", icon="💰")
                    st.success(f"Successfully added {selected_currency}{deposit_amt:,.2f} to {target_account}!")
                    st.rerun()

        # Balance Adjustment History & Deletion
        st.markdown("#### 📜 Deposit & Top-up History")
        dep_history = get_all_balance_adjustments()
        if not dep_history.empty:
            dep_display = dep_history.copy()
            dep_display["amount"] = dep_display["amount"].apply(lambda x: f"{selected_currency}{x:,.2f}")
            dep_display.rename(columns={
                "id": "ID", "date": "Date", "account_name": "Account", "amount": "Amount Added",
                "type": "Source Type", "description": "Note"
            }, inplace=True)
            st.dataframe(dep_display, use_container_width=True, hide_index=True)

            with st.expander("🗑️ Delete a Deposit / Balance Adjustment"):
                dep_ids = dep_history["id"].tolist()
                def format_dep(did):
                    dr = dep_history[dep_history["id"] == did].iloc[0]
                    return f"#{dr['id']} | {dr['date']} | {dr['account_name']} | {selected_currency}{dr['amount']:,.2f} | {dr['type']}"
                
                sel_dep = st.selectbox("Select Deposit to Remove:", dep_ids, format_func=format_dep, key="sel_dep_remove")
                if st.button("Delete Deposit", type="primary"):
                    if delete_balance_adjustment(sel_dep):
                        st.toast(f"Deposit #{sel_dep} deleted!")
                        st.rerun()
        else:
            st.info("No balance deposits recorded yet.")

        # Account Delete Expander
        with st.expander("⚙️ Manage / Delete an Account"):
            acc_ids = acc_df_live["id"].tolist() if not acc_df_live.empty else []
            if acc_ids:
                def format_acc(aid):
                    ar = acc_df_live[acc_df_live["id"] == aid].iloc[0]
                    return f"{ar['name']} ({ar['account_type']}) - Bal: {selected_currency}{ar['current_balance']:,.2f}"
                
                sel_acc_del = st.selectbox("Select Account to Delete:", acc_ids, format_func=format_acc, key="sel_acc_delete")
                st.warning("⚠️ Deleting an account will remove its initial balance record. Existing expense records remain.")
                if st.button("Delete This Account", type="primary"):
                    if delete_account(sel_acc_del):
                        st.toast(f"Account deleted successfully!")
                        st.rerun()

    # --------------------------------------------------------------------------
    # TAB 3: TRANSACTION HISTORY & ADVANCED DELETE
    # --------------------------------------------------------------------------
    with tab_history:
        st.subheader("📝 Transaction Log & Management")
        df_hist = get_all_expenses()

        if not df_hist.empty:
            # Filters
            f_col1, f_col2 = st.columns([1, 1])
            all_banks = ["All Banks"] + sorted(list(df_hist["bank"].unique()))
            selected_bank = f_col1.selectbox("Filter by Bank", all_banks, key="filter_bank_hist")
            all_categories = ["All Categories"] + sorted(list(df_hist["category"].unique()))
            selected_cat = f_col2.selectbox("Filter by Category", all_categories, key="filter_cat_hist")

            filtered_hist = df_hist.copy()
            if selected_bank != "All Banks":
                filtered_hist = filtered_hist[filtered_hist["bank"] == selected_bank]
            if selected_cat != "All Categories":
                filtered_hist = filtered_hist[filtered_hist["category"] == selected_cat]

            # Display table
            display_hist = filtered_hist[["id", "date", "item", "category", "amount", "mode", "bank"]].copy()
            display_hist["amount"] = display_hist["amount"].apply(lambda x: f"{selected_currency}{x:,.2f}")
            display_hist.rename(columns={
                "id": "ID", "date": "Date & Time", "item": "Description",
                "category": "Category", "amount": "Amount", "mode": "Payment Mode", "bank": "Bank / Account"
            }, inplace=True)
            st.dataframe(display_hist, use_container_width=True, hide_index=True)

            st.divider()

            # Dedicated Foolproof Deletion Section
            st.markdown("#### 🗑️ Delete Transactions")
            del_t1, del_t2 = st.tabs(["Single Transaction Delete", "Batch / Multi-Delete"])

            with del_t1:
                st.write("Select a transaction from the list below to delete it immediately:")
                all_ids = df_hist["id"].tolist()
                def format_expense_item(tid):
                    row_match = df_hist[df_hist["id"] == tid]
                    if not row_match.empty:
                        r = row_match.iloc[0]
                        return f"#{r['id']} | {r['date']} | {r['item']} | {selected_currency}{r['amount']:,.2f} | {r['bank']}"
                    return f"#{tid}"

                target_id = st.selectbox(
                    "Select Transaction to Delete:",
                    options=all_ids,
                    format_func=format_expense_item,
                    key="selectbox_single_delete"
                )

                if st.button("🗑️ Delete Selected Transaction", type="primary", use_container_width=True):
                    if delete_expense_from_db(target_id):
                        st.toast(f"✅ Transaction #{target_id} successfully deleted!")
                        st.success(f"Transaction #{target_id} removed.")
                        st.rerun()
                    else:
                        st.error("Could not delete. The transaction may have already been removed.")

            with del_t2:
                st.write("Select multiple transactions to delete simultaneously:")
                batch_targets = st.multiselect(
                    "Select Transactions for Batch Deletion:",
                    options=all_ids,
                    format_func=format_expense_item,
                    key="multiselect_batch_delete"
                )

                if st.button("🗑️ Delete Selected Batch", type="primary", disabled=len(batch_targets) == 0):
                    deleted_count = 0
                    for bid in batch_targets:
                        if delete_expense_from_db(bid):
                            deleted_count += 1
                    st.toast(f"✅ Successfully deleted {deleted_count} transactions!")
                    st.success(f"Removed {deleted_count} transactions from database.")
                    st.rerun()

        else:
            st.info("No transaction records found.")

# ==============================================================================
# FOOTER
# ==============================================================================
st.divider()
f_col1, f_col2 = st.columns([3, 1])
f_col1.caption("Built with Streamlit, Google Gemini API, and SQLite. 100% Free & Open Source.")
f_col2.caption("⚡ Powered by Google DeepMind / Gemini")
