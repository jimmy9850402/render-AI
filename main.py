from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import os

app = FastAPI(
    title="富邦產險 - D&O 智能核保決策中台",
    description="MA 考核專用：自動化財務損益辨識與 Group A 資格判定系統",
    version="3.0.0"
)

# --- 2026 校準數據庫 (含名稱對照) ---
# 確保輸入「名稱」或「代號」都能精準命中
UNDERWRITING_DATA = {
    "2330": {"name": "台積電", "rev": 3809050, "assets": 7933024, "liab": 2471930, "eps": 66.25, "is_adr": True},
    "1101": {"name": "台泥", "rev": 150662, "assets": 485200, "liab": 251000, "eps": -1.28, "is_adr": False},
    "2881": {"name": "富邦金", "rev": 352100, "assets": 13254100, "liab": 12458100, "eps": 5.6, "is_adr": False},
    "2317": {"name": "鴻海", "rev": 6621000, "assets": 4125000, "liab": 2580000, "eps": 10.2, "is_adr": False}
}

# 建立名稱到代號的映射
NAME_TO_ID = {v["name"]: k for k, v in UNDERWRITING_DATA.items()}

@app.get("/")
def health_check():
    return {"status": "Fubon Underwriting API is Online"}

@app.post("/analyze")
async def analyze_company(request: Request):
    try:
        payload = await request.json()
        query = str(payload.get("company", "")).strip()
        
        # 1. 自動辨識輸入 (代號或名稱)
        stock_id = ""
        if query.isdigit():
            stock_id = query
        else:
            stock_id = NAME_TO_ID.get(query, "")

        # 2. 獲取數據 (若不在清單中則預設抓取台積電以確保 Demo 不中斷)
        if stock_id in UNDERWRITING_DATA:
            data = UNDERWRITING_DATA[stock_id]
            source = "✅ 官方校準數據 (2026)"
        else:
            # 沒命中時的防呆機制
            return JSONResponse(content={"error": f"找不到公司：{query}，目前支援：台積電、台泥、富邦金、鴻海"}, status_code=404)

        # 3. 執行 D&O 核保判定邏輯
        rev = data['rev']
        debt_ratio = data['liab'] / data['assets']
        eps = data['eps']
        
        reasons = []
        # 門檻 A：營收 > 150 億 (15000 百萬)
        if rev < 15000: reasons.append("營富未達 150 億門檻")
        # 門檻 B：負債比 < 80%
        if debt_ratio >= 0.8: reasons.append(f"負債比偏高 ({debt_ratio:.1%})")
        # 門檻 C：EPS 為正值
        if eps < 0: reasons.append(f"財務劣化 (EPS: {eps})")
        # 門檻 D：無 ADR 掛牌風險
        if data.get('is_adr'): reasons.append("具美國證券風險 (ADR)")

        # 結論判定
        is_group_a = len(reasons) == 0
        conclusion = "✅ 符合 Group A" if is_group_a else "❌ 非 Group A (需轉報再保)"
        cmcr_score = 1 if is_group_a else (6 if eps < 0 else 4)

        # 4. 回傳完整分析報告
        return {
            "report_header": f"【D&O 核保分析報告 - {data['name']} ({stock_id})】",
            "source": source,
            "metrics": {
                "revenue": f"{rev:,.0f} M",
                "debt_ratio": f"{debt_ratio:.2%}",
                "eps": str(eps)
            },
            "underwriting": {
                "conclusion": conclusion,
                "cmcr": cmcr_score,
                "reasons": ", ".join(reasons) if reasons else "財務穩健，符合標準"
            },
            "dog_link": f"https://statementdog.com/analysis/{stock_id}"
        }

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    # 本地測試用
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
