# Network Monitor — Design Specification

**Version:** 1.0.0
**Status:** Reconciled against the as-built code at first public release.

---

## 0. About this document

### 0.1 Provenance — read this first

This tool was **built before this specification existed**. The spec was written
by reading the shipped code, not the other way round, and it is published that
way deliberately: a README tells you how to use something, a spec tells you why
it is shaped the way it is.

Where a design choice was made implicitly rather than deliberately, this
document says so instead of inventing a rationale after the fact. Section 8
states plainly which behaviours have been verified by use and which have not.

---

## 1. Purpose and scope

### 1.1 What this is for

Seeing what your own machine actually sends. Browser dev-tools show you a single
browser tab; this shows everything that goes through the Windows system proxy —
background updaters, desktop apps, installers, anything that honours proxy
settings.

### 1.2 Explicit non-goals

| Not a goal | Reasoning |
|------------|-----------|
| Capturing traffic from other machines | The proxy binds to loopback only. Broadening that turns a personal inspection tool into network interception infrastructure, which is a different thing with different obligations. |
| Persistence, history, export | Captured traffic is among the most sensitive data on the machine (session cookies, bearer tokens, personal messages). Not writing it to disk means there is no file to leak, forget about, or back up by accident. |
| Modifying traffic in flight | mitmproxy already does this well. This tool observes only. |
| Cross-platform support | The proxy-toggle mechanism is Windows-registry specific (§3.4). |

---

## 2. Architecture

```
┌──────────────────────────┐
│ Browsers, desktop apps,  │
│ background services      │
└────────────┬─────────────┘
             │ Windows system proxy → 127.0.0.1:8080
             ▼
┌──────────────────────────┐
│ mitmdump                 │
│  + backend/proxy.py      │  TLS termination, metadata extraction
└────────────┬─────────────┘
             │ HTTP POST /api/log  (proxy explicitly bypassed)
             ▼
┌──────────────────────────┐
│ backend/server.py        │  FastAPI on 127.0.0.1:8000
│  in-memory body store    │
└────────────┬─────────────┘
             │ WebSocket /ws (live)   +   GET /api/body/... (on demand)
             ▼
┌──────────────────────────┐
│ frontend/                │  static single-page dashboard
└──────────────────────────┘
```

Four processes, supervised by `run.py`: the FastAPI server, `mitmdump`, the
browser, and the supervisor itself.

---

## 3. Components

### 3.1 `backend/proxy.py` — mitmproxy addon

Implements one hook, `response()`, called once per completed transaction.

**Self-exclusion.** Requests to port 8000 or to a `localhost` host return
immediately (`proxy.py:17`). Without this the addon's own log POSTs would be
captured, logged, and re-POSTed — an unbounded feedback loop.

**Text/binary split.** Content type decides handling. Text-ish types (`text`,
`json`, `xml`, `urlencoded`) are extracted as text and truncated at
`MAX_TEXT_CHARS = 100000`. Everything else is treated as binary, capped at
`MAX_BINARY_BYTES = 20 MB`, and base64-encoded.

**Rationale for the split:** text bodies are what you actually want to read, and
they are small enough to push live. Binary bodies are mostly images and fonts —
large, unreadable in a table, and rarely the reason you opened the tool. Sending
them over the same live channel would swamp it.

**Delivery.** `asyncio.create_task` + `asyncio.to_thread` so the blocking POST
never stalls mitmproxy's event loop; a stalled hook would add latency to every
request the machine makes. Failures are swallowed (`proxy.py:90`) — deliberately.
If the dashboard is closed, browsing must not break.

**Proxy bypass.** The POST is made through an empty `ProxyHandler`
(`proxy.py:87`), because the system proxy is at that moment pointed at
mitmproxy itself.

### 3.2 `backend/server.py` — FastAPI server

| Endpoint | Purpose |
|----------|---------|
| `POST /api/log` | Receives a transaction from the addon, stores any binary bodies, fans the rest out to WebSocket clients |
| `GET /api/body/{flow_id}/{direction}` | Serves one stored binary body on demand |
| `WS /ws` | Live transaction stream |
| `GET /` | Static dashboard |

**Body store.** A `dict` keyed by `(flow_id, direction)` with a parallel
`deque` for FIFO eviction, capped at `MAX_STORED_BODIES = 500` to match the
frontend's `MAX_ROWS`. The two caps are aligned on purpose: a body outliving the
row that references it is unreachable memory.

**Why bodies are pulled, not pushed.** Base64 inflates by ~33%, and a 20 MB body
would become ~27 MB on the wire for every connected client. Only bodies the user
actually clicks are ever transferred.

**Content-type sanitisation** (`server.py`): a `content_type` containing a
newline is replaced with `application/octet-stream` before being echoed into a
response header — the value is attacker-controlled, since it comes from a
response the tool was inspecting, and header injection is the obvious risk.

**Dead-client reaping.** Failed sends collect into `dead_clients` and are removed
after iteration, rather than mutating the set mid-loop.

### 3.3 `frontend/` — dashboard

Vanilla JS, no build step and no dependencies. A single `DOMContentLoaded`
handler owns a WebSocket connection, the table, filtering, pause, and the detail
modal. `MAX_ROWS = 500` bounds DOM growth.

No framework because the whole UI is one table and one modal; a build pipeline
would be more machinery than the thing it builds.

### 3.4 `run.py` — supervisor

Starts uvicorn, starts `mitmdump`, sets the proxy, opens the browser, then waits
on `KeyboardInterrupt` to reverse all of it.

**Proxy control** is via `HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings`,
followed by `InternetSetOptionW` with `INTERNET_OPTION_SETTINGS_CHANGED` and
`INTERNET_OPTION_REFRESH` so running browsers pick the change up without a
restart.

**Known weakness, stated rather than hidden:** teardown runs only on
`KeyboardInterrupt`. Closing the terminal with the X button, a crash, or a power
loss leaves `ProxyEnable=1` pointing at a dead proxy — which presents to the user
as "my internet is broken". Both the README and the tool's own console output
warn about this, and the README documents the manual fix. A `SIGBREAK`/console
control handler would close most of the gap and has not been implemented.

**Fixed sleeps** (1.5 s, 1 s) rather than readiness probes. Adequate in practice,
not robust; on a slow machine the browser can open before uvicorn is listening,
and the fix is a refresh.

---

## 4. Data model

One JSON object per transaction:

```jsonc
{
  "id": "…",  "timestamp": "YYYY-MM-DD HH:MM:SS.mmm",
  "method": "GET", "url": "…", "host": "…", "path": "…",
  "status": 200, "content_type": "…",
  "req_size": 0, "res_size": 1234,
  "req_headers": { }, "res_headers": { },
  "req_body": { "kind": "text|binary|too_large|none", … },
  "res_body": { … },
  "blobs": { "req": { "content_type": "…", "data": "<base64>" } }  // stripped at the server
}
```

`blobs` is removed by `POST /api/log` before broadcast, so it never reaches the
WebSocket. The `kind` discriminator lets the frontend render "12 MB image
(click to download)" without holding the bytes.

---

## 5. Design decisions

| Decision | Alternative | Why this one |
|----------|-------------|--------------|
| HTTP POST from addon to server | Shared memory / direct import | mitmdump owns its own process and event loop. A process boundary keeps a slow or crashed dashboard from affecting traffic. |
| In-memory only, no persistence | SQLite log | The data is high-value and high-risk. No file means no leak, and no lifecycle to manage. |
| Bodies pulled on demand | Push everything | Avoids ~33% base64 inflation on the live channel for data usually never opened. |
| Vanilla JS | React/Vue | One table and one modal. |
| Full pinned `requirements.txt` | Three loose direct deps | mitmproxy's transitive tree is large and version-sensitive; a freeze makes installs reproducible. |
| System-wide proxy | Browser-only proxy config | Captures background apps too, which is the main advantage over browser dev-tools. |

---

## 6. Security model

**Threat model:** the user owns the machine and intends to inspect their own
traffic. The adversary considered is the user forgetting they left a root CA
installed.

### 6.1 Residual risks (accepted, not fixed)

| Risk | Status |
|------|--------|
| Any local process can reach `:8000` and `:8080` | Accepted. A hostile local process already has the user's files; an auth token in a single-user local tool would be theatre. |
| mitmproxy CA private key stored unencrypted in `%USERPROFILE%\.mitmproxy` | Inherent to mitmproxy. Mitigated by documentation: the README states the consequence plainly and gives removal instructions. |
| Trust persists after the tool exits | Not auto-revoked — removing a root CA without the user asking is too surprising an action for a tool to take. Documented instead. |
| Dashboard displays secrets in plain text | Inherent to the purpose. |

---

## 7. Limitations

1. **Windows only** (§3.4).
2. **Certificate pinning defeats interception** — by design, on the app's part.
3. **Only proxy-aware traffic is captured.** Software that ignores the Windows
   proxy setting, and non-HTTP protocols, are invisible. This is a traffic
   inspector, not a packet capture.
4. **Ungraceful exit leaves the proxy set** (§3.4).
5. **Fixed startup delays** rather than readiness checks (§3.4).
6. **Bounded buffers** — 500 rows, 500 bodies, 100k chars, 20 MB.

---

## 8. Verification status

Honest accounting. "Verified" means observed working in real use; "unverified"
means believed correct from the code but not deliberately exercised.

| # | Behaviour | Status |
|---|-----------|--------|
| 1 | HTTPS traffic decrypted and displayed after CA install | **Verified** — primary use case, used repeatedly |
| 2 | Live streaming to the dashboard over WebSocket | **Verified** |
| 3 | Detail modal shows headers and text bodies | **Verified** |
| 4 | Proxy set on start, restored on Ctrl+C | **Verified** |
| 5 | Ungraceful close leaves proxy set | **Verified** — that is how the behaviour was discovered |
| 6 | Binary body download via `/api/body` | **Verified** |
| 7 | Row/body eviction at the 500 caps | **Unverified** — logic is straightforward, long sessions not deliberately soak-tested |
| 8 | 20 MB `too_large` path | **Unverified** — not deliberately exercised with an oversized body |
| 9 | Header-injection guard on `content_type` | **Unverified** — no malicious response was crafted to trigger it |
| 10 | Behaviour when the dashboard is closed but the proxy runs | **Verified** — failures are swallowed, browsing unaffected |

Item 9 is the one worth flagging: it is security-relevant and reasoned rather
than tested.
