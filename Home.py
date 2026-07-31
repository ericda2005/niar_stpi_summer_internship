import streamlit as st

st.set_page_config(page_title="Home", layout="wide")

st.title("國研院科政中心—115年度暑期實習計畫")
st.divider()

st.markdown("### 網頁操作指南")
st.markdown("""
歡迎使用本系統，請由左側邊欄選擇所需的功能頁面：

**一、TechTimes**
* 按下搜尋鍵➡️抓取 Techtimes.com 首頁中不同板塊的文章
* 選擇要進行摘要的板塊
* 需於左側邊欄輸入 Gemini API Key。

**二、TechCrunch**
* 需於左側邊欄輸入 Gemini API Key。

**三、Summary**
* 支援自訂關鍵字與日期範圍的 Google 新聞搜尋。
* 自動進行文章過濾、分群，並產出關聯性長篇報告與單一短篇摘要。
* 需於左側邊欄輸入 SerpApi Key 與 Gemini API Key。

**通用操作步驟**
1. 由左側邊欄切換至目標功能頁面。
2. 展開左側邊欄的「⚙️ 系統設定」，確認 API 金鑰已輸入。
3. 依據頁面指示設定搜尋關鍵字、網址或日期區間。
4. 點擊執行按鈕，系統將自動進行爬取與 AI 分析。
5. 處理完成後，可於頁面最下方檢視詳細的視覺化預覽，或直接點擊按鈕下載 CSV 報表。
""")
