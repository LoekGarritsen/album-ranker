"""Shared rate limiter (slowapi). Registered on the app in main.py.

Keys on the real client IP. Behind Cloudflare + Nginx Proxy Manager the direct
peer is the proxy, so prefer CF-Connecting-IP (set by Cloudflare, not spoofable
through it), then the first X-Forwarded-For hop, then the socket peer.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request):
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)
