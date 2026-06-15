import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Test copilot.tencent.com (should be DIRECT now)
req = urllib.request.Request('https://copilot.tencent.com', headers={'User-Agent': 'curl/8.19.0'})
try:
    resp = urllib.request.urlopen(req, context=ctx, timeout=10)
    print(f'copilot.tencent.com -> {resp.status}')
    print(f'  Location: {resp.headers.get("Location", "-")}')
except Exception as e:
    print(f'copilot.tencent.com -> FAILED: {e}')

# Test codebuddy.cn
req2 = urllib.request.Request('https://www.codebuddy.cn', headers={'User-Agent': 'curl/8.19.0'})
try:
    resp2 = urllib.request.urlopen(req2, context=ctx, timeout=10)
    print(f'www.codebuddy.cn -> {resp2.status}')
except Exception as e:
    print(f'www.codebuddy.cn -> FAILED: {e}')

# Test data sources still work through proxy
for url in ['https://api.stlouisfed.org', 'https://query1.finance.yahoo.com']:
    try:
        req3 = urllib.request.Request(url, headers={'User-Agent': 'curl/8.19.0'})
        resp3 = urllib.request.urlopen(req3, context=ctx, timeout=10)
        print(f'{url} -> {resp3.status} OK')
    except Exception as e:
        print(f'{url} -> FAILED: {e}')
