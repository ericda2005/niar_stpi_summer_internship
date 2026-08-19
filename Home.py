import streamlit as st
import pandas as pd
import cloudscraper
import trafilatura
import re
from bs4 import BeautifulSoup
from datetime import datetime
import time
import base64
import urllib.parse
import io
import zipfile

st.set_page_config(page_title="Google News", layout="wide")
st.title("Google News Checklist Crawler ")

# 初始化 session_state
if "news_list_df" not in st.session_state:
    st.session_state.news_list_df = pd.DataFrame()
if "export_text" not in st.session_state:
    st.session_state.export_text = ""
if "preview_results" not in st.session_state:
    st.session_state.preview_results = []
if "select_all" not in st.session_state:
    st.session_state.select_all = True
if "editor_key" not in st.session_state:
    st.session_state.editor_key = 0

def get_original_url(html):
    match = re.search(r'jslog="[^"]*5:([^;]+)', html)
    if not match:
        return None

    encoded = match.group(1)
    encoded += "=" * ((4 - len(encoded) % 4) % 4)

    try:
        decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
        match = re.search(r'https?://[^"]+', decoded)
        if not match:
            return None
        return urllib.parse.unquote(match.group(0))
    except Exception:
        return None

def sanitize_filename(name):
    """清除標題中不能作為檔名的非法字元"""
    return re.sub(r'[\\/*?:"<>|]', "", name)

# 將標題改為 Markdown 以放大字體，並隱藏原本 text_input 的 label
st.markdown("#### 🔗 貼上網址")
story_url = st.text_input("貼上網址", label_visibility="collapsed")

# ==========================================
# 階段一：爬取標題、發文日期與解析 jslog 取得真實網址
# ==========================================
if st.button("取得新聞清單", type="primary"):
    if not story_url:
        st.warning("請先輸入網址")
        st.stop()
        
    with st.status("正在解析頁面...", expanded=True) as status:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        
        try:
            res = scraper.get(story_url, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            href_to_real_url = {}
            for a in soup.find_all('a', attrs={'jslog': True}):
                href = a.get('href', '')
                html_str = str(a)
                real_url = get_original_url(html_str)
                if real_url:
                    href_to_real_url[href] = real_url
            
            scraped_items = []
            title_links = soup.find_all('a', href=re.compile(r'^\./(read|articles)/'))
            
            for a in title_links:
                # 過濾掉隱藏的網頁元素
                if a.get('aria-hidden') == 'true':
                    continue

                title = a.get_text(strip=True)
                if not title:
                    continue
                
                # 尋找絕對時間：往上層父節點找 <time> 標籤
                date_str = "未知"
                container = a.parent
                for _ in range(5):
                    if not container:
                        break
                    time_tag = container.find('time')
                    if time_tag and time_tag.has_attr('datetime'):
                        try:
                            dt_utc = datetime.strptime(time_tag['datetime'], "%Y-%m-%dT%H:%M:%SZ")
                            dt_tw = dt_utc + pd.Timedelta(hours=8)
                            date_str = dt_tw.strftime("%Y/%m/%d %H:%M")
                        except Exception:
                            pass
                        break
                    container = container.parent
                
                if date_str == "未知":
                    continue

                href = a.get('href', '')
                real_url = href_to_real_url.get(href)
                if not real_url:
                    real_url = "https://news.google.com" + href[1:]
                    
                scraped_items.append({
                    "選取": True,
                    "發文日期": date_str,
                    "標題": title,
                    "原始新聞連結": real_url
                })
                
            df = pd.DataFrame(scraped_items).drop_duplicates(subset=['原始新聞連結']).reset_index(drop=True)
            
            if not df.empty:
                st.session_state.export_text = ""
                st.session_state.preview_results = []
                st.session_state.news_list_df = df
                st.session_state.select_all = True
                st.session_state.editor_key += 1 
                
                status.update(label=f"成功找到 {len(df)} 篇關聯新聞！", state="complete")
            else:
                status.update(label="未找到符合結構的新聞，請確認網址是否正確。", state="error")
                
        except Exception as e:
            status.update(label=f"解析過程發生錯誤：{e}", state="error")

# ==========================================
# 階段二：顯示清單供使用者勾選
# ==========================================
if not st.session_state.news_list_df.empty:
    st.divider()
    st.markdown("### ✅ 勾選欲爬取並匯出的文章")
    
    if st.button("全選 / 全不選"):
        st.session_state.select_all = not st.session_state.select_all
        st.session_state.news_list_df["選取"] = st.session_state.select_all
        st.session_state.editor_key += 1 
        st.rerun() 
    
    edited_df = st.data_editor(
        st.session_state.news_list_df,
        key=f"editor_{st.session_state.editor_key}",
        column_config={
            "選取": st.column_config.CheckboxColumn("選取", default=True),
            "發文日期": st.column_config.TextColumn("發文日期"),
            "原始新聞連結": st.column_config.LinkColumn("原始新聞連結", display_text=None)
        },
        disabled=["發文日期", "標題", "原始新聞連結"],
        hide_index=True,
        use_container_width=True,
        height=400
    )

    # ==========================================
    # 階段三：爬取內文、顯示進度與預覽
    # ==========================================
    selected_rows = edited_df[edited_df["選取"] == True]
    
    if st.button("開始爬取", type="primary"):
        if selected_rows.empty:
            st.warning("請至少勾選一篇文章。")
        else:
            with st.status("正在爬取內文...", expanded=True) as scrape_status:
                scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                export_text_merged = ""
                preview_results = []
                total_selected = len(selected_rows)
                
                # 防爬蟲常見關鍵字清單
                anti_scrape_keywords = [
                    "please enable js",
                    "javascript disabled",
                    "access denied",
                    "enable javascript and cookies",
                    "let us know you're not a robot",
                    "update to the latest version of google chrome",
                    "upgrade your browser",
                    "are you a robot",
                    "checking your browser",
                    "checking if the site connection is secure"
                ]
                
                for i, (idx, row) in enumerate(selected_rows.iterrows()):
                    real_url = row['原始新聞連結']
                    title = row['標題']
                    date_str = row['發文日期']
                    
                    status_text.text(f"正在爬取 ({i+1}/{total_selected}): {title[:40]}...")
                    
                    content = ""
                    status_msg = "失敗"
                    try:
                        article_res = scraper.get(real_url, timeout=15)
                        extracted_text = trafilatura.extract(article_res.content)
                        
                        if extracted_text:
                            # 檢查是否包含防爬蟲字眼
                            is_blocked = any(keyword in extracted_text.lower() for keyword in anti_scrape_keywords)
                            if is_blocked:
                                content = f"【遭網站阻擋或需驗證】\n{extracted_text[:100]}..."
                            else:
                                content = extracted_text
                                status_msg = "成功"
                        else:
                            content = "【內文為空】"
                    except Exception as e:
                        content = f"【爬取發生錯誤: {e}】"
                        
                    single_article_text = f"【標題】{title}\n【發文日期】{date_str}\n【真實網址】{real_url}\n【內文】\n{content}\n"
                    
                    export_text_merged += single_article_text + "=" * 60 + "\n\n"
                    
                    preview_snippet = content[:100].replace('\n', ' ') + "..." if status_msg == "成功" else content
                    
                    preview_results.append({
                        "標題": title,
                        "狀態": status_msg,
                        "內文預覽": preview_snippet,
                        "完整單篇內容": single_article_text
                    })
                    
                    progress_bar.progress((i + 1) / total_selected)
                    time.sleep(0.5)
                
                status_text.empty()
                st.session_state.export_text = export_text_merged
                st.session_state.preview_results = preview_results
                scrape_status.update(label="內文爬取完成！", state="complete")

# ==========================================
# 階段四：顯示客製化預覽與提供下載按鈕
# ==========================================
if st.session_state.preview_results:
    st.divider()
    st.markdown("### 📊 爬取結果預覽")
    
    current_date = datetime.now().strftime('%Y%m%d')
    
    col1, col2, col3, col4 = st.columns([1.5, 4, 1, 4])
    with col1: st.write("**獨立下載 TXT**")
    with col2: st.write("**標題**")
    with col3: st.write("**狀態**")
    with col4: st.write("**內文預覽**")
    st.markdown("<hr style='margin: 0.5em 0px; opacity: 0.3;'>", unsafe_allow_html=True)
    
    for i, item in enumerate(st.session_state.preview_results):
        col_dl, col_title, col_status, col_preview = st.columns([1.5, 4, 1, 4])
        
        with col_dl:
            if item["狀態"] == "成功":
                safe_title = sanitize_filename(item["標題"])
                st.download_button(
                    label="下載單篇",
                    data=item["完整單篇內容"].encode('utf-8-sig'),
                    file_name=f"{safe_title}_{current_date}.txt",
                    key=f"dl_{i}"
                )
            else:
                st.write("❌ 無法下載")
                
        with col_title:
            st.write(item["標題"])
        with col_status:
            st.write(item["狀態"])
        with col_preview:
            st.caption(item["內文預覽"])
            
        st.markdown("<hr style='margin: 0.5em 0px; opacity: 0.3;'>", unsafe_allow_html=True)
    
    st.divider()
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in st.session_state.preview_results:
            if item["狀態"] == "成功":
                safe_title = sanitize_filename(item["標題"])
                filename = f"{safe_title}_{current_date}.txt"
                zip_file.writestr(filename, item["完整單篇內容"].encode('utf-8-sig'))
    zip_data = zip_buffer.getvalue()

    st.markdown("### 📦 批次下載選項")
    col_zip, col_merged = st.columns(2)
    
    with col_zip:
        st.download_button(
            label="一次下載全部 TXT (ZIP)",
            data=zip_data,
            file_name=f"News_All_{current_date}.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )
        
    with col_merged:
        st.download_button(
            label="合併 TXT",
            data=st.session_state.export_text.encode('utf-8-sig'),
            file_name=f"{current_date}.txt",
            mime="text/plain",
            use_container_width=True
        )
