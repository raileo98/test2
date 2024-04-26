import qh3
import niquests
from bs4 import BeautifulSoup, CData
from feedgen.feed import FeedGenerator
from datetime import datetime
import urllib.parse
# import bleach
import secrets
from tqdm import tqdm
import html
import json
import re
import lxml

print()
proxies = {'http':'socks5h://localhost:50000', 'https':'socks5h://localhost:50000'}
# session = niquests.Session(multiplexed=True)
# session = niquests.Session(happy_eyeballs=True)
session = niquests.Session(resolver="doh://9.9.9.9") # , happy_eyeballs=True)
session.headers['Cache-Control'] = 'no-cache'
session.headers['Pragma'] = 'no-cache'
userAgent = ['Mozilla/5.0 (Windows NT 10.0; rv:124.0) Gecko/20100101 Firefox/124.0', 'Mozilla/5.0 (Windows NT 10.0; rv:125.0) Gecko/20100101 Firefox/125.0', 'Mozilla/5.0 (Windows NT 10.0; rv:123.0) Gecko/20100101 Firefox/123.0']
session.headers['User-Agent'] = secrets.choice(userAgent)
session.proxies.update(proxies)

def parse_pub_date(date_str):
    date_str = date_str.replace('HKT', '+0800')
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %z %H:%M')
    return date_obj.strftime('%a, %d %b %Y %H:%M:%S %z')
    
def get_item_pub_date(item):
    pub_date = item.find('pubDate')
    if pub_date:
        return pub_date.text

    published = item.find('published')
    if published:
        return published.text

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

urls_dict = {key: value['url'] for key, value in categories_data.items()}
category_titles = {key: value['title'] for key, value in categories_data.items()}

urls_list = list(urls_dict.items())
print(f'urls_list: {urls_list}')
print()

secrets.SystemRandom().shuffle(urls_list)
print(f'secrets.SystemRandom().shuffle(urls_list): {urls_list}')
print()

count = 1

for category, url in urls_list:
    doWeContinue = True
    fg = FeedGenerator()
    rss_filename = f'{category}.rss'

    print(f'{count}: {category} started!')
    print()

    response = session.get(url)
    
    tryCount = 0

    while True:
        if tryCount >= 5:
            doWeContinue = False
            break
        
        response = session.get(url)
        
        if response.ok:
            break
            
        tryCount += 1
    
    if doWeContinue == False:
        continue
    
    web_content = response.content

    soup = BeautifulSoup(web_content, 'html.parser')

    fg.title(category_titles.get(category, ''))
    fg.description(category_titles.get(category, ''))

    fg.link(href=url, rel='alternate')
    fg.language('zh-HK')

    feedImg = f"https://images.weserv.nl/?n=-1&url={urllib.parse.quote_plus('https://external-content.duckduckgo.com/ip3/' + urllib.parse.urlparse(url).netloc + '.ico')}"
    fg.logo(feedImg)

    fg.copyright('© 香港電台 RTHK')
    fg.webMaster('webmaster@rthk.hk')

    articles = soup.select('.ns2-page')

    articles_list = list(articles)

    if len(articles_list) == 0:
        break
    
    secrets.SystemRandom().shuffle(articles_list)

    for article in tqdm(articles_list):
        title = article.select_one('.ns2-title').text
        link = article.select_one('.ns2-title a')['href']

        article_response = session.get(link)
        article_content = article_response.content
        article_soup = BeautifulSoup(article_content, 'html.parser')

        feedDescription = article_soup.select_one('.itemFullText').prettify()

        # images = article_soup.find_all('img', class_='imgPhotoAfterLoad')
        images = article_soup.find_all(class_='imgPhotoAfterLoad', recursive=True, attrs={'class': 'items_content'})
        imgHtml = ''

        for image in images:
            imgUrl = 'https://images.weserv.nl/?n=-1&url=' + urllib.parse.quote_plus(image['src'])
            imgAlt = image.get('alt', '')
            imgHtml += f'<img src="{imgUrl}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto>'

        # 找到所有的<script>標籤
        scripts = article_soup.find_all('script')
        
        # 遍歷所有的<script>標籤
        for script in scripts:
            if 'videoThumbnail' in script.text:
                # 使用正則表達式從JavaScript代碼中提取videoThumbnail的值
                match = re.search(r"videoThumbnail\s*=\s*'(.*)'", script.text)
                if match:
                    video_thumbnail = match.group(1)
                    # print(f'Video Thumbnail URL: {video_thumbnail}')
                    imgAlt = article_soup.select_one('.detailNewsSlideTitle').get_text()
                    imgHtml += f'<img src="{video_thumbnail}" referrerpolicy="no-referrer" alt="{imgAlt}" style=width:100%;height:auto>'
                    break

        feedDescription = f'{imgHtml} <br> {feedDescription} <p>原始網址 Original URL：<a href="{link}" rel=nofollow>{link}</a></p> <p>© rthk.hk</p> <p>電子郵件 Email: <a href="mailto:cnews@rthk.hk" rel="nofollow">cnews@rthk.hk</a></p>'
        feedDescription = BeautifulSoup(feedDescription, 'html.parser').prettify()

        pub_date = article.select_one('.ns2-created').text
        formatted_pub_date = parse_pub_date(pub_date)

        fe = fg.add_entry()
        fe.title(title)
        fe.link(href=link)

        fe.description(feedDescription)
        fe.pubDate(formatted_pub_date)

    # rss_str = fg.rss_str(pretty=True)
    rss_str = fg.rss_str()

    # soup_rss = BeautifulSoup(rss_str, 'xml')
    soup_rss = BeautifulSoup(rss_str, 'lxml')

    for item in soup_rss.find_all('item'):
        if item.description is not None:
            item.description.string = CData(html.unescape(item.description.string))
        # if item.find('content:encoded'):
            # item.find('content:encoded').string = CData(html.unescape(item.find('content:encoded').string))

    if soup_rss.find('url') is not None:
        soup_rss.find('url').string = CData(html.unescape(soup_rss.find('url').string))
    
    # 排序 feed 項目
    sorted_items = sorted(soup_rss.find_all('item'), key=lambda x: datetime.strptime(get_item_pub_date(x), '%a, %d %b %Y %H:%M:%S %z') if get_item_pub_date(x) else datetime.min, reverse=True)

    # 移除原有的項目
    for item in soup_rss.find_all('item'):
        item.extract()

    # 將排序後的項目重新加入 feed
    for item in sorted_items:
        soup_rss.channel.append(item)

    with open(rss_filename, 'w', encoding='utf-8') as file:
        file.write(soup_rss.prettify())

    print(f'{count}: {category} done!')
    print()

    count += 1
