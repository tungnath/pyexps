from urllib.parse import urlencode
from urllib.request import urlopen, Request
import json

def translate_batch(texts, src="en", tgt="hi"):
    base = "https://clients5.google.com/translate_a/t"
    params = [("client", "dict-chrome-ex"), ("sl", src), ("tl", tgt)]
    for t in texts:
        params.append(("q", t))
    url = base + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())

if __name__ == "__main__":
    json_arr= json.loads(open("locales/strings.json").read())
    print(translate_batch(["Where are you?", "Hello world", "How are you?"]))