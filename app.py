import os
import json
import re
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import altair as alt

# ==============================================================================
# 1. STREAMLIT APP CONFIGURATION & THEMING
# ==============================================================================
st.set_page_config(
    page_title="FinChat AI - Smart Expense Tracker",
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
        padding: 12px 16px;
        margin-bottom: 12px;
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
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. DATABASE MANAGEMENT (SQLite Persistence)
# ==============================================================================
DB_PATH = "expenses.db"

def init_db():
    """Initializes local SQLite database and pre-populates with sample data if empty."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    conn.commit()

    # Seed sample transactions if table is completely empty
    cursor.execute("SELECT COUNT(*) FROM expenses")
    count = cursor.fetchone()[0]
    if count == 0:
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        sample_data = [
            (today.strftime("%Y-%m-%d 13:30"), "Grocery & Vegetables", "Groceries", 450.0, "UPI", "Bank of Baroda", "grocessory 450 upi bob"),
            (today.strftime("%Y-%m-%d 10:15"), "ATM Cash Withdrawal", "ATM & Cash", 2000.0, "ATM Withdrawal", "State Bank of India", "atm withdraw 2000 sbi"),
            (yesterday.strftime("%Y-%m-%d 20:45"), "Zomato Dinner", "Food & Dining", 680.0, "Credit Card", "HDFC Bank", "zomato dinner 680 hdfc cc"),
            (two_days_ago.strftime("%Y-%m-%d 09:00"), "Petrol Refill", "Travel & Fuel", 500.0, "Cash", "Cash / Wallet", "petrol 500 cash"),
            (two_days_ago.strftime("%Y-%m-%d 18:20"), "Electricity Bill", "Bills & Utilities", 1250.0, "Net Banking", "ICICI Bank", "electricity 1250 icici netbanking")
        ]
        cursor.executemany("""
            INSERT INTO expenses (date, item, category, amount, mode, bank, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_data)
        conn.commit()
    conn.close()

def add_expense_to_db(date, item, category, amount, mode, bank, raw_text=""):
    """Inserts a new expense record into the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (date, item, category, amount, mode, bank, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date, item, category, amount, mode, bank, raw_text))
    conn.commit()
    conn.close()

def get_all_expenses():
    """Fetches all expenses as a pandas DataFrame sorted by date descending."""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT id, date, item, category, amount, mode, bank, raw_text FROM expenses ORDER BY date DESC, id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def delete_expense_from_db(expense_id):
    """Deletes an expense row by its primary key ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

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
# 3. AI PARSER (GEMINI API + SMART OFFLINE FALLBACK)
# ==============================================================================
def get_gemini_api_key():
    """Retrieves Gemini API key from secrets, environment, or sidebar input safely."""
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
    """Parses natural language expense text into structured JSON using Google Gemini API."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_date = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
    You are an intelligent financial expense parser assistant.
    Today's date and time is: {now_str} (Reference date: {today_date}).

    User expense input: "{user_message}"

    Analyze the message, fix any spelling mistakes, expand short forms, and extract the expense details.
    Return ONLY a valid JSON object with EXACTLY these keys:
    - "item": (string, clean descriptive name with typos corrected, e.g., 'Grocery' instead of 'grocessory', 'Coffee', 'Auto Fare', 'Zomato Food Delivery')
    - "amount": (number/float, positive spend amount)
    - "mode": (string, payment method, e.g., 'UPI', 'ATM Withdrawal', 'Credit Card', 'Debit Card', 'Cash', 'Net Banking'. Default to 'UPI' if ambiguous or 'Other' if unknown)
    - "bank": (string, expand bank abbreviations like 'bob' -> 'Bank of Baroda', 'sbi' -> 'State Bank of India', 'hdfc' -> 'HDFC Bank', 'icici' -> 'ICICI Bank', 'axis' -> 'Axis Bank', 'kotak' -> 'Kotak Mahindra Bank', 'pnb' -> 'Punjab National Bank'. If cash and no bank specified, use 'Cash / Wallet', otherwise 'Other / Not Specified')
    - "category": (string, categorize into one of: 'Food & Dining', 'Groceries', 'Shopping', 'Bills & Utilities', 'Travel & Fuel', 'Entertainment', 'Health & Fitness', 'ATM & Cash', 'Education', 'Investment', 'Miscellaneous')
    - "date": (string, format 'YYYY-MM-DD HH:MM'. If 'yesterday', calculate yesterday's date. If no date is mentioned, use '{now_str}')
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
            # Clean markdown codeblocks if present
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

    # 1. Extract amount
    amount = 0.0
    amount_match = re.search(r'(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d{1,2})?)', msg)
    if amount_match:
        amount = float(amount_match.group(1))

    # 2. Extract Bank
    bank_map = {
        "bob": "Bank of Baroda",
        "bank of baroda": "Bank of Baroda",
        "sbi": "State Bank of India",
        "state bank": "State Bank of India",
        "hdfc": "HDFC Bank",
        "icici": "ICICI Bank",
        "axis": "Axis Bank",
        "kotak": "Kotak Mahindra Bank",
        "pnb": "Punjab National Bank",
        "paytm": "Paytm Payments Bank"
    }
    detected_bank = "Other / Not Specified"
    for code, full_name in bank_map.items():
        if re.search(rf"\b{code}\b", msg):
            detected_bank = full_name
            break

    # 3. Extract Mode
    detected_mode = "UPI"
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

    # 4. Extract Category & Item
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

    # Clean words to make cleaner item title if possible
    words = [w for w in re.sub(r'[^a-zA-Z\s]', '', msg).split() if w not in [
        'upi', 'bob', 'sbi', 'hdfc', 'icici', 'axis', 'kotak', 'cash', 'atm', 'withdraw',
        'rs', 'inr', 'rupees', 'paid', 'spent', 'for', 'at', 'to', 'from', 'via', 'using'
    ]]
    if words:
        clean_title = " ".join(words[:3]).title()
        if len(clean_title) > 2:
            item = clean_title

    # 5. Date calculation
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "yesterday" in msg:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")

    return {
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
# 4. SIDEBAR SETTINGS & QUICK CONTROLS
# ==============================================================================
with st.sidebar:
    st.markdown("### 💸 FinChat AI Settings")

    # API Key Configuration
    active_key = get_gemini_api_key()
    if active_key:
        st.success("🟢 Gemini API Key Active")
    else:
        st.warning("🟡 No API Key Detected (Using Offline Mode)")

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
    selected_currency = st.selectbox("Preferred Currency Symbol", currency_options, index=0)

    st.divider()

    # Quick summary in sidebar
    df_current = get_all_expenses()
    if not df_current.empty:
        st.markdown("### 🏦 Spending by Bank")
        bank_grp = df_current.groupby("bank")["amount"].sum().reset_index()
        for _, row in bank_grp.iterrows():
            st.markdown(f"**{row['bank']}**: {selected_currency}{row['amount']:,.2f}")
    
    st.divider()

    # Database Tools
    with st.expander("🛠️ Database Operations"):
        st.markdown(f"**Records Stored:** `{len(df_current)}` transactions")
        
        # Download CSV
        if not df_current.empty:
            csv_data = df_current.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export to CSV",
                data=csv_data,
                file_name=f"expenses_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # Reset / Clear
        if st.button("🗑️ Clear All Transactions", type="secondary", use_container_width=True):
            clear_all_expenses_from_db()
            st.success("All transactions cleared!")
            st.rerun()

    with st.expander("☁️ Free Cloud Deployment Guide"):
        st.markdown("""
        1. Push this folder to a GitHub repository.
        2. Go to [share.streamlit.io](https://share.streamlit.io).
        3. Connect GitHub and deploy `app.py`.
        4. Add your `GEMINI_API_KEY` under **App Settings -> Secrets**.
        5. Ready to use on phone & desktop!
        """)

# ==============================================================================
# 5. MAIN APPLICATION INTERFACE
# ==============================================================================
st.title("💸 FinChat AI - Chat Expense Tracker")
st.caption("Log your expenses in natural everyday language. Powered by **Google Gemini API**, **Streamlit**, and **SQLite / Sheets**.")

# Top KPI Metric Row
df_all = get_all_expenses()
total_spent = df_all["amount"].sum() if not df_all.empty else 0.0

# Calculate Today's Spend
today_str = datetime.now().strftime("%Y-%m-%d")
if not df_all.empty:
    today_spent = df_all[df_all["date"].str.startswith(today_str)]["amount"].sum()
    top_category = df_all.groupby("category")["amount"].sum().idxmax() if len(df_all) > 0 else "N/A"
    total_txns = len(df_all)
else:
    today_spent = 0.0
    top_category = "N/A"
    total_txns = 0

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("💰 Total Spent", f"{selected_currency}{total_spent:,.2f}")
col_m2.metric("📅 Today's Spend", f"{selected_currency}{today_spent:,.2f}")
col_m3.metric("🏷️ Top Category", f"{top_category}")
col_m4.metric("🧾 Total Transactions", f"{total_txns}")

st.divider()

# Layout: Split Screen into Chat (Left) and Dashboard (Right)
col_chat, col_dash = st.columns([1, 1.35], gap="large")

# ------------------------------------------------------------------------------
# LEFT COLUMN: NATURAL LANGUAGE CHAT INPUT & ENTRY
# ------------------------------------------------------------------------------
with col_chat:
    st.subheader("💬 Add Expense with AI")
    st.write("Type naturally like you would in a WhatsApp message or notebook:")

    # Quick Prompt Chips
    st.caption("✨ **Quick examples (click to fill):**")
    chip_col1, chip_col2 = st.columns(2)
    sample_to_use = None
    if chip_col1.button("🛒 grocessory 450 upi bob", use_container_width=True):
        sample_to_use = "grocessory 450 upi bob"
    if chip_col2.button("🏧 atm withdraw 2000 sbi", use_container_width=True):
        sample_to_use = "atm withdraw 2000 sbi"
    if chip_col1.button("🍕 zomato dinner 680 hdfc cc", use_container_width=True):
        sample_to_use = "zomato dinner 680 hdfc cc"
    if chip_col2.button("⛽ petrol 500 cash", use_container_width=True):
        sample_to_use = "petrol 500 cash"

    # Chat Input Box
    user_input = st.chat_input("Type your spend here (e.g., 'lunch 250 upi icici')...")
    active_prompt = sample_to_use or user_input

    # Process Message
    if active_prompt:
        with st.spinner("🤖 AI is understanding your expense..."):
            try:
                parsed = parse_expense(active_prompt)
                
                # Extract values with safe defaults
                item_name = str(parsed.get("item", "Expense")).title()
                cat_name = str(parsed.get("category", "Miscellaneous"))
                amount_val = float(parsed.get("amount", 0.0))
                mode_name = str(parsed.get("mode", "UPI"))
                bank_name = str(parsed.get("bank", "Other"))
                date_val = str(parsed.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")))
                source_note = parsed.get("source", "")

                if amount_val <= 0:
                    st.warning("⚠️ Could not detect a valid amount. Please mention a number like '450' or '₹100'.")
                else:
                    # Save to database
                    add_expense_to_db(
                        date=date_val,
                        item=item_name,
                        category=cat_name,
                        amount=amount_val,
                        mode=mode_name,
                        bank=bank_name,
                        raw_text=active_prompt
                    )
                    st.toast(f"✅ Added {item_name}: {selected_currency}{amount_val:,.2f}", icon="💸")
                    st.success(f"🎉 **Added {selected_currency}{amount_val:,.2f}** for **{item_name}** ({bank_name} via {mode_name})")
                    if "Offline" in source_note:
                        st.caption(f"ℹ️ {source_note}")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error processing expense: {str(e)}")

    # Manual Form Entry Accordion (Alternative to chat)
    with st.expander("✍️ Or Enter Manually (Traditional Form)"):
        with st.form("manual_entry_form", clear_on_submit=True):
            m_col1, m_col2 = st.columns(2)
            m_item = m_col1.text_input("Item Name", placeholder="e.g. Coffee & Sandwich")
            m_amount = m_col2.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            
            m_col3, m_col4 = st.columns(2)
            categories = ["Food & Dining", "Groceries", "Shopping", "Bills & Utilities", 
                          "Travel & Fuel", "Entertainment", "Health & Fitness", "ATM & Cash", "Investment", "Miscellaneous"]
            m_cat = m_col3.selectbox("Category", categories)
            modes = ["UPI", "Credit Card", "Debit Card", "Cash", "ATM Withdrawal", "Net Banking", "Other"]
            m_mode = m_col4.selectbox("Payment Mode", modes)
            
            m_col5, m_col6 = st.columns(2)
            m_bank = m_col5.text_input("Bank / Card", value="Bank of Baroda")
            m_date = m_col6.date_input("Date", value=datetime.now().date())

            if st.form_submit_button("➕ Save Expense", use_container_width=True):
                if m_amount > 0 and m_item.strip():
                    date_full = f"{m_date.strftime('%Y-%m-%d')} {datetime.now().strftime('%H:%M')}"
                    add_expense_to_db(date_full, m_item.strip(), m_cat, float(m_amount), m_mode, m_bank.strip(), "Manual Entry")
                    st.success(f"Added {m_item} ({selected_currency}{m_amount})")
                    st.rerun()
                else:
                    st.warning("Please enter an item name and amount > 0.")

    # Recent Transactions Feed on Left
    st.markdown("#### 🕒 Latest Activity")
    df_recent = get_all_expenses().head(5)
    if not df_recent.empty:
        for _, row in df_recent.iterrows():
            st.markdown(f"""
            <div class="txn-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <strong style="font-size:1.05rem;">{row['item']}</strong>
                    <span style="font-size:1.15rem; font-weight:700; color:#10B981;">{selected_currency}{row['amount']:,.2f}</span>
                </div>
                <div style="margin-top:6px;">
                    <span class="badge badge-cat">{row['category']}</span>
                    <span class="badge badge-bank">{row['bank']}</span>
                    <span class="badge badge-mode">{row['mode']}</span>
                    <span style="color:#94A3B8; font-size:0.8rem; margin-left:6px;">📅 {row['date']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No activity logged yet. Use the chat bar above!")

# ------------------------------------------------------------------------------
# RIGHT COLUMN: VISUAL DASHBOARD & ANALYTICS
# ------------------------------------------------------------------------------
with col_dash:
    st.subheader("📊 Spending Analytics")
    
    df_dash = get_all_expenses()

    if not df_dash.empty:
        tab_bank, tab_cat, tab_trend = st.tabs(["🏦 Bank Summary", "🏷️ Categories", "📈 Daily Trend"])

        with tab_bank:
            bank_summary = df_dash.groupby("bank")["amount"].sum().reset_index()
            bank_chart = alt.Chart(bank_summary).mark_bar(cornerRadius=6, color="#3B82F6").encode(
                x=alt.X("amount:Q", title=f"Total Spent ({selected_currency})"),
                y=alt.Y("bank:N", sort="-x", title="Bank / Source"),
                tooltip=["bank:N", alt.Tooltip("amount:Q", format=",.2f")]
            ).properties(height=260)
            st.altair_chart(bank_chart, use_container_width=True)

        with tab_cat:
            cat_summary = df_dash.groupby("category")["amount"].sum().reset_index()
            cat_chart = alt.Chart(cat_summary).mark_arc(innerRadius=50).encode(
                theta=alt.Theta("amount:Q", title="Amount"),
                color=alt.Color("category:N", legend=alt.Legend(title="Category")),
                tooltip=["category:N", alt.Tooltip("amount:Q", format=",.2f")]
            ).properties(height=260)
            st.altair_chart(cat_chart, use_container_width=True)

        with tab_trend:
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

        # Transaction Table with Search & Delete
        st.subheader("📝 Transaction History")
        
        # Filter controls
        f_col1, f_col2 = st.columns([1, 1])
        all_banks = ["All Banks"] + sorted(list(df_dash["bank"].unique()))
        selected_bank = f_col1.selectbox("Filter by Bank", all_banks)
        
        all_categories = ["All Categories"] + sorted(list(df_dash["category"].unique()))
        selected_cat = f_col2.selectbox("Filter by Category", all_categories)

        filtered_df = df_dash.copy()
        if selected_bank != "All Banks":
            filtered_df = filtered_df[filtered_df["bank"] == selected_bank]
        if selected_cat != "All Categories":
            filtered_df = filtered_df[filtered_df["category"] == selected_cat]

        # Display clean styled dataframe
        display_df = filtered_df[["id", "date", "item", "category", "amount", "mode", "bank"]].copy()
        display_df["amount"] = display_df["amount"].apply(lambda x: f"{selected_currency}{x:,.2f}")
        display_df.rename(columns={
            "id": "ID", "date": "Date & Time", "item": "Description",
            "category": "Category", "amount": "Amount", "mode": "Payment Mode", "bank": "Bank / Account"
        }, inplace=True)

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Delete Transaction Option
        with st.expander("🗑️ Delete a Transaction"):
            del_id = st.number_input("Enter Transaction ID to Delete:", min_value=1, step=1)
            if st.button("Confirm Delete", type="primary"):
                delete_expense_from_db(del_id)
                st.success(f"Transaction ID {del_id} removed.")
                st.rerun()

    else:
        st.info("No expenses found. Enter your first spend on the left to see live analytics!")

# ==============================================================================
# FOOTER
# ==============================================================================
st.divider()
f_col1, f_col2 = st.columns([3, 1])
f_col1.caption("Built with Streamlit, Google Gemini API, and SQLite/Google Sheets. 100% Free & Open Source.")
f_col2.caption("⚡ Powered by Google DeepMind / Gemini")
