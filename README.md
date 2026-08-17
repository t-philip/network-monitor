# Network Monitor

A local HTTP/HTTPS traffic inspector for Windows. It intercepts the traffic
leaving your own machine and shows it in a live browser dashboard — full URLs,
status codes, headers, and request/response bodies, including the contents of
HTTPS connections.

It is a small, readable tool built around [mitmproxy](https://mitmproxy.org/):
a ~100-line proxy addon, a ~100-line FastAPI server, and a single-page
dashboard. If you want to see exactly what an app on your machine is sending,
this shows you.

---

## Read this before installing

**This tool decrypts your own HTTPS traffic.** It belongs to the same category
as [mitmproxy](https://mitmproxy.org/), [Charles](https://www.charlesproxy.com/)
and [Fiddler](https://www.telerik.com/fiddler) — established, legitimate tools —
but the way it works has real consequences you should understand first.

**Use it only on a machine you own, to inspect traffic you are entitled to
see.** Intercepting other people's traffic is a different activity with
different legal consequences, and this tool is not built for it: it proxies the
local machine only.

### Installing the certificate is a genuine security decision

To read HTTPS, the proxy presents its own certificate for every site you visit.
For your browser to accept that, you install mitmproxy's root CA into Windows'
**Trusted Root Certification Authorities** store.

Once you do, your machine will trust **any certificate signed by that CA, for
any domain**. The CA's private key sits unencrypted in `%USERPROFILE%\.mitmproxy`.
So:

- Anyone who obtains that key file can impersonate any website to your machine —
  your bank, your email, anything — and your browser will show no warning.
- The trust stays in place after you close the tool. It does not expire when
  monitoring stops.

This is not a flaw in this tool; it is inherent to how HTTPS interception works
and applies equally to every tool in this category. It is simply worth making an
informed decision rather than clicking through a wizard.

**Remove the certificate when you are done monitoring** — see
[Removing the certificate](#removing-the-certificate) below. Treat leaving it
installed as a deliberate choice, not a default.

### What this tool does *not* do

- **Nothing is written to disk.** Captured traffic lives in memory only: the
  most recent 500 requests, and at most 500 stored binary bodies. Closing the
  tool discards everything. There is no log file, no database, no export.
- **Nothing leaves your machine.** The dashboard is served on `127.0.0.1:8000`
  and the proxy listens on `127.0.0.1:8080`. There is no telemetry and no
  outbound connection other than the traffic you were making anyway.

---

## Requirements

- Windows (uses the Windows registry to set the system proxy)
- Python 3.10 or newer

The three direct dependencies are `mitmproxy`, `fastapi` and `uvicorn`.
`backend/requirements.txt` is a full pinned freeze of a known-good environment,
so installs are reproducible.

---

## First-time setup

1. Run `setup.bat`. It creates a virtual environment and installs the
   dependencies. (If Windows offers to install Python from the Microsoft Store,
   accept.)
2. Wait for `INSTALLATION COMPLETE`.

## Running

1. Run `start.bat`.
2. A terminal window opens, configures the Windows system proxy, and launches
   the dashboard at <http://localhost:8000>.
3. **Leave that terminal window open** while monitoring.

Click any row to open headers and body for that request. **Pause** freezes the
live stream so you can read something without it scrolling away; **Clear
History** empties the table.

## Trusting the certificate

The first time you run the tool, sites will fail with
`net::ERR_CERT_AUTHORITY_INVALID`. That means interception is working — your
browser is correctly refusing a certificate it does not trust.

Re-read [the security note above](#installing-the-certificate-is-a-genuine-security-decision),
then:

1. Open File Explorer and go to `%USERPROFILE%\.mitmproxy`
2. Double-click `mitmproxy-ca-cert.p12`
3. Certificate Import Wizard → **Current User** → Next
4. Next on the *File to Import* screen
5. Leave the password **blank** → Next
6. Choose **Place all certificates in the following store**
7. **Browse…** → **Trusted Root Certification Authorities** → OK → Next → Finish
8. Accept the Windows security warning

Refresh your browser; sites will load normally and appear in the dashboard.

## Stopping

Click the terminal window and press **Ctrl + C**. The tool disables the Windows
proxy and shuts down cleanly.

> **If you close the window with the X button instead**, the system proxy is
> left enabled and pointing at a proxy that is no longer running — which looks
> exactly like your internet has broken. Fix it by running `start.bat` again and
> exiting properly with Ctrl + C, or by turning off **Settings → Network &
> Internet → Proxy → Use a proxy server**.

## Removing the certificate

When you are finished monitoring:

1. Press `Win + R`, run `certmgr.msc`
2. Go to **Trusted Root Certification Authorities → Certificates**
3. Find **mitmproxy**, delete it
4. Optionally delete `%USERPROFILE%\.mitmproxy` to destroy the private key

---

## How it works

```
Browser / apps
      │  (Windows system proxy → 127.0.0.1:8080)
      ▼
mitmdump + backend/proxy.py          ← decrypts, extracts metadata and bodies
      │  HTTP POST /api/log
      ▼
backend/server.py (FastAPI, :8000)   ← in-memory store, no persistence
      │  WebSocket /ws
      ▼
frontend/ dashboard                  ← live table, detail modal
```

`run.py` supervises all of it and is responsible for setting the Windows proxy
registry keys on start and restoring them on exit.

For the design reasoning — why the proxy pushes over HTTP instead of sharing
memory, why binary bodies are fetched on demand rather than streamed, and the
known limitations — see [`docs/DESIGN_SPEC.md`](docs/DESIGN_SPEC.md).

---

## Limitations

- **Windows only.** The proxy toggle is Windows-registry specific. The rest is
  portable; nothing else would need to change much.
- **Certificate-pinned apps will fail to connect** while the proxy is on. That
  is the pinning working correctly, not a bug. Many mobile-style and banking
  apps do this.
- **Buffers are capped**: 500 rows in the table, 500 stored binary bodies, 100k
  characters per text body, 20 MB per binary body. Older entries are evicted.
- **No filtering before capture.** Everything your machine sends passes through
  the dashboard, so treat the window as sensitive while it is open.

---

## Licence

AGPL-3.0. See [LICENSE](LICENSE).
