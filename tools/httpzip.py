import io, requests, zipfile
class HttpFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests."""
    def __init__(self, url):
        self.s = requests.Session()
        r = self.s.head(url, allow_redirects=True, timeout=60)
        self.url = r.url; self.size = int(r.headers["Content-Length"]); self.pos = 0
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos
    def readinto(self, b):
        if self.pos >= self.size: return 0
        end = min(self.pos + len(b), self.size) - 1
        for i in range(5):
            try:
                r = self.s.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=300)
                if r.status_code in (200, 206): break
            except requests.RequestException: pass
        data = r.content; b[:len(data)] = data; self.pos += len(data); return len(data)
def open_zip(url, buf=8 << 20):
    return zipfile.ZipFile(io.BufferedReader(HttpFile(url), buffer_size=buf))
