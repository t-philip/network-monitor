import json
import urllib.request
import asyncio
import base64
from datetime import datetime
from mitmproxy import http

MAX_TEXT_CHARS = 100000
MAX_BINARY_BYTES = 20 * 1024 * 1024  # captured once for storage, not broadcast live, so this can be generous

class TrafficLogger:
    def response(self, flow: http.HTTPFlow):
        req = flow.request
        res = flow.response

        # Prevent logging our own webhook traffic
        if req.port == 8000 or "localhost" in req.host:
            return

        def _get_text(message):
            try:
                text = message.get_text(strict=False)
                return text[:MAX_TEXT_CHARS] if text else None
            except Exception:
                return None

        req_type = req.headers.get("Content-Type", "")
        res_type = res.headers.get("Content-Type", "")

        req_is_text = any(t in req_type.lower() for t in ["text", "json", "xml", "urlencoded"])
        res_is_text = any(t in res_type.lower() for t in ["text", "json", "xml", "urlencoded"])

        def _describe_body(message, content_type, is_text):
            raw = message.raw_content
            if not raw:
                return {"kind": "none"}, None
            if is_text:
                text = _get_text(message)
                return {"kind": "text", "text": text if text is not None else "None"}, None
            if len(raw) > MAX_BINARY_BYTES:
                return {"kind": "too_large", "content_type": content_type, "size": len(raw)}, None
            return (
                {"kind": "binary", "content_type": content_type, "size": len(raw)},
                base64.b64encode(raw).decode("ascii"),
            )

        req_body, req_blob = _describe_body(req, req_type, req_is_text)
        res_body, res_blob = _describe_body(res, res_type, res_is_text)

        data = {
            "id": flow.id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "method": req.method,
            "url": req.url,
            "host": req.host,
            "path": req.path,
            "status": res.status_code,
            "content_type": res.headers.get("Content-Type", ""),
            "req_size": len(req.raw_content) if req.raw_content else 0,
            "res_size": len(res.raw_content) if res.raw_content else 0,
            "req_headers": dict(req.headers),
            "res_headers": dict(res.headers),
            "req_body": req_body,
            "res_body": res_body,
        }

        blobs = {}
        if req_blob is not None:
            blobs["req"] = {"content_type": req_type, "data": req_blob}
        if res_blob is not None:
            blobs["res"] = {"content_type": res_type, "data": res_blob}
        if blobs:
            data["blobs"] = blobs

        asyncio.create_task(self.send_data(data))

    async def send_data(self, data):
        def _post():
            url = "http://localhost:8000/api/log"
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                # Explicitly bypass system proxy so we don't intercept our own logs
                proxy_handler = urllib.request.ProxyHandler({})
                opener = urllib.request.build_opener(proxy_handler)
                opener.open(req, timeout=3)
            except Exception:
                pass

        await asyncio.to_thread(_post)

addons = [
    TrafficLogger()
]
