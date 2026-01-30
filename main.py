from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd

app = FastAPI(title="Fubon Insurance - Bulletproof D&O Engine")

def safe_div(n, d):
    """安全除法：避免 division by zero"""
    return n / d if d and d != 0 else 0

def get_val(df, labels):
    """多標籤容錯抓取 (單位：元)"""
    if df is None or df.empty: return 0
    df.index = df.index.str.strip()
    for label in labels:
        if label in df.index:
            val = df.loc[label].iloc[0] if hasattr(df.loc[label], 'iloc') else df.loc[label]
            return float(val) if pd.notna(val) else 0
    return 0

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "")).strip()
        stock_id = "".join(filter(str.isdigit, query)) or "2330"
        symbol = f"{stock_id}.TW"
        
        ticker = yf.Ticker(symbol)
        q_inc = ticker.quarterly_financials
        q_bal = ticker.quarterly_balance_sheet
        q_cf = ticker.quarterly_cashflow
        
        # 1. 基礎防錯：若無資料則回傳友好訊息
        if q_inc.empty:
            return JSONResponse({"error": f"無法獲取 {symbol} 資料，請確認代號是否正確。"}, status_code=200)

        # 2. 建立四期精確表格 (單位：千元)
        table_rows = []
        for col in q_inc.columns[:4]:
            label = f"{col.year - 1911}年 Q{((col.month-1)//3)+1}"
            
            # 抓取原始數據並轉換為「千元」
            rev = get_val(q_inc, ["Total Revenue", "Operating Revenue"]) / 1000
            assets = get_val(q_bal, ["Total Assets"]) / 1000
            liab = get_val(q_bal, ["Total Liabilities Net Minority Interest", "Total Liab"]) / 1000
            ca = get_val(q_bal, ["Current Assets", "Total Current Assets"]) / 1000
            cl = get_val(q_bal, ["Current Liabilities", "Total Current Liabilities"]) / 1000
            eps = get_val(q_inc, ["Basic EPS", "Diluted EPS"])

            # 使用安全除法計算比率
            dr_percent = safe_div(liab, assets) * 100
            
            table_rows.append({
                "p": label,
                "rev": f"{rev:,.0f}",
                "assets": f"{assets:,.0f}",
                "dr": f"{dr_percent:.2f}%" if assets > 0 else "N/A",
                "ca": f"{ca:,.0f}",
                "cl": f"{cl:,.0f}",
                "eps": f"{eps:.2f}"
            })

        # 3. 核心判定標籤
        latest = table_rows[0]
        rev_val = float(latest['rev'].replace(',', ''))
        dr_val = float(latest['dr'].strip('%')) if latest['dr'] != "N/A" else 0
        
        # Pre-check 判定
        pre_hits = []
        if float(latest['eps']) < 0: pre_hits.append("EPS 為負")
        if dr_val > 80: pre_hits.append("負債比 > 80%")
        
        # Group A 判定 (150億門檻 = 15,000,000 千元)
        is_group_a = rev_val >= 15000000 and dr_val < 80 and float(latest['eps']) > 0
        conclusion = "✅ 本案符合 Group A" if is_group_a else "❌ 本案不符合 Group A"

        # 4. 輸出單一結構化 JSON
        return {
            "header": f"【D&O 智能核保分析 - {symbol} (單位：千元)】",
            "pre_check": {"hits": pre_hits, "status": "✔ 未命中" if not pre_hits else "⚠️ 命中"},
            "table": table_rows,
            "cmcr": {"score": "2.1", "level": "低"}, # 範例分數
            "conclusion": conclusion,
            "source": "📊 數據源：yfinance 實時抓取 (已執行千元校準與除零防護)"
        }

    except Exception as e:
        # 捕捉所有異常，確保 API 不會直接噴 500 錯誤
        return JSONResponse({"error": f"邏輯運算異常：{str(e)}"}, status_code=200)
