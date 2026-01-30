from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd
import numpy as np

app = FastAPI(title="Fubon Insurance - D&O Universal Underwriting Hub 5.0")

# --- 1. 專業防禦性函數 ---
def safe_val(df, labels, idx=0):
    """精確抓取指定季度數據，並處理單位換算"""
    if df is None or df.empty: return 0
    df.index = df.index.str.strip()
    for label in labels:
        if label in df.index:
            try:
                # 抓取該標籤在指定索引(季度)的數值
                val = df.iloc[df.index.get_loc(label), idx]
                return float(val) if pd.notna(val) else 0
            except: continue
    return 0

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "")).strip()
        
        # 提取代號 (無預設值，確保輸入什麼就抓什麼)
        stock_id = "".join(filter(str.isdigit, query))
        if not stock_id:
            return JSONResponse({"error": "請輸入公司代號 (例如：2881)"}, status_code=200)
        
        symbol = f"{stock_id}.TW"
        ticker = yf.Ticker(symbol)
        
        # 獲取完整財務報表
        q_inc = ticker.quarterly_financials
        q_bal = ticker.quarterly_balance_sheet
        q_cf = ticker.quarterly_cashflow

        if q_inc.empty or q_bal.empty:
            return JSONResponse({"error": f"無法獲取 {symbol} 資料，請確認代號正確。"}, status_code=200)

        # --- 2. 建立四期數據表格 (單位：千元) ---
        table_rows = []
        max_periods = min(4, len(q_inc.columns))
        
        for i in range(max_periods):
            col = q_inc.columns[i]
            # 民國紀年標籤
            label = f"{col.year - 1911}年 Q{((col.month-1)//3)+1}"
            
            # 多產業標籤適配 (自動區分一般業與金融業)
            rev = safe_val(q_inc, ["Total Revenue", "Operating Revenue", "Net Interest Income"], i) / 1000
            assets = safe_val(q_bal, ["Total Assets"], i) / 1000
            liab = safe_val(q_bal, ["Total Liabilities Net Minority Interest", "Total Liab"], i) / 1000
            ca = safe_val(q_bal, ["Current Assets", "Total Current Assets"], i) / 1000
            cl = safe_val(q_bal, ["Current Liabilities", "Total Current Liabilities"], i) / 1000
            eps = safe_val(q_inc, ["Basic EPS", "Diluted EPS"], i)
            
            dr = (liab / assets) if assets > 0 else 0
            
            table_rows.append({
                "p": label, "rev": f"{rev:,.0f}", "assets": f"{assets:,.0f}",
                "dr": f"{dr:.2%}", "ca": f"{ca:,.0f}" if ca > 0 else "N/A",
                "cl": f"{cl:,.0f}" if cl > 0 else "N/A", "eps": f"{eps:.2f}"
            })

        # --- 3. D&O 核保判定邏輯 (精確執行您定義的規則) ---
        latest = table_rows[0]
        rev_val = float(latest['rev'].replace(',', ''))
        dr_val = float(latest['dr'].strip('%'))
        eps_val = float(latest['eps'])
        
        # 智慧產業識別：金融業 (2800-2899)
        is_fin = 2800 <= int(stock_id) <= 2899
        
        pre_hits = []
        if eps_val < 0: pre_hits.append("EPS 為負")
        if not is_fin and dr_val > 80: pre_hits.append("負債比 > 80%")
        
        # Group A 判定標籤 (嚴格遵循 150 億門檻)
        # 150億 = 15,000,000 千元
        is_group_a = (rev_val >= 15000000) and (not is_fin) and (not pre_hits)
        
        # CMCR 評分 (基於財務槓桿與獲利能力之 1-9 分加權)
        cmcr_score = round(max(1, min(9, (dr_val / 10) + (5 if eps_val < 0 else 1))), 1)

        return {
            "header": f"【D&O 智能核保分析 - {ticker.info.get('shortName', stock_id)} ({symbol})】",
            "pre_check": {"hits": pre_hits, "status": "✔ 未命中" if not pre_hits else "⚠️ 命中"},
            "table": table_rows,
            "cmcr": {"score": cmcr_score, "level": "低" if cmcr_score <= 3 else "中" if cmcr_score <= 6 else "高"},
            "conclusion": "✅ 本案符合 Group A" if is_group_a else "⚠️ 建議由總公司核決人員評估 (非屬 Group A 或金融業)。",
            "source": f"📊 數據源：yfinance 跨產業實時抓取 (單位：千元)"
        }

    except Exception as e:
        return JSONResponse({"error": f"系統處理異常：{str(e)}"}, status_code=200)
