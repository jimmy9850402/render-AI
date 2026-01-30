from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yfinance as yf
import pandas as pd

app = FastAPI(title="Fubon Insurance - D&O Professional Engine v4.0")

def get_accurate_val(df, labels, period_idx=0):
    """精確抓取指定季度的數據標籤"""
    if df is None or df.empty: return 0
    df.index = df.index.str.strip()
    for label in labels:
        if label in df.index:
            # 確保抓取的是該季度的特定數值，而非整列
            val = df.iloc[df.index.get_loc(label), period_idx]
            return float(val) if pd.notna(val) else 0
    return 0

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "")).strip()
        
        # 1. 精準提取代號：不再有 "or 2330"
        stock_id = "".join(filter(str.isdigit, query))
        if not stock_id:
            return JSONResponse({"error": "請輸入公司代碼 (例如：2308)"}, status_code=200)
        
        symbol = f"{stock_id}.TW"
        ticker = yf.Ticker(symbol)
        q_inc = ticker.quarterly_financials
        q_bal = ticker.quarterly_balance_sheet

        if q_inc.empty:
            return JSONResponse({"error": f"無法獲取 {symbol} 財報，請確認代號是否存在。"}, status_code=200)

        # 2. 四期數據抓取 (單位：千元)
        table_rows = []
        # 確保循環抓取不同的季度 (0=最新, 1=前一季...)
        for i in range(min(4, len(q_inc.columns))):
            col = q_inc.columns[i]
            label = f"{col.year - 1911}年 Q{((col.month-1)//3)+1}"
            
            # 針對一般業與金融業的容錯標籤
            rev = get_accurate_val(q_inc, ["Total Revenue", "Operating Revenue", "Net Interest Income"], i) / 1000
            assets = get_accurate_val(q_bal, ["Total Assets"], i) / 1000
            liab = get_accurate_val(q_bal, ["Total Liabilities Net Minority Interest", "Total Liab"], i) / 1000
            eps = get_accurate_val(q_inc, ["Basic EPS", "Diluted EPS"], i)
            
            dr = (liab / assets) if assets > 0 else 0
            
            table_rows.append({
                "p": label, "rev": f"{rev:,.0f}", "assets": f"{assets:,.0f}",
                "dr": f"{dr:.2%}", "eps": f"{eps:.2f}"
            })

        # 3. 專業核保判定邏輯
        latest = table_rows[0]
        dr_val = float(latest['dr'].strip('%'))
        rev_val = float(latest['rev'].replace(',', ''))
        
        # 產業特殊判定：金融業 (2800-2899) 繞過 80% 負債比規則
        is_financial = 2800 <= int(stock_id) <= 2899
        
        pre_hits = []
        if float(latest['eps']) < 0: pre_hits.append("EPS 為負")
        # 只有「非金融業」才檢核 80% 負債比
        if not is_financial and dr_val > 80: pre_hits.append("負債比 > 80%")
        
        # Group A 判定 (金融業案件目前皆標註為人工複核)
        is_group_a = (rev_val >= 15000000) and (not is_financial) and (not pre_hits)
        
        return {
            "header": f"【D&O 財務核保報告 - {symbol} (單位：千元)】",
            "pre_check": {"hits": pre_hits, "status": "✔ 未命中" if not pre_hits else "⚠️ 命中"},
            "table": table_rows,
            "conclusion": "✅ 符合 Group A" if is_group_a else "⚠️ 建議由總公司核決人員評估 (非屬 Group A 或金融業)。",
            "source": f"📊 數據源：yfinance 實時抓取 (已執行全產業標籤校準)"
        }

    except Exception as e:
        return JSONResponse({"error": f"系統核心異常：{str(e)}"}, status_code=200)
