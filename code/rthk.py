import os
import sys
import asyncio
import psutil
import logging
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

# 獲取Python解釋器路徑
python_path = sys.executable

# 使用Python解釋器運行命令
os.system(f'{python_path} -m niquests.help')

# 設置環境變數
os.environ["NIQUESTS_STRICT_OCSP"] = "1"

# 驗證設置是否成功
if os.environ.get("NIQUESTS_STRICT_OCSP") == "1":
    print("NIQUESTS_STRICT_OCSP is enabled")
else:
    print("NIQUESTS_STRICT_OCSP is not enabled")

# 設置日誌記錄
logging.basicConfig(filename='rthk_feed.log', level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# 設置HTTP客戶端
class CachedSession(requests_cache.session.CacheMixin, requests_cache.Session):
    pass

session = CachedSession(allowable_methods=('GET', 'HEAD'), resolver="doh://mozilla.cloudflare-dns.com/dns-query", pool_connections=10, pool_maxsize=10000, retries=1, backend='redis', happy_eyeballs=True)

# 設置分類數據
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

async def memUsage():
    memory = psutil.virtual_memory()
    swap_memory = psutil.swap_memory()
    print(f"虛擬記憶體使用情况：{memory.percent}% | {memory.used / (1024 * 1024):.2f} MB")
    print(f"交換記憶體使用情况：{swap_memory.percent}% | {swap_memory.used / (1024 * 1024):.2f} MB")

async def check():
    urls = [
        'https://1.1.1.1/cdn-cgi/trace',
        'https://mozilla.cloudflare-dns.com/cdn-cgi/trace',
        'https://images.weserv.nl/cdn-cgi/trace',
        'https://images.weserv.nl/quota'
    ]

    for url in urls:
        try:
            headersForCheck = dict(session.headers)
            headersForCheck['Cache-Control'] = 'no-cache'
            headersForCheck['Pragma'] = 'no-cache'
            print(f'headersForCheck: {headersForCheck}')
            response = await get_response(url, headers=headersForCheck)
            if response.ok:
                print(f'使用代理獲取 {url} 成功: \n{response.text}\n')
            else:
                print(f'使用代理獲取 {url} 失敗:\n{response.status_code}\n')
        except Exception as e:
            print(f'使用代理獲取 {url} 出錯:\n{e}\n')

async def process_category(category, url):
    try:
        logging.info(f'開始處理分類: {category}')
        response = await get_response(url)
        if response.ok:
            web_content = response.text
        else:
            logging.error(f'{category} 處理失敗，即將重試!')
            return
    except Exception as e:
        logging.error(f'{category} 獲取響應出錯，即將重試! 錯誤: {e}')
        return

    soup = BeautifulSoup(web_content, 'html.parser')

    fg = FeedGenerator()
    fg.title(categories_data[category]['title'])
    fg.description(categories_data[category]['title'])
    fg.link(href=categories_data[category]['url'], rel='alternate')
    fg.language('zh-HK')

    articles = soup.select('.ns2-page')
    articles_list = list(articles)

    if len(articles_list) == 0:
        return

    # 處理每篇文章
    tasks = [asyncio.create_task(process_article(fg, category, article)) for article in articles_list]
    await asyncio.gather(*tasks)

    rss_str = fg.rss_str()

    soup_rss = BeautifulSoup(rss_str, 'xml')

    for item in soup_rss.find_all('item'):
        if item.description is not None:
            item.description.string = CData(html.unescape(item.description.string.strip()))

    sorted_items = sorted(soup_rss.find_all('item'), key=lambda x: datetime.strptime(get_item_pub_date(x), '%a, %d %b %Y %H:%M:%S %z') if get_item_pub_date(x) else datetime.min, reverse=True)

    for item in soup_rss.find_all('item'):
        item.extract()

    for item in sorted_items:
        soup_rss.channel.append(item)

    rss_filename = f'{category}.rss'

    # 找到<lastBuildDate>標籤並移除它們
    tag = soup_rss.find('lastBuildDate')
    if tag:
        tag.decompose()

    async with aiofiles.open(rss_filename, 'w', encoding='utf-8') as file:
        await file.write(soup_rss.prettify())

    logging.info(f'{category} 處理完成!')

async def process_article(fg, category, article):
    try:
        fe = fg.add_entry()

        articleTitle = article.select_one('.ns2-title').text
        articleLink = article.select_one('.ns2-title a')['href']
        articleLink = articleLink.replace('?spTabChangeable=0', '')

        logging.info(f'{articleTitle} started!')

        article_response = await get_response(articleLink)
        article_content = article_response.text
        article_soup = BeautifulSoup(article_content, 'html.parser')

        feedDescription = article_soup.select_one('.itemFullText').prettify()

        pub_date = article.select_one('.ns2-created').text
        formatted_pub_date = parse_pub_date(pub_date)

        feedDescription = f'{feedDescription} <br><hr> <p>原始網址 Original URL：<a href="{articleLink}" rel="nofollow">{articleLink}</a></p> <p>© rthk.hk</p> <p>電子郵件 Email: <a href="mailto:cnews@rthk.hk" rel="nofollow">cnews@rthk.hk</a></p>'

        feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify()

        fe.title(articleTitle)
        fe.link(href=articleLink)
        fe.description(feedDescription)
        fe.pubDate(formatted_pub_date)

        logging.info(f'{articleTitle} done!')
        await memUsage()
    except Exception as e:
        logging.error(f'{articleTitle} 處理出錯: {e}')

async def get_response(url, timeout=30, method='GET', headers=None):
    global total_requests, cache_hits
    total_requests += 1
    while True:
        try:
            response = await asyncio.to_thread(session.request, method, url, timeout=timeout, headers=headers)
            if response.from_cache:
                cache_hits += 1
            return response
        except Exception as e:
            logging.error(f'[ERROR] 獲取響應失敗，即將重試! url: {url} - 錯誤: {e}')

async def main():
    for category, data in categories_data.items():
        await process_category(category, data['url'])

if __name__ == '__main__':
    print('11111111')
    start_time = time.time()
    await memUsage()
    print('333')
    await check()
    await check()
    print('444')
    await main()
    await check()
    await check()
    end_time = time.time()
    execution_time = end_time - start_time

    # 計算並打印緩存命中率
    cache_hit_rate = cache_hits / total_requests * 100
    print(f'總請求數: {total_requests}')
    print(f'緩存命中數: {cache_hits}')
    print(f'緩存命中率: {cache_hit_rate:.2f}%')

    await memUsage()
    print(f'執行時間：{execution_time}秒')
