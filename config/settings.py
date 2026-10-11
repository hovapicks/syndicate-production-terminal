import os
import socket
import dns.resolver
from dotenv import load_dotenv

load_dotenv()

# Force dnspython to query Google DNS directly
resolver = dns.resolver.Resolver()
resolver.nameservers = ['8.8.8.8', '1.1.1.1']

_orig_getaddrinfo = socket.getaddrinfo

def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and "supabase.co" in host:
        try:
            answers = resolver.resolve(host, 'A')
            ip = str(answers[0])
            return _orig_getaddrinfo(ip, port, family, type, proto, flags)
        except Exception:
            pass
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = custom_getaddrinfo

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

TARGET_BOOKS = ["pinnacle", "circa", "draftkings", "fanduel", "betmgm", "caesars"]
