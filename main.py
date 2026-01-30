from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd
import urllib3

# 禁用 SSL 警告以確保連線穩定
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="Fubon Insurance - Precision D&O Underwriting Engine")

def get_accurate_val(df, labels):
    """精確抓取最新數據標籤並處理多索引問題"""
    for label in labels:
        if label in df.index:
            series = df.loc[label]
            # 取得最新一季 (iloc[0]) 並確保非 NaN
            val = series.iloc[0] if hasattr(series, 'iloc') else series
            return float(val) if pd.notna(val) else 0
    return 0

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "")).strip()
        # 提取數字代號，預設 2330
        stock_id = "".join(filter(str.isdigit, query)) or "2330"
        symbol = f"{stock_id}.TW"

        # 1. 介接 yfinance (與您的 Streamlit 邏輯同步)
        ticker = yf.Ticker(symbol)
        q_inc = ticker.quarterly_financials
        q_bal = ticker.quarterly_balance_sheet
        q_cf = ticker.quarterly_cashflow
        
        # 2. 建立四期財務表格 (單位：千元)
        table_rows = []
        # 抓取最近 4 個季度
        periods = q_inc.columns[:4] if not q_inc.empty else []
        
        for col in periods:
            # 轉換為民國紀年標籤範式
            label = f"{col.year - 1911}年 Q{((col.month-1)//3)+1}"
            
            # 獲取原始數據 (元) 並除以 1000 轉換為 (千元)
            rev = get_accurate_val(q_inc, ["Total Revenue", "Operating Revenue"]) / 1000
            assets = get_accurate_val(q_bal, ["Total Assets"]) / 1000
            liab = get_accurate_val(q_bal, ["Total Liabilities Net Minority Interest", "Total Liab"]) / 1000
            c_assets = get_accurate_val(q_bal, ["Current Assets"]) / 1000
            c_liab = get_accurate_val(q_bal, ["Current Liabilities"]) / 1000
            ocf = get_accurate_val(q_cf, ["Operating Cash Flow"]) / 1000
            eps = get_accurate_val(q_inc, ["Basic EPS", "Diluted EPS"])

            table_rows.append({
                "p": label,
                "rev": f"{rev:,.0f}",
                "assets": f"{assets:,.0f}",
                "dr": f"{(liab/assets):.2%}" if assets > 0 else "-",
                "ca": f"{c_assets:,.0f}",
                "cl": f"{c_liab:,.0f}",
                "cfo": f"{ocf:,.0f}",
                "eps": f"{eps:.2f}"
            })

        # 3. D&O Group A 核保自動判定 (150億門檻 = 15,000,000 千元)
        if not table_rows:
            return JSONResponse({"error": "無法獲取財報數據"}, status_code=200)
            
        latest = table_rows[0]
        latest_rev_val = float(latest['rev'].replace(',', ''))
        debt_ratio_val = float(latest['dr'].strip('%')) / 100 if latest['dr'] != "-" else 1.0
        
        reasons = []
        if latest_rev_val < 15000000: reasons.append("單季營收未達150億")
        if debt_ratio_val >= 0.8: reasons.append("負債比高於80%")
        
        conclusion = "✅ 符合 Group A" if not reasons else "❌ 不符合 Group A"

        return {
            "header": f"【D&O 財務核保分析 - {symbol} (單位：千元)】",
            "table": table_rows,
            "conclusion": conclusion,
            "reasons": "、".join(reasons) if reasons else "財務穩健且符合 A 類標準",
            "source": "📊 數據源：yfinance 官方介面 (已自動校準至截圖千元單位)"
        }

    except Exception as e:
        return JSONResponse({"error": f"數據抓取引擎異常：{str(e)}"}, status_code=200)
