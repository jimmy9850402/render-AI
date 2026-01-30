from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd
import requests
import os
from supabase import create_client

app = FastAPI(title="Fubon Insurance - Resilient D&O Engine")

# 1. 安全初始化：從 Render 環境變數讀取
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. 建立偽裝 Session，避免被 Yahoo 封鎖
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
})

def find_stock_code(query):
    """移植您的 Supabase 邏輯，並加入模糊容錯"""
    if query.isdigit(): return f"{query}.TW"
    try:
        res = supabase.table("stock_isin_list").select("code, name").ilike("name", f"%{query}%").execute()
        if res.data:
            # 優先回傳完全符合的名字，否則回傳第一個搜尋結果
            for item in res.data:
                if item['name'] == query: return f"{item['code']}.TW"
            return f"{res.data[0]['code']}.TW"
    except: return None

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "")).strip()
        symbol = find_stock_code(query)
        
        if not symbol:
            return JSONResponse({"error": f"找不到「{query}」的公司代號"}, status_code=200)

        # 3. 使用 Session 抓取數據，解決空值問題
        ticker = yf.Ticker(symbol, session=session)
        q_inc = ticker.quarterly_financials
        q_bal = ticker.quarterly_balance_sheet

        # 基礎防護：如果真的還是抓不到，回傳詳細錯誤供 Debug
        if q_inc is None or q_inc.empty:
            return JSONResponse({"error": f"yf 無法抓取 {symbol}。原因：Yahoo 伺服器拒絕連線或標籤格式更新。"}, status_code=200)

        # 4. 財務指標處理 (單位：千元)
        table_rows = []
        for col in q_inc.columns[:4]:
            label = f"{col.year - 1911}年 Q{((col.month-1)//3)+1}"
            
            # 使用您 Streamlit 的精確標籤邏輯
            def get_f(df, key): 
                try: return float(df.loc[key, col]) / 1000
                except: return 0

            rev = get_f(q_inc, "Total Revenue")
            assets = get_f(q_bal, "Total Assets")
            liab = get_f(q_bal, "Total Liabilities Net Minority Interest")
            if liab == 0: liab = get_f(q_bal, "Total Liab")
            eps = get_f(q_inc, "Basic EPS") * 1000 # EPS 不除 1000

            dr = (liab / assets) if assets > 0 else 0
            
            table_rows.append({
                "p": label, "rev": f"{rev:,.0f}", "assets": f"{assets:,.0f}",
                "dr": f"{dr:.2%}", "eps": f"{eps:.22f}" # EPS 保留兩位
            })

        # 5. D&O Group A 判定標籤
        latest_rev = float(table_rows[0]['rev'].replace(',', ''))
        is_group_a = (latest_rev >= 15000000) and (not (2800 <= int(symbol[:4]) <= 2899))
        
        return {
            "header": f"【D&O 核保分析 - {query} ({symbol})】",
            "table": table_rows,
            "conclusion": "✅ 符合 Group A" if is_group_a else "⚠️ 建議由總公司核決人員評估。",
            "source": "📊 數據源：yfinance 實時抓取 (已執行連線優化)"
        }

    except Exception as e:
        return JSONResponse({"error": f"邏輯異常：{str(e)}"}, status_code=200)
