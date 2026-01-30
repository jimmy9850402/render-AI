from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd
from supabase import create_client
import urllib3

# 1. 初始化連線 (請確保在 Render 的 Environment Variables 設定這些值)
SUPABASE_URL = "https://cemnzictjgunjyktrruc.supabase.co"
SUPABASE_KEY = "您的_SUPABASE_KEY" #
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Fubon Insurance - Precision Engine v5.0")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def find_stock_code(query):
    """移植您的 Supabase 名稱轉換邏輯"""
    if query.isdigit(): return f"{query}.TW"
    try:
        res = supabase.table("stock_isin_list").select("code, name").ilike("name", f"%{query}%").execute()
        if res.data:
            for item in res.data:
                if item['name'] == query: return f"{item['code']}.TW"
            return f"{res.data[0]['code']}.TW"
    except: return None

def safe_get(df, index_name, col):
    """移植您的精確標籤檢索邏輯"""
    try:
        if index_name in df.index:
            val = df.loc[index_name, col]
            # 處理可能回傳 Series 的情況
            return float(val.iloc[0] if hasattr(val, 'iloc') else val)
        return 0
    except: return 0

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "2330")).strip()
        
        # 1. 執行標的代碼轉換 (解決「打富邦金跑出台積電」的問題)
        symbol = find_stock_code(query)
        if not symbol:
            return JSONResponse({"error": f"資料庫中查無「{query}」的公司代號"}, status_code=200)

        # 2. 數據抓取 (比照 Streamlit 邏輯)
        ticker = yf.Ticker(symbol)
        q_inc = ticker.quarterly_financials
        q_bal = ticker.quarterly_balance_sheet
        q_cf = ticker.quarterly_cashflow

        if q_inc.empty:
            return JSONResponse({"error": "yf 抓取空值，請確認 Yahoo Finance 標記"}, status_code=200)

        # 3. 建立財務表格 (單位：千元，比照您 989B 的校準邏輯)
        table_rows = []
        for col in q_inc.columns[:4]:
            label = f"{col.year - 1911}年 Q{((col.month-1)//3)+1}"
            
            # 依照您的 safe_get 邏輯抓取，並除以 1000 轉換為「千元」
            rev = safe_get(q_inc, "Total Revenue", col) / 1000
            assets = safe_get(q_bal, "Total Assets", col) / 1000
            liab = safe_get(q_bal, "Total Liabilities Net Minority Interest", col) / 1000
            if liab == 0: liab = safe_get(q_bal, "Total Liab", col) / 1000
            ca = safe_get(q_bal, "Current Assets", col) / 1000
            cl = safe_get(q_bal, "Current Liabilities", col) / 1000
            eps = safe_get(q_inc, "Basic EPS", col)
            
            dr = (liab / assets) if assets > 0 else 0
            
            table_rows.append({
                "p": label, "rev": f"{rev:,.0f}", "assets": f"{assets:,.0f}",
                "dr": f"{dr:.2%}", "ca": f"{ca:,.0f}", "cl": f"{cl:,.0f}", "eps": f"{eps:.2f}"
            })

        # 4. 判定與結論
        latest = table_rows[0]
        rev_val = float(latest['rev'].replace(',', ''))
        dr_val = float(latest['dr'].strip('%'))
        
        is_group_a = (rev_val >= 15000000) and (dr_val < 80) and (float(latest['eps']) > 0)

        return {
            "header": f"【D&O 核保分析 - {query} ({symbol})】",
            "table": table_rows,
            "conclusion": "✅ 符合 Group A" if is_group_a else "⚠️ 建議由總公司核決人員評估。",
            "source": "📊 數據源：yfinance 實時抓取 (同步您的 Streamlit 邏輯)"
        }

    except Exception as e:
        return JSONResponse({"error": f"系統異常：{str(e)}"}, status_code=200)
