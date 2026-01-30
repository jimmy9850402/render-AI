from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd

app = FastAPI(title="Fubon D&O - yfinance Accurate Engine")

def safe_get(df, label):
    """仿照您 Streamlit 的安全抓取邏輯"""
    try:
        if label in df.index:
            return df.loc[label].iloc[0] # 抓取最新一季
        return 0
    except: return 0

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "2330")).strip()
        symbol = f"{query}.TW" if query.isdigit() else f"{query}.TW" # 這裡建議搭配您的代碼轉換

        # 使用 yfinance 抓取 (與 Streamlit 一致)
        ticker = yf.Ticker(symbol)
        q_inc = ticker.quarterly_financials
        q_bal = ticker.quarterly_balance_sheet
        
        # 精確對應台積電數據
        rev = safe_get(q_inc, "Total Revenue") / 1000000 # 轉為百萬
        assets = safe_get(q_bal, "Total Assets") / 1000000
        liab = safe_get(q_bal, "Total Liabilities Net Minority Interest") / 1000000
        if liab == 0: liab = safe_get(q_bal, "Total Liab") / 1000000
        eps = safe_get(q_inc, "Basic EPS")
        
        # 核保邏輯判定
        dr = liab / assets if assets > 0 else 0
        reasons = []
        if rev < 15000: reasons.append("營收未達150億")
        if dr >= 0.8: reasons.append("負債比高於80%")
        if eps < 0: reasons.append("EPS 財務劣化")

        conclusion = "✅ 符合 Group A" if not reasons else "❌ 不符合 Group A"

        return {
            "header": f"【D&O 核保分析 - {symbol}】",
            "table": {
                "p": "最新一季數據",
                "rev": f"{rev:,.0f}",
                "assets": f"{assets:,.0f}",
                "dr": f"{dr:.2%}",
                "eps": f"{eps:.2f}"
            },
            "conclusion": conclusion,
            "reasons": "、".join(reasons) if reasons else "財務數據符合良質業務標準",
            "source": "✅ 數據源：yfinance API 實時對接 (同步 Streamlit 邏輯)"
        }
    except Exception as e:
        return JSONResponse({"error": f"API 處理失敗: {str(e)}"}, status_code=200)
