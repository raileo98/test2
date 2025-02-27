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

# ------------------------
# 印出初始提示字
print('111')

# 利用當前 Python 解釋器呼叫 niquests.help 模組
python_path = sys.executable
subprocess.run([python_path, '-m', 'niquests.help'], shell=False)

print('222')

# ------------------------
# 設置環境變數
os.environ["NIQUESTS_STRICT_OCSP"] = "1"

if os.environ.get("NIQUESTS_STRICT_OCSP") == "1":
    print("NIQUESTS_STRICT_OCSP is enabled")
else:
    print("NIQUESTS_STRICT_OCSP is not enabled")

# ------------------------
# 自定一個 CachedSession
class CachedSession(requests_cache.session.CacheMixin, niquests.Session):
    pass

retries = niquests.adapters.Retry(
    total=2,
    backoff_factor=1,
)

# 設置 session
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
session.quic_cache_layer.add_domain('ocsp1.ecert.gov.hk')

userAgent = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:130.0) Gecko/130.0 Firefox/130.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0',
]
session.headers['User-Agent'] = secrets.choice(userAgent)

# ------------------------
# 設置日誌記錄
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

# ------------------------
# 定義輔助函數

def memUsage():
    memory = psutil.virtual_memory()
    swap_memory = psutil.swap_memory()
    print(f"虛擬記憶體使用情况：{memory.percent}% | {memory.used / (1024 * 1024):.2f} MB")
    print(f"交換記憶體使用情况：{swap_memory.percent}% | {swap_memory.used / (1024 * 1024):.2f} MB")

def check():
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
            headersForCheck = dict(session.headers)
            headersForCheck['Cache-Control'] = 'no-cache'
            headersForCheck['Pragma'] = 'no-cache'
            headersForCheck['User-Agent'] = secrets.choice(userAgent)
            print(f'headersForCheck: {headersForCheck}')
            response = session.get(url, timeout=2, headers=headersForCheck)
            if response.ok:
                print(f'使用代理獲取 {url} 成功: \n{ response.text.splitlines()[:10] }\n')
            else:
                print(f'使用代理獲取 {url} 失敗:\n{response.status_code}\n')
        except Exception as e:
            print(f'使用代理獲取 {url} 出錯:\n{e}\n')
        except:
            print(f'使用代理獲取 {url} 出現未知錯誤\n')


def parse_pub_date(date_str):
    date_str = date_str.replace('HKT', '+0800')
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %z %H:%M')
    return date_obj.strftime('%a, %d %b %Y %H:%M:%S %z')


def get_item_pub_date(item):
    pub_date = item.find('pubDate')
    if pub_date:
        return pub_date.text.strip()
    published = item.find('published')
    if published:
        return published.text.strip()
    return None

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

total_requests = 0
cache_hits = 0
verCount11 = 0
verCount20 = 0
verCount30 = 0

cleaner = Cleaner()

# ------------------------
# 非同步文章處理函數

async def process_article(fg, category, article):
    try:
        fe = fg.add_entry()
        articleTitle = article.select_one('.ns2-title').text.strip()
        articleLink = article.select_one('.ns2-title a')['href']
        articleLink = articleLink.replace('?spTabChangeable=0', '').strip()
        print(f'{articleTitle} started!')

        article_response = await get_response(articleLink)
        if not article_response.ok:
            print(f'{articleTitle} 處理失敗，將跳過此文章!')
            logging.error(f'{articleTitle} 處理失敗，HTTP 狀態碼: {article_response.status_code}')
            return

        article_content = article_response.text.strip()
        article_soup = BeautifulSoup(article_content, 'html.parser')
        # 預設使用 .itemFullText 作為文章內容
        feedDescription = article_soup.select_one('.itemFullText').prettify().strip()

        imgHtml = ''
        imgList = set()
        images = article_soup.select('.items_content .imgPhotoAfterLoad')
        for image in images:
            imgUrl = modify_image_url('https://wsrv.nl/?n=-1&we&h=1080&output=webp&trim=1&url=' + urllib.parse.quote_plus(image['src']), 99)
            print(f"{articleLink} - {articleTitle}: {imgUrl}")
            imgList.add(imgUrl)
            imgUrl = imgUrl.replace('_S_', '_L_').replace('_M_', '_L_')
            print(f"{articleLink} - {articleTitle}: {imgUrl}")
            imgList.add(imgUrl)
            imgUrl = imgUrl.replace('_L_', '_')
            print(f"{articleLink} - {articleTitle}: {imgUrl}")
            imgList.add(imgUrl)
            latest_imgUrl = await optimize_image_quality(imgUrl)
            imgAlt = image.get('alt', '')
            imgAlt = html.escape(imgAlt.strip()).strip()
            if latest_imgUrl:
                imgHtml += f'<img src="{latest_imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                imgList.add(latest_imgUrl)
                print(f'Final imgUrlWithQ: {latest_imgUrl}')
            else:
                imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                imgList.add(imgUrl)
                print(f'Final imgUrl: {imgUrl}')

        if len(images) == 0:
            scripts = article_soup.find_all('script')
            for script in scripts:
                if 'videoThumbnail' in script.text:
                    match = re.search(r"videoThumbnail\s{0,1000}=\s{0,1000}'(.*)'", script.text)
                    if match:
                        video_thumbnail = match.group(1)
                        imgUrl = modify_image_url('https://wsrv.nl/?n=-1&we&h=1080&output=webp&trim=1&url=' + urllib.parse.quote_plus(video_thumbnail), 99)
                        print(f"{articleLink} - {articleTitle}: {imgUrl}")
                        imgList.add(imgUrl)
                        imgUrl = imgUrl.replace('_S_', '_L_').replace('_M_', '_L_')
                        print(f"{articleLink} - {articleTitle}: {imgUrl}")
                        imgList.add(imgUrl)
                        imgUrl = imgUrl.replace('_L_', '_')
                        print(f"{articleLink} - {articleTitle}: {imgUrl}")
                        imgList.add(imgUrl)
                        # 根據圖片大小調整壓縮質量
                        latest_imgUrl = await optimize_image_quality(imgUrl)
                        # 用另一個選擇器獲取 alt（例如：.detailNewsSlideTitleText）
                        imgAlt = article_soup.select_one('.detailNewsSlideTitleText').get_text()
                        imgAlt = html.escape(imgAlt.strip()).strip()
                        if latest_imgUrl:
                            imgHtml += f'<img src="{latest_imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                            imgList.add(latest_imgUrl)
                            print(f'Final imgUrlWithQ: {latest_imgUrl}')
                        else:
                            imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style="width:100%;height:auto">'
                            imgList.add(imgUrl)
                            print(f'Final imgUrl: {imgUrl}')
                        break

        # 緩存圖片
        await asyncio.gather(*(cache_image(imageUrl) for imageUrl in imgList))

        pub_date = article.select_one('.ns2-created').text.strip()
        formatted_pub_date = parse_pub_date(pub_date)

        # 將圖片 HTML 同 文章內容整合，並加入其他資訊
        feedDescription = f'{imgHtml} <br> {feedDescription} <br><hr> <p>原始網址 Original URL：<a href="{articleLink}" rel="nofollow">{articleLink}</a></p> <p>© rthk.hk</p> <p>電子郵件 Email: <a href="mailto:cnews@rthk.hk" rel="nofollow">cnews@rthk.hk</a></p>'
        feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify().strip()

        fe.title(articleTitle)
        fe.link(href=articleLink)
        fe.guid(guid=articleLink, permalink=True)
        fe.description(feedDescription)
        fe.pubDate(formatted_pub_date)

        print(f'{articleTitle} done!')
        memUsage()

        # 同時利用 markdownify 將 HTML 轉 Markdown，並回傳文章資料（方便後續 .md 寫檔）
        md_content = md(feedDescription)
        return {
            "title": articleTitle,
            "url": articleLink,
            "html": feedDescription,
            "markdown": md_content
        }
    except Exception as e:
        print(f'{articleTitle} 處理出錯: {e}')
        logging.error(f'{articleTitle} 處理出錯: {e}')
    except:
        exception_type, exception_value, _ = sys.exc_info()
        print(f'{articleTitle} 出現未知錯誤: {exception_type.__name__} - {exception_value}')
        logging.error(f'{articleTitle} 出現未知錯誤: {exception_type.__name__} - {exception_value}')

async def cache_image(imageUrl):
    try:
        response = await get_response(imageUrl, timeout=2, mustFetch=False, method='HEAD', session=session)
        if response.ok:
            if response.from_cache:
                print(f'[INFO] 已緩存! 耗時: {response.elapsed.total_seconds()} - imageUrl: {imageUrl}')
    except Exception as e:
        logging.error(f'[ERROR] 緩存 {imageUrl} - 出錯: {e}')
    except:
        exception_type, exception_value, _ = sys.exc_info()
        logging.error(f'[ERROR] 緩存 {imageUrl} - 出現未知錯誤: {exception_type.__name__} - {exception_value}')

async def optimize_image_quality(imgUrl):
    q = 99
    latest_imgUrl = modify_image_url(imgUrl, 1)
    latestAvailableQ = None
    # 用呢個變數記錄原始 q=99 嘅 content_length（用於後續判斷）
    content_length_q99 = None
    has_matched_condition = False

    while True:
        imgUrlWithQ = modify_image_url(imgUrl, q)
        try:
            response = await get_response(imgUrlWithQ, method='HEAD', session=session)
            if response.status_code >= 400 and response.status_code < 600:
                if q > 1:
                    q = 1
                    logging.error(f'[ERROR] 將質量參數 q 設置為 1 - response.status_code: {response.status_code} - imageUrl: {imgUrl}')
                else:
                    logging.error(f'[ERROR] 無法獲取有效圖片，退出迴圈 - imageUrl: {imgUrl}')
                    break
            elif response.ok:
                latestAvailableQ = imgUrlWithQ
                content_length = int(response.headers.get('Content-Length', 0))
                upstream_response_length = int(response.headers.get('x-upstream-response-length', 0))
                logging.info(f'[INFO] 獲取圖片大小成功 - imageUrl: {imgUrl} - content_length: {content_length} - upstream_response_length: {upstream_response_length} - 當前質量參數 q: {q}')
                if q == 99:
                    content_length_q99 = content_length
                if q == 1:
                    logging.error(f'[ERROR] 當前質量參數 q 為 1，退出迴圈 - imageUrl: {imgUrl}')
                    break
                if content_length > 1000 * 150 or content_length > upstream_response_length:
                    if q == 99:
                        q = 95
                    if q <= 95:
                        q = max(1, q - 5)
                    if content_length > upstream_response_length:
                        has_matched_condition = True
                elif content_length <= 1000 * 150:
                    logging.info(f'[INFO] 圖片大小小於 150 KB - imageUrl: {imgUrl} - 當前質量參數 q: {q}')
                    latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
                    break
        except Exception as e:
            logging.error(f'[ERROR] 獲取圖片大小出錯 - imageUrl: {imgUrl} - 錯誤: {e}')
            q = 1
            latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
            break

    if (upstream_response_length <= 1000 * 150 or (content_length_q99 is not None and content_length_q99 <= 1000 * 150)):
        if q == 99:
            q = 90
        elif q <= 95:
            q = max(1, q - 10)
        latest_imgUrl = modify_image_url(imgUrl, q)
        print(f'圖像小於 150 KB，{imgUrl} --> {latest_imgUrl}')
    return latest_imgUrl

def modify_image_url(imageUrl, new_quality):
    parsed_url = urllib.parse.urlparse(imageUrl)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params['q'] = [str(new_quality)]
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    new_url = urllib.parse.urlunparse(parsed_url._replace(query=new_query))
    new_url = new_url.replace('n=-1&h=1080', 'n=-1&we&h=1080')
    new_url = new_url.replace('&amp;', '&')
    return new_url

async def get_response(url, timeout=10, mustFetch=True, method='GET', session=session):
    global total_requests, cache_hits, verCount11, verCount20, verCount30
    total_requests += 1
    while True:
        try:
            session.quic_cache_layer.add_domain(urllib.parse.urlparse(url).netloc)
            response = await asyncio.to_thread(session.request, method, url, timeout=timeout)
            if response.from_cache:
                cache_hits += 1
            # 根據 HTTP 版本統計數量
            if not response.from_cache and response.raw.version:
                if response.raw.version == 11:
                    verCount11 += 1
                if response.raw.version == 20:
                    verCount20 += 1
                if response.raw.version == 30:
                    verCount30 += 1
            return response
        except Exception as e:
            if str(e).strip() == 'Cannot select a disposable connection to ease the charge':
                continue
            else:
                logging.error(f'[ERROR] 獲取響應失敗，即將重試! url: {url} - 錯誤: {e}')
        except:
            exception_type, exception_value, _ = sys.exc_info()
            logging.error(f'[ERROR] 獲取響應出現未知錯誤，即將重試! url: {url} - 錯誤: {exception_type.__name__} - {exception_value}')
        if mustFetch:
            continue
        else:
            break

# ------------------------
# 非同步處理分類
# 注意：本範例將會產生兩種文件：RSS XML (.rss.xml) 同 Markdown (.md)
async def process_category(category, url):
    try:
        response = await get_response(url)
        if response.ok:
            web_content = response.text.strip()
        else:
            print(f'{category} 處理失敗，即將結束程序!')
            logging.error(f'{category} 處理失敗，HTTP 狀態碼: {response.status_code}')
            sys.exit(1)
    except Exception as e:
        print(f'{category} 獲取響應出錯，即將結束程序!')
        logging.error(f'{category} 獲取響應出錯: {e}')
        sys.exit(1)
    except:
        print(f'{category} 出現未知錯誤，即將結束程序!')
        logging.error(f'{category} 出現未知錯誤')
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
    articles_list = list(articles)
    if len(articles_list) == 0:
        return

    # 每篇文章分別處理，並同時收集 Markdown 格式文章內容（方便匯出 .md 文件）
    md_articles = []
    tasks = []
    for article in articles_list:
        tasks.append(asyncio.create_task(process_article(fg, category, article)))
    results = await asyncio.gather(*tasks)
    for item in results:
        if item is not None:
            md_articles.append(item)

    # 產生 RSS XML 字串，同執行 HTML 清理等工作
    rss_str = fg.rss_str()
    soup_rss = BeautifulSoup(rss_str, 'lxml-xml')
    for item in soup_rss.find_all('item'):
        if item.description is not None:
            document = lxmlhtml.fromstring(html.unescape(item.description.string.strip()))
            clean_html = cleaner.clean_html(document)
            clean_html_str = lxmlhtml.tostring(clean_html, pretty_print=True, encoding='unicode')
            item.description.string = CData(html.unescape(clean_html_str))
    if soup_rss.find('url') is not None:
        soup_rss.find('url').string = CData(html.unescape(soup_rss.find('url').string.strip()))
    sorted_items = sorted(soup_rss.find_all('item'), key=lambda x: datetime.strptime(get_item_pub_date(x), '%a, %d %b %Y %H:%M:%S %z') if get_item_pub_date(x) else datetime.min, reverse=True)
    for item in soup_rss.find_all('item'):
        item.extract()
    for item in sorted_items:
        soup_rss.channel.append(item)
    tag = soup_rss.find('lastBuildDate')
    if tag:
        tag.decompose()
    soup_rss = soup_rss.prettify().strip()
    soup_rss = soup_rss.replace('http://', 'https://')
    
    # 儲存 RSS XML
    rss_filename = f'{category}.rss.xml'
    
    async with aiofiles.open(rss_filename, 'w', encoding='utf-8') as file:
        await file.write(soup_rss)
    
    print(f'{category} RSS 已輸出至 {rss_filename}')

    # 將 Markdown 格式文章內容統整，並儲存 Markdown 文件
    md_filename = f'{category}.md'
    md_lines = []
    # md_lines.append(f"# {categories_data[category]['title']} Feed (Markdown Format)")
    # md_lines.append("\n---\n")
    
    for article in md_articles:
        md_lines.append(f"## {article['title']}")
        md_lines.append(f"原文連結：[{article['url']}]({article['url']})")
        md_lines.append("\n" + article['markdown'] + "\n")
        md_lines.append("---\n")
    md_str = "\n".join(md_lines)
    
    async with aiofiles.open(md_filename, 'w', encoding='utf-8') as file:
        await file.write(md_str)
    
    print(f'{category} Markdown 已輸出至 {md_filename}')

# ------------------------
# 用 threading 包裝非同步處理（方便多分類同時運行）
def process_category_thread(category, url):
    asyncio.run(process_category(category, url))

def main():
    threads = []
    for category, data in categories_data.items():
        t = threading.Thread(target=process_category_thread, args=(category, data['url']))
        threads.append(t)
        t.start()
    
    for thread in threads:
        thread.join()

if __name__ == '__main__':
    start_time = time.time()
    memUsage()
    print('333')
    # 兩次檢查（如原先邏輯）
    check()
    check()
    print('444')
    print('555')
    main()
    check()
    check()
    end_time = time.time()
    execution_time = end_time - start_time

    cache_hit_rate = cache_hits / total_requests * 100 if total_requests > 0 else 0
    print(f'總請求數: {total_requests}')
    print(f'緩存命中數: {cache_hits}')
    print(f'緩存命中率: {cache_hit_rate:.2f}%')
    print(f'HTTP/1.1 數: {verCount11}')
    print(f'HTTP/2.0 數: {verCount20}')
    print(f'HTTP/3.0 數: {verCount30}')
    memUsage()

    # 顯示 netlocList（若有使用，可根據需要加入到代碼）
    # print(f'len( netlocList ): { len( netlocList ) }')
    # print(f'netlocList: { netlocList }')
    print(f'執行時間：{execution_time}秒')
