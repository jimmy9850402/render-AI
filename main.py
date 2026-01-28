from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import os

app = FastAPI(title="Fubon Insurance - TWSE OpenAPI Underwriting Hub")

# 證交所 OpenAPI 端點
ENDPOINTS = {
    "BS_GENERAL": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci", # 一般業資產負債
    "IS_GENERAL": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci", # 一般業損益
    "BS_INS": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ins",     # 保險業資產負債
    "IS_FIN": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_fh",     # 金控業損益
}

def get_twse_data(stock_id):
    try:
        headers = {'accept': 'application/json'}
        # 同時請求資產負債與損益 (一般業為例)
        bs_res = requests.get(ENDPOINTS["BS_GENERAL"], headers=headers, timeout=10).json()
        is_res = requests.get(ENDPOINTS["IS_GENERAL"], headers=headers, timeout=10).json()
        
        # 篩選特定公司
        bs = next((x for x in bs_res if x['公司代號'] == stock_id), None)
        is_data = next((x for x in is_res if x['公司代號'] == stock_id), None)
        
        return bs, is_data
    except: return None, None

@app.post("/analyze")
async def analyze(request: Request):
    body = await request.json()
    query = str(body.get("company", "")).strip()
    stock_id = "".join(filter(str.isdigit, query)) or "2330"

    bs, is_data = get_twse_data(stock_id)
    if not bs or not is_data:
        return JSONResponse({"error": f"證交所 OpenAPI 找不到代號 {stock_id}"}, status_code=200)

    # --- 財務指標運算 (LaTeX 公式定義) ---
    # 負債比 = 負債總額 / 資產總額
    # 流動比 = 流動資產 / 流動負債
    def to_float(s): return float(s.replace(',', '')) if s else 0.0

    assets = to_float(bs.get('資產總額', '0'))
    liab = to_float(bs.get('負債總額', '0'))
    c_assets = to_float(bs.get('流動資產', '0'))
    c_liab = to_float(bs.get('流動負債', '0'))
    rev = to_float(is_data.get('營業收入', '0'))
    eps = to_float(is_data.get('基本每股盈餘（元）', '0'))

    debt_ratio = liab / assets if assets > 0 else 0
    curr_ratio = c_assets / c_liab if c_liab > 0 else 0

    # --- 嚴格核保判定邏輯 ---
    reasons = []
    if rev < 15000: reasons.append("營收未達150億門檻")
    if debt_ratio >= 0.8: reasons.append(f"負債比偏高 ({debt_ratio:.1%})")
    if eps < 0: reasons.append(f"EPS 財務劣化 ({eps})")
    
    is_a = len(reasons) == 0
    conclusion = "✅ 符合 Group A" if is_a else "❌ 不符合 Group A"

    return {
        "header": f"【D&O 官方核保分析 - {bs['公司名稱']} ({stock_id})】",
        "pre_check": {
            "eps_fail": "✔ 命中" if eps < 0 else "❌ 未命中",
            "curr_fail": "✔ 命中" if curr_ratio < 1.0 else "❌ 未命中",
            "debt_fail": "✔ 命中" if debt_ratio >= 0.8 else "❌ 未命中"
        },
        "table": {
            "p": f"{bs['年度']}年第{bs['季別']}季",
            "rev": f"{rev:,.0f}",
            "assets": f"{assets:,.0f}",
            "debt": f"{debt_ratio:.2%}",
            "curr": f"{curr_ratio:.2%}",
            "eps": f"{eps}"
        },
        "conclusion": conclusion,
        "reasons": "、".join(reasons) if reasons else "無明顯風險指標",
        "source": "✅ 來源：證交所 OpenAPI (t187ap07_L_ci / t187ap06_L_ci) 實時對接"
    }
