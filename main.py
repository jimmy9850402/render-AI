from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd
import numpy as np

app = FastAPI(title="Fubon D&O Intelligent Underwriting Engine v2.0")

def get_val(df, labels):
    """多標籤容錯抓取 (單位：千元)"""
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
        
        if q_inc.empty: return JSONResponse({"error": "查無公開資料"}, status_code=200)

        # 1. 建立四期財務表格 (單位：千元)
        table_rows = []
        for col in q_inc.columns[:4]:
            label = f"{col.year - 1911}年 Q{((col.month-1)//3)+1}"
            rev = get_val(q_inc.loc[:, [col]], ["Total Revenue", "Operating Revenue"]) / 1000
            assets = get_val(q_bal.loc[:, [col]], ["Total Assets"]) / 1000
            liab = get_val(q_bal.loc[:, [col]], ["Total Liabilities Net Minority Interest", "Total Liab"]) / 1000
            ca = get_val(q_bal.loc[:, [col]], ["Current Assets"]) / 1000
            cl = get_val(q_bal.loc[:, [col]], ["Current Liabilities"]) / 1000
            ocf = get_val(q_cf.loc[:, [col]], ["Operating Cash Flow"]) / 1000
            eps = get_val(q_inc.loc[:, [col]], ["Basic EPS"])
            
            table_rows.append({
                "p": label, "rev": f"{rev:,.0f}", "assets": f"{assets:,.0f}",
                "dr": f"{(liab/assets)*100:.2f}%" if assets > 0 else "0%",
                "ca": f"{ca:,.0f}", "cl": f"{cl:,.0f}", "cfo": f"{ocf:,.0f}", "eps": eps
            })

        # 2. CMCR 財務評分計算 (30/30/15/15/10 權重)
        # 模擬比率計算邏輯 (實務上需對應更多 yfinance 標籤)
        latest = q_inc.iloc[:, 0]
        ebitda = get_val(q_inc, ["EBITDA"])
        interest = get_val(q_inc, ["Interest Expense"]) or 1 # 避免除以 0
        debt = get_val(q_bal, ["Total Liab"])
        focf = get_val(q_cf, ["Free Cash Flow"])
        ffo = get_val(q_inc, ["Net Income"]) + get_val(q_inc, ["Reconciliation Notes"]) # 模擬 FFO

        # 評分邏輯：比率越高分數越低 (1-9分)
        def scale_1_9(val, threshold): return max(1, min(9, round(threshold / (val + 0.1))))
        
        s1 = scale_1_9(ffo/debt, 0.2) * 0.3
        s2 = scale_1_9(ebitda/debt, 0.3) * 0.3
        s3 = scale_1_9(ocf/debt, 0.2) * 0.15
        s4 = scale_1_9(focf/debt, 0.1) * 0.15
        s5 = scale_1_9(ebitda/interest, 5.0) * 0.1
        cmcr = round(s1 + s2 + s3 + s4 + s5, 1)

        # 3. Pre-check 與 Group A 判定標籤
        latest_data = table_rows[0]
        dr_val = float(latest_data['dr'].strip('%'))
        eps_val = latest_data['eps']
        rev_val = float(latest_data['rev'].replace(',', ''))
        
        pre_check_hits = []
        if eps_val < 0: pre_check_hits.append("EPS 為負")
        if dr_val > 80: pre_check_hits.append("負債比 > 80%")
        # 流動比判定
        curr_ratio = (float(latest_data['ca'].replace(',','')) / float(latest_data['cl'].replace(',',''))) * 100
        if curr_ratio < 100: pre_check_hits.append("流動比 < 100%")

        # 4. 最終標籤判定
        # 嚴格規則：營收 < 150億 (15,000,000千元) 或 負債比 >= 80% 或 命中 Pre-check
        is_group_a = (rev_val >= 15000000) and (dr_val < 80) and (len(pre_check_hits) == 0)
        
        return {
            "header": f"【D&O 智能核保分析 - {symbol}】",
            "pre_check": {"hits": pre_check_hits, "count": len(pre_check_hits)},
            "table": table_rows,
            "cmcr": {"score": cmcr, "level": "低" if cmcr <= 3 else "中" if cmcr <= 6 else "高"},
            "group_a": "符合" if is_group_a else "不符合",
            "conclusion_type": "A" if is_group_a else "B",
            "source": "✅ 數據源：yfinance 實時抓取與 Fubon 邏輯引擎"
        }
    except Exception as e:
        return JSONResponse({"error": f"系統異常：{str(e)}"}, status_code=200)
