#!/usr/bin/env python3
# coding: utf-8

# 載入必要的 Python 模組，用於網路請求、HTML 解析、RSS 生成等
import sys
import subprocess
import psutil
import os
import qh3
import asyncio
import niquests
import requests_cache
import secrets
import html
import re
import aiofiles
import time
import threading
import urllib.parse
from datetime import datetime
from markdownify import markdownify as md
from mistune import create_markdown
from bs4 import BeautifulSoup, CData
from lxml import html as lxmlhtml
from lxml.html.clean import Cleaner
from feedgen.feed import FeedGenerator

# ------------------------------
# 初始設定：檢查環境並顯示提示
def initial_setup():
    print("開始初始化環境...")
    # 使用當前 Python 執行 niquests 的幫助模組，檢查環境是否正常
    python_path = sys.executable
    subprocess.run([python_path, '-m', 'niquests.help'], shell=False)
    print("初始化完成！")

# ------------------------------
# 環境變數設定（可選，若不需要可忽略）
def setup_environment():
    # 若需啟用嚴格 OCSP 檢查，可取消以下註解
    # os.environ["NIQUESTS_STRICT_OCSP"] = "1"
    pass

# ------------------------------
# 設定網路請求的緩存與配置
class CachedSession(requests_cache.session.CacheMixin, niquests.Session):
    pass

poolConn = 100
poolSize = 10000

# 建立網路請求的 Session，包含緩存和 QUIC 支援
session = CachedSession(
    # allowable_methods=('GET', 'HEAD'),  # 支援的 HTTP 方法
    resolver="doh://mozilla.cloudflare-dns.com/dns-query",  # 使用 DoH 解析 DNS
    pool_connections=poolConn,  # 連線池設定
    pool_maxsize=poolSize,
    backend='redis',  # 緩存後端使用 Redis
    happy_eyeballs=True,  # 加快連線速度
)

# 設定重試機制：最多重試 2 次，每次間隔時間增加
retries = niquests.adapters.Retry(total=2, backoff_factor=1)
adapter = niquests.adapters.HTTPAdapter(max_retries=retries, pool_connections=poolConn, pool_maxsize=poolSize)
session.mount("https://", adapter=adapter)
session.mount("http://", adapter=adapter)
session.trust_env = False  # 不使用系統代理
session.quic_cache_layer.add_domain('mozilla.cloudflare-dns.com')

# 隨機選擇 User-Agent，模擬不同瀏覽器
userAgent = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:137.0) Gecko/137.0 Firefox/137.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:136.0) Gecko/136.0 Firefox/136.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:135.0) Gecko/135.0 Firefox/135.0',
]
session.headers['User-Agent'] = secrets.choice(userAgent)

# ------------------------------
# 全域變數：用於統計請求次數和緩存命中率
total_requests = 0  # 總請求數
cache_hits = 0     # 緩存命中數
verCount11 = 0     # HTTP/1.1 使用次數
verCount20 = 0     # HTTP/2.0 使用次數
verCount30 = 0     # HTTP/3.0 使用次數

cleaner = Cleaner()  # 用於清理 HTML 內容

# ------------------------------
# 工具函數：顯示記憶體使用情況
def mem_usage():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    print(f"虛擬記憶體使用: {mem.percent}% | {mem.used / (1024 * 1024):.2f} MB")
    print(f"交換記憶體使用: {swap.percent}% | {swap.used / (1024 * 1024):.2f} MB")

# 檢查網路連線狀態
def check_urls():
    urls = [
        'https://1.1.1.1/cdn-cgi/trace',
        'https://mozilla.cloudflare-dns.com/cdn-cgi/trace',
        'https://wsrv.nl/cdn-cgi/trace',
        'https://wsrv.nl/quota',
        'https://github.com/raileo98/test2/raw/refs/heads/main/hk_rthk_ch.xml',
        'https://raw.githubusercontent.com/raileo98/test2/refs/heads/main/hk_rthk_ch.xml',
    ]
    
    for url in urls:
        try:
            headers = dict(session.headers)
            # headers['Cache-Control'] = 'no-cache'  # 不使用緩存
            # headers['Pragma'] = 'no-cache'
            headers['User-Agent'] = secrets.choice(userAgent)
            response = session.get(url, timeout=2, headers=headers)
            
            if response.ok:
                print(f"連線測試 {url[:50]}... 成功！前 10 行內容：{response.text.splitlines()[:10]}")
            else:
                print(f"連線測試 {url} 失敗，HTTP 狀態碼：{response.status_code}")
        
        except Exception as e:
            print(f"連線測試 {url} 出錯：{e}")

# 解析日期格式，將 HKT 轉為標準時區格式
def parse_pub_date(date_str):
    date_str = date_str.replace('HKT', '+0800')
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %z %H:%M')
    return date_obj.strftime('%a, %d %b %Y %H:%M:%S %z')

# 從 XML 節點提取發佈日期
def get_item_pub_date(item):
    pub_date = item.find('pubDate')
    if pub_date:
        return pub_date.text.strip()
    published = item.find('published')
    if published:
        return published.text.strip()
    return None

# ------------------------------
# Markdown 與 HTML 處理函數
def generate_markdown(html_content):
    # 將 HTML 轉為 Markdown 格式
    md_content = md(html_content, heading_style="ATX")
    markdown = create_markdown()
    mistune_output = markdown(md_content)  # 可選：將 Markdown 轉回 HTML
    return md_content, mistune_output

def clean_item_html(item_html):
    # 清理 HTML 內容，移除不必要的標籤
    document = lxmlhtml.fromstring(html.unescape(item_html))
    cleaned = cleaner.clean_html(document)
    cleaned_str = lxmlhtml.tostring(cleaned, pretty_print=True, encoding='unicode')
    return cleaned_str

# ------------------------------
# 圖片處理函數
def modify_image_url(imageUrl, new_quality):
    # 修改圖片 URL 中的質量參數
    parsed_url = urllib.parse.urlparse(imageUrl)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params['q'] = [str(new_quality)]
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    new_url = urllib.parse.urlunparse(parsed_url._replace(query=new_query))
    new_url = new_url.replace('n=-1&w=720', 'n=-1&we&w=720')  # 修正特定參數
    return new_url

async def optimize_image_quality(imgUrl):
    # 優化圖片品質，確保檔案大小適中
    q = 99  # 初始品質
    latest_imgUrl = modify_image_url(imgUrl, 1)
    latestAvailableQ = None
    content_length_q99 = None
    
    while True:
        imgUrlWithQ = modify_image_url(imgUrl, q)
        try:
            response = await get_response(imgUrlWithQ, method='HEAD', session=session)
            if response.status_code >= 400 and response.status_code < 600:
                if q > 1:
                    q = 1
                    print(f"圖片品質設為 1，因 HTTP 狀態: {response.status_code}, URL: {imgUrl}")
                else:
                    print(f"無法獲取圖片，退出迴圈, URL: {imgUrl}")
                    break
            
            elif response.ok:
                latestAvailableQ = imgUrlWithQ
                content_length = int(response.headers.get('Content-Length', 0))
                upstream_response_length = int(response.headers.get('x-upstream-response-length', 0))
                print(f"圖片大小: {content_length} bytes, Upstream: {upstream_response_length}, q: {q}, URL: {imgUrl}")
                
                if q == 99:
                    content_length_q99 = content_length
                
                if q == 1:
                    print(f"品質已降至 1，退出迴圈, URL: {imgUrl}")
                    break
                
                if content_length > 1000 * 50 or content_length > upstream_response_length:
                    if q == 99:
                        q = 95
                    if q <= 95:
                        q = max(1, q - 5)
                elif content_length <= 1000 * 50:
                    print(f"圖片小於 100KB，品質適中, URL: {imgUrl}, q: {q}")
                    latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
                    break
        
        except Exception as e:
            print(f"獲取圖片大小失敗, URL: {imgUrl}, 錯誤: {e}")
            q = 1
            latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
            break

    if (upstream_response_length <= 1000 * 50 or (content_length_q99 is not None and content_length_q99 <= 1000 * 50)):
        if q == 99:
            q = 90
        elif q <= 95:
            q = max(1, q - 10)
        latest_imgUrl = modify_image_url(imgUrl, q)
        print(f"圖片小於 100KB，調整品質至 q={q}, URL: {latest_imgUrl}")
    
    return latest_imgUrl

# ------------------------------
# HTTP 請求函數：支援緩存與錯誤重試
async def get_response(url, timeout=10, mustFetch=True, method='GET', session=session):
    global total_requests, cache_hits, verCount11, verCount20, verCount30
    total_requests += 1
    while True:
        try:
            session.quic_cache_layer.add_domain(urllib.parse.urlparse(url).netloc)
            response = await asyncio.to_thread(session.request, method, url, timeout=timeout)
            
            if response.from_cache:
                cache_hits += 1
            
            if not response.from_cache and response.raw.version:
                if response.raw.version == 10: # fix later
                    verCount11 += 1 # fix later
                if response.raw.version == 11:
                    verCount11 += 1
                elif response.raw.version == 20:
                    verCount20 += 1
                elif response.raw.version == 30:
                    verCount30 += 1
            
            return response

        # except OverwhelmedTraffic as e:
            # print('error: OverwhelmedTraffic')
            # continue
        
        except Exception as e:
            # if str(e).strip() == 'Cannot select a disposable connection to ease the charge':
            if str(e).strip().startswith('Cannot select a disposable connection to ease the charge') or str(e).strip().startswith('Cannot memorize traffic indicator upon unknown connection'):
                # print('error: Cannot select a disposable connection to ease the charge, aka OverwhelmedTraffic(?)')
                print(f"請求 {url} 出錯: {e}，嘗試重試...")
                
                continue
                
            else:
                print(f"請求 {url} 出錯: {e}，嘗試重試...")
        
        if not mustFetch:
            break

# ------------------------------
# 文章處理：解析內容、下載圖片並生成 RSS 項目
async def process_article(fg, category, article):
    try:
        fe = fg.add_entry()  # 新增 RSS 項目
        articleTitle = article.select_one('.ns2-title').text.strip()
        articleLink = article.select_one('.ns2-title a')['href'].replace('?spTabChangeable=0', '').strip()
        print(f"正在處理文章：{articleTitle}")
        
        article_response = await get_response(articleLink)
        if not article_response.ok:
            print(f"文章 {articleTitle} 載入失敗 (HTTP: {article_response.status_code})，跳過")
            return

        article_content = article_response.text.strip()
        article_soup = BeautifulSoup(article_content, 'html.parser')
        feedDescription = article_soup.select_one('.itemFullText').prettify().strip()

        # 處理圖片
        imgHtml = ''
        imgList = set()
        images = article_soup.select('.items_content .imgPhotoAfterLoad')
        for image in images:
            raw_img_url = 'https://i3.wp.com' + image['src'].replace('http://', '').replace('https://', '')
            raw_img_url = 'https://external-content.duckduckgo.com/iu/?u=' + urllib.parse.quote( raw_img_url )
            raw_img_url = 'https://images.weserv.nl/?n=-1&we&output=webp&url=' + urllib.parse.quote( raw_img_url )
            imgUrl = modify_image_url(raw_img_url, 99).replace('_S_', '_L_').replace('_M_', '_L_').replace('_L_', '_')
            imgList.add(imgUrl)
            latest_imgUrl = await optimize_image_quality(imgUrl)
            imgAlt = html.escape(image.get('alt', '').strip())
            imgHtml += f'<img src="{latest_imgUrl or imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
            imgList.add(latest_imgUrl or imgUrl)
        
        # 若無圖片，從 script 中提取縮圖
        if not images:
            for script in article_soup.find_all('script'):
                if 'videoThumbnail' in script.text:
                    match = re.search(r"videoThumbnail\s{0,1000}=\s{0,1000}'(.*)'", script.text)
                    if match:
                        video_thumbnail = match.group(1)
                        raw_img_url = 'https://i3.wp.com' + video_thumbnail.replace('http://', '').replace('https://', '')
                        raw_img_url = 'https://external-content.duckduckgo.com/iu/?u=' + urllib.parse.quote( raw_img_url )
                        raw_img_url = 'https://images.weserv.nl/?n=-1&we&output=webp&url=' + urllib.parse.quote( raw_img_url )
                        imgUrl = modify_image_url(raw_img_url, 99).replace('_S_', '_L_').replace('_M_', '_L_').replace('_L_', '_')
                        imgList.add(imgUrl)
                        latest_imgUrl = await optimize_image_quality(imgUrl)
                        imgAlt = html.escape(article_soup.select_one('.detailNewsSlideTitleText').get_text().strip())
                        imgHtml += f'<img src="{latest_imgUrl or imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                        imgList.add(latest_imgUrl or imgUrl)
                        break
        
        # 緩存圖片
        await asyncio.gather(*(cache_image(imageUrl) for imageUrl in imgList))

        pub_date = article.select_one('.ns2-created').text.strip()
        formatted_pub_date = parse_pub_date(pub_date)
        feedDescription = (
            f'{imgHtml} <br> {feedDescription} <br><hr>'
            f'<p>原始網址：<a href="{articleLink}" rel="nofollow">{articleLink}</a></p>'
            f'<p>© rthk.hk</p>'
            f'<p>電子郵件: <a href="mailto:cnews@rthk.hk" rel="nofollow">cnews@rthk.hk</a></p>'
        )
        feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify().strip()

        fe.title(articleTitle)
        fe.link(href=articleLink)
        fe.guid(guid=articleLink, permalink=True)
        fe.description(feedDescription)
        fe.pubDate(formatted_pub_date)

        md_content, _ = generate_markdown(feedDescription)
        print(f"完成處理文章：{articleTitle}")
        
        return {"title": articleTitle, "url": articleLink, "html": feedDescription, "markdown": md_content}
    
    except Exception as e:
        print(f"處理文章 {articleTitle} 出錯: {e}")

async def cache_image(imageUrl):
    try:
        response = await get_response(imageUrl, timeout=2, mustFetch=False, method='HEAD', session=session)
        if response and response.ok and response.from_cache:
            print(f"圖片已緩存: {imageUrl}, 耗時: {response.elapsed.total_seconds()} 秒")
    except Exception as e:
        print(f"緩存圖片 {imageUrl} 出錯: {e}")

# ------------------------------
# 分類數據：包含所有 RTHK 新聞分類
categories_data = {
    'hk_rthk_ch': {
        'title': 'rthk',
        'url': 'https://news.rthk.hk/rthk/ch/latest-news.htm'
    },
    'hk_rthk_local_ch': {
        'title': 'rthk - 本地',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=3&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_greaterChina_ch': {
        'title': 'rthk - 大中華',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=2&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_world_ch': {
        'title': 'rthk - 國際',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=4&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_finance_ch': {
        'title': 'rthk - 財經',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=5&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_sport_ch': {
        'title': 'rthk - 體育',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=6&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_en': {
        'title': 'rthk - English',
        'url': 'https://news.rthk.hk/rthk/en/latest-news.htm'
    },
    'hk_rthk_local_en': {
        'title': 'rthk - Local',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=8&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_greaterChina_en': {
        'title': 'rthk - Greater China',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=9&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_world_en': {
        'title': 'rthk - World',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=10&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_finance_en': {
        'title': 'rthk - Finance',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=12&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_sport_en': {
        'title': 'rthk - Sport',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=11&newsCount=60&dayShiftMode=1&archive_date='
    }
}

# ------------------------------
# 分類處理：生成 RSS 和 Markdown 文件
async def process_category(category, url):
    try:
        response = await get_response(url)
        if response and response.ok:
            web_content = response.text.strip()
        else:
            print(f"分類 {category} 載入失敗, HTTP 狀態碼: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"分類 {category} 載入出錯: {e}")
        sys.exit(1)
    
    soup = BeautifulSoup(web_content, 'html.parser')
    fg = FeedGenerator()
    fg.title(categories_data[category]['title'])
    fg.description(categories_data[category]['title'])
    fg.link(href=categories_data[category]['url'], rel='alternate')
    fg.language('zh-HK')
    # feedImg = 'https://wsrv.nl/?n=-1&url=https://i3.wp.com/news.rthk.hk/rthk/templates/st_tyneo/favicon_144x144.png'
    feedImg = 'https://news.rthk.hk/rthk/templates/st_tyneo/favicon_144x144.png'
    feedImg = 'https://i3.wp.com' + feedImg.replace('http://', '').replace('https://', '')
    feedImg = 'https://external-content.duckduckgo.com/iu/?u=' + urllib.parse.quote( raw_img_url )
    feedImg = 'https://images.weserv.nl/?n=-1&we&output=webp&url=' + urllib.parse.quote( raw_img_url )
    fg.logo(feedImg)
    fg.copyright('© 香港電台 RTHK')
    fg.webMaster('webmaster@rthk.hk')

    articles = soup.select('.ns2-page')
    if not articles:
        print(f"分類 {category} 無文章可處理")
        return

    md_articles = []
    tasks = [asyncio.create_task(process_article(fg, category, article)) for article in articles]
    results = await asyncio.gather(*tasks)

    for item in results:
        if item:
            md_articles.append(item)
    
    # 生成 RSS XML
    rss_str = fg.rss_str()
    soup_rss = BeautifulSoup(rss_str, 'lxml-xml')
    
    for item in soup_rss.find_all('item'):
        if item.description:
            cleaned_html = clean_item_html(item.description.string.strip())
            item.description.string = CData(html.unescape(cleaned_html))
    if soup_rss.find('url'):
        soup_rss.find('url').string = CData(html.unescape(soup_rss.find('url').string.strip()))
    
    # 按發佈時間排序
    sorted_items = sorted(
        soup_rss.find_all('item'),
        key=lambda x: datetime.strptime(get_item_pub_date(x), '%a, %d %b %Y %H:%M:%S %z') if get_item_pub_date(x) else datetime.min,
        reverse=True
    )
    for item in soup_rss.find_all('item'):
        item.extract()
    for item in sorted_items:
        soup_rss.channel.append(item)
    if soup_rss.find('lastBuildDate'):
        soup_rss.find('lastBuildDate').decompose()
    
    rss_content = soup_rss.prettify().strip().replace('http://', 'https://')
    
    # 儲存 RSS 檔案
    rss_filename = f'{category}.xml'
    async with aiofiles.open(rss_filename, 'w', encoding='utf-8') as file:
        await file.write(rss_content)
    print(f"分類 {category} RSS 已儲存至 {rss_filename}")

    # 生成 Markdown 檔案
    md_filename = f'{category}.md'
    md_lines = []
    for article in md_articles:
        md_lines.append(f"# {article['title']}")
        md_lines.append("\n" + article['markdown'] + "\n")
        md_lines.append(f"原文連結：[{article['url']}]({article['url']})\n")
        md_lines.append("---\n")
    md_content = "\n".join(md_lines)
    async with aiofiles.open(md_filename, 'w', encoding='utf-8') as file:
        await file.write(md_content)
    print(f"分類 {category} Markdown 已儲存至 {md_filename}")

# ------------------------------
# 多執行緒處理分類
def process_category_thread(category, url):
    asyncio.run(process_category(category, url))

# ------------------------------
# 主程式：執行所有分類處理
def main():
    threads = []
    for category, data in categories_data.items():
        t = threading.Thread(target=process_category_thread, args=(category, data['url']))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

if __name__ == '__main__':
    start_time = time.time()
    print("程式開始執行...")
    mem_usage()
    check_urls()  # 檢查網路連線
    check_urls()
    main()
    check_urls()
    check_urls()
    end_time = time.time()
    execution_time = end_time - start_time
    cache_hit_rate = cache_hits / total_requests * 50 if total_requests > 0 else 0
    print(f"總請求數: {total_requests}")
    print(f"緩存命中數: {cache_hits}")
    print(f"緩存命中率: {cache_hit_rate:.2f}%")
    print(f"HTTP/1.1 使用次數: {verCount11}")
    print(f"HTTP/2.0 使用次數: {verCount20}")
    print(f"HTTP/3.0 使用次數: {verCount30}")
    mem_usage()
    print(f"程式執行時間：{execution_time:.2f} 秒")
    print("程式執行完畢！")
