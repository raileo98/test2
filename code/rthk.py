#!/usr/bin/env python3
# coding: utf-8

# 匯入必要的 Python 模組
import os
import asyncio
import niquests  # 用於發送 HTTP 請求
import logging  # 用於記錄日誌
import aiofiles  # 用於非同步文件操作
import time
from datetime import datetime
from bs4 import BeautifulSoup  # 用於解析 HTML
from feedgen.feed import FeedGenerator  # 用於生成 RSS
from markdownify import markdownify as md  # 用於將 HTML 轉為 Markdown

# ------------------------------
# 設定日誌
def setup_logging():
    """設置日誌，讓執行過程和錯誤訊息記錄下來，方便檢查問題。"""
    logging.basicConfig(
        level=logging.INFO,  # 記錄資訊級別以上的訊息
        format='%(asctime)s %(levelname)s: %(message)s',  # 日誌格式
        datefmt='%Y-%m-%d %H:%M:%S',  # 時間格式
        handlers=[
            logging.FileHandler('rthk_feed.log'),  # 將日誌寫入檔案
            logging.StreamHandler()  # 同時顯示在螢幕上
        ]
    )

setup_logging()  # 初始化日誌設定

# ------------------------------
# 全域變數
session = niquests.Session()  # 用於發送 HTTP 請求的會話

# ------------------------------
# 分類資料
# 包含 RTHK 的所有新聞分類名稱和網址
categories_data = {
    'hk_rthk_ch': {
        'title': '香港電台 - 最新新聞',
        'url': 'https://news.rthk.hk/rthk/ch/latest-news.htm'
    },
    'hk_rthk_local_ch': {
        'title': '香港電台 - 本地',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=3&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_greaterChina_ch': {
        'title': '香港電台 - 大中華',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=2&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_world_ch': {
        'title': '香港電台 - 國際',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=4&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_finance_ch': {
        'title': '香港電台 - 財經',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=5&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_sport_ch': {
        'title': '香港電台 - 體育',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=zh-TW&cat=6&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_en': {
        'title': 'RTHK - English Latest News',
        'url': 'https://news.rthk.hk/rthk/en/latest-news.htm'
    },
    'hk_rthk_local_en': {
        'title': 'RTHK - Local',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=8&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_greaterChina_en': {
        'title': 'RTHK - Greater China',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=9&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_world_en': {
        'title': 'RTHK - World',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=10&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_finance_en': {
        'title': 'RTHK - Finance',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=12&newsCount=60&dayShiftMode=1&archive_date='
    },
    'hk_rthk_sport_en': {
        'title': 'RTHK - Sport',
        'url': 'https://news.rthk.hk/rthk/webpageCache/services/loadModNewsShowSp2List.php?lang=en-GB&cat=11&newsCount=60&dayShiftMode=1&archive_date='
    }
}

# ------------------------------
# 工具函數
def parse_pub_date(date_str):
    """將新聞的發佈日期轉換成 RSS 標準格式，例如 'Tue, 15 Oct 2024 14:30:00 +0800'。"""
    date_str = date_str.replace('HKT', '+0800')  # 將 HKT 轉為時區格式
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %z %H:%M')  # 解析日期
    return date_obj.strftime('%a, %d %b %Y %H:%M:%S %z')  # 轉為 RSS 格式

# ------------------------------
# 文章處理
async def process_article(fg, article):
    """處理單篇文章，生成 RSS 項目並返回 Markdown 內容。"""
    try:
        fe = fg.add_entry()  # 在 RSS 中新增一篇文章項目
        # 提取文章標題和連結
        article_title = article.select_one('.ns2-title').text.strip()
        article_link = article.select_one('.ns2-title a')['href'].strip()
        logging.info(f"正在處理文章：{article_title}")

        # 獲取文章內容
        response = session.get(article_link, timeout=10)
        if response.status_code != 200:
            logging.error(f"無法獲取文章：{article_title}，狀態碼：{response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.select_one('.itemFullText')  # 提取文章正文
        if not content:
            logging.error(f"文章內容缺失：{article_title}")
            return None

        # 處理圖片
        img_html = ''
        images = soup.select('.items_content .imgPhotoAfterLoad')
        for img in images:
            img_url = img['src']
            img_alt = img.get('alt', article_title).strip()
            img_html += f'<img src="{img_url}" alt="{img_alt}" style="width:100%;height:auto">'

        # 提取發佈日期
        pub_date = article.select_one('.ns2-created').text.strip()
        formatted_pub_date = parse_pub_date(pub_date)

        # 組合文章描述
        description = f"{img_html}<br>{content.prettify()}<br><hr>" \
                      f"<p>原文連結：<a href='{article_link}'>{article_link}</a></p>" \
                      f"<p>© 香港電台 RTHK</p>"

        # 填入 RSS 項目
        fe.title(article_title)
        fe.link(href=article_link)
        fe.guid(guid=article_link, permalink=True)
        fe.description(description)
        fe.pubDate(formatted_pub_date)

        # 生成 Markdown 內容
        md_content = md(description)  # 將 HTML 轉為 Markdown
        logging.info(f"完成處理文章：{article_title}")

        return {
            "title": article_title,
            "url": article_link,
            "markdown": md_content
        }
    except Exception as e:
        logging.error(f"處理文章時出錯：{article_title}，錯誤：{e}")
        return None

# ------------------------------
# 分類處理
async def process_category(category, url):
    """處理單個分類，生成 RSS 和 Markdown 文件。"""
    logging.info(f"開始處理分類：{category}")
    try:
        # 獲取分類頁面內容
        response = session.get(url, timeout=10)
        if response.status_code != 200:
            logging.error(f"無法獲取分類 {category}，狀態碼：{response.status_code}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.select('.ns2-page')  # 提取所有文章區塊
        if not articles:
            logging.warning(f"分類 {category} 沒有找到文章")
            return

        # 初始化 RSS 產生器
        fg = FeedGenerator()
        fg.title(categories_data[category]['title'])
        fg.description(categories_data[category]['title'])
        fg.link(href=url, rel='alternate')
        fg.language('zh-HK')
        fg.logo('https://news.rthk.hk/rthk/templates/st_tyneo/favicon_144x144.png')
        fg.copyright('© 香港電台 RTHK')

        # 處理每篇文章
        md_articles = []
        tasks = [process_article(fg, article) for article in articles]
        results = await asyncio.gather(*tasks)

        for result in results:
            if result:
                md_articles.append(result)

        # 生成並儲存 RSS 文件
        rss_filename = f"{category}.xml"
        rss_content = fg.rss_str(pretty=True)  # 生成格式化的 RSS
        async with aiofiles.open(rss_filename, 'w', encoding='utf-8') as file:
            await file.write(rss_content)
        logging.info(f"已生成 RSS 文件：{rss_filename}")

        # 生成並儲存 Markdown 文件
        md_filename = f"{category}.md"
        md_lines = []
        for article in md_articles:
            md_lines.append(f"# {article['title']}")
            md_lines.append(article['markdown'])
            md_lines.append(f"原文連結：[{article['url']}]({article['url']})")
            md_lines.append("---")
        md_content = "\n".join(md_lines)
        async with aiofiles.open(md_filename, 'w', encoding='utf-8') as file:
            await file.write(md_content)
        logging.info(f"已生成 Markdown 文件：{md_filename}")

    except Exception as e:
        logging.error(f"處理分類 {category} 時出錯：{e}")

# ------------------------------
# 主程式
async def main():
    """主程式，處理所有分類。"""
    start_time = time.time()
    tasks = [process_category(category, data['url']) for category, data in categories_data.items()]
    await asyncio.gather(*tasks)
    end_time = time.time()
    logging.info(f"總執行時間：{end_time - start_time:.2f} 秒")

if __name__ == '__main__':
    asyncio.run(main())
