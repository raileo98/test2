print('111')

import sys
import subprocess

# 獲取Python解釋器路徑
python_path = sys.executable

# 使用Python解釋器運行命令
# os.system(f'{python_path} -m niquests.help')
# subprocess.run([python_path, '-m', 'niquests.help'])
subprocess.run([python_path, '-m', 'niquests.help'], shell=False)

import psutil
import os
import qh3
import asyncio
import niquests
import requests_cache
from bs4 import BeautifulSoup, CData
from feedgen.feed import FeedGenerator
from datetime import datetime
import urllib.parse
import secrets
import html
import re
import aiofiles
import time
import logging
import threading
import sys
# from urllib3_future.util import Retry
from niquests.adapters import HTTPAdapter, Retry
from lxml import html as lxmlhtml
from lxml.html.clean import Cleaner

verCount11 = 0
verCount20 = 0
verCount30 = 0
netlocList = []

print('222')

# 設置環境變數
os.environ["NIQUESTS_STRICT_OCSP"] = "1"

# 驗證設置是否成功
if os.environ.get("NIQUESTS_STRICT_OCSP") == "1":
    print("NIQUESTS_STRICT_OCSP is enabled")
else:
    print("NIQUESTS_STRICT_OCSP is not enabled")

# 設置HTTP客戶端
class CachedSession(requests_cache.session.CacheMixin, niquests.Session):
    pass

retries = Retry(
    total = 2,
    backoff_factor = 1,
)

# session = CachedSession( trust_env=False, allowable_methods=('GET', 'HEAD'), resolver="doh://mozilla.cloudflare-dns.com/dns-query", pool_connections=1, pool_maxsize=10000, retries=retries, backend='redis', happy_eyeballs=True)
# pool_connections = len( categories_data )
session = CachedSession( allowable_methods=('GET', 'HEAD'), resolver="doh://mozilla.cloudflare-dns.com/dns-query", pool_connections=1, pool_maxsize=10000, backend='redis', happy_eyeballs=True )
adapter = HTTPAdapter( max_retries=retries )
session.mount("https://", adapter=adapter)
session.mount("http://", adapter=adapter)
session.trust_env = False
# time.sleep(1) # 'Cannot select a disposable connection to ease the charge'

session.quic_cache_layer.add_domain( 'mozilla.cloudflare-dns.com' )
session.quic_cache_layer.add_domain( 'ocsp1.ecert.gov.hk' )
# session.headers['Cache-Control'] = 'no-cache'
# session.headers['Pragma'] = 'no-cache'
userAgent = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:130.0) Gecko/130.0 Firefox/130.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0',
    'Mozilla/5.0 (Android 10; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0',
]
session.headers['User-Agent'] = secrets.choice(userAgent)

# 創建另一個 session 用於處理 localhost 請求
# localhost_session = niquests.Session(pool_connections=10, pool_maxsize=10000, retries=1)

# 設置日誌記錄
# logging.basicConfig(filename='rthk_feed.log', level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# 創建一個日誌器
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # 設置日誌器的級別為 INFO

# 創建一個處理器，用於寫入文件
file_handler = logging.FileHandler('rthk_feed.log')
file_handler.setLevel(logging.WARNING)  # 只記錄 WARNING 和 ERROR 級別的日誌

# 創建一個處理器，用於輸出到控制台
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # 記錄所有 INFO 級別的日誌

# 設置日誌格式
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 將處理器添加到日誌器
logger.addHandler(file_handler)
logger.addHandler(console_handler)

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
            print( f'headersForCheck: { headersForCheck }' )
            response = session.get(url, timeout=2, headers=headersForCheck )
            if response.ok:
                # print(f'使用代理獲取 {url} 成功: \nhttp_version: {response.http_version} \n{response.text}\n')
                print(f'使用代理獲取 {url} 成功: \n{ response.text.splitlines()[:10] }\n')
            else:
                print(f'使用代理獲取 {url} 失敗:\n{response.status_code}\n')
        except Exception as e:
            print(f'使用代理獲取 {url} 出錯:\n{e}\n')
        except:
            print(f'使用代理獲取 {url} 出現未知錯誤\n')

# 解析發布日期
def parse_pub_date(date_str):
    date_str = date_str.replace('HKT', '+0800')
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %z %H:%M')
    return date_obj.strftime('%a, %d %b %Y %H:%M:%S %z')

# 獲取文章發布日期
def get_item_pub_date(item):
    pub_date = item.find('pubDate')
    if pub_date:
        return pub_date.text.strip()

    published = item.find('published')
    if published:
        return published.text.strip()

    return None

# 分類數據
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

# 創建 Cleaner 實例
cleaner = Cleaner()

async def process_category(category, url):
    try:
        response = await get_response(url)
        if response.ok:
            web_content = response.text.strip()
        else:
            print(f'{category} 處理失敗，即將結束程序!')
            logging.error(f'{category} 處理失敗，HTTP 狀態碼: {response.status_code}')
            sys.exit(1)  # 結束程序
    except Exception as e:
        print(f'{category} 獲取響應出錯，即將結束程序!')
        logging.error(f'{category} 獲取響應出錯: {e}')
        sys.exit(1)  # 結束程序
    except:
        print(f'{category} 出現未知錯誤，即將結束程序!')
        logging.error(f'{category} 出現未知錯誤')
        sys.exit(1)  # 結束程序

    # soup = BeautifulSoup(web_content, 'lxml')
    soup = BeautifulSoup(web_content, 'html.parser')

    fg = FeedGenerator()
    fg.title(categories_data[category]['title'])
    fg.description(categories_data[category]['title'])
    fg.link(href=categories_data[category]['url'], rel='alternate')
    fg.language('zh-HK')

    # feedImg = f"https://wsrv.nl/?n=-1&output=webp&trim=1&url={urllib.parse.quote_plus('https://favicone.com/' + urllib.parse.urlparse(categories_data[category]['url']).netloc)}"
    feedImg = 'https://wsrv.nl/?n=-1&url=https://news.rthk.hk/rthk/templates/st_tyneo/favicon_144x144.png'
    fg.logo(feedImg)

    fg.copyright('© 香港電台 RTHK')
    fg.webMaster('webmaster@rthk.hk')

    articles = soup.select('.ns2-page')
    articles_list = list(articles)

    if len(articles_list) == 0:
        return
    
    # 處理每篇文章
    tasks = [asyncio.create_task(process_article(fg, category, article)) for article in articles_list]
    await asyncio.gather(*tasks)

    rss_str = fg.rss_str()

    soup_rss = BeautifulSoup(rss_str, 'lxml-xml')

    for item in soup_rss.find_all('item'):
        if item.description is not None:
            # 解析 HTML
            # document = lxmlhtml.fromstring(soup_rss)
            document = lxmlhtml.fromstring(html.unescape(item.description.string.strip())) # .encode('utf-8')
        
            # 使用 Cleaner 清理文檔
            clean_html = cleaner.clean_html(document)
        
            # 將清理後的 HTML 轉換為字符串
            clean_html_str = lxmlhtml.tostring(clean_html, pretty_print=True, encoding='unicode')
            item.description.string = CData(html.unescape(clean_html_str))

    if soup_rss.find('url') is not None:
        soup_rss.find('url').string = CData(html.unescape(soup_rss.find('url').string.strip()))
    
    sorted_items = sorted(soup_rss.find_all('item'), key=lambda x: datetime.strptime(get_item_pub_date(x), '%a, %d %b %Y %H:%M:%S %z') if get_item_pub_date(x) else datetime.min, reverse=True)

    for item in soup_rss.find_all('item'):
        item.extract()

    for item in sorted_items:
        soup_rss.channel.append(item)

    rss_filename = f'{category}.xml'
    
    # 找到<lastBuildDate>標籤並移除它們
    tag = soup_rss.find('lastBuildDate')
    if tag:
        tag.decompose()
    
    soup_rss = soup_rss.prettify().strip()
    soup_rss = soup_rss.replace( 'http://', 'https://' )
    
    async with aiofiles.open(rss_filename, 'w', encoding='utf-8') as file:
        await file.write(soup_rss)

    print(f'{category} 處理完成!')

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
            return  # 跳過該文章，繼續處理下一篇文章
        
        article_content = article_response.text.strip()
        article_soup = BeautifulSoup(article_content, 'html.parser')

        feedDescription = article_soup.select_one('.itemFullText').prettify().strip()

        # 處理圖片
        images = article_soup.select('.items_content .imgPhotoAfterLoad')
        imgHtml = ''
        imgList = set()
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

            # 根據圖片大小調整壓縮質量
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

        feedDescription = f'{imgHtml} <br> {feedDescription} <br><hr> <p>原始網址 Original URL：<a href="{articleLink}" rel="nofollow">{articleLink}</a></p> <p>© rthk.hk</p> <p>電子郵件 Email: <a href="mailto:cnews@rthk.hk" rel="nofollow">cnews@rthk.hk</a></p>'
        
        feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify().strip()
        
        fe.title(articleTitle)
        fe.link(href=articleLink)
        fe.guid(guid=articleLink, permalink=True)
        fe.description(feedDescription)
        fe.pubDate(formatted_pub_date)
        
        print(f'{articleTitle} done!')
        memUsage()
    except Exception as e:
        print(f'{articleTitle} 處理出錯: {e}')
        logging.error(f'{articleTitle} 處理出錯: {e}')
    except:
        exception_type, exception_value, exception_traceback = sys.exc_info()
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
        exception_type, exception_value, exception_traceback = sys.exc_info()
        logging.error(f'[ERROR] 緩存 {imageUrl} - 出現未知錯誤: {exception_type.__name__} - {exception_value}')

async def optimize_image_quality(imgUrl):
    q = 99
    latest_imgUrl = modify_image_url(imgUrl, 1)
    latestAvailableQ = None
    
    # 在函數開始時新增一個布林變數
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
                content_length = int(response.headers['Content-Length'])
                upstream_response_length = int(response.headers['x-upstream-response-length'])
    
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
                        q = max(1, q - 5)  # 確保 q 不會低於 1

                    # 檢查是否已經滿足過條件
                    if content_length > upstream_response_length:
                        has_matched_condition = True  # 設置為 True
    
                elif content_length <= 1000 * 150:
                    logging.info(f'[INFO] 圖片大小小於 150 KB - imageUrl: {imgUrl} - 當前質量參數 q: {q}')
                    latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
                    break
    
        except Exception as e:
            logging.error(f'[ERROR] 獲取圖片大小出錯 - imageUrl: {imgUrl} - 錯誤: {e}')
            q = 1  # 將質量參數設置為 1
            latest_imgUrl = latestAvailableQ if latestAvailableQ else imgUrlWithQ
            break

    # 在迴圈結束後檢查是否滿足過條件，並額外減少 q
    # if has_matched_condition and (upstream_response_length < 1000 * 150 or content_length_q99 < 1000 * 150):
    # if has_matched_condition and (upstream_response_length < 1000 * 100 or content_length_q99 < 1000 * 100):
    if upstream_response_length <= 1000 * 150 or content_length_q99 <= 1000 * 150:
        if q == 99:
            q = 90

        elif q <= 95:
            q = max(1, q - 10)  # 確保 q 不會低於 1

        # 更新 latest_imgUrl 以反映最終的 q 值
        # latest_imgUrl = imgUrl.replace('n=-1', f'n=-1&q={q}')
        latest_imgUrl = modify_image_url(imgUrl, q)
        print( f'圖像小於 150 KB，{ imgUrl } --> { latest_imgUrl }' )

    return latest_imgUrl

def modify_image_url(imageUrl, new_quality):
    # 解析 URL
    parsed_url = urllib.parse.urlparse(imageUrl)
    
    # 解析查詢參數
    query_params = urllib.parse.parse_qs(parsed_url.query)
    
    # 只修改質量參數 q
    query_params['q'] = [str(new_quality)]
    
    # 重新組合查詢參數
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    
    # 重新組合 URL
    new_url = urllib.parse.urlunparse(parsed_url._replace(query=new_query))
    # new_url = new_url.replace('h=1080', 'we&h=1080') # temp solution, ha!
    new_url = new_url.replace('n=-1&h=1080', 'n=-1&we&h=1080') # temp solution, ha!
    new_url = new_url.replace('&amp;', '&') # temp solution, ha!
    
    return new_url

async def get_response(url, timeout=10, mustFetch=True, method='GET', session=session):
    # global total_requests, cache_hits
    # global verCount11, verCount20, verCount30
    global total_requests, cache_hits, verCount11, verCount20, verCount30
    total_requests += 1
    while True:
        try:
            # if urllib.parse.urlparse( url ).netloc not in netlocList:
                # session.quic_cache_layer.add_domain( urllib.parse.urlparse( url ).netloc )
                # netlocList.append( urllib.parse.urlparse( url ).netloc )
            
            session.quic_cache_layer.add_domain( urllib.parse.urlparse( url ).netloc )
            response = await asyncio.to_thread(session.request, method, url, timeout=timeout)
            
            if response.from_cache:
                cache_hits += 1

            if response.from_cache == False and response.raw.version:
                
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
                # print(f'[ERROR] 獲取響應失敗，即將重試! url: {url} - 錯誤: {e}')
                logging.error(f'[ERROR] 獲取響應失敗，即將重試! url: {url} - 錯誤: {e}')
        
        except:
            exception_type, exception_value, exception_traceback = sys.exc_info()
            # print(f'[ERROR] 獲取響應出現未知錯誤，即將重試! url: {url} - 錯誤: {exception_type.__name__} - {exception_value}')
            logging.error(f'[ERROR] 獲取響應出現未知錯誤，即將重試! url: {url} - 錯誤: {exception_type.__name__} - {exception_value}')
        
        if mustFetch:
            continue
        else:
            break

def main():
    threads = []
    for category, data in categories_data.items():
        t = threading.Thread(target=process_category_thread, args=(category, data['url']))
        threads.append(t)
        t.start()
    
    for thread in threads:
        thread.join()

def process_category_thread(category, url):
    asyncio.run(process_category(category, url))

if __name__ == '__main__':
    start_time = time.time()
    memUsage()
    print('333')
    check()
    check()
    print('444')
    print('555')
    main()
    check()
    check()
    end_time = time.time()
    execution_time = end_time - start_time

    # 計算並打印緩存命中率
    cache_hit_rate = cache_hits / total_requests * 100
    print(f'總請求數: {total_requests}')
    print(f'緩存命中數: {cache_hits}')
    print(f'緩存命中率: {cache_hit_rate:.2f}%')
    print( f'HTTP/1.1 數: { verCount11 }' )
    print( f'HTTP/2.0 數: { verCount20 }' )
    print( f'HTTP/3.0 數: { verCount30 }' )

    memUsage()
    print( f'len( netlocList ): { len( netlocList ) }' )
    print( f'netlocList: { netlocList }' )
    # print(f'len( session.cache.responses.values ): { len( session.cache.responses.values ) }')
    print(f'執行時間：{execution_time}秒')
