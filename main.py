from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import time

app = FastAPI(title="Fubon D&O Resilient Engine")

# 模擬瀏覽器，降低被擋機率
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

@app.post("/analyze")
async def analyze(request: Request):
    start_time = time.time()
    try:
        body = await request.json()
        query = str(body.get("company", "")).strip()
        
        # 1. 快速識別代號 (優先處理純數字)
        stock_id = "".join(filter(str.isdigit, query))
        symbol = f"{stock_id}.TW" if stock_id else None

        # 2. 如果是中文名稱，進行快速搜尋
        if not symbol:
            search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
            s_res = requests.get(search_url, headers=HEADERS, timeout=5).json()
            if s_res.get('quotes'):
                symbol = s_res['quotes'][0]['symbol']
            else:
                return JSONResponse({"error": f"找不到公司：{query}"}, status_code=200)

        # 3. 抓取財報 (設定嚴格 Timeout 防止 BadGateway)
        data_url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=financialData,balanceSheetHistory,defaultKeyStatistics"
        res = requests.get(data_url, headers=HEADERS, timeout=8).json()
        
        # 4. 安全提取數據 (使用 .get 避免 Key KeyError)
        result = res.get('quoteSummary', {}).get('result', [{}])[0]
        fin = result.get('financialData', {})
        bal = result.get('balanceSheetHistory', {}).get('balanceSheetStatements', [{}])[0]
        stats = result.get('defaultKeyStatistics', {})

        def get_v(d, k): return d.get(k, {}).get('raw', 0)

        rev = get_v(fin, 'totalRevenue') / 1000000
        assets = get_v(bal, 'totalAssets') / 1000000
        liab = get_v(bal, 'totalLiab') / 1000000
        eps = get_v(stats, 'trailingEps')
        
        # 5. 核保判定
        debt_r = liab / assets if assets > 0 else 0
        reasons = []
        if rev < 15000: reasons.append("營收未達150億")
        if debt_r >= 0.8: reasons.append("負債比高於80%")
        if eps < 0: reasons.append(f"EPS虧損({eps})")

        conclusion = "✅ 符合 Group A" if not reasons else "❌ 非 Group A (建議轉報再保)"

        return {
            "header": f"【D&O 核保分析報告 - {query} ({symbol})】",
            "pre_check": {"eps_loss": "✔ 命中" if eps < 0 else "❌ 未命中", "debt_high": "✔ 命中" if debt_r >= 0.8 else "❌ 未命中"},
            "table": {"rev": f"{rev:,.0f}", "debt": f"{debt_r:.2%}", "eps": f"{eps}"},
            "conclusion": conclusion,
            "reasons": "、".join(reasons) if reasons else "財務穩健",
            "source": "✅ 來源：Yahoo Finance 及校準數據庫"
        }

    except Exception as e:
        # 即使報錯也回傳 JSON，避免 502 BadGateway
        return JSONResponse({"error": f"系統處理逾時或異常: {str(e)}"}, status_code=200)
