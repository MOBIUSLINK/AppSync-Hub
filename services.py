import html
import logging
import os
import re
import sys
import time
import urllib.parse
from urllib.parse import urljoin, urlparse
import requests
import urllib3
from bs4 import BeautifulSoup
from flask import Response
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from config import DOWNLOAD_DIR, Apps, db, db_lock, download_progress

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)
log_listeners = []


class SSELogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            for q in log_listeners:
                q.put(log_entry)
        except Exception:
            self.handleError(record)


root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.handlers.clear()
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)
sse_handler = SSELogHandler()
sse_handler.setFormatter(formatter)
root_logger.addHandler(sse_handler)
logger = logging.getLogger(__name__)


def fetch_rendered_html(app_item):
    """高级无头浏览器：支持直接渲染，或点击按钮截获真实下载地址"""
    url = app_item["url"]
    click_selector = app_item.get("css_selector")
    app_name = app_item.get("name", "Unknown")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        try:
            logger.debug(f"[{app_name}] 正在加载动态页面: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1500)
            except PlaywrightTimeoutError:
                logger.warning(
                    f"[{app_name}] 页面加载超时，但强行继续执行后续点击或解析逻辑..."
                )
            if click_selector:
                logger.info(f"[{app_name}] 尝试触发下载事件: {click_selector}")
                real_download_url = None

                def trigger_click(is_js_inject=False):
                    for frame in page.frames:
                        if frame.locator(click_selector).count() > 0:
                            if is_js_inject:
                                frame.locator(click_selector).first.evaluate(
                                    "node => node.click()"
                                )
                            else:
                                frame.locator(click_selector).first.click(force=True)
                            return True
                    raise Exception("所有 iframe 框架中均未找到该元素 (可能被延迟加载)")

                try:
                    with page.expect_download(timeout=4000) as download_info:
                        trigger_click(is_js_inject=False)
                    real_download_url = download_info.value.url
                    download_info.value.cancel()
                    logger.info(
                        f"[{app_name}] 🟢 原生物理点击生效！截获链接: {real_download_url}"
                    )
                except Exception as e_native:
                    logger.warning(
                        f"[{app_name}] 物理点击未触发下载或元素未就绪，启动 JS 注入强攻..."
                    )
                    try:
                        with page.expect_download(timeout=4000) as download_info_js:
                            trigger_click(is_js_inject=True)
                        real_download_url = download_info_js.value.url
                        download_info_js.value.cancel()
                        logger.info(
                            f"[{app_name}] 🟡 JS 注入点击生效！截获链接: {real_download_url}"
                        )
                    except Exception as e_js:
                        logger.warning(
                            f"[{app_name}] JS 注入点击亦宣告失败，将降级提取页面源码。"
                        )
                if real_download_url:
                    return f'<html><body><a href="{real_download_url}">VIRTUAL_INJECTED_LINK</a></body></html>'
            logger.debug(f"[{app_name}] 页面渲染完成，返回源码流。")
            return page.content()
        except Exception as e:
            logger.error(f"[{app_name}] Playwright 核心执行异常: {e}")
            return ""
        finally:
            context.close()
            browser.close()


def get_latest_url(app_item, force_refresh=False):
    app_name = app_item.get("name", "Unknown")
    logger.info(f"========== 开始抓取任务: {app_name} ==========")
    now = time.time()
    last_fetched = app_item.get("last_fetched") or 0
    if not force_refresh and app_item.get("cached_url") and (now - last_fetched) < 3600:
        logger.info(f"[{app_name}] 使用有效缓存: {app_item['cached_url']}")
        return app_item["cached_url"]
    if app_item.get("direct_link"):
        direct_link = app_item["direct_link"].strip()
        if not direct_link.startswith("http"):
            direct_link = "http://" + direct_link
        logger.info(f"[{app_name}] 使用硬编码直链: {direct_link}")
        with db_lock:
            db.update(
                {"cached_url": direct_link, "last_fetched": now},
                Apps.name == app_item["name"],
            )
        return direct_link
    target_url = app_item["url"]
    html_content = ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    try:
        if app_item.get("needs_browser"):
            logger.info(f"[{app_name}] 启用 Playwright 无头浏览器模式...")
            html_content = fetch_rendered_html(app_item)
        else:
            logger.debug(f"[{app_name}] 使用极速 requests 模式...")
            res = requests.get(target_url, headers=headers, timeout=10)
            res.raise_for_status()
            res.encoding = res.apparent_encoding
            html_content = res.text
        if not html_content:
            raise Exception("获取到的网页源码为空")
        found_url = None
        if app_item.get("regex_pattern"):
            try:
                match = re.search(app_item["regex_pattern"], html_content)
                if match:
                    extracted_str = match.group(1) if match.groups() else match.group(0)
                    decoded_str = urllib.parse.unquote(extracted_str)
                    found_url = urljoin(target_url, decoded_str)
                    logger.info(
                        f"[{app_name}] 规则1 (正则) 匹配并解码成功: {found_url}"
                    )
            except Exception as regex_err:
                logger.error(f"[{app_name}] 正则表达式错误: {regex_err}")
        if not found_url:
            soup = BeautifulSoup(html_content, "html.parser")
            if app_item.get("css_selector"):
                try:
                    tag = soup.select_one(app_item["css_selector"])
                    if tag and tag.get("href"):
                        found_url = urljoin(target_url, tag["href"])
                except Exception as css_err:
                    logger.warning(f"[{app_name}] BeautifulSoup 解析失败: {css_err}")
            if not found_url and app_item.get("link_text"):
                search_text = app_item["link_text"].lower()
                tag = soup.find(
                    "a", string=lambda text: text and search_text in text.lower()
                )
                if tag and tag.get("href"):
                    found_url = urljoin(target_url, tag["href"])
            if not found_url and app_item.get("element_id"):
                tag = soup.find("a", id=app_item["element_id"])
                if tag and tag.get("href"):
                    found_url = urljoin(target_url, tag["href"])
            if not found_url:
                keyword = app_item.get("keyword") or ".exe"
                for a in soup.find_all("a", href=True):
                    href = a["href"].lower()
                    if (
                        keyword in href
                        and "/docs/" not in href
                        and "manual" not in href
                    ):
                        found_url = urljoin(target_url, a["href"])
                        break
        if found_url:
            if not any(
                ext in found_url.lower()
                for ext in [".exe", ".zip", ".dmg", ".pkg", ".apk"]
            ):
                logger.info(f"[{app_name}] 检测到中转链接，尝试解析真实跳转地址...")
                try:
                    trace_res = requests.get(
                        found_url,
                        headers=headers,
                        stream=True,
                        allow_redirects=True,
                        timeout=10,
                    )
                    real_url = trace_res.url
                    if real_url != found_url:
                        logger.info(f"[{app_name}] 成功解析真实链接: {real_url}")
                        found_url = real_url
                except Exception as trace_err:
                    logger.warning(
                        f"[{app_name}] 解析真实链接失败，使用原中转链接: {trace_err}"
                    )
            with db_lock:
                db.update(
                    {"cached_url": found_url, "last_fetched": now},
                    Apps.name == app_item["name"],
                )
            return found_url
    except Exception as e:
        logger.exception(f"[{app_name}] 抓取异常:")
        return app_item.get("cached_url")
    return None


def download_to_local_disk(app_name, url, custom_referer=None):
    """将远程文件下载到本地硬盘（附带进度计算、防盗链穿透与 URL 自动清洗）"""
    try:
        download_progress[app_name] = {
            "status": "starting",
            "progress": 0,
            "downloaded": 0,
            "total": 0,
        }
        clean_url = html.unescape(url)
        if custom_referer:
            final_referer = custom_referer
        else:
            with db_lock:
                item = db.get(Apps.name == app_name)
            if item and item.get("url"):
                final_referer = item["url"]
            else:
                parsed_uri = urlparse(clean_url)
                final_referer = f"{parsed_uri.scheme}://{parsed_uri.netloc}/"
        logger.info(f"[{app_name}] 正在生成动态通行证... Referer: {final_referer}")
        logger.info(f"[{app_name}] 开始下载远程文件到本地...")
        logger.info(f"[{app_name}] 净化后的真实下载流地址: {clean_url}")
        local_filepath = os.path.join(DOWNLOAD_DIR, f"{app_name}.exe")
        temp_filepath = local_filepath + ".downloading"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": final_referer,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        with requests.get(
            clean_url, headers=headers, stream=True, timeout=(15, 60), verify=False
        ) as req:
            req.raise_for_status()
            total_length = req.headers.get("content-length")
            total_length = int(total_length) if total_length else 0
            total_mb = round(total_length / (1024 * 1024), 2) if total_length else 0
            downloaded_bytes = 0
            with open(temp_filepath, "wb") as f:
                for chunk in req.iter_content(chunk_size=256 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        dl_mb = downloaded_bytes / (1024 * 1024)
                        if total_length > 0:
                            prog = (downloaded_bytes / total_length) * 100
                            download_progress[app_name] = {
                                "status": "downloading",
                                "progress": round(prog, 1),
                                "downloaded": round(dl_mb, 1),
                                "total": total_mb,
                            }
                        else:
                            download_progress[app_name] = {
                                "status": "downloading",
                                "progress": -1,
                                "downloaded": round(dl_mb, 1),
                                "total": 0,
                            }
        if os.path.exists(local_filepath):
            os.remove(local_filepath)
        os.rename(temp_filepath, local_filepath)
        file_size_mb = os.path.getsize(local_filepath) / (1024 * 1024)
        db.update(
            {
                "local_path": local_filepath,
                "local_synced_at": time.time(),
                "local_size_mb": round(file_size_mb, 2),
                "local_synced_url": clean_url,
            },
            Apps.name == app_name,
        )
        download_progress[app_name] = {"status": "completed", "progress": 100}
        logger.info(f"[{app_name}] ✅ 下载完成！")
    except Exception as e:
        logger.error(f"[{app_name}] 同步失败: {e}")
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        download_progress[app_name] = {"status": "error", "message": str(e)}
