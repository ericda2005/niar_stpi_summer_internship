import streamlit as st

st.set_page_config(page_title="Home", layout="wide")

st.title("新興科技新聞採集： 跨媒體自動化抓取與 AI 分類摘要設計")
st.subheader("國研院科政中心 — 115年度暑期實習計畫")
st.divider()

st.markdown("### 網頁操作指南")
st.markdown("歡迎使用本系統，請由左側邊欄選擇所需的功能頁面：")

st.markdown("""
<div style="background-color: #F7F7FF; color: #3c3c3c; padding: 20px; border-radius: 10px; margin-top: 10px;">
    <h4 style="margin-top: 0px;">一、TechTimes</h4>
    <ol style="margin-bottom: 0px;">
        <li>按下搜尋鍵 ➡️ 抓取 Techtimes.com 首頁中不同板塊的文章</li>
        <li>選擇要進行長篇摘要的板塊</li>
        <li>需於左側邊欄輸入 <span style="color: #fe5f55; font-weight: bold;">Gemini API Key</span>。</li>
    </ol>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style="background-color: #BDD5EA; color: #3c3c3c; padding: 20px; border-radius: 10px; margin-top: 10px;">
    <h4 style="margin-top: 0px;">二、TechCrunch</h4>
    <ol style="margin-bottom: 0px;">
        <li>按下搜尋鍵 ➡️ 抓取 Techcrunch.com 首頁中不同板塊的文章</li>
        <li>選擇要進行長篇摘要的板塊</li>
        <li>需於左側邊欄輸入 <span style="color: #fe5f55; font-weight: bold;">Gemini API Key</span>。</li>
    </ol>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style="background-color: #577399; color: #fcfcfc; padding: 20px; border-radius: 10px; margin-top: 10px;">
    <h4 style="margin-top: 0px;">三、Summary</h4>
    <ol style="margin-bottom: 0px;">
        <li>支援自訂關鍵字與日期範圍的 Google News 搜尋。</li>
        <li>自動進行文章過濾、分群，並產出具關連性之長篇摘要與單一短篇摘要。</li>
        <li>需於左側邊欄輸入  <span style="color: #fe5f55; font-weight: bold;">SerpApi API Key</span> 與  <span style="color: #fe5f55; font-weight: bold;">Gemini API Key</span>。</li>
    </ol>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style="background-color: #495867; color: #fcfcfc; padding: 20px; border-radius: 10px; margin-top: 10px;">
    <h4 style="margin-top: 0px;">備註、API 額度說明</h4>
    <ul style="margin-bottom: 0px;">
        <li><b>SerpApi</b>
            <ul>
                <li>Starter Plan：每 30 天 1000 次搜尋額度。</li>
            </ul>
        </li>
        <li style="margin-top: 10px;"><b>Gemini API</b>
            <ul>
                <li>3.5-flash-lite（預設）：每天 500 次請求 (RPD)。</li>
                <li>3.1-flash-lite：每天 500 次請求 (RPD)。</li>
            </ul>
        </li>
    </ul>
</div>
""", unsafe_allow_html=True)
