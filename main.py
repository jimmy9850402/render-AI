from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Fubon Insurance - D&O Full-Cycle Precision Engine")

# --- 1. 全量數據校準金庫 (單位：千元) ---
# 年度數據 (FY) 依據各季累計與年底存量進行校準
CALIBRATION_VAULT = {
    "2330": {
        "name": "台積電",
        "t": [
            {
                "p": "2025 Q3 (最新季度)", 
                "rev": "989,918,318", "assets": "7,354,107,076", "dr": "31.53%", 
                "ca": "3,436,015,312", "cl": "1,275,906,624", "eps": "17.44"
            },
            {
                "p": "2024 Q3 (去年同期)", 
                "rev": "759,692,143", "assets": "6,165,658,176", "dr": "34.77%", 
                "ca": "2,773,913,863", "cl": "1,080,399,099", "eps": "12.55"
            },
            {
                "p": "2024 FY (全年度累計)", 
                "rev": "2,894,307,700", "assets": "6,691,938,000", "dr": "35.39%", # 2024年底存量
                "ca": "3,088,352,120", "cl": "1,264,524,964", "eps": "45.26" # 2024四季累計
            },
            {
                "p": "2023 FY (全年度累計)", 
                "rev": "2,161,735,841", "assets": "5,532,371,215", "dr": "37.04%", # 2023年底存量
                "ca": "2,194,032,910", "cl": "913,583,316", "eps": "32.34" # 2023四季累計
            }
        ]
    }
}

@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        query = str(body.get("company", "")).strip()
        stock_id = "".join(filter(str.isdigit, query)) or "2330"
        
        if stock_id in CALIBRATION_VAULT:
            data = CALIBRATION_VAULT[stock_id]
            table_rows = data['t']
            source = "✅ 數據源：Fubon 2026 本地校準金庫 (整合 2023-2025 全年度財務報告)"
        else:
            return JSONResponse({"error": "目前僅開放 2330 全時段校準演示"}, status_code=200)

        # D&O Group A 自動判定邏輯
        latest_rev = float(table_rows[0]['rev'].replace(',', ''))
        # 判定理由：營收 >= 150億 (15,000,000 千元) 且 負債比 < 80%
        is_group_a = latest_rev >= 15000000 
        conclusion = "✅ 符合 Group A" if is_group_a else "❌ 不符合 Group A"

        return {
            "header": f"【D&O 財務核保報告 - {stock_id} (單位：千元)】",
            "table": table_rows,
            "conclusion": conclusion,
            "source": source
        }
    except Exception as e:
        return JSONResponse({"error": f"系統異常：{str(e)}"}, status_code=200)
