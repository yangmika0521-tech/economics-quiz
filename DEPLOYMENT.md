# 經濟學 互動式評量與題庫測驗系統 — 部署與維運手冊 (Deployment Guide)

本文件詳細說明 **經濟學 互動式評量與題庫測驗系統 (Economics Interactive Evaluation & Quiz Practice System)** 之雙運行架構 (Dual-Runtime Mode)、本地端 FastAPI 服務啟動流程、以及 GitHub Pages 純靜態站點部署操作指南。

---

## 1. 雙運行架構設計 (Dual-Runtime Architecture)

本系統採用領先的 **雙運行架構 (Dual-Runtime Mode)**，同一套前端 SPA 程式碼可無縫適應兩種截然不同的執行環境，無需任何繁瑣的環境變數重新編譯：

```
                      ┌────────────────────────────────────────┐
                      │          SPA 前端進入點                │
                      │ (index.html / static/js/app.js)        │
                      └──────────────────┬─────────────────────┘
                                         │
                         環境自動探測 (initDualRuntime)
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
    [模式 A: FastAPI 動態後端]                        [模式 B: 純前端靜態運行]
  • 適用：本地研究、教學實驗室、內部伺服器             • 適用：GitHub Pages、CDN、離線封裝
  • 條件：本機或伺服器連線成功 (`/api/chapters`)      • 條件：網址為 `*.github.io` 或無後端
  • 隨機抽取：後端 `app.quiz_engine`                 • 隨機抽取：前端客戶端 Fisher-Yates
  • 評分診斷：後端防作弊運算                          • 評分診斷：前端安全對比評分引擎
  • 資料來源：記憶體快取 + `data/questions.json`      • 資料來源：非同步載入 `./data/questions.json`
```

### 1.1 自動探測機制 (Auto-Detection)
- 當使用者透過瀏覽器存取頁面時，`static/js/app.js` 會自動檢查當前網域名稱：
  1. 若網址後綴為 `github.io` 或使用 `file://` 協定，系統立即啟用 **靜態運行模式 (Static Mode)**。
  2. 若為一般網址（如 `http://localhost:8000/`），前端會在 1.8 秒內非同步探測 `GET /api/chapters`：
     - 若後端 API 成功回應，啟用 **🟢 API 連線模式 (FastAPI)**。
     - 若無後端伺服器回應（連線失敗或超時），平滑切換至 **🌐 靜態運行模式 (GitHub Pages)**。
- 頂部導航列的狀態徽章 (`#runtime-badge`) 會即時顯示目前的運作模式，清晰透明。

---

## 2. 本地開發與 FastAPI 動態後端運行

### 2.1 環境需求
- Python 3.12+ (支援 Windows / macOS / Linux)
- pip 套件管理器

### 2.2 安裝相依套件
在專案根目錄執行：
```powershell
pip install fastapi uvicorn pydantic python-docx pytest httpx
```

### 2.3 啟動 FastAPI 動態伺服器
在專案根目錄下啟動 Uvicorn 服務器：
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
或直接使用 uvicorn 命令：
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2.4 系統存取與 API 文件
- **互動式前端 SPA**：打開瀏覽器訪問 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Swagger UI 互動式 API 文件**：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc 規範說明文件**：[http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 3. GitHub Pages 純靜態部署指南

本系統的前端採用原生 Vanilla JavaScript (ES6+) 與 CSS3 模組化架構，完全不依賴 Webpack/Vite 複雜打包流程，天生支援 GitHub Pages 零配置靜態部署。

### 3.1 目錄結構契約 (Relative Paths Compliance)
為確保在 GitHub Pages 存儲庫子目錄（例如 `https://<username>.github.io/<repository-name>/`）下正常存取，所有靜態資源與題庫載入一律使用標準相對路徑：
- 根目錄入口：`./index.html`
- 靜態 CSS 樣式：`./static/css/style.css`
- 靜態 JS 核心：`./static/js/app.js`
- 圖表媒體檔案：`./static/media/*.png`
- 題庫 JSON 檔案：`./data/questions.json`

### 3.2 部署步驟
1. **建立並推送 GitHub 儲存庫**：
   將整個專案目錄推送至 GitHub 儲存庫的 `main` 分支：
   ```powershell
   git add .
   git commit -m "feat: complete Milestone 3 Interactive SPA & Dual-Runtime Deployment"
   git push origin main
   ```
2. **開啟 GitHub Pages 託管設定**：
   - 前往 GitHub 儲存庫頁面，點選頂部 **Settings** (設定)。
   - 在左側選單點選 **Pages**。
   - 在 **Build and deployment** 下方的 **Source** 選擇 **Deploy from a branch**。
   - 在 **Branch** 選單選擇 `main`，資料夾選擇 `/ (root)`。
   - 點選 **Save** 儲存設定。
3. **完成部署**：
   - GitHub Actions 將於 1~2 分鐘內自動完成靜態網站發佈。
   - 發布後網址為：`https://<您的帳號>.github.io/<儲存庫名稱>/`。
   - 瀏覽器開啟該網址即可直接進入測驗系統，頂部自動顯示「🌐 靜態運行模式 (GitHub Pages)」，所有隨機抽題、圖表放大、交卷評分與繁體中文詳析診斷皆在瀏覽器端流暢執行！

### 3.3 本地模擬測試純靜態模式
若要在本機不啟動 FastAPI 的情況下測試 GitHub Pages 靜態運作行為，可使用 Python 內建的 HTTP 靜態伺服器：
```powershell
python -m http.server 8080
```
開啟瀏覽器訪問 [http://127.0.0.1:8080/](http://127.0.0.1:8080/)，系統將完美展現純靜態模式運作。

---

## 4. 行動端響應式體驗 (Mobile-First RWD) 特色

本系統嚴格遵循現代行動優先設計規範：
1. **觸控友善尺寸 (Touch Target Sizing)**：
   - 所有點選按鈕、選項卡片、抽屜按鍵皆保證大於等於 **44px × 44px**，徹底防止手機誤觸。
2. **滑入式題號抽屜 (Slide-in Palette Drawer)**：
   - 在手機等窄螢幕寬度（< 768px）下，題號抽屜以平滑滑入式底層覆蓋設計呈現；在平板與電腦螢幕（≥ 768px）下提供寬闊導航面板。
   - 題號具備即時四態徽章（當前題目 藍框微光、已作答 實心藍、未填答 柔和灰、標記題 警示黃 🚩）。
3. **經濟學圖表互動放大鏡 (Diagram Lightbox Modal)**：
   - 針對經濟學供需曲線、PPF 生產可能曲線與彈性圖表，點擊即可開啟全螢幕視窗放大檢視，手機端輕鬆看清坐標與文字。
4. **交卷防呆機制 (Submission Guardrail)**：
   - 點選交卷時若有未答題目，系統會主動彈出高對比警示視窗，列出未答題號並支援一鍵點擊跳轉續答，避免誤交。
5. **分項診斷與三維解析卡片 (Diagnostic Cards)**：
   - 測驗完成後提供各章答對率進度條。
   - 每題解析清晰區分為：
     - 💡 **【考點核心】**：核心概念定義與定理。
     - 📖 **【正解詳析】**：為什麼正確答案為真之推理步驟。
     - ⚠️ **【干擾項辨析】**：逐項說明其他選項之錯誤癥結。
   - 支援「錯題重練」專屬模式，針對薄弱章節強化衝刺。

---

## 5. 自動化測試與完整性驗證 (Verification)

本系統內建四層級 (Tiers 1-4) 全面自動化測試，可透過以下指令進行嚴格驗證：

### 5.1 執行 Pytest 測試套件
```powershell
python -m pytest tests/ -v -p no:cacheprovider
```

### 5.2 執行獨立四層級 E2E 驗證運行器
```powershell
python tests/e2e_test_runner.py
```
全部 18 項端到端斷言應 100% 通過（報告顯示 `[PASS]`，Exit Code 為 0）。
