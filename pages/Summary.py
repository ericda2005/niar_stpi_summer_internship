import streamlit as st
import pandas as pd
import serpapi
import cloudscraper
import trafilatura
import time
from bs4 import BeautifulSoup
import json
from google import genai
import re
from datetime import datetime
import requests

# ==========================================
# 輔助函式：文字換行處理
# ==========================================
def wrap_text_smart(text, width):
    if not isinstance(text, str) or not text:
        return text

    pattern = r'[a-zA-Z0-9]+[a-zA-Z0-9\.\-\'’\,\!\?\;\:\"\)\]]*|.'
    tokens = re.findall(pattern, text, flags=re.DOTALL)

    lines = []
    current_line = ""
    current_length = 0

    for token in tokens:
        token_len = len(token)
        if token == '\n':
            lines.append(current_line.strip())
            current_line = ""
            current_length = 0
            continue

        if current_length + token_len > width:
            if current_line:
                if token.isspace():
                    continue
                lines.append(current_line.strip())
                current_line = token
                current_length = token_len
            else:
                current_line = token
                current_length = token_len
        else:
            current_line += token
            current_length += token_len

    if current_line:
        lines.append(current_line.strip())

    return '\n'.join(lines)

# ==========================================
# LLM 處理函式
# ==========================================
def filter_llm(article_list, gemini_client, model_name):
    prompt = f"""
    你是一個科技文獻審查員。請檢視以下清單。
    請依據以下標準審查：
    剔除：學校首頁、期刊目錄、賣報告的推銷頁面、內容農場、股價預測分析、年代久遠的舊文章。
    保留：單篇具體文獻、深度產業報導、獨立研究文章。

    待審查清單：
    {json.dumps(article_list, ensure_ascii=False)}

    【輸出格式要求】：
    請對「每一篇」文章進行判定，並直接回傳包含所有文章的 JSON 陣列，格式如下：
    [
      {{
        "title": "完整文章標題",
        "url": "網址",
        "date": "日期",
        "decision": "keep" (代表保留) 或 "drop" (代表剔除),
        "reason": "請用一句話說明為什麼保留或剔除"
      }}
    ]
    絕對不要加上 Markdown 標記或任何廢話。
    """
    try:
        response = gemini_client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_text)
    except Exception as e:
        print(f"過濾失敗: {e}")
        return []

def cluster_llm(article_list, gemini_client, model_name):
    prompt = f"""
    你是一位科技情報分析師。請閱讀以下 {len(article_list)} 篇新聞的完整內文。
    任務：將探討「同一個核心議題脈絡」或「具強烈關聯的延續性故事」的文章分在同一群。
    若只是大方向相似請勿分在一起。若沒有其他報導講同件事，可獨立成群。
    
    輸入資料：
    {json.dumps(article_list, ensure_ascii=False)}
    
    分群判斷基準：
        1. 報導同一個具體單一事件、技術發表或商業交易。
        2. 文章之間具有明確的引用、背景補充或因果關係，或，如：A文章明確提到了B文章在講的東西
        3. 針對同一個特定發展中議題的多篇追蹤報導。
    
    請輸出 JSON 陣列格式：
    [
      {{
        "主題名稱": "自訂此主題事件或技術名稱",
        "id": ["id1", "id2"],
        "參考網址": ["url1", "url2"],
        "涵蓋日期": ["date1", "date2"]
      }}
    ]
    絕對不要輸出 Markdown 標記或其他文字。
    """
    try:
        response = gemini_client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_text)
    except Exception as e:
        print(f"分群失敗: {e}")
        return []

def long_summary(article_group, gemini_client, model_name):
    topic = article_group["主題名稱"]
    articles = article_group["articles"]
    cluster_urls = [art["url"] for art in articles]

    prompt = f"""
    你現在是科技文獻摘要專家。請根據以下多篇探討同一主題的新聞內文，綜合生成以下 JSON 格式的繁體中文摘要：
    {{
        "標題": "自訂一個專業且涵蓋此事件的繁體中文標題",
        "關鍵字": "列出5到10個關鍵字，以逗號分隔",
        "長篇內文": "請撰寫一份字數大約在 800 至 1300 字之間的完整長篇報告。結構必須包含：1. 前言/引言（說明事件背景與核心意義）；2. 內文（深入剖析各篇報導的細節、技術、爭議或發展脈絡）；3. 總結（綜合評析此事件對產業或未來的影響）。",
        "參考文獻": "將以下網址逐行排列：\\n" + "\\n".join(cluster_urls)
    }}

    主題：
    {topic}
    
    新聞資料：
    {json.dumps(articles, ensure_ascii=False)}

    絕對不要輸出 Markdown 標記或其他文字。
    """
    try:
        response = gemini_client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)
    except Exception:
        return {}

def short_summary(article, gemini_client, model_name):
    prompt = f"""
    你現在是科技文獻摘要專家。請根據內文生成以下 JSON 格式的繁體中文摘要：
    {{
        "中文標題": "將英文標題翻譯為繁體中文",
        "問題需求": "嚴格遵守50字內",
        "解決手段": "嚴格遵守50字內",
        "摘要結構": "嚴格遵守200字摘要，包含研究單位或學校名稱或刊登期刊",
        "關鍵字": "給出10個以內的文章關鍵字，請合併為單一字串並用半形逗號分隔（例如：關鍵字1, 關鍵字2）"
    }}

    文章標題：
    {article["title"]}
    
    文章內文：
    {article["content"]}
    
    絕對不要輸出 Markdown 標記或其他文字。
    """
    try:
        response = gemini_client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)
    except Exception:
        return {}


# ==========================================
# Streamlit 介面與主邏輯
# ==========================================
st.set_page_config(page_title="AI 摘要系統", layout="wide")
st.title("AI 摘要系統")

if "results_dict" not in st.session_state:
    st.session_state.results_dict = {}

# 側邊欄：設定 API Key
with st.sidebar:
    st.header("⚙️ 系統設定")

    serpapi_key = st.text_input("SerpApi Key", type="password")
    if "serpapi_quota" not in st.session_state:
        st.session_state.serpapi_quota = None

    if serpapi_key:
        if st.button("顯示 / 更新額度（請於搜尋完成後再點擊刷新，否則會中斷搜尋）", use_container_width=True):
            try:
                # 修正端點：必須加上 .json
                url = f"https://serpapi.com/account.json?api_key={serpapi_key}"
                res = requests.get(url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    searches_left = data.get("plan_searches_left", "未知")
                    total_searches = data.get("plan_searches_limit", 1000)
                    st.session_state.serpapi_quota = f"{searches_left} / {total_searches}"
                else:
                    st.session_state.serpapi_quota = f"查詢失敗 (狀態碼: {res.status_code})"
            except Exception as e:
                st.session_state.serpapi_quota = f"連線錯誤: {e}"
        
        if st.session_state.serpapi_quota:
            if "失敗" in st.session_state.serpapi_quota or "錯誤" in st.session_state.serpapi_quota:
                st.error(st.session_state.serpapi_quota)
            else:
                st.success(f"剩餘額度：{st.session_state.serpapi_quota}")

    st.divider()
    gemini_key = st.text_input("Gemini API Key", type="password")
    
    selected_model = st.selectbox(
        "選擇 Gemini 模型",
        options=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        index=0
    )

# ------------------------------------------
# 搜尋條件設定與執行模式
# ------------------------------------------
st.markdown("### 🔍 搜尋條件設定")
col1, col2 = st.columns([2, 1])

with col1:
    keyword_input = st.text_input("輸入搜尋關鍵字 (多個請用半形逗號分隔)")

with col2:
    # 設定預設值為過去7天到今天
    today = datetime.now().date()
    last_week = today - pd.Timedelta(days=7)
    
    # 使用 st.date_input 讓使用者選擇區間
    date_range = st.date_input("選擇查詢日期範圍", value=(last_week, today))
    
    # 判斷使用者是否已經選好起始與結束日期
    if len(date_range) == 2:
        start_str = date_range[0].strftime("%m/%d/%Y")
        end_str = date_range[1].strftime("%m/%d/%Y")
    else:
        # 若使用者只點了一天，將結束日期設與開始日期相同防錯
        start_str = date_range[0].strftime("%m/%d/%Y")
        end_str = start_str
        
    tbs_param = f"cdr:1,cd_min:{start_str},cd_max:{end_str}"

st.divider()

scrape_mode = st.radio("請選擇爬取模式：", ["Beta (每個關鍵字僅爬取第 1 頁，消耗 1 次額度)", "All (爬取前 10 頁)"])
test_mode = "Beta" in scrape_mode

col_start, col_stop = st.columns(2)

with col_stop:
    st.button("中斷 / 重新開始", use_container_width=True)

with col_start:
    run_button = st.button("搜尋", type="primary", use_container_width=True)


if run_button:
    if not serpapi_key or not gemini_key:
        st.error("請先在左側邊欄輸入 SerpApi 與 Gemini API Key")
        st.stop()
        
    keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]
    if not keywords:
        st.warning("請輸入至少一個搜尋關鍵字！")
        st.stop()

    client_genai = genai.Client(api_key=gemini_key)

    with st.status("系統執行中，請稍候...", expanded=True) as status:

        # --- 步驟 1：取得搜尋結果 ---
        st.write("步驟 1/6：取得搜尋結果")
        client_serp = serpapi.Client(api_key=serpapi_key)
        
        all_results = []
        fetch_status_text = st.empty()
        
        # 依照模式決定要抓取的頁數
        pages_to_fetch = 1 if test_mode else 10

        for kw in keywords:
            for page in range(pages_to_fetch):
                start_index = page * 10
                fetch_status_text.text(f"正在搜尋: [{kw}] (第 {page + 1} 頁)")
                
                try:
                    results = client_serp.search({
                        "engine": "google",
                        "q": kw,
                        "no_cache": "true",
                        "tbm": "nws",
                        "tbs": tbs_param,
                        "start": start_index,
                        "gl": "us"
                    })
                    
                    if "news_results" in results:
                        all_results.extend(results["news_results"])
                    else:
                        break
                        
                except Exception as e:
                    st.error(f"抓取關鍵字 {kw} 失敗: {e}")
                    
                time.sleep(1)

        fetch_status_text.empty()
        
        if not all_results:
            st.warning("在此條件下未找到任何新聞。")
            st.stop()

       # 整理 DataFrame 與日期格式轉換
        df_all_news = pd.DataFrame(all_results)
        
        # 1. 篩選需要的欄位（加入檢查機制避免報錯）
        cols_to_keep = ['link', 'title', 'source', 'published_at', 'snippet']
        existing_cols = [col for col in cols_to_keep if col in df_all_news.columns]
        df_all_news = df_all_news[existing_cols]

        # 2. 將 published_at 改名為 date
        if 'published_at' in df_all_news.columns:
            df_all_news = df_all_news.rename(columns={"published_at": "date"})

        # 3. 進行時區轉換與格式化
        if 'date' in df_all_news.columns:
            df_all_news['date'] = pd.to_datetime(df_all_news['date'], errors='coerce')
            
            try:
                df_all_news['date'] = df_all_news['date'].dt.tz_convert('Asia/Taipei')
            except TypeError:
                df_all_news['date'] = df_all_news['date'].dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
                
            df_all_news['date'] = df_all_news['date'].dt.strftime('%m-%d-%Y')
        else:
            df_all_news['date'] = "無日期資料"

        df_all_news = df_all_news.drop_duplicates(subset=['link'])
        news_results = df_all_news.to_dict('records')

        st.write(f"✅ 共抓取 {len(news_results)} 筆新聞連結")

        # --- 步驟 2：爬取文章內文 ---
        st.write("步驟 2/6：爬取文章內文")
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        scraped_articles = []
        progress_bar_scrape = st.progress(0)
        scrape_status_text = st.empty() 

        for index, news in enumerate(news_results):
            title = news.get("title", "無標題")
            news_url = news.get("link")
            date = news.get("date", "無日期資料")
            scrape_status_text.text(f"正在擷取: {title[:40]}...")

            try:
                res = scraper.get(news_url, timeout=15)
                if res.status_code == 200:
                    content = trafilatura.extract(res.text)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    if soup.title and soup.title.string:
                        title = soup.title.string.strip()
                    if content:
                        scraped_articles.append({"title": title, "url": news_url, "content": content, "date": date})
            except Exception:
                pass
            progress_bar_scrape.progress((index + 1) / len(news_results))

        scrape_status_text.empty() 
        st.write(f"✅ 成功爬取 {len(scraped_articles)} / {len(news_results)} 篇文章正文")

        # --- 步驟 3：過濾無效文章 ---
        st.write("步驟 3/6：過濾無效文章")
        batch_size = 5
        filter_results = []
        progress_bar_filter = st.progress(0)
        filter_status_text = st.empty() 

        for i in range(0, len(scraped_articles), batch_size):
            batch = scraped_articles[i:i + batch_size]
            current_end = min(i + batch_size, len(scraped_articles))
            filter_status_text.text(f"AI 正在過濾第 {i + 1} 到 {current_end} 篇文章...")
            
            batch_result = filter_llm(batch, client_genai, selected_model)
            filter_results.extend(batch_result)
            progress_bar_filter.progress(min(1.0, (i + batch_size) / len(scraped_articles)))
            time.sleep(5)
          
        filter_status_text.empty() 

        df_filter = pd.DataFrame(filter_results)
        if not df_filter.empty and 'decision' in df_filter.columns:
            df_filter = df_filter[df_filter['decision'] == 'keep'].reset_index(drop=True)
        else:
            df_filter = pd.DataFrame()

        df_scraped_temp = pd.DataFrame(scraped_articles).drop_duplicates(subset=['url'])
        
        if not df_filter.empty and not df_scraped_temp.empty:
            df_merge = pd.merge(df_filter, df_scraped_temp[['url', 'content']], on='url', how='left')
            df_merge = df_merge.dropna(subset=['content']).reset_index(drop=True)
        else:
            df_merge = pd.DataFrame()
            
        st.write(f"✅ 過濾完成，保留 {len(df_merge)} 篇具價值文章")

        # --- 步驟 4：AI 分群 ---
        st.write("步驟 4/6：長摘與短摘分群")
        article_list = []
        for idx, row in df_merge.iterrows():
            article_list.append({
                "id": idx,
                "title": row["title"],
                "url": row["url"],
                "content": row["content"],
                "date": row["date"]
            })
        
        clusters = cluster_llm(article_list, client_genai, selected_model)
        st.write(f"✅ 總共分成 {len(clusters)} 群")

        long_articles = []
        short_articles = []
        for cluster in clusters:
            article_ids = cluster.get("id", [])
            articles = [art for art in article_list if art["id"] in article_ids]
            
            if len(articles) >= 2:
                long_articles.append({
                    "主題名稱": cluster.get("主題名稱", "未命名主題"),
                    "articles": articles
                })
            elif len(articles) == 1:
                short_articles.append(articles[0])

        # --- 步驟 5：生成長篇與短篇摘要 ---
        st.write("步驟 5/6：生成長摘與短摘")
        
        # 長篇摘要
        long_results = []
        if long_articles:
            progress_bar_long = st.progress(0)
            long_status = st.empty()
            for i, group in enumerate(long_articles, start=1):
                long_status.text(f"正在進行長摘：{i}/{len(long_articles)}")
                res = long_summary(group, client_genai, selected_model)
                if res:
                    long_results.append(res)
                progress_bar_long.progress(i / len(long_articles))
                time.sleep(5)
            long_status.empty()

        # 短篇摘要
        short_results = []
        if short_articles:
            progress_bar_short = st.progress(0)
            short_status = st.empty()
            for i, article in enumerate(short_articles, start=1):
                short_status.text(f"正在進行短摘：{i}/{len(short_articles)}")
                res = short_summary(article, client_genai, selected_model)
                if res:
                    res["文章日期"] = article["date"]
                    res["參考連結"] = article["url"]
                    res["英文標題"] = article["title"]
                    short_results.append(res)
                progress_bar_short.progress(i / len(short_articles))
                time.sleep(5)
            short_status.empty()

        # --- 步驟 6：格式處理與輸出 ---
        st.write("步驟 6/6：格式處理")
        
        df_long = pd.DataFrame(long_results)
        df_short = pd.DataFrame(short_results)

        if not df_long.empty:
            wrap_columns_long_50 = ["長篇內文"]
            wrap_columns_long_20 = ["標題", "關鍵字"]
            for col in wrap_columns_long_50:
                if col in df_long.columns:
                    df_long[col] = df_long[col].apply(lambda x: wrap_text_smart(x, width=50))
            for col in wrap_columns_long_20:
                if col in df_long.columns:
                    df_long[col] = df_long[col].apply(lambda x: wrap_text_smart(x, width=20))

        if not df_short.empty:
            cols = ['英文標題'] + [col for col in df_short.columns if col != '英文標題']
            df_short = df_short[cols]

            wrap_columns_short_10 = ["中文標題", "問題需求", "解決手段", "文章日期"]
            wrap_columns_short_50 = ["英文標題"]
            wrap_columns_short_30 = ["摘要結構", "關鍵字"]
            
            for col in wrap_columns_short_10:
                if col in df_short.columns:
                    df_short[col] = df_short[col].apply(lambda x: wrap_text_smart(x, width=10))
            for col in wrap_columns_short_50:
                if col in df_short.columns:
                    df_short[col] = df_short[col].apply(lambda x: wrap_text_smart(x, width=50))
            for col in wrap_columns_short_30:
                if col in df_short.columns:
                    df_short[col] = df_short[col].apply(lambda x: wrap_text_smart(x, width=30))

        status.update(label="✅ 所有處理皆已完成！", state="complete", expanded=False)

    if not df_long.empty or not df_short.empty:
        st.success("🎉 分析完成！預覽結果如下：")
        
        # 建立安全的檔名前綴，替換掉空格
        file_prefix = "_".join(keywords).replace(" ", "_")
        current_date = datetime.now().strftime('%Y%m%d')
        
        tab1, tab2 = st.tabs(["長篇摘要 (多篇關聯)", "短篇摘要 (單一報導)"])
        
        with tab1:
            if not df_long.empty:
                st.dataframe(df_long)
                csv_long = df_long.to_csv(index=False, encoding="utf-8-sig", doublequote=True).encode('utf-8-sig')
                st.download_button(
                    label="📥 下載長摘 CSV",
                    data=csv_long,
                    file_name=f"{file_prefix}_long_{current_date}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("本次抓取無產生長篇摘要（沒有兩篇以上相關聯的文章）。")

        with tab2:
            if not df_short.empty:
                st.dataframe(df_short)
                csv_short = df_short.to_csv(index=False, encoding="utf-8-sig", doublequote=True).encode('utf-8-sig')
                st.download_button(
                    label="📥 下載短摘 CSV",
                    data=csv_short,
                    file_name=f"{file_prefix}_short_{current_date}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("本次抓取無產生短篇摘要。")

        # ==========================================
        # 視覺化預覽區塊 (比照 TechCrunch 格式)
        # ==========================================
        st.divider()
        st.markdown("### 摘要預覽")
        
        if not df_long.empty:
            st.markdown("#### 📚 長篇摘要")
            for idx, row in df_long.iterrows():
                with st.expander(f"📑 {row.get('標題', '無標題')}"):
                    st.markdown(f"**【關鍵字】** {row.get('關鍵字', '')}")
                    st.markdown("---")
                    st.markdown(row.get('長篇內文', ''))
                    st.markdown("---")
                    st.markdown("**【參考文獻】**")
                    st.text(row.get('參考文獻', ''))
                    
        if not df_short.empty:
            st.markdown("#### 📝 短篇摘要")
            for idx, row in df_short.iterrows():
                with st.expander(f"📑 {row.get('中文標題', '無標題')} (原標題: {row.get('英文標題', '')})"):
                    st.markdown(f"**【關鍵字】** {row.get('關鍵字', '')}")
                    st.markdown("---")
                    st.markdown("**【問題需求】**")
                    st.markdown(row.get('問題需求', ''))
                    st.markdown("**【解決手段】**")
                    st.markdown(row.get('解決手段', ''))
                    st.markdown("**【摘要結構】**")
                    st.markdown(row.get('摘要結構', ''))
                    st.markdown("---")
                    st.markdown(f"[🔗 點此閱讀主文章原文]({row.get('參考連結', '')})")

    else:
        st.warning("沒有可輸出的資料。")
