import socket
import urllib.request
import json

_orig_getaddrinfo = socket.getaddrinfo
_dns_cache = {}

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and host.endswith("supabase.co"):
        if host not in _dns_cache:
            try:
                # Query Google Public DNS over HTTPS (DoH)
                url = f"https://dns.google/resolve?name={host}&type=A"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    answers = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
                    if answers:
                        _dns_cache[host] = answers[0]
            except Exception:
                pass
        if host in _dns_cache:
            return _orig_getaddrinfo(_dns_cache[host], port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = patched_getaddrinfo
