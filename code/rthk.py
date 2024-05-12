import qh3
import asyncio
import niquests
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

# 設置代理和HTTP客戶端
proxies = {'http': 'socks5h://localhost:50000', 'https': 'socks5h://localhost:50000'}
session = niquests.Session(resolver="doh://mozilla.cloudflare-dns.com/dns-query", pool_connections=10, pool_maxsize=10000, retries=3)
session.quic_cache_layer.add_domain('images.weserv.nl')
session.quic_cache_layer.add_domain('mozilla.cloudflare-dns.com')
session.headers['Cache-Control'] = 'no-cache'
session.headers['Pragma'] = 'no-cache'
userAgent = [
    'Mozilla/5.0 (Windows NT 10.0; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Windows NT 10.0; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Windows NT 10.0; rv:123.0) Gecko/20100101 Firefox/123.0',
]
session.headers['User-Agent'] = secrets.choice(userAgent)

# 創建另一個 session 用於處理 localhost 請求
localhost_session = niquests.Session(pool_connections=5, pool_maxsize=10000, retries=3)

# 設置日誌記錄
logging.basicConfig(filename='rthk_feed.log', level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def check_proxy():
    try:
        response = session.get('https://1.1.1.1/cdn-cgi/trace', proxies=None)
        if response.ok:
            print(f'使用代理獲取 https://1.1.1.1/cdn-cgi/trace 成功:\n{response.text}\n')
        else:
            print(f'使用代理獲取 https://1.1.1.1/cdn-cgi/trace 失敗:\n{response.status_code}\n')
    except Exception as e:
        print(f'使用代理獲取 https://1.1.1.1/cdn-cgi/trace 出錯:\n{e}\n')
    except:
        print(f'使用代理獲取 https://1.1.1.1/cdn-cgi/trace 出現未知錯誤\n')

    try:
        response = session.get('https://1.1.1.1/cdn-cgi/trace', proxies=proxies)
        if response.ok:
            print(f'不使用代理獲取 https://1.1.1.1/cdn-cgi/trace 成功:\n{response.text}\n')
        else:
            print(f'不使用代理獲取 https://1.1.1.1/cdn-cgi/trace 失敗:\n{response.status_code}\n')
    except Exception as e:
        print(f'不使用代理獲取 https://1.1.1.1/cdn-cgi/trace 出錯:\n{e}\n')
    except:
        print(f'不使用代理獲取 https://1.1.1.1/cdn-cgi/trace 出現未知錯誤\n')

# 解析發布日期
def parse_pub_date(date_str):
    date_str = date_str.replace('HKT', '+0800')
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %z %H:%M')
    return date_obj.strftime('%a, %d %b %Y %H:%M:%S %z')

# 獲取文章發布日期
def get_item_pub_date(item):
    pub_date = item.find('pubDate')
    if pub_date:
        return pub_date.text

    published = item.find('published')
    if published:
        return published.text

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

async def process_category(category, url):
    try:
        response = await get_response(url)
        if response.ok:
            web_content = response.text
        else:
            print(f'{category} 處理失敗，即將重試!')
            logging.error(f'{category} 處理失敗，HTTP 狀態碼: {response.status_code}')
            return
    except Exception as e:
        print(f'{category} 獲取響應出錯，即將重試!')
        logging.error(f'{category} 獲取響應出錯: {e}')
        return
    except:
        print(f'{category} 出現未知錯誤，即將重試!')
        logging.error(f'{category} 出現未知錯誤')
        return

    soup = BeautifulSoup(web_content, 'html.parser')

    fg = FeedGenerator()
    fg.title(categories_data[category]['title'])
    fg.description(categories_data[category]['title'])
    fg.link(href=categories_data[category]['url'], rel='alternate')
    fg.language('zh-HK')

    feedImg = f"https://images.weserv.nl/?n=-1&output=webp&url={urllib.parse.quote_plus('https://favicone.com/' + urllib.parse.urlparse(categories_data[category]['url']).netloc)}"
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

    soup_rss = BeautifulSoup(rss_str, 'xml')

    for item in soup_rss.find_all('item'):
        if item.description is not None:
            item.description.string = CData(html.unescape(item.description.string.strip()))

    if soup_rss.find('url') is not None:
        soup_rss.find('url').string = CData(html.unescape(soup_rss.find('url').string))
    
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

    print(f'{category} 處理完成!')

async def process_article(fg, category, article):
    try:
        fe = fg.add_entry()
                
        articleTitle = article.select_one('.ns2-title').text
        articleLink = article.select_one('.ns2-title a')['href']
        articleLink = articleLink.replace('?spTabChangeable=0', '')
        
        print( f'{articleTitle} started!' )

        article_response = await get_response(articleLink)
        article_content = article_response.text
        article_soup = BeautifulSoup(article_content, 'html.parser')

        feedDescription = article_soup.select_one('.itemFullText').prettify()

        # 處理圖片
        images = article_soup.find_all(class_='imgPhotoAfterLoad', recursive=True, attrs={'class': 'items_content'})
        imgHtml = ''
        imgList = set()
        for image in images:
            imgUrl = 'http://localhost:8080/?n=-1&output=webp&url=' + urllib.parse.quote_plus(image['src'])
            print(f'{articleLink} - {articleTitle}: {imgUrl}')
            imgList.add(imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/'))
            
            imgUrl = imgUrl.replace('_S_', '_L_').replace('_M_', '_L_')
            print(f'{articleLink} - {articleTitle}: {imgUrl}')
            imgList.add(imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/'))
            
            imgUrl = imgUrl.replace('_L_', '_')
            print(f'{articleLink} - {articleTitle}: {imgUrl}')
            imgList.add(imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/'))

            # 根據圖片大小調整壓縮質量
            latest_imgUrl = await optimize_image_quality(imgUrl)

            imgAlt = image.get('alt', '')
            imgAlt = imgAlt.strip()
            if latest_imgUrl:
                latest_imgUrl = latest_imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/')
                imgHtml += f'<img src="{latest_imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto> <br>'
                imgList.add(latest_imgUrl)
                print(f'Final imgUrlWithQ: {latest_imgUrl}')
            else:
                imgUrl = imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/')
                imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto> <br>'
                imgList.add(imgUrl)
                print(f'Final imgUrl: {imgUrl}')

        scripts = article_soup.find_all('script')
        for script in scripts:
            if 'videoThumbnail' in script.text:
                match = re.search(r"videoThumbnail\s*=\s*'(.*)'", script.text)
                if match:
                    video_thumbnail = match.group(1)
                    imgUrl = 'http://localhost:8080/?n=-1&output=webp&url=' + urllib.parse.quote_plus(video_thumbnail)
                    imgList.add(imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/'))
                    
                    imgUrl = imgUrl.replace('_S_', '_L_').replace('_M_', '_L_')
                    imgList.add(imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/'))
                    
                    imgUrl = imgUrl.replace('_L_', '_')
                    imgList.add(imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/'))
                    
                    # 根據圖片大小調整壓縮質量
                    latest_imgUrl = await optimize_image_quality(imgUrl)

                    imgAlt = article_soup.select_one('.detailNewsSlideTitle').get_text()
                    imgAlt = imgAlt.strip()
                    if latest_imgUrl:
                        latest_imgUrl = latest_imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/')
                        imgHtml += f'<img src="{latest_imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto> <br>'
                        imgList.add(latest_imgUrl)
                        print(f'Final imgUrlWithQ: {latest_imgUrl}')
                    else:
                        imgUrl = imgUrl.replace('http://localhost:8080/', 'https://images.weserv.nl/')
                        imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto> <br>'
                        imgList.add(imgUrl)
                        print(f'Final imgUrl: {imgUrl}')
                    break
        
        # 緩存圖片
        await asyncio.gather(*(cache_image(imageUrl) for imageUrl in imgList))

        pub_date = article.select_one('.ns2-created').text
        formatted_pub_date = parse_pub_date(pub_date)

        feedDescription = f'{imgHtml} {feedDescription} <br><hr> <p>原始網址 Original URL：<a href="{articleLink}" rel=nofollow>{articleLink}</a></p> <p>© rthk.hk</p> <p>電子郵件 Email: <a href="mailto:cnews@rthk.hk" rel=nofollow>cnews@rthk.hk</a></p>'
        feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify()
                
        fe.title(articleTitle)
        fe.link(href=articleLink)
        fe.description(feedDescription)
        fe.pubDate(formatted_pub_date)
        

        print( f'{articleTitle} done!' )
    except Exception as e:
        print(f'{articleTitle} 處理出錯: {e}')
        logging.error(f'{articleTitle} 處理出錯: {e}')
    except:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        print(f'{articleTitle} 出現未知錯誤: {exception_type.__name__} - {exception_value}')
        logging.error(f'{articleTitle} 出現未知錯誤: {exception_type.__name__} - {exception_value}')

async def cache_image(imageUrl):
    try:
        if imageUrl.startswith('http://localhost'):
            response = await get_response(imageUrl, timeout=(1, 1), mustFetch=False, method='HEAD', session=localhost_session)
        else:
            response = await get_response(imageUrl, timeout=(1, 1), proxies=proxies, mustFetch=False, method='HEAD', session=session)
        if response.ok:
            print(f'[INFO] 已緩存! 耗時: {response.elapsed.total_seconds()} - imageUrl: {imageUrl}')
    except Exception as e:
        print(f'[ERROR] 緩存 {imageUrl} 出錯: {e}')
        logging.error(f'[ERROR] 緩存 {imageUrl} 出錯: {e}')
    except:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        print(f'[ERROR] 緩存 {imageUrl} 出現未知錯誤: {exception_type.__name__} - {exception_value}')
        logging.error(f'[ERROR] 緩存 {imageUrl} 出現未知錯誤: {exception_type.__name__} - {exception_value}')

async def optimize_image_quality(imgUrl):
    q = 80
    latest_imgUrl = None
    
    while True:
        imgUrlWithQ = imgUrl.replace('n=-1', f'n=-1&q={q}')
        
        try:
            if imgUrl.startswith('http://localhost'):
                response = await get_response(imgUrlWithQ, method='HEAD', session=localhost_session)
            else:
                response = await get_response(imgUrlWithQ, proxies=None, method='HEAD', session=session)
            
            if response.ok:
                content_length = int(response.headers['Content-Length'])
                
                if content_length < 100 * 1024:  # 小於 100 KB 時不壓縮
                    latest_imgUrl = imgUrlWithQ
                    break
                    
                elif content_length > 100 * 1024:  # 大於 100 KB 時壓縮
                    if q > 10:
                        q -= 10
                        
                    elif q == 5:
                        q = 1
                        
                    elif q == 1:
                        latest_imgUrl = imgUrlWithQ
                        break
                        
                    else:
                        q = 5
                        
                else:
                    latest_imgUrl = imgUrlWithQ
                    break
        except Exception as e:
            # 如果獲取圖片大小失敗，則保持上一次的壓縮質量
            print(f'[ERROR] 獲取圖片大小出錯 - imageUrl: {imgUrl} - 錯誤: {e}')
            logging.error(f'[ERROR] 獲取圖片大小出錯 - imageUrl: {imgUrl} - 錯誤: {e}')
        except:
            exception_type, exception_value, exception_traceback = sys.exc_info()
            print(f'[ERROR] 獲取圖片大小出現未知錯誤 - imageUrl: {imgUrl} - 錯誤: {exception_type.__name__} - {exception_value}')
            logging.error(f'[ERROR] 獲取圖片大小出現未知錯誤 - imageUrl: {imgUrl} - 錯誤: {exception_type.__name__} - {exception_value}')
            latest_imgUrl = imgUrlWithQ
            break
    
    return latest_imgUrl

async def get_response(url, timeout=30, proxies=proxies, mustFetch=True, method='GET', session=session):
    while True:
        try:
            response = await asyncio.to_thread(session.request, method, url, proxies, timeout=timeout)
            return response
        except Exception as e:
            print(f'[ERROR] 獲取響應失敗，即將重試! url: {url} - 錯誤: {e}')
            logging.error(f'[ERROR] 獲取響應失敗，即將重試! url: {url} - 錯誤: {e}')
        except:
            exception_type, exception_value, exception_traceback = sys.exc_info()
            print(f'[ERROR] 獲取響應出現未知錯誤，即將重試! url: {url} - 錯誤: {exception_type.__name__} - {exception_value}')
            logging.error(f'[ERROR] 獲取響應出現未知錯誤，即將重試! url: {url} - 錯誤: {exception_type.__name__} - {exception_value}')
        if mustFetch:
            continue
        else:
            break

def main():
    # check_proxy()
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
    main()
    end_time = time.time()
    execution_time = end_time - start_time
    print(f'執行時間：{execution_time}秒')
