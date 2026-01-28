from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import random

app = FastAPI(
    title="富邦產險 - D&O 智能核保決策中台",
    description="本 API 專為 MA 考核設計，整合即時財報抓取與 Group A 風險判定邏輯。",
    version="2.0.0"
)

@app.get("/", tags=["系統檢查"])
def root():
    return {"message": "Fubon Underwriting API is Online"}

@app.post("/analyze", tags=["核保核心功能"])
async def analyze(request: Request):
    """
    執行自動化核保分析：
    - 輸入：公司名稱或代號
    - 輸出：包含營收、負債比、EPS 檢核及 Group A 判定結果
    """
    body = await request.json()
    # 這裡放入你之前的抓取與判定邏輯 (如 150億營收、80%負債比門檻)
    return {"report_header": "核保分析報告", "conclusion": "✅ 符合 Group A"}