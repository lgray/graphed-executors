import json, sys, uproot
url = next(iter(json.load(open(sys.argv[1])).values()))[0]
print("URL", url)
try:
    print("KEYS", uproot.open(url, timeout=60).keys()[:3])
except Exception as e:
    print("ERROR", type(e).__name__, e)
