import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import trafilatura
import time
import json
import re
from google import genai
from datetime import datetime

# ==========================================
# 輔助函式：文字換行處理
# ==========================================
def wrap_text(text, width):
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
# 爬蟲與摘要函式
# ==========================================
def get_techcrunch_categories_and_links(homepage_url="https://techcrunch.com/"):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    
    try:
        res = requests.get(homepage_url, headers=headers, timeout=10)
        res.raise_for_status()
    except Exception as e:
        return {"error": str(e)}

    soup = BeautifulSoup(res.text, 'html.parser')
    all_elements = soup.find_all(['h2', 'h3', 'h4'])
    
    raw_category_dict = {}
    current_category = "頂部區塊 (未分類)" 
    
    for elem in all_elements:
        classes = elem.get('class', [])
        if not isinstance(classes, list):
            classes = [classes]
            
        if elem.name == 'h2' and 'wp-block-heading' in classes:
            current_category = elem.get_text(strip=True)
            if current_category not in raw_category_dict:
                raw_category_dict[current_category] = []
            continue
            
        if 'wp-block-post-title' in classes or 'loop-card__title' in classes:
            a_tag = elem.find('a', href=True)
            if a_tag:
                title = a_tag.get_text(strip=True)
                href = a_tag['href']
                if href.startswith('/'):
                    href = "https://techcrunch.com" + href
                    
                if current_category not in raw_category_dict:
                    raw_category_dict[current_category] = []
                    
                urls_in_current = [item['url'] for item in raw_category_dict[current_category]]
                if href.startswith('https://techcrunch.com/') and href not in urls_in_current:
                    raw_category_dict[current_category].append({'標題': title, 'url': href, '分類': current_category})

    final_category_dict = {}
    global_seen_urls = set()
    
    for cat, articles in raw_category_dict.items():
        if cat == "頂部區塊 (未分類)":
            continue
            
        final_category_dict[cat] = []
        for art in articles:
            if art['url'] not in global_seen_urls:
                global_seen_urls.add(art['url'])
                final_category_dict[cat].append(art)
                
    final_category_dict["頂部區塊 (未分類)"] = []
    if "頂部區塊 (未分類)" in raw_category_dict:
        for art in raw_category_dict["頂部區塊 (未分類)"]:
            if art['url'] not in global_seen_urls:
                global_seen_urls.add(art['url'])
                final_category_dict["頂部區塊 (未分類)"].append(art)

    display_dict = {}
    if final_category_dict.get("頂部區塊 (未分類)"):
        display_dict["頂部區塊 (未分類)"] = final_category_dict["頂部區塊 (未分類)"]
    for cat, articles in final_category_dict.items():
        if cat != "頂部區塊 (未分類)" and articles:
            display_dict[cat] = articles

    return display_dict


def scrape_techcrunch_with_refs(main_url, status_text=None, current_article_info=""):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://techcrunch.com/'
    }
    try:
        res = requests.get(main_url, headers=headers, timeout=10)
        res.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(res.text, 'html.parser')
    title_tag = soup.find('h1')
    main_title = title_tag.text.strip() if title_tag else "未知標題"

    main_text = trafilatura.extract(res.text)
    
    if not main_text:
        content_div = soup.find('div', class_='entry-content')
        if content_div:
            for ad in content_div.find_all('div', class_='ad-unit'):
                ad.decompose()
            main_text = content_div.get_text(separator='\n', strip=True)
        else:
            return []

    articles_data = [{
        "主文章網址": main_url,
        "角色": "主文章",
        "標題": main_title,
        "網址": main_url,
        "內文": main_text
    }]

    article_body = soup.find('div', class_='entry-content')
    ref_urls = []
    if article_body:
        for a in article_body.find_all('a', href=True):
            href = a['href']
            if href.startswith('/'):
                href = "https://techcrunch.com" + href
            if (href.startswith('http') and 
                href not in ref_urls and 
                href != main_url and
                'twitter.com' not in href and 
                'facebook.com' not in href):
                ref_urls.append(href)

    for j, url in enumerate(ref_urls, 1):
        if status_text and current_article_info:
            status_text.info(f"{current_article_info} (正在爬取參考連結 {j} / {len(ref_urls)})")
            
        try:
            r_res = requests.get(url, headers=headers, timeout=10)
            if r_res.status_code == 200:
                r_content = trafilatura.extract(r_res.text)
                r_soup = BeautifulSoup(r_res.text, 'html.parser')
                r_title = r_soup.title.string.strip() if r_soup.title else "未知標題"
                
                if r_content:
                    articles_data.append({
                        "主文章網址": main_url,
                        "角色": "參考資料",
                        "標題": r_title,
                        "網址": url,
                        "內文": r_content
                    })
        except Exception:
            pass
        time.sleep(2)

    return articles_data

def long_summary(client, article_group):
    main_title = article_group["主文章名稱"]
    articles = article_group["articles"]
    main_url = article_group["主文章網址"]

    cluster_urls = [art["網址"] for art in articles if art["角色"] == "參考資料"]
    urls_string = "\n".join(cluster_urls)

    prompt = f"""
    你現在是科技文獻摘要專家。請根據以下多篇探討同一主題的新聞內文，綜合生成以下 JSON 格式的繁體中文摘要：
    {{
        "標題": "自訂一個專業且涵蓋此事件的繁體中文標題",
        "關鍵字": "列出5到10個關鍵字，以逗號分隔",
        "長篇內文": "請撰寫一份字數大約在 800 至 1300 字之間的完整長篇報告。結構必須包含：1. 前言/引言（說明事件背景與核心意義）；2. 內文（深入剖析各篇報導的細節、技術、爭議或發展脈絡）；3. 總結（綜合評析此事件對產業或未來的影響）。"
    }}

    主題：
    {main_title}
    
    新聞資料：
    {json.dumps(articles, ensure_ascii=False)}

    絕對不要輸出 Markdown 標記或其他文字。
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )

    # 加上 strict=False 防止 JSON 報錯
    generated_data = json.loads(response.text.strip().replace("```json", "").replace("```", ""), strict=False)

    final_result = {
        "主文章網址": main_url,
        "英文標題": main_title,
        "標題": generated_data.get("標題", ""),
        "關鍵字": generated_data.get("關鍵字", ""),
        "長篇內文": generated_data.get("長篇內文", ""),
        "參考資料": urls_string
    }
    return final_result


# ==========================================
# Streamlit 介面與主邏輯
# ==========================================
st.set_page_config(page_title="Techcrunch 自動化爬蟲與長摘", layout="wide")

# 側邊欄：設定 API Key
with st.sidebar:
    st.header("⚙️ 系統設定")
    api_key_input = st.text_input("Gemini API Key", type="password")

# 初始化 session_state (TechCrunch 專用)
if 'tc_category_dict' not in st.session_state:
    st.session_state.tc_category_dict = {}
if 'tc_article_urls' not in st.session_state:
    st.session_state.tc_article_urls = []
if 'tc_scraped_df' not in st.session_state:
    st.session_state.tc_scraped_df = None
if 'tc_scraped_data_list' not in st.session_state:
    st.session_state.tc_scraped_data_list = []
if 'tc_final_summary_df' not in st.session_state:
    st.session_state.tc_final_summary_df = None

st.title("自動化爬蟲長摘系統：TechCrunch.com")

# ------------------------------------------
# 第一階段：獲取首頁板塊與文章網址
# ------------------------------------------
col1, col2 = st.columns([2, 1])
with col1:
    url_input = st.text_input("首頁網址", value="https://techcrunch.com/")
with col2:
    if st.button("搜尋", type="primary", use_container_width=True):
        with st.spinner("正在掃描首頁板塊與文章..."):
            cat_dict = get_techcrunch_categories_and_links(url_input)
            
            if "error" in cat_dict:
                st.error(f"請求失敗：{cat_dict['error']}")
            elif cat_dict:
                st.session_state.tc_category_dict = cat_dict
                st.success(f"成功取得 {len(cat_dict)} 個板塊。")
            else:
                st.warning("未抓取到任何板塊資訊。")

# ------------------------------------------
# 第二階段：選擇特定板塊進行爬取
# ------------------------------------------
if st.session_state.tc_category_dict:
    st.divider()
    
    available_categories = list(st.session_state.tc_category_dict.keys())
    selected_categories = st.multiselect("請選擇欲爬取的板塊（可複選）", options=available_categories)
    
    if selected_categories:
        st.session_state.tc_article_urls = []
        for cat in selected_categories:
            st.session_state.tc_article_urls.extend(st.session_state.tc_category_dict[cat])
            
        st.write(f"在選定的板塊中，共找到 **{len(st.session_state.tc_article_urls)}** 篇文章。")
        scrape_mode = st.radio("請選擇爬取模式：", ["Beta (僅爬取第 1 篇測試)", "All (爬取所有選定文章)"])
        
        # 將開始與中斷按鈕並排
        col_start, col_stop = st.columns(2)
        
        with col_stop:
            st.button("中斷 / 重新開始", use_container_width=True)
            
        with col_start:
            if st.button("開始爬取", type="primary", use_container_width=True):
                urls_to_scrape = st.session_state.tc_article_urls[:1] if "Beta" in scrape_mode else st.session_state.tc_article_urls
                
                st.session_state.scraped_data_list = []
                st.session_state.tc_scraped_df = None
                
                status_text = st.empty()
                progress_bar = st.progress(0)
                
                for i, item in enumerate(urls_to_scrape, 1):
                    target_url = item['url']
                    current_info = f"正在爬取第 {i} / {len(urls_to_scrape)} 篇：【{item.get('分類', '未知')}】{item['標題']}"
                    status_text.info(current_info)
                    
                    data = scrape_techcrunch_with_refs(target_url, status_text=status_text, current_article_info=current_info)
                    if data:
                        st.session_state.scraped_data_list.extend(data)
                        st.session_state.tc_scraped_df = pd.DataFrame(st.session_state.scraped_data_list)
                        
                    progress_bar.progress(i / len(urls_to_scrape))
                    time.sleep(3)
                    
                status_text.success("內文與參考資料爬取完成！")

if st.session_state.tc_scraped_df is not None and not st.session_state.tc_scraped_df.empty:
    st.divider()
    st.markdown("### 爬取結果預覽")
    st.dataframe(st.session_state.tc_scraped_df, use_container_width=True)

# ------------------------------------------
# 第三階段：LLM 生成長篇摘要與自動換行
# ------------------------------------------
if st.session_state.tc_scraped_df is not None and not st.session_state.tc_scraped_df.empty:
    st.divider()
    st.write(f"已準備好 **{st.session_state.tc_scraped_df['主文章網址'].nunique()}** 個主題的資料可供摘要。")
    
    col_sum_start, col_sum_stop = st.columns(2)
    
    with col_sum_stop:
        # 使用獨立的 key 避免按鈕衝突
        st.button("中斷 / 重新開始", key="stop_summary", use_container_width=True)
        
    with col_sum_start:
        if st.button("開始長摘", type="primary", use_container_width=True):
            if not api_key_input:
                st.error("請先在左側邊欄輸入 Gemini API Key！")
            else:
                try:
                    client = genai.Client(api_key=api_key_input)
                    df_combined_all = st.session_state.tc_scraped_df
                    
                    summary_status = st.empty()
                    summary_progress = st.progress(0)
                    all_summaries = []
                    
                    grouped = list(df_combined_all.groupby('主文章網址', sort=False))
                    total_groups = len(grouped)
                    
                    for i, (main_url, group_df) in enumerate(grouped, 1):
                        main_articles = group_df[group_df['角色'] == '主文章']
                        main_title = main_articles['標題'].values[0] if not main_articles.empty else "未知標題"
                        articles_list = group_df[['角色', '標題', '網址', '內文']].to_dict(orient='records')
                        
                        article_group = {
                            "主文章名稱": main_title,
                            "主文章網址": main_url,
                            "articles": articles_list
                        }
                        
                        summary_status.info(f"正在生成摘要 [{i}/{total_groups}]: {main_title}")
                        
                        try:
                            summary_result = long_summary(client, article_group)
                            all_summaries.append(summary_result)
                        except Exception as e:
                            st.error(f"摘要生成失敗 ({main_title}): {e}")
                            
                        summary_progress.progress(i / total_groups)
                        time.sleep(15)  # 避免 API 限制
                        
                    summary_status.success("所有摘要生成完畢，正在處理格式")
                    
                    if all_summaries:
                        dated_df = pd.DataFrame(all_summaries)
                        
                        wrap_columns_10 = ["關鍵字"]
                        wrap_columns_30 = ["英文標題", "標題"]
                        wrap_columns_50 = ["長篇內文"]

                        for col in wrap_columns_10:
                            if col in dated_df.columns:
                                dated_df[col] = dated_df[col].apply(lambda x: wrap_text(x, width=10))

                        for col in wrap_columns_50:
                            if col in dated_df.columns:
                                dated_df[col] = dated_df[col].apply(lambda x: wrap_text(x, width=50))

                        for col in wrap_columns_30:
                            if col in dated_df.columns:
                                dated_df[col] = dated_df[col].apply(lambda x: wrap_text(x, width=30))
                        
                        st.session_state.tc_final_summary_df = dated_df
                        st.success("格式處理完成！")
                        
                except Exception as e:
                    st.error(f"Gemini 初始化或執行發生錯誤：{e}")

# ------------------------------------------
# 第四階段：顯示與下載結果
# ------------------------------------------
if st.session_state.tc_final_summary_df is not None and not st.session_state.tc_final_summary_df.empty:
    st.divider()
    
    col_title, col_dl = st.columns([2, 1])
    with col_title:
        st.markdown("### 摘要總覽")
    
    with col_dl:
        current_date = datetime.now().strftime('%Y%m%d')
        file_name = f"{current_date}_techcrunch.csv"
        
        csv_summary = st.session_state.tc_final_summary_df.to_csv(index=False, encoding="utf-8-sig", doublequote=True).encode("utf-8-sig")

        st.download_button(
            label="📥 下載 CSV 檔案", 
            data=csv_summary, 
            file_name=file_name,
            mime="text/csv",
            use_container_width=True
        )

    st.dataframe(st.session_state.tc_final_summary_df, use_container_width=True)
    
    st.markdown("### 摘要預覽")
    for i, row in st.session_state.tc_final_summary_df.iterrows():
        with st.expander(f"📑 {row['標題']} (原標題: {row['英文標題']})"):
            st.markdown(f"**【關鍵字】** {row['關鍵字']}")
            st.markdown("---")
            st.markdown(row['長篇內文'])
            st.markdown("---")
            st.markdown("**【參考資料】**")
            st.text(row['參考資料'])
            st.markdown(f"[🔗 點此閱讀主文章原文]({row['主文章網址']})")
