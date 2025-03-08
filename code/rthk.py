#!/usr/bin/env python3
# coding: utf-8

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
import logging
import threading
import urllib.parse
from datetime import datetime
from markdownify import markdownify as md

from bs4 import BeautifulSoup, CData
from feedgen.feed import FeedGenerator
from lxml import html as lxmlhtml
from lxml.html.clean import Cleaner

# ------------------------------
# 初始提示與說明（可選，供 IT 人員或使用者參考）
def initial_setup():
    logging.info("開始初始化環境")
    # 使用當前 Python 解譯器呼叫 niquests.help 模組
    python_path = sys.executable
    subprocess.run([python_path, '-m', 'niquests.help'], shell=False)

# ------------------------------
# 環境變數設定（如需要可開啟）
def setup_environment():
    # os.environ["NIQUESTS_STRICT_OCSP"] = "1"
    pass

# ------------------------------
# 定義緩存 Session 物件與全域變數
class CachedSession(requests_cache.session.CacheMixin, niquests.Session):
    pass

retries = niquests.adapters.Retry(
    total=2,
    backoff_factor=1,
)

session = CachedSession(
    allowable_methods=('GET', 'HEAD'),
    resolver="doh://mozilla.cloudflare-dns.com/dns-query",
    pool_connections=1,
    pool_maxsize=10000,
    maxsize=10000,
    max_size=10000,
    backend='redis',
    happy_eyeballs=True
)
adapter = niquests.adapters.HTTPAdapter(max_retries=retries)
session.mount("https://", adapter=adapter)
session.mount("http://", adapter=adapter)
session.trust_env = False
session.quic_cache_layer.add_domain('mozilla.cloudflare-dns.com')

# 設定 User-Agent
userAgent = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:130.0) Gecko/130.0 Firefox/130.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0',
]
session.headers['User-Agent'] = secrets.choice(userAgent)

# ------------------------------
# 日誌設定
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler('rthk_feed.log')
    file_handler.setLevel(logging.WARNING)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

setup_logging()

# ------------------------------
# 全域變數
total_requests = 0
cache_hits = 0
verCount11 = 0
verCount20 = 0
verCount30 = 0

cleaner = Cleaner()

# ------------------------------
# 基本工具函數
def mem_usage():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    logging.info(f"虛擬記憶體使用: {mem.percent}% | {mem.used / (1024 * 1024):.2f} MB")
    logging.info(f"交換記憶體使用: {swap.percent}% | {swap.used / (1024 * 1024):.2f} MB")

def check_urls():
    # 檢查各路徑對外連線狀況
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
            headers['Cache-Control'] = 'no-cache'
            headers['Pragma'] = 'no-cache'
            headers['User-Agent'] = secrets.choice(userAgent)
            response = session.get(url, timeout=2, headers=headers)
            
            if response.ok:
                logging.info(f"獲取 {url[:50]}... 成功，前 10 行內容：{response.text.splitlines()[:10]}")
            else:
                logging.error(f"獲取 {url} 失敗, HTTP 狀態碼：{response.status_code}")
        
        except Exception as e:
            logging.error(f"獲取 {url} 出錯：{e}")

def parse_pub_date(date_str):
    # 將 "HKT" 轉換成標準時區格式
    date_str = date_str.replace('HKT', '+0800')
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %z %H:%M')
    return date_obj.strftime('%a, %d %b %Y %H:%M:%S %z')

def get_item_pub_date(item):
    # 從 XML 節點獲取 pubDate （依輸入格式判斷）
    pub_date = item.find('pubDate')
    if pub_date:
        return pub_date.text.strip()
    published = item.find('published')
    if published:
        return published.text.strip()
    return None

# ------------------------------
# Markdown 與 HTML 處理函數
# （此區塊處理文章內容轉 Markdown 與清理 HTML）
def generate_markdown(html_content):
    return md(html_content)

def clean_item_html(item_html):
    document = lxmlhtml.fromstring(html.unescape(item_html))
    cleaned = cleaner.clean_html(document)
    cleaned_str = lxmlhtml.tostring(cleaned, pretty_print=True, encoding='unicode')
    return cleaned_str

# ------------------------------
# Image 處理相關函數
def modify_image_url(imageUrl, new_quality):
    parsed_url = urllib.parse.urlparse(imageUrl)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params['q'] = [str(new_quality)]
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    new_url = urllib.parse.urlunparse(parsed_url._replace(query=new_query))
    # 針對部分網址做額外調整
    new_url = new_url.replace('n=-1&h=720', 'n=-1&we&h=720')
    new_url = new_url.replace('&amp;', '&')
    return new_url

async def optimize_image_quality(imgUrl):
    q = 99
    latest_imgUrl = modify_image_url(imgUrl, 1)
    latestAvailableQ = None
    content_length_q99 = None
    has_matched_condition = False
    
    while True:
        imgUrlWithQ = modify_image_url(imgUrl, q)
        try:
            response = await get_response(imgUrlWithQ, method='HEAD', session=session)
            # 若 HTTP 狀態碼介於 400 ~ 599，嘗試設 q 為 1
            if response.status_code >= 400 and response.status_code < 600:
                if q > 1:
                    q = 1
                    logging.error(f"將質量參數設為 1, HTTP 狀態: {response.status_code}, URL: {imgUrl}")
                else:
                    logging.error(f"無法獲取有效圖片, 退出迴圈, URL: {imgUrl}")
                    break
            
            elif response.ok:
                latestAvailableQ = imgUrlWithQ
                content_length = int(response.headers.get('Content-Length', 0))
                upstream_response_length = int(response.headers.get('x-upstream-response-length', 0))
                logging.info(f"獲取圖片大小成功, URL: {imgUrl} (Content-Length: {content_length}, Upstream: {upstream_response_length}, q: {q})")
                
                if q == 99:
                    content_length_q99 = content_length
                
                if q == 1:
                    logging.error(f"質量參數已調至 1，退出迴圈, URL: {imgUrl}")
                    break
                
                # 如果圖片尺寸太大則降低質量查找更適合的圖片
                if content_length > 1000 * 100 or content_length > upstream_response_length:
                    if q == 99:
                        q = 95
                    if q <= 95:
                        q = max(1, q - 5)
                    if content_length > upstream_response_length:
                        has_matched_condition = True
                elif content_length <= 1000 * 100:
                    logging.info(f"圖片小於 100KB, URL: {imgUrl}, 當前 q: {q}")
                    latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
                    break
        
        except Exception as e:
            logging.error(f"獲取圖片大小出錯, URL: {imgUrl}, Error: {e}")
            q = 1
            latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
            break

    # 若上游傳回的圖片較小，則嘗試將 q 調整
    if (upstream_response_length <= 1000 * 100 or (content_length_q99 is not None and content_length_q99 <= 1000 * 100)):
        if q == 99:
            q = 90
        elif q <= 95:
            q = max(1, q - 10)
        latest_imgUrl = modify_image_url(imgUrl, q)
        logging.info(f"圖片小於 100KB調整品質, 原 URL: {imgUrl} -> 新 URL: {latest_imgUrl}")
    
    return latest_imgUrl

# ------------------------------
# HTTP 請求（包含緩存處理與錯誤重試）
async def get_response(url, timeout=10, mustFetch=True, method='GET', session=session):
    global total_requests, cache_hits, verCount11, verCount20, verCount30
    total_requests += 1
    while True:
        try:
            session.quic_cache_layer.add_domain(urllib.parse.urlparse(url).netloc)
            response = await asyncio.to_thread(session.request, method, url, timeout=timeout)
            
            if response.from_cache:
                cache_hits += 1
            
            # 統計 HTTP 版本資訊
            if not response.from_cache and response.raw.version:
                if response.raw.version == 11:
                    verCount11 += 1
                elif response.raw.version == 20:
                    verCount20 += 1
                elif response.raw.version == 30:
                    verCount30 += 1
            
            return response
        
        except Exception as e:
            if str(e).strip() == 'Cannot select a disposable connection to ease the charge':
                continue
            else:
                logging.error(f"獲取響應出錯 (URL: {url}), 錯誤: {e}, 嘗試重試...")
        except:
            exception_type, exception_value, _ = sys.exc_info()
            logging.error(f"獲取響應未知錯誤 (URL: {url}), 錯誤: {exception_type.__name__} - {exception_value}, 嘗試重試...")
        
        if mustFetch:
            continue
        else:
            break

# ------------------------------
# 文章處理：解析文章、下載圖片與整合文章資訊
async def process_article(fg, category, article):
    try:
        fe = fg.add_entry()
        articleTitle = article.select_one('.ns2-title').text.strip()
        articleLink = article.select_one('.ns2-title a')['href']
        # 整理文章連結
        articleLink = articleLink.replace('?spTabChangeable=0', '').strip()
        logging.info(f"開始處理文章：{articleTitle}")
        
        article_response = await get_response(articleLink)
        if not article_response.ok:
            logging.error(f"文章處理失敗，跳過文章：{articleTitle} (HTTP: {article_response.status_code})")
            return

        article_content = article_response.text.strip()
        article_soup = BeautifulSoup(article_content, 'html.parser')
        # 預設使用 .itemFullText 區塊作為文章內容
        feedDescription = article_soup.select_one('.itemFullText').prettify().strip()

        # 處理圖片
        imgHtml = ''
        imgList = set()
        images = article_soup.select('.items_content .imgPhotoAfterLoad')
        for image in images:
            raw_img_url = 'https://wsrv.nl/?n=-1&we&h=720&output=webp&trim=1&url=' + urllib.parse.quote_plus(image['src'])
            imgUrl = modify_image_url(raw_img_url, 99)
            # 調整大小參數
            imgUrl = imgUrl.replace('_S_', '_L_').replace('_M_', '_L_')
            imgUrl = imgUrl.replace('_L_', '_')
            imgList.add(imgUrl)
            # 優化圖片品質
            latest_imgUrl = await optimize_image_quality(imgUrl)
            imgAlt = html.escape(image.get('alt', '').strip())
            if latest_imgUrl:
                imgHtml += f'<img src="{latest_imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                imgList.add(latest_imgUrl)
            else:
                imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                imgList.add(imgUrl)
        
        # 若未有圖片區塊，嘗試從 script 中獲取
        if not images:
            scripts = article_soup.find_all('script')
            for script in scripts:
                if 'videoThumbnail' in script.text:
                    match = re.search(r"videoThumbnail\s{0,1000}=\s{0,1000}'(.*)'", script.text)
                    if match:
                        video_thumbnail = match.group(1)
                        raw_img_url = 'https://wsrv.nl/?n=-1&we&h=720&output=webp&trim=1&url=' + urllib.parse.quote_plus(video_thumbnail)
                        imgUrl = modify_image_url(raw_img_url, 99)
                        imgUrl = imgUrl.replace('_S_', '_L_').replace('_M_', '_L_')
                        imgUrl = imgUrl.replace('_L_', '_')
                        imgList.add(imgUrl)
                        latest_imgUrl = await optimize_image_quality(imgUrl)
                        imgAlt = article_soup.select_one('.detailNewsSlideTitleText').get_text().strip()
                        imgAlt = html.escape(imgAlt)
                        if latest_imgUrl:
                            imgHtml += f'<img src="{latest_imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                            imgList.add(latest_imgUrl)
                        else:
                            imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                            imgList.add(imgUrl)
                        break
        
        # 緩存圖片（非同步下載頭部資訊）
        await asyncio.gather(*(cache_image(imageUrl) for imageUrl in imgList))

        pub_date = article.select_one('.ns2-created').text.strip()
        formatted_pub_date = parse_pub_date(pub_date)
        # 將圖片 HTML 加入文章內容，並附上原文資訊
        feedDescription = (
            f'{imgHtml} <br> {feedDescription} <br><hr>'
            f'<p>原始網址 Original URL：<a href="{articleLink}" rel="nofollow">{articleLink}</a></p>'
            f'<p>© rthk.hk</p>'
            f'<p>電子郵件 Email: <a href="mailto:cnews@rthk.hk" rel="nofollow">cnews@rthk.hk</a></p>'
        )
        # 格式化 HTML
        feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify().strip()

        fe.title(articleTitle)
        fe.link(href=articleLink)
        fe.guid(guid=articleLink, permalink=True)
        fe.description(feedDescription)
        fe.pubDate(formatted_pub_date)

        # 同時產生 Markdown 格式內容（獨立儲存供其他用途）
        md_content = generate_markdown(feedDescription)
        logging.info(f"完成文章處理：{articleTitle}")
        
        return {
            "title": articleTitle,
            "url": articleLink,
            "html": feedDescription,
            "markdown": md_content
        }
    
    except Exception as e:
        logging.error(f"文章處理出錯：{articleTitle}, Error: {e}")

async def cache_image(imageUrl):
    try:
        response = await get_response(imageUrl, timeout=2, mustFetch=False, method='HEAD', session=session)
        if response and response.ok and response.from_cache:
            logging.info(f"已緩存圖片, URL: {imageUrl}, 耗時: {response.elapsed.total_seconds()} 秒")
    except Exception as e:
        logging.error(f"緩存圖片出錯, URL: {imageUrl}, Error: {e}")

# ------------------------------
# 分類處理：下載分類頁面、解析 RSS 與 Markdown 文件的生成
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

async def process_category(category, url):
    try:
        response = await get_response(url)
        if response and response.ok:
            web_content = response.text.strip()
        else:
            logging.error(f"分類 {category} 處理失敗, HTTP 狀態碼: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        logging.error(f"分類 {category} 獲取響應出錯: {e}")
        sys.exit(1)
    
    soup = BeautifulSoup(web_content, 'html.parser')
    fg = FeedGenerator()
    fg.title(categories_data[category]['title'])
    fg.description(categories_data[category]['title'])
    fg.link(href=categories_data[category]['url'], rel='alternate')
    fg.language('zh-HK')
    feedImg = 'https://wsrv.nl/?n=-1&url=https://news.rthk.hk/rthk/templates/st_tyneo/favicon_144x144.png'
    fg.logo(feedImg)
    fg.copyright('© 香港電台 RTHK')
    fg.webMaster('webmaster@rthk.hk')

    articles = soup.select('.ns2-page')
    if not articles:
        return

    md_articles = []
    tasks = []
    for article in articles:
        tasks.append(asyncio.create_task(process_article(fg, category, article)))
    
    results = await asyncio.gather(*tasks)

    print( f'results: { results }' )

    for item in results:
        if item:
            print( f'item: { item }' )
            md_articles.append(item)
    
    # 產生 RSS XML
    rss_str = fg.rss_str()
    soup_rss = BeautifulSoup(rss_str, 'lxml-xml')
    
    # 清理 RSS 中的 HTML（利用 lxml 與 Cleaner 處理）
    for item in soup_rss.find_all('item'):
        if item.description:
            cleaned_html = clean_item_html(item.description.string.strip())
            item.description.string = CData(html.unescape(cleaned_html))
    if soup_rss.find('url'):
        soup_rss.find('url').string = CData(html.unescape(soup_rss.find('url').string.strip()))
    
    # 依文章發佈時間排序
    sorted_items = sorted(
        soup_rss.find_all('item'),
        key=lambda x: datetime.strptime(get_item_pub_date(x), '%a, %d %b %Y %H:%M:%S %z') if get_item_pub_date(x) else datetime.min,
        reverse=True
    )
    # 清除原先順序，再重新加入排序後的項目
    for item in soup_rss.find_all('item'):
        item.extract()
    for item in sorted_items:
        soup_rss.channel.append(item)
    if soup_rss.find('lastBuildDate'):
        soup_rss.find('lastBuildDate').decompose()
    
    rss_content = soup_rss.prettify().strip().replace('http://', 'https://')
    
    # 儲存 RSS XML 檔案
    rss_filename = f'{category}.xml'
    async with aiofiles.open(rss_filename, 'w', encoding='utf-8') as file:
        await file.write(rss_content)
    logging.info(f"分類 {category} RSS 已輸出至 {rss_filename}")

    # 產生 Markdown 文件：將所有文章 Markdown 內容統整後輸出
    md_filename = f'{category}.md'
    md_lines = []
    
    print( f'md_articles: { md_articles }')
    
    for article in md_articles:
        md_lines.append(f"# {article['title']}")
        md_lines.append("\n" + article['markdown'] + "\n")
        md_lines.append(f"原文連結：[{article['url']}]({article['url']})\n")
        md_lines.append("---\n")
    md_content = "\n".join(md_lines)
    async with aiofiles.open(md_filename, 'w', encoding='utf-8') as file:
        await file.write(md_content)
    logging.info(f"分類 {category} Markdown 已輸出至 {md_filename}")

# ------------------------------
# 以 thread 執行非同步處理，以實現多分類同時運行
def process_category_thread(category, url):
    asyncio.run(process_category(category, url))

# ------------------------------
# 主程式
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
    mem_usage()
    # 檢查連線狀態（可重複檢查）
    check_urls()
    check_urls()
    main()
    check_urls()
    check_urls()
    end_time = time.time()
    execution_time = end_time - start_time
    cache_hit_rate = cache_hits / total_requests * 100 if total_requests > 0 else 0
    logging.info(f"總請求數: {total_requests}")
    logging.info(f"緩存命中數: {cache_hits}")
    logging.info(f"緩存命中率: {cache_hit_rate:.2f}%")
    logging.info(f"HTTP/1.1 數: {verCount11}")
    logging.info(f"HTTP/2.0 數: {verCount20}")
    logging.info(f"HTTP/3.0 數: {verCount30}")
    mem_usage()
    logging.info(f"執行時間：{execution_time} 秒")
