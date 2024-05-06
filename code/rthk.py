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

# 設置代理和HTTP客戶端
proxies = {'http': 'socks5h://localhost:50000', 'https': 'socks5h://localhost:50000'}
session = niquests.Session(resolver="doh://mozilla.cloudflare-dns.com/dns-query", pool_connections=2, pool_maxsize=100)
session.headers['Cache-Control'] = 'no-cache'
session.headers['Pragma'] = 'no-cache'
userAgent = [
    'Mozilla/5.0 (Windows NT 10.0; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Windows NT 10.0; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Windows NT 10.0; rv:123.0) Gecko/20100101 Firefox/123.0',
]
session.headers['User-Agent'] = secrets.choice(userAgent)
session.proxies.update(proxies)

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
        response = await asyncio.to_thread(session.get, url, proxies=proxies)
        if response.ok:
            web_content = response.text
        else:
            print(f'{category} 處理失敗: HTTP 狀態碼')
            return
    except:
        print(f'{category} 處理失敗')
        return

    soup = BeautifulSoup(web_content, 'html.parser')

    fg = FeedGenerator()
    fg.title(categories_data[category]['title'])
    fg.description(categories_data[category]['title'])
    fg.link(href=categories_data[category]['url'], rel='alternate')
    fg.language('zh-HK')

    feedImg = f"https://images.weserv.nl/?n=-1&url={urllib.parse.quote_plus('https://external-content.duckduckgo.com/ip3/' + urllib.parse.urlparse(categories_data[category]['url']).netloc + '.ico')}"
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
            item.description.string = CData(html.unescape(item.description.string))

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
    fe = fg.add_entry()
            
    title = article.select_one('.ns2-title').text
    link = article.select_one('.ns2-title a')['href']
    
    print( f'{title} started!' )

    article_response = await asyncio.to_thread(session.get, link, proxies=proxies)
    article_content = article_response.text
    article_soup = BeautifulSoup(article_content, 'html.parser')

    feedDescription = article_soup.select_one('.itemFullText').prettify()

    # 處理圖片
    images = article_soup.find_all(class_='imgPhotoAfterLoad', recursive=True, attrs={'class': 'items_content'})
    imgHtml = ''
    imgList = set()
    for image in images:
        imgUrl = 'https://images.weserv.nl/?n=-1&url=' + urllib.parse.quote_plus(image['src'])
        imgAlt = image.get('alt', '')
        imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto> <br>'
        imgList.add(imgUrl)

    scripts = article_soup.find_all('script')
    for script in scripts:
        if 'videoThumbnail' in script.text:
            match = re.search(r"videoThumbnail\s*=\s*'(.*)'", script.text)
            if match:
                video_thumbnail = match.group(1)
                imgAlt = article_soup.select_one('.detailNewsSlideTitle').get_text()
                imgHtml += f'<img src="{video_thumbnail}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto> <br>'
                break
    
    # 緩存圖片
    await asyncio.gather(*(cache_image(imageUrl) for imageUrl in imgList))

    pub_date = article.select_one('.ns2-created').text
    formatted_pub_date = parse_pub_date(pub_date)

    feedDescription = f'{imgHtml} {feedDescription} <p>原始網址 Original URL：<a href="{link}" rel=nofollow>{link}</a></p> <p>© rthk.hk</p> <p>電子郵件 Email: <a href="mailto:cnews@rthk.hk" rel="nofollow">cnews@rthk.hk</a></p>'
    feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify()
            
    fe.title(title)
    fe.link(href=link)
    fe.description(feedDescription)
    fe.pubDate(formatted_pub_date)
    
    print( f'{title} done!' )

# 緩存圖片的異步函數
async def cache_image(imageUrl):
    while True:
        try:
            imageUrlResponse = await asyncio.to_thread(session.head, imageUrl, timeout=(1, 1), proxies=proxies)
            if imageUrlResponse.ok:
                print(f'{imageUrlResponse.elapsed.total_seconds()} - {imageUrl} : 已緩存！')
                break
            else:
                print(f'{imageUrlResponse.elapsed.total_seconds()} - {imageUrl} : 緩存失敗！')
        except:
            print(f'{imageUrl} : 嘗試失敗，將重試。')

async def main():
    tasks = [asyncio.create_task(process_category(category, data['url'])) for category, data in categories_data.items()]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    end_time = time.time()
    execution_time = end_time - start_time
    print(f'執行時間：{execution_time}秒')
