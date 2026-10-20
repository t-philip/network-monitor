document.addEventListener('DOMContentLoaded', () => {
    const tableBody = document.getElementById('trafficBody');
    const totalTrafficEl = document.getElementById('totalTraffic');
    const clearBtn = document.getElementById('clearBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const filterInput = document.getElementById('filterInput');
    
    let totalBytes = 0;
    const MAX_ROWS = 500;
    const trafficData = {};
    
    let isPaused = false;
    let filterText = '';

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    let ws;
    
    function connect() {
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log("Connected to backend");
            if (!isPaused) {
                const orb = document.querySelector('.glow-orb');
                orb.style.background = 'var(--get-color)';
                orb.style.boxShadow = '0 0 12px var(--get-color)';
            }
        };
        
        ws.onclose = () => {
            console.log("Disconnected. Reconnecting...");
            const orb = document.querySelector('.glow-orb');
            orb.style.background = 'var(--status-error)';
            orb.style.boxShadow = '0 0 12px var(--status-error)';
            setTimeout(connect, 3000);
        };
        
        ws.onmessage = (event) => {
            if (isPaused) return; // Drop everything when paused
            
            try {
                const data = JSON.parse(event.data);
                addRow(data);
                updateStats(data.req_size + data.res_size);
            } catch (e) {
                console.error("Error parsing message", e);
            }
        };
    }
    
    connect();

    // Pause functionality
    pauseBtn.addEventListener('click', () => {
        isPaused = !isPaused;
        const orb = document.querySelector('.glow-orb');
        if (isPaused) {
            pauseBtn.textContent = 'Resume';
            pauseBtn.classList.add('paused');
            orb.classList.add('paused');
        } else {
            pauseBtn.textContent = 'Pause';
            pauseBtn.classList.remove('paused');
            orb.classList.remove('paused');
        }
    });

    // Filter functionality
    filterInput.addEventListener('input', (e) => {
        filterText = e.target.value.toLowerCase();
        applyFilter();
    });

    function applyFilter() {
        const rows = document.querySelectorAll('#trafficBody tr');
        rows.forEach(row => {
            const data = trafficData[row.dataset.id];
            if (data && matchesFilter(data)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }

    function matchesFilter(data) {
        if (!filterText) return true;
        const searchable = `${data.method} ${data.host} ${data.path} ${data.status}`.toLowerCase();
        return searchable.includes(filterText);
    }

    clearBtn.addEventListener('click', () => {
        tableBody.innerHTML = '';
        totalBytes = 0;
        updateStats(0);
        for (let prop in trafficData) { if (trafficData.hasOwnProperty(prop)) { delete trafficData[prop]; } }
    });

    function formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function updateStats(newBytes) {
        if (newBytes > 0) {
            totalBytes += newBytes;
        }
        totalTrafficEl.textContent = formatBytes(totalBytes);
    }

    function getStatusClass(status) {
        if (status >= 200 && status < 300) return 'status-200';
        if (status >= 300 && status < 400) return 'status-info';
        if (status >= 400 && status < 500) return 'status-warn';
        if (status >= 500) return 'status-error';
        return 'status-info';
    }

    // At-a-glance indicator of what the response body actually is, so you
    // don't have to open every row to tell text apart from binary.
    function getBodyIndicator(body) {
        if (!body || body.kind === 'none') return { icon: '—', label: 'None', cls: 'body-none' };
        if (body.kind === 'text') return { icon: '📄', label: 'Text', cls: 'body-text' };
        if (body.kind === 'too_large') return { icon: '⚠️', label: 'Too Large', cls: 'body-warn' };
        if (body.kind === 'binary') {
            const isImage = body.content_type && body.content_type.startsWith('image/');
            return isImage
                ? { icon: '🖼️', label: 'Binary', cls: 'body-binary' }
                : { icon: '📦', label: 'Binary', cls: 'body-binary' };
        }
        return { icon: '—', label: 'None', cls: 'body-none' };
    }

    function addRow(data) {
        trafficData[data.id] = data;

        const tr = document.createElement('tr');
        tr.className = 'row-enter-active';
        tr.dataset.id = data.id;
        
        // Setup initial visibility based on filter
        if (!matchesFilter(data)) {
            tr.style.display = 'none';
        }
        
        tr.onclick = () => openModal(data.id);
        
        const methodClass = `method-${(data.method || 'get').toLowerCase()}`;
        const path = data.path || '/';
        const host = data.host || '-';
        const type = data.content_type?.split(';')[0] || '-';
        const status = data.status || '-';
        const bodyInfo = getBodyIndicator(data.res_body);

        tr.innerHTML = `
            <td class="col-time">${data.timestamp || '-'}</td>
            <td class="col-method ${methodClass}">${data.method || 'GET'}</td>
            <td class="col-status">
                <span class="status-badge ${getStatusClass(status)}">${status}</span>
            </td>
            <td class="col-bodykind" title="${bodyInfo.label}"><span class="body-badge ${bodyInfo.cls}">${bodyInfo.icon} ${bodyInfo.label}</span></td>
            <td class="col-size">${formatBytes(data.req_size + data.res_size)}</td>
            <td class="col-host">${host}</td>
            <td class="col-path" title="${path}">${path}</td>
            <td class="col-type" title="${type}">${type}</td>
        `;

        if (tableBody.firstChild) {
            tableBody.insertBefore(tr, tableBody.firstChild);
        } else {
            tableBody.appendChild(tr);
        }

        if (tableBody.children.length > MAX_ROWS) {
            const lastChild = tableBody.lastChild;
            delete trafficData[lastChild.dataset.id];
            tableBody.removeChild(lastChild);
        }
    }

    // Modal Logic
    const modal = document.getElementById('detailsModal');
    const closeModal = document.getElementById('closeModal');
    
    closeModal.onclick = () => modal.classList.add('hidden');
    
    modal.onclick = (e) => {
        if (e.target === modal) modal.classList.add('hidden');
    };
    
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.onclick = (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
            e.target.classList.add('active');
            document.getElementById(e.target.dataset.target).classList.remove('hidden');
        };
    });

    function formatText(text) {
        if (!text || text === 'None' || text === 'null') return 'No Content';
        try {
            const parsed = JSON.parse(text);
            return JSON.stringify(parsed, null, 2);
        } catch(e) {
            return text;
        }
    }

    // Binary bodies are never fetched automatically — only type/size is shown
    // until the user explicitly clicks Preview or Download.
    function renderBody(el, body, flowId, direction) {
        el.innerHTML = '';

        if (!body || body.kind === 'none') {
            el.textContent = 'No Content';
            return;
        }

        if (body.kind === 'text') {
            el.textContent = formatText(body.text);
            return;
        }

        if (body.kind === 'too_large') {
            el.textContent = `Binary data too large to capture (${formatBytes(body.size)}, ${body.content_type}) — not stored.`;
            return;
        }

        if (body.kind === 'binary') {
            const url = `/api/body/${encodeURIComponent(flowId)}/${direction}`;

            const info = document.createElement('div');
            info.textContent = `${body.content_type} — ${formatBytes(body.size)}`;
            info.style.marginBottom = '0.75rem';
            el.appendChild(info);

            const actions = document.createElement('div');
            actions.style.display = 'flex';
            actions.style.gap = '0.75rem';
            el.appendChild(actions);

            if (body.content_type && body.content_type.startsWith('image/')) {
                const previewBtn = document.createElement('button');
                previewBtn.className = 'btn';
                previewBtn.textContent = 'Preview';
                previewBtn.onclick = () => {
                    const img = document.createElement('img');
                    img.src = url;
                    img.style.maxWidth = '100%';
                    img.style.borderRadius = '8px';
                    img.style.display = 'block';
                    img.style.marginTop = '0.75rem';
                    el.appendChild(img);
                    previewBtn.remove();
                };
                actions.appendChild(previewBtn);
            }

            const downloadLink = document.createElement('a');
            downloadLink.href = url;
            downloadLink.className = 'btn';
            downloadLink.textContent = 'Download';
            actions.appendChild(downloadLink);
            return;
        }
    }

    function openModal(id) {
        const data = trafficData[id];
        if (!data) return;

        document.getElementById('modalTitle').textContent = `${data.method} ${data.host}${data.path}`;

        document.getElementById('reqHeaders').textContent = JSON.stringify(data.req_headers || {}, null, 2);
        document.getElementById('resHeaders').textContent = JSON.stringify(data.res_headers || {}, null, 2);

        renderBody(document.getElementById('reqBody'), data.req_body, data.id, 'req');
        renderBody(document.getElementById('resBody'), data.res_body, data.id, 'res');

        modal.classList.remove('hidden');
    }
});
