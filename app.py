import io
import json
import logging
import os
import queue
import threading
import time
import urllib.parse
from functools import wraps
from urllib.parse import urlparse
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from config import (
    ADMIN_PASSWORD,
    SECRET_KEY,
    Apps,
    Query,
    active_downloads,
    active_downloads_lock,
    db,
    db_lock,
    download_progress,
)
from services import download_to_local_disk, get_latest_url, log_listeners, re

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
app = Flask(__name__)
app.secret_key = SECRET_KEY


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page", next=request.url))
        return f(*args, **kwargs)

    return decorated_function


def add_sys_log(app_name, level, message):
    """level: success, warning, error, info"""
    with db_lock:
        table = db.table("sys_logs")
        table.insert(
            {
                "time": time.time(),
                "app_name": app_name,
                "level": level,
                "message": message,
            }
        )
        all_logs = table.all()
        if len(all_logs) > 200:
            oldest_docs = sorted(all_logs, key=lambda x: x["time"])[:-200]
            for doc in oldest_docs:
                table.remove(doc_ids=[doc.doc_id])


@app.route("/api/logs")
@login_required
def get_sys_logs():
    with db_lock:
        logs = db.table("sys_logs").all()
    logs = sorted(logs, key=lambda x: x["time"], reverse=True)
    return jsonify(logs)


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        password = request.form.get("password")
        if password == ADMIN_PASSWORD:
            session["logged_in"] = True
            next_url = request.args.get("next") or url_for("admin_ui")
            return redirect(next_url)
        else:
            error = "管理员密码错误"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login_page"))


@app.route("/api/check_update/<name>")
@login_required
def check_update_api(name):
    with db_lock:
        item = db.get(Apps.name == name)
    if not item:
        return jsonify({"error": "not found"}), 404
    synced_url = item.get("local_synced_url") or item.get("cached_url")
    latest_url = get_latest_url(item, force_refresh=True)

    def get_clean_filename(url_str):
        if not url_str:
            return ""
        parsed_path = urllib.parse.urlparse(url_str).path
        filename = parsed_path.split("/")[-1]
        return urllib.parse.unquote(filename).lower().strip()

    def extract_core_version(filename):
        if not filename:
            return ""
        match = re.search(r"[v]?(\d+\.\d+\.\d+(?:\.\d+)?)", filename)
        if match:
            return match.group(1)
        return filename

    synced_filename = get_clean_filename(synced_url)
    latest_filename = get_clean_filename(latest_url)
    synced_core = extract_core_version(synced_filename)
    latest_core = extract_core_version(latest_filename)
    logger.info(
        f"[{name}] 🔍 更新雷达 -> 本地核心: '{synced_core}' | 远程核心: '{latest_core}' (来源: {latest_filename})"
    )
    local_path = item.get("local_path")
    missing_local = not local_path or not os.path.exists(local_path)
    has_new_link = bool(latest_url and synced_url and latest_core != synced_core)
    needs_update = missing_local or has_new_link
    if has_new_link:
        reason = f"发现新版本 ({latest_core})"
    elif missing_local:
        reason = "本地缓存文件缺失"
    else:
        reason = "已是最新版本"
    return jsonify(
        {
            "name": name,
            "needs_update": needs_update,
            "reason": reason,
            "latest_url": latest_url,
        }
    )


@app.route("/api/sync_selected", methods=["POST"])
@login_required
def sync_selected():
    names = request.json.get("names", [])
    for n in names:
        download_progress[n] = {
            "status": "starting",
            "progress": 0,
            "downloaded": 0,
            "total": 0,
        }

    def download_task(app_names):
        logger.info(f"开始批量下载任务: {app_names}")
        for n in app_names:
            with db_lock:
                item = db.get(Apps.name == n)
            if item and item.get("cached_url"):
                download_to_local_disk(n, item["cached_url"])
        logger.info("批量下载任务全部完成！")

    threading.Thread(target=download_task, args=(names,)).start()
    return jsonify(
        {"status": "ok", "message": f"已将 {len(names)} 个软件加入后台下载队列"}
    )


def auto_sync_all_apps():
    logger.info("🕒 === 开始执行定时任务：全局软件更新与同步检测 ===")
    with db_lock:
        db.table("sys_meta").upsert(
            {"id": "daily_sync", "status": "running", "time": time.time()},
            Query().id == "daily_sync",
        )
        apps = db.all()

    def get_clean_filename(url_str):
        if not url_str:
            return ""
        parsed_path = urllib.parse.urlparse(url_str).path
        filename = parsed_path.split("/")[-1]
        return urllib.parse.unquote(filename).lower().strip()

    for item in apps:
        app_name = item.get("name", "Unknown")
        synced_url = item.get("local_synced_url") or item.get("cached_url")
        try:
            logger.info(f"🔄 正在检测: {app_name} ...")
            latest_url = get_latest_url(item, force_refresh=True)
            synced_filename = get_clean_filename(synced_url)
            latest_filename = get_clean_filename(latest_url)
            local_path = item.get("local_path")
            missing_local = not local_path or not os.path.exists(local_path)
            has_new_link = bool(
                latest_url and synced_url and latest_filename != synced_filename
            )
            if has_new_link or missing_local:
                if has_new_link:
                    msg = f"发现新版本！{synced_filename} -> {latest_filename}"
                    logger.info(f"[{app_name}] 🌟 {msg}")
                    add_sys_log(app_name, "success", msg)
                if missing_local:
                    msg = "本地缓存文件缺失，已重新下载！"
                    logger.warning(f"[{app_name}] ⚠️ {msg}")
                    add_sys_log(app_name, "warning", msg)
                if latest_url:
                    download_to_local_disk(app_name, latest_url)
            else:
                logger.info(f"[{app_name}] ✅ 已是最新版本。")
                add_sys_log(app_name, "info", "已是最新版本")
        except Exception as e:
            msg = f"检测异常: {str(e)}"
            logger.error(f"[{app_name}] {msg}")
            add_sys_log(app_name, "error", msg)
        time.sleep(3)
    logger.info("🏁 === 全局软件更新检测定时任务执行完毕 ===")
    with db_lock:
        db.table("sys_meta").upsert(
            {"id": "daily_sync", "status": "success", "time": time.time()},
            Query().id == "daily_sync",
        )


scheduler = BackgroundScheduler()
scheduler.add_job(
    auto_sync_all_apps,
    trigger="cron",
    hour=3,
    minute=0,
    misfire_grace_time=300,
    coalesce=True,
    max_instances=1,
)
scheduler.start()


@app.before_request
def log_request_info():
    """拦截并打印真实的客户端请求，解决 Waitress 静默问题并穿透代理获取真实 IP"""
    if request.path.startswith("/dl/"):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            real_ip = forwarded_for.split(",")[0].strip()
        else:
            real_ip = request.headers.get("X-Real-IP", request.remote_addr)
        user_agent = request.headers.get("User-Agent", "Unknown")
        ua_short = user_agent[:60] + "..." if len(user_agent) > 60 else user_agent
        parts = request.path.split("/")
        app_name = parts[2] if len(parts) > 2 else "Unknown"
        logger.info(
            f"📥 客户端请求 | IP: {real_ip} | 目标: {app_name} | UA: {ua_short}"
        )


@app.template_filter("ctime")
def timestr(s):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(s)) if s > 0 else "未同步"


@app.route("/")
@login_required
def admin_ui():
    base_url = request.host_url
    with db_lock:
        apps = db.all()
        sys_meta = db.table("sys_meta").get(Query().id == "daily_sync") or {}
    for item in apps:
        local_path = item.get("local_path")
        if local_path and os.path.exists(local_path):
            item["file_ready"] = True
            item["real_size_mb"] = round(os.path.getsize(local_path) / (1024 * 1024), 2)
        else:
            item["file_ready"] = False
    return render_template(
        "index.html", apps=apps, base_url=base_url, sys_meta=sys_meta
    )


@app.route("/dl/<name>", methods=["GET", "HEAD"])
@app.route("/dl/<name>/<filename>", methods=["GET", "HEAD"])
def download_redirect(name, filename=None):
    with db_lock:
        item = db.get(Apps.name == name)
    if not item:
        return "Not Found", 404
    is_test = request.args.get("test") == "1"
    if is_test:
        log_capture_string = io.StringIO()
        ch = logging.StreamHandler(log_capture_string)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(ch)
        url = None
        try:
            url = get_latest_url(item, force_refresh=True)
        finally:
            logging.getLogger().removeHandler(ch)
        log_contents = log_capture_string.getvalue()
        test_html = f"""
        <!DOCTYPE html>
        <html lang="zh">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>抓取测试: {item['name']}</title>
            <style>
                body {{  font-family: system-ui, sans-serif; background: #f1f5f9; padding: 2rem; color: #1e293b; }} 
                .container {{  max-width: 900px; margin: 0 auto; background: white; padding: 2rem; border-radius: 16px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }} 
                .status-badge {{  display: inline-block; padding: 4px 12px; border-radius: 999px; font-weight: bold; font-size: 0.875rem; margin-bottom: 1rem; }} 
                .success {{  background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }} 
                .failed {{  background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }} 
                .url-box {{  background: #f8fafc; border: 1px dashed #cbd5e1; padding: 1rem; border-radius: 8px; word-break: break-all; font-family: monospace; font-size: 1.1rem; color: #0ea5e9; margin-bottom: 1.5rem; }} 
                .log-console {{  background: #1e1e1e; color: #d4d4d4; padding: 1.5rem; border-radius: 12px; overflow-x: auto; font-family: 'Consolas', monospace; font-size: 14px; white-space: pre-wrap; line-height: 1.5; }} 
            </style>
        </head>
        <body>
            <div class="container">
                <h2>抓取测试报告 - {item['name']}</h2>
                {"<div class='status-badge success'>✅ 提取成功</div>" if url else "<div class='status-badge failed'>❌ 提取失败</div>"}
                <h4>最终提取到的下载链接：</h4>
                <div class="url-box">{url if url else '未找到链接 (请查看下方日志)'}</div>
                <hr>
                <h4>📡 执行日志</h4>
                <pre class="log-console">{log_contents}</pre>
            </div>
        </body>
        </html>
        """
        return render_template_string(test_html)
    local_path = item.get("local_path")
    local_path = item.get("local_path")
    dl_name = filename if filename else f"{item['name']}.exe"
    if local_path and os.path.exists(local_path):
        logger.info(f"[{item['name']}] 命中本地硬盘缓存，下发文件 (支持断点续传)...")
        return send_file(
            local_path, conditional=True, as_attachment=True, download_name=dl_name
        )
    logger.warning(f"[{item['name']}] 无本地缓存，启动纯净流代理穿透...")
    with active_downloads_lock:
        if item["name"] not in active_downloads:
            active_downloads.add(item["name"])
            should_start = True
        else:
            should_start = False
    if should_start:

        def safe_download():
            try:
                download_to_local_disk(item["name"], url)
            finally:
                with active_downloads_lock:
                    active_downloads.discard(item["name"])

        threading.Thread(target=safe_download).start()
    try:
        proxy_headers = {
            "User-Agent": request.headers.get(
                "User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            ),
            "Referer": item["url"],
        }
        if "Range" in request.headers:
            proxy_headers["Range"] = request.headers["Range"]
        req = requests.get(url, headers=proxy_headers, stream=True, timeout=15)

        def generate():
            for chunk in req.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk

        response = Response(
            stream_with_context(generate()),
            status=req.status_code,
            content_type=req.headers.get("content-type", "application/octet-stream"),
        )
        if "content-length" in req.headers:
            response.headers["Content-Length"] = req.headers["content-length"]
        if "content-range" in req.headers:
            response.headers["Content-Range"] = req.headers["content-range"]
        response.headers["Content-Disposition"] = f'attachment; filename="{dl_name}"'
        return response
    except Exception as e:
        logger.error(f"[{item['name']}] 流式转发代理失败: {e}")
        return f"Streaming Error: {str(e)}", 500


@app.route("/api/save", methods=["POST"])
@login_required
def save_app():
    data = request.form.to_dict()
    data["needs_browser"] = "needs_browser" in request.form
    with db_lock:
        old_item = db.get(Apps.name == data["name"])
        if old_item:
            data["cached_url"] = old_item.get("cached_url")
            data["last_fetched"] = old_item.get("last_fetched")
        db.upsert(data, Apps.name == data["name"])
    return redirect("/")


@app.route("/api/delete/<name>")
@login_required
def delete_app(name):
    with db_lock:
        db.remove(Apps.name == name)
    return jsonify({"status": "ok"})


@app.route("/api/sync_all", methods=["POST"])
@login_required
def manual_sync_all():
    threading.Thread(target=auto_sync_all_apps).start()
    return jsonify({"status": "ok", "message": "后台同步指令已下发，正在静默下载"})


@app.route("/api/quick_sync/<name>", methods=["POST"])
def quick_sync(name):
    with db_lock:
        item = db.get(Apps.name == name)
    if not item:
        return jsonify({"status": "error", "message": "未找到软件配置"}), 404

    def single_sync_task():
        try:
            logger.info(f"⚡ 启动极速单体同步任务: [{name}]")
            download_progress[name] = {
                "status": "starting",
                "progress": 0,
                "downloaded": 0,
                "total": 0,
            }
            latest_url = get_latest_url(item, force_refresh=True)
            if not latest_url:
                logger.error(f"[{name}] 极速同步失败：未能抓取到有效链接。")
                download_progress[name] = {
                    "status": "error",
                    "message": "抓取链接失败，请检查配置或日志。",
                }
                return
            with active_downloads_lock:
                if name not in active_downloads:
                    active_downloads.add(name)
                    should_start = True
                else:
                    should_start = False
            if should_start:
                try:
                    download_to_local_disk(name, latest_url)
                finally:
                    with active_downloads_lock:
                        active_downloads.discard(name)
            else:
                logger.warning(f"[{name}] 任务已在下载中，跳过重复触发。")
        except Exception as e:
            logger.error(f"[{name}] 极速同步发生严重异常: {e}")
            download_progress[name] = {"status": "error", "message": str(e)}

    threading.Thread(target=single_sync_task).start()
    return jsonify({"status": "ok"})


@app.route("/api/sync_progress")
@login_required
def sync_progress_api():
    """供前端实时拉取所有正在下载的进度"""
    return jsonify(download_progress)


@app.route("/api/stream-logs")
def stream_logs():
    def generate():
        q = queue.Queue(maxsize=100)
        log_listeners.append(q)
        try:
            while True:
                try:
                    msg = q.get(timeout=3)
                    yield f"data: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            if q in log_listeners:
                log_listeners.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    from waitress import serve

    logger.info("🚀 启动 Waitress 生产级服务器 (支持多线程并发)")
    serve(app, host="0.0.0.0", port=5000, threads=16)
