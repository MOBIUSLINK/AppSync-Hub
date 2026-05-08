// 初始化模态框
        const appModal = new bootstrap.Modal(document.getElementById('appModal'));
        const regexModal = new bootstrap.Modal(document.getElementById('regexModal'));
        const updateModal = new bootstrap.Modal(document.getElementById('updateModal'));
        
        // 全局 Toast
        const Toast = Swal.mixin({
            toast: true,
            position: 'top-end',
            showConfirmButton: false,
            timer: 2000,
            timerProgressBar: true
        });

        // ================= 软件配置逻辑 =================
        function openAddModal() {
            document.getElementById('modalTitle').innerHTML = '<i class="fas fa-plus-circle text-primary me-2"></i>新增软件配置';
            document.getElementById('form_name').readOnly = false;
            document.getElementById('form_name').classList.remove('bg-light');
            document.getElementById('form_name').value = "";
            document.getElementById('form_url').value = "";
            document.getElementById('form_browser').checked = false;
            document.getElementById('form_regex').value = "";
            document.getElementById('form_css').value = "";
            document.getElementById('form_text').value = "";
            document.getElementById('form_id').value = "";
            document.getElementById('form_keyword').value = ".exe";
            document.getElementById('form_direct').value = "";
            appModal.show();
        }

        function openEditModal(item) {
            document.getElementById('modalTitle').innerHTML = '<i class="fas fa-edit text-primary me-2"></i>编辑配置';
            document.getElementById('form_name').value = item.name;
            document.getElementById('form_name').readOnly = true; 
            document.getElementById('form_name').classList.add('bg-light');
            document.getElementById('form_url').value = item.url || "";
            document.getElementById('form_browser').checked = item.needs_browser === true || item.needs_browser === "true";
            document.getElementById('form_regex').value = item.regex_pattern || "";
            document.getElementById('form_css').value = item.css_selector || "";
            document.getElementById('form_text').value = item.link_text || "";
            document.getElementById('form_id').value = item.element_id || "";
            document.getElementById('form_keyword').value = item.keyword || ".exe";
            document.getElementById('form_direct').value = item.direct_link || "";
            appModal.show();
        }

        function copyText(id) {
            const inputElement = document.getElementById(id);
            inputElement.select();
            navigator.clipboard.writeText(inputElement.value).then(() => {
                Toast.fire({ icon: 'success', title: '链接已复制！' });
            }).catch(err => {
                Toast.fire({ icon: 'error', title: '复制失败' });
            });
        }

        function deleteApp(name) {
            Swal.fire({
                title: '确定要删除吗？',
                text: `即将从仓库中移除 [${name}] 的镜像配置及本地文件`,
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#ef4444',
                cancelButtonColor: '#94a3b8',
                confirmButtonText: '确定删除',
                cancelButtonText: '取消'
            }).then((result) => {
                if (result.isConfirmed) {
                    fetch('/api/delete/'+name)
                        .then(() => {
                            Swal.fire({ icon: 'success', title: '已删除', showConfirmButton: false, timer: 1000 })
                            .then(() => location.reload());
                        });
                }
            });
        }

        function filterApps() {
            const input = document.getElementById('searchInput').value.toLowerCase();
            const cards = document.querySelectorAll('.app-item');
            cards.forEach(card => {
                const name = card.getAttribute('data-name');
                if (name.includes(input)) {
                    card.style.display = '';
                } else {
                    card.style.display = 'none';
                }
            });
        }
        
        // 获取页面上所有已配置的软件名称
        function getAllAppNames() {
            return Array.from(document.querySelectorAll('.app-item')).map(el => el.getAttribute('data-name'));
        }

        // 打开更新管理器并启动逐个扫描
        async function openUpdateManager() {
            const allNames = getAllAppNames();
            if (allNames.length === 0) {
                Toast.fire({ icon: 'info', title: '仓库为空，无可检查项' });
                return;
            }

            document.getElementById('scanProgressArea').style.display = 'block';
            document.getElementById('updateListArea').style.display = 'none';
            document.getElementById('updateFooter').style.display = 'none';
            document.getElementById('btnCloseUpdate').style.display = 'none'; 
            document.getElementById('scanProgressBar').style.width = '0%';
            
            updateModal.show();

            let scanned = 0;
            const total = allNames.length;
            const updateCandidates = [];

            for (let name of allNames) {
                document.getElementById('scanStatusText').innerText = `正在探测: ${name}`;
                document.getElementById('scanSubText').innerText = `进度: ${scanned} / ${total}`;
                
                try {
                    const res = await fetch(`/api/check_update/${name}`);
                    const data = await res.json();
                    if (data.needs_update) {
                        updateCandidates.push(data);
                    }
                } catch (e) {
                    console.error('探测失败:', name);
                }
                
                scanned++;
                document.getElementById('scanProgressBar').style.width = `${(scanned / total) * 100}%`;
            }

            renderUpdateList(updateCandidates);
        }

        // 渲染勾选列表
        function renderUpdateList(candidates) {
            document.getElementById('scanProgressArea').style.display = 'none';
            document.getElementById('updateListArea').style.display = 'block';
            document.getElementById('updateFooter').style.display = 'flex';
            document.getElementById('btnCloseUpdate').style.display = 'block';
            
            const tbody = document.getElementById('updateTableBody');
            document.getElementById('updateCountBadge').innerText = `${candidates.length} 项可用`;
            
            if (candidates.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="text-center text-success py-5"><i class="fas fa-check-circle fs-1 mb-2 d-block"></i>太棒了！所有软件均已缓存且是最新版本。</td></tr>';
                document.getElementById('btnStartSync').disabled = true;
                document.getElementById('checkAllUpdates').disabled = true;
            } else {
                let html = '';
                candidates.forEach(item => {
                    const badgeClass = item.reason.includes('缺失') ? 'bg-danger' : 'bg-warning text-dark';
                    html += `
                        <tr>
                            <td style="text-align: center;">
                                <input type="checkbox" class="form-check-input update-checkbox border-secondary" value="${item.name}" checked onchange="updateSyncBtnState()">
                            </td>
                            <td class="fw-bold text-primary"><i class="fas fa-cube me-2 text-muted"></i>${item.name}</td>
                            <td><span class="badge ${badgeClass}">${item.reason}</span></td>
                        </tr>
                    `;
                });
                tbody.innerHTML = html;
                document.getElementById('btnStartSync').disabled = false;
                document.getElementById('checkAllUpdates').disabled = false;
            }
        }

        // 全选/反选交互
        function toggleAllUpdates(source) {
            const checkboxes = document.querySelectorAll('.update-checkbox');
            checkboxes.forEach(cb => cb.checked = source.checked);
            updateSyncBtnState();
        }

        // 监听勾选状态，动态禁用下载按钮
        function updateSyncBtnState() {
            const checkedCount = document.querySelectorAll('.update-checkbox:checked').length;
            const btn = document.getElementById('btnStartSync');
            const checkAll = document.getElementById('checkAllUpdates');
            const totalCount = document.querySelectorAll('.update-checkbox').length;
            
            btn.disabled = checkedCount === 0;
            btn.innerHTML = `<i class="fas fa-download me-1"></i> 同步选中项 (${checkedCount})`;
            checkAll.checked = checkedCount === totalCount;
        }

        // 提交选中的软件进行后台下载
        function startSelectedSync() {
            const selectedNames = Array.from(document.querySelectorAll('.update-checkbox:checked')).map(cb => cb.value);
            
            const btn = document.getElementById('btnStartSync');
            btn.innerHTML = `<i class="fas fa-spinner fa-spin me-1"></i> 正在发送指令...`;
            btn.disabled = true;

            fetch('/api/sync_selected', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ names: selectedNames })
            })
            .then(res => res.json())
            .then(data => {
                updateModal.hide();
                Toast.fire({ icon: 'success', title: '后台下载已启动！' });
                startProgressPolling();
            })
            .catch(err => {
                Toast.fire({ icon: 'error', title: '任务提交失败' });
                btn.disabled = false;
            });
        }

        // ================= 正则沙盒逻辑 =================
        function openRegexModal() {
            regexModal.show();
            generateRegex(); 
        }

        function escapeHtml(unsafe) {
            return (unsafe || "").toString()
                .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }

        document.getElementById('sandbox_strategy').addEventListener('change', function(e) {
            const val = e.target.value;
            document.getElementById('param_text_area').style.display = val === 'text' ? 'block' : 'none';
            document.getElementById('param_domain_area').style.display = val === 'domain' ? 'block' : 'none';
            document.getElementById('param_ext_area').style.display = (val === 'domain' || val === 'ext') ? 'block' : 'none';
            generateRegex();
        });

        function generateRegex() {
            const strategy = document.getElementById('sandbox_strategy').value;
            let pattern = "";
            
            if (strategy === 'ext') {
                const ext = document.getElementById('sandbox_ext').value || '.exe';
                const safeExt = ext.replace(/\./g, '\\.');
                pattern = `href="(https?://[^"]+${safeExt})"`;
            } else if (strategy === 'domain') {
                const domain = document.getElementById('sandbox_domain').value || 'domain.com';
                const safeDomain = domain.replace(/\./g, '\\.');
                const ext = document.getElementById('sandbox_ext').value || '.exe';
                const safeExt = ext.replace(/\./g, '\\.');
                pattern = `href="(https?://${safeDomain}/[^"]+${safeExt}[^"]*)"`;
            } else if (strategy === 'text') {
                const text = document.getElementById('sandbox_text').value || 'Windows';
                pattern = `href="([^"]+)"[^>]*>.*?${text}</a>`;
            }
            
            document.getElementById('sandbox_pattern').value = pattern;
            evaluateRegex();
        }

        function evaluateRegex() {
            const source = document.getElementById('sandbox_source').value;
            const patternStr = document.getElementById('sandbox_pattern').value;
            const groupMatchEl = document.getElementById('sandbox_group_match');

            if (!patternStr || !source) {
                groupMatchEl.innerHTML = '<span class="text-muted fs-6"><i class="fas fa-keyboard me-2"></i>等待源码输入...</span>';
                return;
            }

            try {
                const regex = new RegExp(patternStr);
                const match = regex.exec(source);

                if (match && match.length > 1 && match[1] !== undefined) {
                    groupMatchEl.innerHTML = escapeHtml(match[1]);
                    groupMatchEl.className = "font-monospace fw-bold text-break text-success fs-5 w-100";
                } else {
                    groupMatchEl.innerHTML = '<span class="text-danger fs-6"><i class="fas fa-exclamation-triangle me-2"></i>未匹配到有效链接</span>';
                }
            } catch (e) {
                groupMatchEl.innerHTML = `<span class="text-danger fs-6"><i class="fas fa-times-circle me-2"></i>正则语法错误</span>`;
            }
        }

        function copySandboxRegex() {
            const patternInput = document.getElementById('sandbox_pattern');
            patternInput.select();
            navigator.clipboard.writeText(patternInput.value).then(() => {
                Toast.fire({ icon: 'success', title: '正则表达式已复制！' });
            });
        }

        ['sandbox_source', 'sandbox_text', 'sandbox_domain', 'sandbox_ext'].forEach(id => {
            document.getElementById(id).addEventListener('input', generateRegex);
        });

// ================= 下载进度监控引擎 =================
        let pollingInterval = null;
        let recentlyDownloadedApps = new Set(); // 👑 核心追踪器：记住这次更新了谁

        function startProgressPolling() {
            if (pollingInterval) return; 
            recentlyDownloadedApps.clear(); // 每次启动轮询前清空记忆
            
            pollingInterval = setInterval(async () => {
                try {
                    const res = await fetch('/api/sync_progress');
                    const data = await res.json();
                    
                    let activeDownloads = 0;
                    let hasError = false; 
                    
                    for (const [appName, info] of Object.entries(data)) {
                        const statusContainer = document.getElementById(`status_${appName}`);
                        const progressBg = document.getElementById(`progress_bg_${appName}`);
                        
                        if (!statusContainer || !progressBg) continue;

                        if (info.status === 'downloading' || info.status === 'starting') {
                            activeDownloads++;
                            recentlyDownloadedApps.add(appName); // 👑 记住这个正在干活的软件
                            
                            if (info.progress >= 0) {
                                statusContainer.innerHTML = `<span class="status-pill text-primary fw-bold" style="background: transparent;"><i class="fas fa-spinner fa-spin me-1"></i> 下载中 ${info.progress}% (${info.downloaded}M / ${info.total}M)</span>`;
                                progressBg.style.width = `${info.progress}%`;
                            } else {
                                statusContainer.innerHTML = `<span class="status-pill text-primary fw-bold" style="background: transparent;"><i class="fas fa-spinner fa-spin me-1"></i> 正在拉取 ${info.downloaded} MB</span>`;
                                progressBg.style.width = '100%';
                                progressBg.style.background = 'repeating-linear-gradient(45deg, #dbeafe, #dbeafe 10px, #eff6ff 10px, #eff6ff 20px)';
                            }
                        } 
                        else if (info.status === 'completed') {
                            statusContainer.innerHTML = `<span class="status-pill status-ready"><i class="fas fa-check-circle"></i> 最新就绪</span>`;
                            progressBg.style.width = '0%';
                        } 
                        else if (info.status === 'error') {
                            hasError = true;
                            statusContainer.innerHTML = `<span class="status-pill bg-danger bg-opacity-10 text-danger" title="${info.message}"><i class="fas fa-exclamation-triangle"></i> 下载失败</span>`;
                            progressBg.style.width = '0%';
                        }
                    }

                    // 👑 终极闭环：任务全部静止时的处理
                    if (activeDownloads === 0) {
                        clearInterval(pollingInterval);
                        pollingInterval = null;
                        
                        // 只要有软件成功下载过
                        if (recentlyDownloadedApps.size > 0) {
                            setTimeout(() => {
                                Swal.fire({
                                    title: hasError ? '部分同步完成' : '🎉 批量同步圆满完成',
                                    text: '本地缓存已达最新状态！',
                                    icon: hasError ? 'warning' : 'success',
                                    confirmButtonText: '我知道了',
                                    confirmButtonColor: '#10b981'
                                }).then(() => {
                                    // 👑 DOM 魔法：不再暴力重载页面！
                                    // 精准打击：把刚才更新过的软件时间，瞬间变成高亮的“刚刚”！
                                    recentlyDownloadedApps.forEach(appName => {
                                        const timeSpan = document.getElementById(`time_fetched_${appName}`);
                                        if (timeSpan) {
                                            timeSpan.innerHTML = `<span class="text-success fw-bold"><i class="fas fa-bolt me-1"></i>刚刚更新</span>`;
                                            // 加上一点动态闪烁动画，让用户明确感觉到它变了
                                            timeSpan.classList.add('flash-animation'); 
                                        }
                                    });
                                });
                            }, 500);
                        }
                    }
                    
                } catch (e) {
                    console.error('获取进度失败', e);
                }
            }, 800);
        }

        // 页面加载完毕自动探测是否有未完成的任务
        document.addEventListener('DOMContentLoaded', startProgressPolling);

        // 初始化 Bootstrap Offcanvas 组件
const logsOffcanvas = new bootstrap.Offcanvas(document.getElementById('logsOffcanvas'));

function openLogsPanel() {
    logsOffcanvas.show();
    fetchLogs();
}

function fetchLogs() {
    const container = document.getElementById('logsContainer');
    container.innerHTML = '<li class="list-group-item text-center text-muted py-4"><i class="fas fa-spinner fa-spin me-2"></i>正在拉取日志...</li>';

    fetch('/api/logs')
        .then(response => response.json())
        .then(data => {
            if (data.length === 0) {
                container.innerHTML = '<li class="list-group-item text-center text-muted py-4">暂无系统日志</li>';
                return;
            }

            container.innerHTML = '';
            data.forEach(log => {
                // 格式化时间戳
                let date = new Date(log.time * 1000);
                let timeStr = date.toLocaleString('zh-CN', {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit', second:'2-digit'});
                
                // 根据日志级别设定颜色和图标
                let icon = '';
                let colorClass = '';
                if (log.level === 'success') {
                    icon = '<i class="fas fa-check-circle text-success"></i>';
                    colorClass = 'bg-success bg-opacity-10 border-start border-success border-4';
                } else if (log.level === 'error') {
                    icon = '<i class="fas fa-times-circle text-danger"></i>';
                    colorClass = 'bg-danger bg-opacity-10 border-start border-danger border-4';
                } else if (log.level === 'warning') {
                    icon = '<i class="fas fa-exclamation-triangle text-warning"></i>';
                    colorClass = 'bg-warning bg-opacity-10 border-start border-warning border-4';
                } else {
                    icon = '<i class="fas fa-info-circle text-secondary"></i>';
                    colorClass = '';
                }

                let li = document.createElement('li');
                li.className = `list-group-item py-3 ${colorClass}`;
                li.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <strong class="text-dark">${icon} ${log.app_name}</strong>
                        <small class="text-muted" style="font-size: 0.75rem;">${timeStr}</small>
                    </div>
                    <div class="text-muted small ms-3" style="word-break: break-all;">
                        ${log.message}
                    </div>
                `;
                container.appendChild(li);
            });
        })
        .catch(err => {
            container.innerHTML = '<li class="list-group-item text-center text-danger py-4">拉取日志失败</li>';
        });
}

let logEventSource = null;

function openLiveTerminal() {
    // 1. 显示底部终端窗口（用 flex 布局保证顶栏和输出区排版）
    document.getElementById('floatingTerminal').style.display = 'flex';

    // 2. 如果还没有连接，则开启 SSE 连接
    if (!logEventSource) {
        logEventSource = new EventSource('/api/stream-logs');
        const terminal = document.getElementById('terminalOutput');
        
        logEventSource.onmessage = function(event) {
            const msg = JSON.parse(event.data);

            // 高亮引擎
            let colorClass = "text-light"; 
            if (msg.includes("[ERROR]")) colorClass = "text-danger fw-bold";
            else if (msg.includes("[WARNING]")) colorClass = "text-warning";
            else if (msg.includes("[DEBUG]")) colorClass = "text-secondary";
            else if (msg.includes("[INFO]")) colorClass = "text-info";
            if (msg.includes("🎉") || msg.includes("🟢") || msg.includes("✅")) colorClass = "text-success fw-bold";

            const line = document.createElement('div');
            line.className = colorClass;
            line.innerText = msg;
            terminal.appendChild(line);

            // 自动滚屏到底部
            terminal.scrollTop = terminal.scrollHeight;

            // 内存保护：保留最新 1000 行
            if (terminal.childElementCount > 1000) {
                terminal.removeChild(terminal.children[1]); 
            }
        };
        
        logEventSource.onerror = function() {
            const terminal = document.getElementById('terminalOutput');
            terminal.innerHTML += '<div class="text-danger fw-bold">> Connection lost. Reconnecting...</div>';
            terminal.scrollTop = terminal.scrollHeight;
        };
    }
}

function closeLiveTerminal() {
    // 隐藏窗口
    document.getElementById('floatingTerminal').style.display = 'none';
    
    // 断开连接释放服务器资源
    if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
        const terminal = document.getElementById('terminalOutput');
        terminal.innerHTML += '<div class="text-secondary">> Connection closed.</div>';
    }
}

function clearTerminal() {
    const terminal = document.getElementById('terminalOutput');
    terminal.innerHTML = '<div class="text-success">> Terminal cleared. Waiting for tasks...</div>';
}

// ================= 单体极速同步逻辑 =================
        function quickSync(appName) {
            Swal.fire({
                title: `准备极速同步 [${appName}]`,
                text: "将跳过全局大盘扫描，直接抓取并下载该软件的最新版本。",
                icon: 'info',
                showCancelButton: true,
                confirmButtonColor: '#10b981', // 极客绿
                cancelButtonColor: '#6c757d',
                confirmButtonText: '<i class="fas fa-bolt"></i> 立即拉取',
                cancelButtonText: '取消'
            }).then((result) => {
                if (result.isConfirmed) {
                    
                    // 让前端状态先变成 loading 态，反馈更灵敏
                    const statusContainer = document.getElementById(`status_${appName}`);
                    if (statusContainer) {
                        statusContainer.innerHTML = `<span class="status-pill text-primary fw-bold" style="background: transparent;"><i class="fas fa-spinner fa-spin me-1"></i> 正在嗅探直链...</span>`;
                    }

                    // 呼叫后端专属 API
                    fetch(`/api/quick_sync/${appName}`, { 
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })
                    .then(res => res.json())
                    .then(data => {
                        if(data.status === 'ok') {
                            Toast.fire({ icon: 'success', title: '任务已发射，开始抓取与下载！' });
                            // 👑 王炸：唤醒现成的进度条轮询引擎！
                            startProgressPolling(); 
                        } else {
                            Swal.fire('发射失败', data.message, 'error');
                        }
                    })
                    .catch(err => {
                        Swal.fire('网络错误', '无法连接到后台大盘', 'error');
                    });
                }
            });
        }