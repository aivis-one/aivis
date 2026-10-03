#!/usr/bin/env python3
"""run-checks.py -- machine checks from testing-guide.md, stdlib only, headless Chrome over CDP.

WHAT IT DOES   Runs the checks of the guide that a machine can decide, against each URL
               (default http://127.0.0.1:8731/ and /ru/), printing PASS / FAIL / WARN / INFO
               per check. The check id (A2, B7, F10 ...) is the rule id in testing-guide.md.
WHAT IT NEEDS  Python 3.9+ (stdlib only) and Chrome or Edge. No npm, no pip, no server start.
USAGE          python run-checks.py [URL ...] [--chrome PATH] [--headers-file PATH]
                                    [--skip-browser] [--shots] [--no-external] [--self-test]
EXIT CODE      1 when any FAIL was printed, else 0. WARN never fails the run.
LIMITS         Lab data on this machine, no network throttling: LCP/CLS here are a smoke
               test, not field data. Contrast covers flat backgrounds only (gradients and
               images are counted as "not measurable", never as pass).
"""
import argparse, base64, hashlib, json, os, re, shutil, socket, struct, subprocess, sys
import time, urllib.request, urllib.parse, urllib.error, zlib, threading, http.server

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # Russian text must print as UTF-8 on any console
    except Exception:
        pass
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URLS = ["http://127.0.0.1:8731/", "http://127.0.0.1:8731/ru/"]
VIEWPORTS = [320, 360, 375, 390, 414, 768, 1024, 1280, 1440]
BRAND_OK = {"AIVIS", "ONE", "SANKORD", "EXSPECS", "FAQ", "English", "AI", "URL", "SANKORD.COM", "COM", "ID", "LLC", "VIS", "TELEGRAM", "LINKEDIN", "X", "MEDIUM"}
RESULTS = []


def rep(status, cid, url, msg):
    RESULTS.append((status, cid, url, msg))
    print("%-5s %-4s %-26s %s" % (status, cid, short(url), msg), flush=True)


def locale_of(u):
    """ru when the path has a /ru/ or /ru. segment, else en"""
    return "ru" if re.search(r"/ru(/|\.|$)", urllib.parse.urlparse(u).path) else "en"


def short(u):
    p = urllib.parse.urlparse(u)
    return p.path or "/"


def fetch(url, method="GET", timeout=15):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "run-checks/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict((k.lower(), v) for k, v in r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict((k.lower(), v) for k, v in e.headers.items()), b""
    except Exception as e:  # noqa
        return 0, {}, str(e).encode()


# ----------------------------------------------------------------- static HTML model
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "area", "base", "col", "embed", "param", "track", "wbr"}


class Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.els, self.texts, self.stack, self.inline, self._buf = [], [], [], [], ""
        self.title = None
        self.order = []  # (tag) in document order for head ordering

    def handle_starttag(self, tag, attrs):
        d = dict((k, (v if v is not None else "")) for k, v in attrs)
        self.els.append((tag, d))
        if tag not in VOID:
            self.stack.append((tag, d))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.stack and self.stack[-1][0] == tag:
            self.inline.append((tag, self.stack[-1][1], self._buf))
            self._buf = ""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] in ("script", "style"):
            self._buf += data
            return
        names = [t for t, _ in self.stack]
        if "title" in names:
            self.title = (self.title or "") + data
            return
        if "body" in names and "svg" not in names and data.strip():
            self.texts.append(re.sub(r"[ \t\r\n]+", " ", data).strip())


def parse(html):
    d = Doc()
    d.feed(html)
    d.close()
    return d


def attr(d, tag, **kw):
    out = []
    for t, a in d.els:
        if t == tag and all(a.get(k) == v for k, v in kw.items()):
            out.append(a)
    return out


# ----------------------------------------------------------------- minimal websocket + CDP
class WS:
    def __init__(self, host, port, path):
        self.s = socket.create_connection((host, port), 10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(1)
        if b" 101 " not in buf.split(b"\r\n")[0]:
            raise RuntimeError("websocket handshake failed: " + buf[:80].decode(errors="replace"))

    def send(self, text):
        data = text.encode()
        n = len(data)
        hdr = bytearray([0x81])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126); hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127); hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        self.s.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise ConnectionError("closed")
            b += c
        return b

    def recv(self, timeout):
        self.s.settimeout(timeout)
        msg = b""
        while True:
            try:
                h = self._read(2)
            except socket.timeout:
                return None
            fin, op, n = h[0] & 0x80, h[0] & 0x0F, h[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 8:
                raise ConnectionError("closed")
            if op in (1, 0):
                msg += payload
                if fin:
                    return msg.decode("utf-8", "replace")


class CDP:
    def __init__(self, ws):
        self.ws, self.i, self.events = ws, 0, []

    def call(self, method, params=None, timeout=30):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            m = self.ws.recv(1.0)
            if m is None:
                continue
            j = json.loads(m)
            if j.get("id") == mid:
                if "error" in j:
                    raise RuntimeError("%s: %s" % (method, j["error"]))
                return j.get("result", {})
            if "method" in j:
                self.events.append(j)
        raise TimeoutError(method)

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            m = self.ws.recv(0.2)
            if m:
                j = json.loads(m)
                if "method" in j:
                    self.events.append(j)

    def ev(self, expr):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError("js: " + json.dumps(r["exceptionDetails"])[:300])
        return r["result"].get("value")

    def navigate(self, url, settle=1.0):
        self.events = []
        self.call("Page.navigate", {"url": url})
        end = time.time() + 30
        while time.time() < end:
            if any(e["method"] == "Page.loadEventFired" for e in self.events):
                break
            self.pump(0.2)
        self.pump(settle)

    def key(self, key, code, vk, mods=0):
        for t in ("keyDown", "keyUp"):
            self.call("Input.dispatchKeyEvent", {"type": t, "key": key, "code": code,
                                                 "windowsVirtualKeyCode": vk, "modifiers": mods})

    def click_xy(self, x, y):
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left",
                                                   "clickCount": 1})


def find_chrome(arg):
    cands = [arg] if arg else []
    cands += [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("msedge")


# ----------------------------------------------------------------- JS probes (run in the page)
INIT_JS = r"""
(function(){
  var m = window.__m = {cls:0, lcp:0, csp:[], errs:[], longTasks:0};
  try{ new PerformanceObserver(function(l){ l.getEntries().forEach(function(e){ if(!e.hadRecentInput) m.cls+=e.value; }); }).observe({type:'layout-shift',buffered:true}); }catch(e){}
  try{ new PerformanceObserver(function(l){ var es=l.getEntries(); m.lcp=es[es.length-1].startTime; }).observe({type:'largest-contentful-paint',buffered:true}); }catch(e){}
  try{ new PerformanceObserver(function(l){ l.getEntries().forEach(function(e){ m.longTasks+=Math.max(0,e.duration-50); }); }).observe({type:'longtask',buffered:true}); }catch(e){}
  document.addEventListener('securitypolicyviolation', function(e){ m.csp.push(e.violatedDirective+' '+e.blockedURI); });
  window.addEventListener('error', function(e){ m.errs.push(String(e.message)); });
})();
"""

LAYOUT_JS = r"""
(function(){
  var W = __W__, out = {W:W, sw:document.documentElement.scrollWidth, off:[], small:[], tiny:[], lines:[], orph:[], fonts:{}, imgs:[]};
  function vis(el){ try{ return el.checkVisibility({visibilityProperty:true, opacityProperty:true}); }catch(e){ return true; } }
  function name(el){ return el.tagName.toLowerCase()+(el.className&&typeof el.className==='string'?'.'+el.className.trim().split(/\s+/)[0]:''); }
  var drawer = document.querySelector('[data-ls-drawer]');
  function inClosedDrawer(el){ return drawer && drawer.contains(el) && !drawer.classList.contains('is-open') && drawer.getAttribute('data-open')!=='true'; }
  document.querySelectorAll('body *').forEach(function(el){
    if(!vis(el) || inClosedDrawer(el)) return;
    var r = el.getBoundingClientRect(); if(r.width===0&&r.height===0) return;
    var cs = getComputedStyle(el);
    if(cs.position==='fixed' && (r.left<-1||r.right>W+1) && drawer && drawer.contains(el)) return;
    if((r.right>W+1 || r.left<-1) && out.off.length<6){
      var p = el.parentElement, clipped=false;
      for(;p&&p!==document.body;p=p.parentElement){ var o=getComputedStyle(p).overflowX; if(o==='hidden'||o==='auto'||o==='scroll'||o==='clip'){ var pr=p.getBoundingClientRect(); if(pr.right<=W+1&&pr.left>=-1){clipped=true;break;} } }
      if(!clipped) out.off.push(name(el)+' L'+Math.round(r.left)+' R'+Math.round(r.right));
    }
  });
  // targets
  document.querySelectorAll('a[href],button,summary,input:not([type=hidden]),select,textarea,[role=button],[tabindex]:not([tabindex="-1"])').forEach(function(el){
    if(!vis(el) || inClosedDrawer(el)) return;
    var r = el.getBoundingClientRect(); if(r.width===0||r.height===0) return;
    if(r.right<=0||r.left>=W) return;
    var cs = getComputedStyle(el);
    if(el.tagName==='A' && cs.display==='inline'){
      var par = el.parentElement; var own=0; par.childNodes.forEach(function(n){ if(n.nodeType===3) own+=n.textContent.trim().length; });
      if(own>0) return; // inline link inside a sentence: WCAG 2.5.8 inline exception
    }
    out.small.push({n:name(el), t:(el.getAttribute('aria-label')||el.textContent||'').trim().slice(0,24), w:Math.round(r.width*10)/10, h:Math.round(r.height*10)/10});
  });
  // text sizes and lines
  var paras = [];
  document.querySelectorAll('body *').forEach(function(el){
    if(!vis(el) || inClosedDrawer(el)) return;
    var own=''; el.childNodes.forEach(function(n){ if(n.nodeType===3) own+=n.textContent; });
    own=own.trim(); if(!own) return;
    var cs=getComputedStyle(el), fs=parseFloat(cs.fontSize);
    var k=Math.round(fs*10)/10; out.fonts[k]=(out.fonts[k]||0)+1;
    if(fs<12 && out.tiny.length<8) out.tiny.push(name(el)+' '+fs+'px "'+own.slice(0,20)+'"');
    if((el.tagName==='P'||el.tagName==='LI') && el.textContent.trim().length>=80 && paras.length<14) paras.push(el);
  });
  function lineGroups(el){
    var g=[], tw=document.createTreeWalker(el,NodeFilter.SHOW_TEXT), n;
    while((n=tw.nextNode())){ var t=n.textContent; for(var i=0;i<t.length;i++){ if(!/\S/.test(t[i])&&t[i]!==' ') continue; var rg=document.createRange(); rg.setStart(n,i); rg.setEnd(n,i+1); var rs=rg.getClientRects(); if(!rs.length) continue; var top=Math.round(rs[0].top/4); var last=g[g.length-1]; if(!last||Math.abs(last.top-top)>2){ last={top:top,s:''}; g.push(last);} last.s+=t[i]; } }
    return g;
  }
  paras.forEach(function(p){ var g=lineGroups(p); var mx=0; g.forEach(function(l){ mx=Math.max(mx,l.s.trim().length); }); out.lines.push({n:name(p), max:mx, lines:g.length}); });
  var lastTargets = [];
  document.querySelectorAll('h1,h2,h3,p,li').forEach(function(el){ if(vis(el)&&!inClosedDrawer(el)&&el.textContent.trim().length>20&&lastTargets.length<60) lastTargets.push(el); });
  lastTargets.forEach(function(el){ var g=lineGroups(el); if(g.length>=2){ var w=g[g.length-1].s.trim().split(/\s+/).filter(Boolean).length; if(w<2) out.orph.push(name(el)+': "'+g[g.length-1].s.trim()+'"'); } });
  // images
  document.querySelectorAll('img').forEach(function(im){ if(!vis(im)) return; var r=im.getBoundingClientRect(); out.imgs.push({src:(im.getAttribute('src')||'').split('/').pop(), nw:im.naturalWidth, rw:Math.round(r.width), ok:im.complete&&im.naturalWidth>0, dpr:window.devicePixelRatio, lazy:im.loading, fp:im.getAttribute('fetchpriority')}); });
  return out;
})()
"""

CONTRAST_JS = r"""
(function(){
  function parse(c){ var m=c.match(/rgba?\(([^)]+)\)/); if(m){ var p=m[1].split(/[ ,\/]+/).filter(Boolean).map(parseFloat); return [p[0],p[1],p[2],p.length>3?p[3]:1]; }
    m=c.match(/color\(srgb ([^)]+)\)/); if(m){ var q=m[1].split(/[ \/]+/).filter(Boolean).map(parseFloat); return [q[0]*255,q[1]*255,q[2]*255,q.length>3?q[3]:1]; } return null; }
  function lin(v){ v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); }
  function L(c){ return 0.2126*lin(c[0])+0.7152*lin(c[1])+0.0722*lin(c[2]); }
  function over(f,b){ var a=f[3]; return [f[0]*a+b[0]*(1-a), f[1]*a+b[1]*(1-a), f[2]*a+b[2]*(1-a), 1]; }
  function bg(el){ var layers=[]; for(var e=el;e;e=e.parentElement){ var cs=getComputedStyle(e); if(cs.backgroundImage!=='none') return null; var b=parse(cs.backgroundColor); if(b&&b[3]>0){ layers.push(b); if(b[3]>=1) break; } }
    var base=[255,255,255,1]; for(var i=layers.length-1;i>=0;i--) base=over(layers[i],base); return base; }
  var res={checked:0, skipped:0, fails:[]}, seen={};
  var drawer=document.querySelector('[data-ls-drawer]');
  document.querySelectorAll('body *').forEach(function(el){
    var own=''; el.childNodes.forEach(function(n){ if(n.nodeType===3) own+=n.textContent; }); own=own.trim(); if(!own) return;
    try{ if(!el.checkVisibility({visibilityProperty:true})) return; }catch(e){}
    if(drawer&&drawer.contains(el)&&!(drawer.getBoundingClientRect().right>0&&drawer.getBoundingClientRect().left<window.innerWidth)) return;
    var r=el.getBoundingClientRect(); if(!r.width||!r.height) return;
    var cs=getComputedStyle(el); var f=parse(cs.color); var b=bg(el);
    if(!f||!b){ res.skipped++; return; }
    var op=1; for(var e=el;e;e=e.parentElement){ op*=parseFloat(getComputedStyle(e).opacity); }
    var fg=over([f[0],f[1],f[2],f[3]*op], b);
    var l1=L(fg), l2=L(b), ratio=(Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    var fs=parseFloat(cs.fontSize), bold=parseInt(cs.fontWeight)>=700, large=fs>=24||(fs>=18.66&&bold);
    res.checked++;
    if(ratio < (large?3:4.5)){ var k=el.tagName+own.slice(0,16); if(!seen[k]){ seen[k]=1; res.fails.push(el.tagName.toLowerCase()+' "'+own.slice(0,22)+'" '+ratio.toFixed(2)+':1 need '+(large?3:4.5)); } }
  });
  return res;
})()
"""

FOCUS_JS = r"""
(function(){
  var el=document.activeElement; if(!el||el===document.body) return null;
  var cs=getComputedStyle(el), r=el.getBoundingClientRect();
  var vis = (cs.outlineStyle!=='none' && parseFloat(cs.outlineWidth)>0) || cs.boxShadow!=='none' || el.matches(':focus-visible') && false;
  var pts=[[.5,.5],[.1,.5],[.9,.5],[.5,.1],[.5,.9]], nCov=0, nTot=0;
  pts.forEach(function(p){ var x=r.left+r.width*p[0], y=r.top+r.height*p[1]; if(x<0||y<0||x>=window.innerWidth||y>=window.innerHeight) return; nTot++; var hit=document.elementFromPoint(x,y); if(hit && !(el.contains(hit)||hit.contains(el))) nCov++; });
  var covered = nTot===0 || nCov===nTot;   // 2.4.11 AA: fails only when the control is ENTIRELY hidden
  var partial = !covered && nCov>0;
  return {partial:partial,tag:el.tagName.toLowerCase(), name:(el.getAttribute('aria-label')||el.textContent||el.getAttribute('href')||'').trim().slice(0,24), vis:!!vis, covered:!!covered, ow:cs.outlineWidth, os:cs.outlineStyle, w:r.width, h:r.height, key:(el.__fid||(el.__fid=(window.__fidc=(window.__fidc||0)+1)))+'|'+(el.getAttribute('href')||el.getAttribute('aria-label')||el.textContent||'').trim().slice(0,30)};
})()
"""

OPACITY_JS = r"""
(async function(){
  var h=document.documentElement.scrollHeight;
  for(var y=0;y<=h;y+=250){ window.scrollTo(0,y); await new Promise(function(r){setTimeout(r,100)}); }
  window.scrollTo(0,document.documentElement.scrollHeight);
  await new Promise(function(r){setTimeout(r,1500)});
  var rx=/reveal|ls-mo-|stagger|fade|animate/i, out={n:0,bad:[]};
  document.querySelectorAll('body *').forEach(function(el){
    var cn=(typeof el.className==='string')?el.className:'';
    var flagged = rx.test(cn) || el.getAnimations().length>0;
    if(!flagged) return;
    try{ if(!el.checkVisibility({visibilityProperty:true})) return; }catch(e){}
    var r=el.getBoundingClientRect(); if(!r.width||!r.height) return;
    var op=1; for(var e=el;e;e=e.parentElement){ op*=parseFloat(getComputedStyle(e).opacity); }
    out.n++;
    if(op<0.99) out.bad.push(el.tagName.toLowerCase()+(cn?'.'+cn.trim().split(/\s+/).slice(0,2).join('.'):'')+' '+op.toFixed(2));
  });
  return out;
})()
"""

SPACING_JS = r"""
(function(){
  var secs=[].slice.call(document.querySelectorAll('main section, main > div > section')); var res={bad:[],vals:{}};
  secs.forEach(function(s){ var cs=getComputedStyle(s); [cs.paddingTop,cs.paddingBottom].forEach(function(v){ var n=Math.round(parseFloat(v)); res.vals[n]=(res.vals[n]||0)+1; if(n%4!==0) res.bad.push((s.id||s.className||'section')+' '+v); }); });
  var fam={};
  document.querySelectorAll('main [class*=card],main [class*=tile]').forEach(function(c){ var p=c.parentElement; if(!p) return; var k=(p.id||p.className||'p')+'|'+c.className; (fam[k]=fam[k]||[]).push(c); });
  res.cards=[]; Object.keys(fam).forEach(function(k){ var els=fam[k]; if(els.length<2) return; var rows={}; els.forEach(function(e){ var r=e.getBoundingClientRect(); if(!r.height) return; var t=Math.round(r.top+window.scrollY); var key=Math.round(t/8); (rows[key]=rows[key]||[]).push(r.height); }); Object.keys(rows).forEach(function(rk){ var hs=rows[rk]; if(hs.length>1){ var d=Math.max.apply(null,hs)-Math.min.apply(null,hs); if(d>2) res.cards.push(k.split('|')[1].split(' ')[0]+' height spread '+Math.round(d)+'px'); } }); });
  return res;
})()
"""


# ----------------------------------------------------------------- static checks
# I10: internal or technical text that must never reach a published page (rule A1 of the home). Every pattern is
# searched in the RAW html, so comments, title/alt/aria-* values, meta tags, JSON-LD and inline script/style text
# are all covered. (label, regex)
INTERNAL_PATTERNS = [
    ("counsel/review marker", re.compile(r"\[COUNSEL|\[REVIEW|REVIEW-GATE|\bcounsel\b", re.I)),
    ("draft word", re.compile(r"\bdrafts?\b|черновик", re.I)),
    ("placeholder word", re.compile(r"placeholder|плейсхолдер", re.I)),
    ("TODO marker", re.compile(r"\b(?:TODO|FIXME|TBD|XXX)\b")),
    ("source or composition mark", re.compile(r"\bCOMPOSED\b|\bHIS WORD\b|\bSRC\b|\bSOURCE:")),
    ("row/task number", re.compile(r"\b(?:row|task|ruling|finding|item)\s*#?\d{1,4}\b", re.I)),
    ("file path", re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|\bsandbox/|\bnavigator/|\blanding-work\b|\blegal-site\b|\bAgent-[A-Z][\w.]*|/Users/|"
                             r"\bcontent/[\w.-]+\.json|[\w-]+\.(?:py|md|tsv|sh|css|js|json)\b")),
    ("internal skill or record id", re.compile(r"\bW-[A-Z]{2,}\b|(?<![\w#.-])P[0-9]{2}(?![\w-])|\b(?:R|Q|D|CF|REQ)-\d{1,3}\b|\bR\d+-\d+\b")),
    ("lorem ipsum", re.compile(r"lorem\s+ipsum|\blorem\b", re.I)),
    ("version stamp", re.compile(r"Версия\s+0\.|Version\s+0\.|\bv0\.\d|data-version")),
]


def internal_marker_hits(raw):
    """[(label, snippet)] for every internal or technical leftover in one page's raw html."""
    hits = []
    for label, rx in INTERNAL_PATTERNS:
        for m in rx.finditer(raw):
            a, b = max(0, m.start() - 30), min(len(raw), m.end() + 30)
            hits.append((label, re.sub(r"\s+", " ", raw[a:b])))
    return hits


def static_checks(url, html, hdrs, status, args, docs_by_url):
    d = parse(html)
    docs_by_url[url] = d
    ih = internal_marker_hits(html)
    labels = sorted(set(l for l, _ in ih))
    rep("FAIL" if ih else "PASS", "I10", url, "no internal markers in published pages: %s" % (
        "%d hit(s), kinds: %s; first: %s" % (len(ih), ", ".join(labels), " | ".join("[%s]" % s for _, s in ih[:3])) if ih else "none found"))
    base = urllib.parse.urlparse(url)
    loc = locale_of(url)
    htmltag = [a for t, a in d.els if t == "html"]
    ha = htmltag[0] if htmltag else {}
    rep("PASS" if status == 200 else "FAIL", "H0", url, "HTTP status %s" % status)
    # B1 / C2
    exp = loc
    ok = ha.get("lang", "").lower().split("-")[0] == exp and ha.get("dir", "ltr") in ("ltr", "rtl")
    rep("PASS" if ok else "FAIL", "B1", url, 'html lang="%s" dir="%s" (locale %s)' % (ha.get("lang"), ha.get("dir"), exp))
    # B2 / E1 / E2
    t = (d.title or "").strip()
    rep("PASS" if 15 <= len(t) <= 65 else "WARN", "E1", url, "title %d chars: %s" % (len(t), t))
    md = [a.get("content", "") for a in attr(d, "meta", name="description")]
    ml = len(md[0]) if md else 0
    rep("PASS" if 70 <= ml <= 170 else ("FAIL" if ml == 0 else "WARN"), "E2", url, "meta description %d chars" % ml)
    # E3 canonical
    can = [a.get("href") for a in attr(d, "link", rel="canonical")]
    self_url = None
    rep("PASS" if len(can) == 1 and can[0].startswith("https://") else "FAIL", "E3", url, "canonical %s" % can)
    # E4 hreflang
    hl = dict((a.get("hreflang"), a.get("href")) for a in attr(d, "link", rel="alternate") if a.get("hreflang"))
    need = {"en", "ru", "x-default"}
    miss = need - set(hl)
    rep("PASS" if not miss else "FAIL", "E4", url, "hreflang set %s%s" % (sorted(hl), " missing %s" % sorted(miss) if miss else ""))
    rep("PASS" if can and can[0] in hl.values() else "FAIL", "E4", url, "canonical is one of the hreflang targets (self-reference)")
    # E6 open graph
    og = dict((a.get("property"), a.get("content")) for a in attr(d, "meta") if a.get("property", "").startswith("og:"))
    for k in ("og:title", "og:type", "og:url", "og:image", "og:description"):
        rep("PASS" if og.get(k) else ("FAIL" if k != "og:description" else "WARN"), "E6", url, "%s %s" % (k, "set" if og.get(k) else "MISSING"))
    if og.get("og:image"):
        rep("PASS" if og.get("og:image:alt") else "WARN", "E6", url, "og:image:alt %s" % ("set" if og.get("og:image:alt") else "missing"))
    tw = [a for a in attr(d, "meta") if a.get("name", "").startswith("twitter:")]
    rep("PASS" if any(a.get("name") == "twitter:card" for a in tw) else "WARN", "E6", url, "twitter:card %s" % ("set" if tw else "missing"))
    robots = [a.get("content", "") for a in attr(d, "meta", name="robots")]
    rep("FAIL" if any("noindex" in r for r in robots) else "PASS", "E8", url, "robots meta: %s" % (robots or "none (indexable)"))
    rep("PASS" if attr(d, "link", rel="icon") else "WARN", "E11", url, "favicon link")
    # A1 viewport
    vp = [a.get("content", "") for a in attr(d, "meta", name="viewport")]
    v = vp[0] if vp else ""
    bad = re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*[01](\.\d+)?(\s|,|$)", v)
    rep("PASS" if "width=device-width" in v and "initial-scale=1" in v and not bad else "FAIL", "A1", url, "viewport: %s" % v)
    # B3 headings
    hs = [int(t[1]) for t, a in d.els if re.fullmatch(r"h[1-6]", t)]
    rep("PASS" if hs.count(1) == 1 else "FAIL", "B3", url, "h1 count %d" % hs.count(1))
    jump = [(a, b) for a, b in zip(hs, hs[1:]) if b - a > 1]
    rep("PASS" if not jump else "FAIL", "B3", url, "heading levels never skip down %s" % (jump or ""))
    # B4 landmarks
    tags = [t for t, a in d.els]
    miss = [x for x in ("header", "nav", "main", "footer") if x not in tags]
    rep("PASS" if not miss else "FAIL", "B4", url, "landmarks present (missing: %s)" % (miss or "none"))
    navs = [a for t, a in d.els if t == "nav"]
    rep("PASS" if all(a.get("aria-label") or a.get("aria-labelledby") for a in navs) else "WARN", "B4", url, "%d nav landmarks all labelled" % len(navs))
    skip = [a for t, a in d.els if t == "a" and a.get("href", "").startswith("#") and re.search(r"skip", a.get("class", "") + a.get("href", ""), re.I)]
    rep("PASS" if skip else "WARN", "B4", url, "skip link to main content %s" % ("present" if skip else "not found (page has a sticky header; WCAG 2.4.1 bypass blocks)"))
    # B5 alt
    imgs = [a for t, a in d.els if t == "img"]
    noalt = [a.get("src") for a in imgs if "alt" not in a]
    rep("PASS" if not noalt else "FAIL", "B5", url, "%d img, missing alt: %s" % (len(imgs), noalt or "none"))
    # D7 dims
    nodim = [a.get("src") for a in imgs if not (a.get("width") and a.get("height"))]
    rep("PASS" if not nodim else "FAIL", "D7", url, "img width+height set (CLS) missing: %s" % (nodim or "none"))
    # B6 names
    unnamed = []
    for t, a in d.els:
        if t in ("button",) and not a.get("aria-label") and not a.get("aria-labelledby"):
            unnamed.append("button")
    rep("PASS" if not unnamed else "WARN", "B6", url, "icon-only buttons carry aria-label (static: buttons without aria-label: %d; text buttons are fine, see browser check)" % len(unnamed))
    # B11 ids
    ids = [a["id"] for t, a in d.els if a.get("id")]
    dup = sorted(set(i for i in ids if ids.count(i) > 1))
    rep("PASS" if not dup else "FAIL", "B11", url, "%d ids, duplicates: %s" % (len(ids), dup or "none"))
    idset = set(ids)
    brokenctl = [a.get("aria-controls") for t, a in d.els if a.get("aria-controls") and a["aria-controls"] not in idset]
    rep("PASS" if not brokenctl else "FAIL", "B11", url, "aria-controls targets exist %s" % (brokenctl or ""))
    anchors = sorted(set(a["href"][1:] for t, a in d.els if t == "a" and a.get("href", "").startswith("#") and len(a["href"]) > 1))
    brokenanc = [x for x in anchors if x not in idset]
    rep("PASS" if not brokenanc else "FAIL", "H1", url, "in-page anchors resolve (%d) broken: %s" % (len(anchors), brokenanc or "none"))
    # B13 svg
    # B17 lang switch
    sw = [a for t, a in d.els if t == "a" and a.get("hreflang")]
    rep("PASS" if sw and all(a.get("lang") for a in sw) else "WARN", "B17", url, "language links carry hreflang+lang (3.1.2): %d" % len(sw))
    # F: CSP
    csp = [a.get("content", "") for a in attr(d, "meta") if a.get("http-equiv", "").lower() == "content-security-policy"]
    hcsp = hdrs.get("content-security-policy")
    pol = (hcsp or (csp[0] if csp else ""))
    rep("PASS" if pol else "FAIL", "F1", url, "CSP present via %s" % ("HTTP header" if hcsp else "meta" if csp else "NOWHERE"))
    dirs = {}
    for part in pol.split(";"):
        p = part.strip().split()
        if p:
            dirs[p[0]] = p[1:]
    unsafe = [k for k, vv in dirs.items() if any(x in ("'unsafe-inline'", "'unsafe-eval'", "*", "data:") for x in vv) and k in ("default-src", "script-src", "style-src", "script-src-elem")]
    rep("PASS" if pol and not unsafe else "FAIL", "F1", url, "no unsafe-inline/unsafe-eval/wildcards in script/style sources %s" % (unsafe or ""))
    rep("PASS" if (dirs.get("default-src") == ["'none'"] or dirs.get("object-src") == ["'none'"]) else "FAIL", "F2", url, "object-src none (directly or via default-src 'none')")
    rep("PASS" if "base-uri" in dirs else "FAIL", "F2", url, "base-uri set")
    rep("PASS" if "form-action" in dirs else "WARN", "F2", url, "form-action set")
    hosts = set(re.findall(r"https?://[^\s;'\"]+", pol))
    rep("PASS" if not hosts else "WARN", "F9", url, "CSP lists no external hosts %s" % (sorted(hosts) or ""))
    # F10 hashes
    shas = set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", pol))
    actual = {}
    for tag, a, raw in d.inline:
        if tag == "script" and a.get("type", "").lower() in ("application/ld+json", "application/json"):
            continue
        if a.get("src"):
            continue
        norm = raw.replace("\r\n", "\n").replace("\r", "\n")  # the HTML parser normalises newlines before CSP hashes
        actual[base64.b64encode(hashlib.sha256(norm.encode("utf-8")).digest()).decode()] = tag
    miss = [t for h, t in actual.items() if h not in shas]
    extra = [h[:8] for h in shas if h not in actual]
    rep("PASS" if not miss and not extra else "FAIL", "F10", url,
        "inline blocks %d, hashes in CSP %d, unhashed %s, stale hashes %s" % (len(actual), len(shas), miss or "none", extra or "none"))
    onev = [(t, k) for t, a in d.els for k in a if k.startswith("on")]
    rep("PASS" if not onev else "FAIL", "F9", url, "inline event handlers: %s" % (onev or "none"))
    sty = [t for t, a in d.els if "style" in a]
    rep("PASS" if not sty else "FAIL", "F9", url, "style= attributes (CSP style-src): %d" % len(sty))
    ext = []
    for t, a in d.els:
        for k in ("src", "href", "action", "data-src", "srcset"):
            val = a.get(k, "")
            if val.startswith(("http://", "https://", "//")):
                pu = urllib.parse.urlparse(val if not val.startswith("//") else "https:" + val)
                if t in ("script", "img", "iframe", "source", "video", "audio", "embed", "object") or (t == "link" and a.get("rel") in ("stylesheet", "preload", "modulepreload", "preconnect", "prefetch", "dns-prefetch", "icon")):
                    ext.append("%s %s" % (t, pu.netloc))
    rep("PASS" if not ext else "FAIL", "D5", url, "third-party resource references in markup: %s" % (ext or "none"))
    absroot = [(t, a.get("src") or a.get("href")) for t, a in d.els if t in ("img", "script") and (a.get("src", "").startswith("/") and not a.get("src", "").startswith("//"))]
    rep("PASS" if not absroot else "WARN", "H10", url, "asset paths relative (page must open from file:// double-click): root-absolute %s" % (absroot or "none"))
    # G3 / A4 CSS facts
    css = "\n".join(raw for tag, a, raw in d.inline if tag == "style")
    cover = "viewport-fit=cover" in v
    env = "safe-area-inset" in css
    rep("PASS" if (not cover) or env else "FAIL", "A4", url, "viewport-fit=cover %s, env(safe-area-inset-*) used in CSS: %s" % (cover, env))
    phys = len(re.findall(r"(?<![-\w])(margin|padding)-(left|right)\s*:|(?<![-\w])(left|right)\s*:\s*[-\d.]|text-align\s*:\s*(left|right)|float\s*:\s*(left|right)|border-(left|right)", css))
    logi = len(re.findall(r"-inline-(start|end)|inset-inline|margin-inline|padding-inline|text-align\s*:\s*(start|end)", css))
    rep("PASS" if phys == 0 else "WARN", "C8", url, "physical left/right CSS declarations: %d (logical-property uses: %d). Each one is a rule to re-check under dir=rtl" % (phys, logi))
    rm = "prefers-reduced-motion" in css
    anim = bool(re.search(r"@keyframes|animation\s*:|transition\s*:", css))
    rep("PASS" if rm or not anim else "FAIL", "B9", url, "CSS has motion: %s; honours prefers-reduced-motion: %s" % (anim, rm))
    rep("PASS" if "prefers-color-scheme" in css or any("prefers-color-scheme" in raw for tag, a, raw in d.inline) else "WARN", "H4", url, "prefers-color-scheme honoured (CSS or preboot)")
    hov = len(re.findall(r":hover", css))
    hovm = len(re.findall(r"@media\s*\(\s*hover\s*:\s*hover", css))
    rep("INFO", "A9", url, ":hover rules %d, wrapped in @media (hover: hover): %d (hover must never be the only way to reach content, 1.4.13)" % (hov, hovm))
    newf = [f for f, rx in (("text-wrap", r"text-wrap"), (":has()", r":has\("), ("color-mix()", r"color-mix\("), ("dvh/svh", r"\d(dvh|svh|lvh)"),
                            ("container queries", r"@container"), ("@layer", r"@layer"), ("nesting", r"&\s*[.:#\[]"), ("oklch()", r"oklch\(")) if re.search(rx, css)]
    rep("INFO", "G3", url, "newer CSS features used (check Baseline / caniuse for the engines in G1): %s" % (newf or "none"))
    return d


def i18n_checks(urls, docs):
    en = next((u for u in urls if locale_of(u) == "en"), None)
    ru = next((u for u in urls if locale_of(u) == "ru"), None)
    if not (en and ru and en in docs and ru in docs):
        rep("INFO", "C1", "-", "EN and RU both needed for parity checks; skipped")
        return
    a, b = docs[en], docs[ru]

    def sig(d):
        c = {}
        for t, at in d.els:
            if t in ("h1", "h2", "h3", "a", "img", "button", "section", "li", "p", "nav"):
                c[t] = c.get(t, 0) + 1
        return c
    sa, sb = sig(a), sig(b)
    rep("PASS" if sa == sb else "FAIL", "C1", ru, "structure parity EN vs RU (counts of h1-3,a,img,button,section,li,p,nav): EN %s RU %s" % (sa, sb))
    ia = sorted(at["id"] for t, at in a.els if at.get("id")); ib = sorted(at["id"] for t, at in b.els if at.get("id"))
    rep("PASS" if ia == ib else "FAIL", "C1", ru, "same element ids in both locales (%d vs %d) diff %s" % (len(ia), len(ib), sorted(set(ia) ^ set(ib)) or "none"))
    la = [at.get("href") for t, at in a.els if t == "a"]; lb = [at.get("href") for t, at in b.els if t == "a"]
    rep("PASS" if len(la) == len(lb) else "FAIL", "C1", ru, "link count parity %d vs %d" % (len(la), len(lb)))
    # untranslated
    lat = []
    for tx in b.texts:
        if re.search(r"[\u0400-\u04FF]", tx):
            continue
        words = [w for w in re.findall(r"[A-Za-z]{3,}", tx) if w.upper() not in {x.upper() for x in BRAND_OK}]
        if words:
            lat.append(tx[:40])
    rep("PASS" if not lat else "WARN", "C3", ru, "RU text nodes with Latin words and no Cyrillic (untranslated?): %s" % (lat[:8] or "none"))
    attrs = []
    for t, at in b.els:
        for k in ("alt", "aria-label", "title", "placeholder"):
            val = at.get(k, "")
            if val and not re.search(r"[\u0400-\u04FF]", val) and [w for w in re.findall(r"[A-Za-z]{3,}", val) if w.upper() not in {x.upper() for x in BRAND_OK}]:
                attrs.append("%s %s=%r" % (t, k, val[:28]))
    rep("PASS" if not attrs else "FAIL", "C3", ru, "RU accessible names/attributes still English (screen-reader users hear them): %s" % (attrs[:8] or "none"))
    # head translation
    md_en = [x.get("content") for x in attr(a, "meta", name="description")]; md_ru = [x.get("content") for x in attr(b, "meta", name="description")]
    rep("PASS" if (a.title != b.title and md_en != md_ru) else "FAIL", "C13", ru, "title and meta description differ from EN (translated)")
    # expansion
    if len(a.texts) == len(b.texts):
        worst = []
        for x, y in zip(a.texts, b.texts):
            if len(x) >= 3 and len(y) / len(x) > 1.5:
                worst.append("%d->%d %r" % (len(x), len(y), x[:18]))
        tot = sum(len(x) for x in a.texts); tr = sum(len(x) for x in b.texts)
        rep("PASS" if tr / tot <= 1.3 else "WARN", "C4", ru, "RU/EN total text length ratio %.2f; strings above x1.5: %s" % (tr / tot, worst[:6] or "none"))
    else:
        rep("INFO", "C4", ru, "text node count differs (%d vs %d); pairwise expansion check skipped, total ratio %.2f" % (len(a.texts), len(b.texts), sum(map(len, b.texts)) / max(1, sum(map(len, a.texts)))))
    # terminology
    terms = ["AIVIS", "SANKORD", "EXSPECS"]
    ta, tb = " ".join(a.texts), " ".join(b.texts)
    bad = [t for t in terms if (t in ta) != (t in tb)]
    rep("PASS" if not bad else "FAIL", "C11", ru, "brand terms %s appear in both locales (mismatch: %s)" % (terms, bad or "none"))


def typography(url, d, loc):
    texts = d.texts + [at.get(k, "") for t, at in d.els for k in ("alt", "aria-label", "title") if at.get(k)]
    full = "\n".join(texts)
    if loc == "ru":
        straight = [t[:30] for t in texts if '"' in t]
        rep("PASS" if not straight else "FAIL", "C5", url, 'straight " in RU text (use «ёлочки»): %s' % (straight[:4] or "none"))
        curly = [t[:30] for t in texts if re.search(r"[\u201C\u201D]", t)]
        rep("PASS" if not curly else "WARN", "C5", url, "English curly quotes in RU text (nested level only: „лапки“): %s" % (curly[:4] or "none"))
        rep("PASS" if full.count("«") == full.count("»") else "FAIL", "C5", url, "« » balanced (%d/%d)" % (full.count("«"), full.count("»")))
        hy = [t[:40] for t in texts if re.search(r"\s[-\u2010\u2012]\s|\s--\s", t)]
        rep("PASS" if not hy else "FAIL", "C5", url, "hyphen used as dash (need em dash): %s" % (hy[:4] or "none"))
        en = [t[:40] for t in texts if re.search(r"\s\u2013\s", t)]
        rep("PASS" if not en else "WARN", "C5", url, "spaced en dash in RU (house style: em dash with nbsp before): %s" % (en[:4] or "none"))
        pre = [t[:40] for t in texts if re.search(r"[^\s\u00A0\u2009\u202F]\s\u2014", t) or re.search(r"[^\s]\u2014", t)]
        rep("PASS" if not pre else "WARN", "C5", url, "em dash not preceded by nbsp (line may start with the dash): %d nodes e.g. %s" % (len(pre), pre[:2]))
        shortw = re.compile(r"(?<![\w\u0400-\u04FF])(в|к|с|у|о|и|а|я|на|по|за|из|от|до|не|ни|об|во|со|ко|но|же|ли|бы|для|без|при|над|под)\s(?=[\w\u0400-\u04FF«])", re.I)
        hits = [t[:46] for t in texts if shortw.search(t)]
        rep("PASS" if not hits else "WARN", "C5", url, "short word followed by a normal space (orphan risk; use nbsp): %d nodes e.g. %s" % (len(hits), hits[:2]))
        dec = [t[:30] for t in texts if re.search(r"\d\.\d", t)]
        rep("PASS" if not dec else "WARN", "C7", url, "decimal point in RU text (RU uses comma): %s" % (dec[:4] or "none"))
        th = [t[:30] for t in texts if re.search(r"\d,\d{3}(?!\d)", t)]
        rep("PASS" if not th else "WARN", "C7", url, "comma thousands separator in RU (use nbsp): %s" % (th[:4] or "none"))
    else:
        dd = [t[:40] for t in texts if re.search(r"\s-\s|--", t)]
        rep("PASS" if not dd else "WARN", "C6", url, "spaced hyphen or -- in EN text (use em/en dash): %s" % (dd[:4] or "none"))
    endp = [t[-34:] for t in d.texts if len(t) > 50 and not re.search(r"[.!?:;…»\)\"”]$", t)]
    rep("PASS" if not endp else "WARN", "C6", url, "text blocks over 50 chars that end without terminal punctuation (copy defect or truncated string): %d e.g. %s" % (len(endp), endp[:4]))
    dots = [t[:30] for t in texts if "..." in t]
    rep("PASS" if not dots else "WARN", "C6", url, "three dots instead of the ellipsis character: %s" % (dots[:4] or "none"))
    dbl = [t[:30] for t in texts if re.search(r"  ", t)]
    rep("PASS" if not dbl else "WARN", "C6", url, "double spaces: %s" % (dbl[:4] or "none"))
    ee = [t[:30] for t in texts if re.search(r"\s[,.;:!?]", t)]
    rep("PASS" if not ee else "WARN", "C6", url, "space before punctuation: %s" % (ee[:4] or "none"))


def headers_checks(url, hdrs, hf):
    """Headers from the live response AND from the Cloudflare _headers file (the deploy truth)."""
    want = [("strict-transport-security", "F4", lambda v: "max-age" in v and int(re.search(r"max-age=(\d+)", v).group(1)) >= 31536000),
            ("x-content-type-options", "F5", lambda v: v.strip().lower() == "nosniff"),
            ("referrer-policy", "F6", lambda v: bool(v)),
            ("permissions-policy", "F7", lambda v: bool(v)),
            ("cross-origin-opener-policy", "F8", lambda v: bool(v))]
    live = {}
    for k, cid, fn in want:
        live[k] = hdrs.get(k)
    server = hdrs.get("server", "")
    src = {}
    if hf and os.path.exists(hf):
        cur = None
        for line in open(hf, encoding="utf-8").read().splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            if not line.startswith((" ", "\t")):
                cur = line.strip(); src.setdefault(cur, {})
            elif cur is not None and ":" in line:
                k, v = line.strip().split(":", 1)
                src[cur][k.strip().lower()] = v.strip()
    allrules = {}
    for pat in ("/*",):
        allrules.update(src.get(pat, {}))
    for k, cid, fn in want:
        v = hdrs.get(k) or allrules.get(k)
        where = "live" if hdrs.get(k) else ("_headers file" if allrules.get(k) else "")
        ok = False
        try:
            ok = bool(v) and fn(v)
        except Exception:
            ok = False
        rep("PASS" if ok else "FAIL", cid, url, "%s: %s%s" % (k, (v or "MISSING"), " [%s]" % where if where else ""))
    csp_h = hdrs.get("content-security-policy") or allrules.get("content-security-policy")
    fa = (csp_h and "frame-ancestors" in csp_h) or hdrs.get("x-frame-options") or allrules.get("x-frame-options")
    rep("PASS" if fa else "FAIL", "F3", url, "clickjacking protection (frame-ancestors in a HEADER; ignored in a meta CSP): %s" % ("found" if fa else "MISSING"))
    if not hf or not os.path.exists(hf or ""):
        rep("INFO", "F4", url, "no _headers file found; pass --headers-file (live server here is %s and sets no security headers)" % (server or "unknown"))
    cc = hdrs.get("cache-control") or allrules.get("cache-control")
    rep("INFO", "D8", url, "Cache-Control on the page: %s (live) -- also check /assets/* in the _headers file: %s" % (hdrs.get("cache-control"), src.get("/assets/*", "no rule")))
    enc = hdrs.get("content-encoding")
    rep("INFO", "D8", url, "content-encoding live: %s (Cloudflare compresses at the edge; verify on the deployed host with curl -H 'accept-encoding: br')" % enc)
    return src


def site_files(base, docs):
    st, h, body = fetch(base + "robots.txt")
    rep("PASS" if st == 200 and b"Sitemap:" in body else "FAIL", "E5", base, "robots.txt status %s, has Sitemap line: %s" % (st, b"Sitemap:" in body))
    st, h, body = fetch(base + "sitemap.xml")
    rep("PASS" if st == 200 else "FAIL", "E5", base, "sitemap.xml status %s" % st)
    txt = body.decode("utf-8", "replace")
    subs = re.findall(r"<loc>([^<]+)</loc>", txt)
    allloc = list(subs)
    for s in subs:
        if s.endswith(".xml"):
            p = urllib.parse.urlparse(s).path
            st2, h2, b2 = fetch(base.rstrip("/") + p)
            if st2 == 200:
                allloc += re.findall(r"<loc>([^<]+)</loc>", b2.decode("utf-8", "replace"))
    pages = [x for x in allloc if not x.endswith(".xml")]
    rep("INFO", "E5", base, "sitemap lists %d page URLs (%s ...)" % (len(pages), ", ".join(pages[:3])))
    for pth in ("/", "/ru/"):
        full = "https://aivis.one" + pth
        rep("PASS" if full in pages else "WARN", "E5", base, "sitemap contains %s" % full)
    st, h, b = fetch(base + "this-page-does-not-exist-%d/" % os.getpid())
    rep("PASS" if st == 404 else "WARN", "H8", base, "unknown path returns 404 (got %s); deployed host must also serve a 404 page" % st)


def link_checks(url, d, args):
    base = url
    seen, bad, ext_bad, rootabs = set(), [], [], []
    for t, a in d.els:
        if t != "a":
            continue
        h = a.get("href", "")
        if not h or h.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if h.startswith("/") and not h.startswith("//"):
            rootabs.append(h)
            continue  # app routes (for example /login) are not files of the static build; checked by hand
        full = urllib.parse.urljoin(base, h)
        full = full.split("#")[0]
        if full in seen:
            continue
        seen.add(full)
        u = urllib.parse.urlparse(full)
        if u.netloc == urllib.parse.urlparse(base).netloc:
            st, _, _ = fetch(full, "GET")
            if st != 200:
                bad.append("%s -> %s" % (h, st))
        elif not args.no_external:
            st, _, _ = fetch(full, "HEAD", 10)
            if st == 0 or st >= 400:
                ext_bad.append("%s -> %s" % (u.netloc, st))
    rep("PASS" if not bad else "FAIL", "H1", url, "%d internal file links resolve; broken: %s" % (len(seen), bad or "none"))
    rep("INFO", "H1", url, "root-absolute app routes not fetched (judge by hand on the deployed host): %s" % (sorted(set(rootabs)) or "none"))
    if not args.no_external:
        rep("PASS" if not ext_bad else "WARN", "H2", url, "external links answer a HEAD request (st 0 = no response from here: not deployed yet, DNS, TLS or firewall): %s" % (ext_bad or "all ok"))
    ext_blank = [a.get("href") for t, a in d.els if t == "a" and a.get("target") == "_blank" and "noopener" not in a.get("rel", "") and "noreferrer" not in a.get("rel", "")]
    rep("PASS" if not ext_blank else "WARN", "H2", url, 'target=_blank without rel=noopener: %s (modern browsers imply it; keep explicit)' % (ext_blank or "none"))


# ----------------------------------------------------------------- browser checks
ALL_PARTS = {"layout", "load", "opacity", "contrast", "motion", "nojs", "textspacing", "kbd", "anchors", "ui", "rhythm"}


def browser_checks(cdp, url, args, loc, parts=None):
    P = ALL_PARTS if parts is None else parts
    shots = os.path.join(HERE, "shots")
    # network bookkeeping helper
    def net_summary():
        reqs, fin, resp = {}, {}, {}
        for e in cdp.events:
            m, p = e["method"], e.get("params", {})
            if m == "Network.requestWillBeSent":
                reqs[p["requestId"]] = p["request"]["url"]
            elif m == "Network.loadingFinished":
                fin[p["requestId"]] = p.get("encodedDataLength", 0)
            elif m == "Network.responseReceived":
                resp[p["requestId"]] = (p["response"]["status"], p["response"].get("mimeType"), p["type"], p["response"].get("headers", {}))
        return reqs, fin, resp

    origin = urllib.parse.urlparse(url)
    # --- per-viewport layout
    if "layout" in P:
        for w in VIEWPORTS:
            mobile = w < 768
            h = 800 if w >= 768 else 780
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 2 if mobile else 1, "mobile": mobile})
            cdp.navigate(url, 0.8)
            L = cdp.ev(LAYOUT_JS.replace("__W__", str(w)))
            tag = "%dpx" % w
            rep("PASS" if L["sw"] <= L["W"] + 1 and not L["off"] else "FAIL", "A2", url, "%s no horizontal scroll (scrollWidth %d vs %d) %s" % (tag, L["sw"], L["W"], L["off"] or ""))
            sm = [x for x in L["small"] if x["w"] < 24 or x["h"] < 24]
            rep("PASS" if not sm else "FAIL", "A3", url, "%s targets under 24x24 CSS px (WCAG 2.5.8 AA): %s" % (tag, ["%s '%s' %sx%s" % (x["n"], x["t"], x["w"], x["h"]) for x in sm[:4]] or "none"))
            if w in (360, 390):
                s44 = [x for x in L["small"] if (x["w"] < 44 or x["h"] < 44)]
                rep("PASS" if not s44 else "WARN", "A3", url, "%s targets under 44x44 (Apple HIG; Material uses 48): %d of %d e.g. %s" % (tag, len(s44), len(L["small"]), ["%s '%s' %sx%s" % (x["n"], x["t"], x["w"], x["h"]) for x in s44[:3]]))
            if w in (320, 390, 1280):
                rep("PASS" if not L["tiny"] else "FAIL", "A5", url, "%s no text under 12px: %s" % (tag, L["tiny"] or "ok"))
                mx = max([x["max"] for x in L["lines"]] or [0])
                mn = [x["max"] for x in L["lines"] if x["lines"] >= 2]
                rep("PASS" if mx <= 80 else "WARN", "A6", url, "%s longest line %d chars over %d paragraphs (HOUSE number: 80 is WCAG 1.4.8 AAA, target 45-75, owner decides); longest-per-paragraph %s" % (tag, mx, len(L["lines"]), sorted([x["max"] for x in L["lines"]])[-4:]))
                rep("PASS" if not L["orph"] else "WARN", "I2", url, "%s last line of a heading/paragraph is one word: %s" % (tag, L["orph"][:4] or "none"))
            if w == 390:
                bodyfs = [fs for fs, c in L["fonts"].items() if float(fs) >= 16]
                big = sum(c for fs, c in L["fonts"].items() if float(fs) >= 16)
                tot = sum(L["fonts"].values())
                rep("PASS" if tot and big / tot >= 0.5 else "WARN", "A5", url, "390px: %d of %d text elements at 16px or larger; sizes in use %s" % (big, tot, sorted(float(k) for k in L["fonts"])))
                rep("INFO", "I6", url, "distinct font sizes: %d (a type scale should stay near 8-10)" % len(L["fonts"]))
            if w == 390:
                ims = L["imgs"]
                noload = [i["src"] for i in ims if not i["ok"]]
                rep("PASS" if not noload else "FAIL", "D7", url, "all %d visible images loaded: %s" % (len(ims), noload or "ok"))
                over = ["%s %dpx for %dpx box" % (i["src"], i["nw"], i["rw"]) for i in ims if i["nw"] > i["rw"] * i["dpr"] * 1.5 and i["rw"] > 0 and not i["src"].endswith(".svg")]
                rep("PASS" if not over else "WARN", "D7", url, "images no larger than 1.5x of rendered*DPR (wasted bytes): %s" % (over or "none"))
            if args.shots:
                os.makedirs(shots, exist_ok=True)
                r = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
                open(os.path.join(shots, "%s-%s-%d.png" % (loc, "shot", w)), "wb").write(base64.b64decode(r["data"]))
    # --- orientation
    if "layout" in P:
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 812, "height": 375, "deviceScaleFactor": 2, "mobile": True})
        cdp.navigate(url, 0.6)
        L = cdp.ev(LAYOUT_JS.replace("__W__", str(812)))
        rep("PASS" if L["sw"] <= L["W"] + 1 else "FAIL", "A8", url, "landscape 812x375 no horizontal scroll (%d vs %d)" % (L["sw"], L["W"]))
    # --- load metrics on mobile and desktop
    if "load" in P:
        for w, mobile, name in ((390, True, "mobile 390"), (1280, False, "desktop 1280")):
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": 800, "deviceScaleFactor": 2 if mobile else 1, "mobile": mobile})
            cdp.navigate(url, 2.0)
            reqs, fin, resp = net_summary()
            m = cdp.ev("window.__m")
            total = sum(fin.values())
            cnt = len(reqs)
            third = sorted(set(urllib.parse.urlparse(u).netloc for u in reqs.values() if urllib.parse.urlparse(u).netloc not in (origin.netloc, "") and not u.startswith("data:")))
            errs = ["%s %s" % (v[0], reqs.get(k, "")[-40:]) for k, v in resp.items() if v[0] >= 400]
            rep("PASS" if m["lcp"] and m["lcp"] <= 2500 else ("FAIL" if m["lcp"] else "WARN"), "D1", url, "%s LCP %.0f ms (lab, no throttling; target <= 2500)" % (name, m["lcp"]))
            rep("PASS" if m["cls"] <= 0.1 else "FAIL", "D3", url, "%s CLS %.3f (target <= 0.1)" % (name, m["cls"]))
            rep("PASS" if m["longTasks"] < 200 else "WARN", "D2", url, "%s total blocking-time proxy %.0f ms from long tasks (INP needs a real interaction; keep main-thread work near zero)" % (name, m["longTasks"]))
            rep("PASS" if total <= 500 * 1024 else ("WARN" if total <= 1024 * 1024 else "FAIL"), "D4", url, "%s transferred %d KB in %d requests (house proposal: <= 500 KB soft, 1 MB hard; owner's number)" % (name, total // 1024, cnt))
            rep("PASS" if not third else "FAIL", "D5", url, "%s third-party hosts contacted: %s" % (name, third or "none"))
            rep("PASS" if not errs else "FAIL", "H1", url, "%s sub-resource errors: %s" % (name, errs or "none"))
            rep("PASS" if not m["csp"] else "FAIL", "F11", url, "%s CSP violations at runtime: %s" % (name, m["csp"] or "none"))
            rep("PASS" if not m["errs"] else "FAIL", "H11", url, "%s uncaught JS errors: %s" % (name, m["errs"] or "none"))
            console = [e["params"] for e in cdp.events if e["method"] in ("Log.entryAdded",) and e["params"]["entry"]["level"] in ("error", "warning")]
            console = [c["entry"]["text"][:80] for c in console]
            rep("PASS" if not console else "WARN", "H11", url, "%s console errors/warnings: %s" % (name, console[:3] or "none"))
            fonts = [(v[2], reqs[k]) for k, v in resp.items() if v[2] == "Font"]
            ff = [os.path.basename(u) for t, u in fonts]
            notw2 = [f for f in ff if not f.lower().endswith(".woff2")]
            if name.startswith("mobile"):
                rep("PASS" if not notw2 else "FAIL", "D6", url, "fonts loaded: %s (WOFF2 only)" % (ff or "none, system fonts"))
                fsz = [(os.path.basename(reqs[k]), fin.get(k, 0) // 1024) for k, v in resp.items() if v[2] == "Font"]
                rep("INFO", "D6", url, "font sizes KB (subset check: Latin+Cyrillic under ~60 KB each): %s" % fsz)
            if name.startswith("mobile"):
                doc = [v for k, v in resp.items() if v[2] == "Document"]
                if doc:
                    dh = dict((a.lower(), b) for a, b in doc[0][3].items())
                    if not hasattr(browser_checks, "hdr"):
                        browser_checks.hdr = {}
                    browser_checks.hdr[url] = dh
    # --- effective opacity of revealed content (I9)
    if "opacity" in P:
        for w, mobile in ((390, True), (1280, False)):
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": 800, "deviceScaleFactor": 2 if mobile else 1, "mobile": mobile})
            cdp.navigate(url, 0.8)
            O = cdp.ev(OPACITY_JS)
            rep("PASS" if not O["bad"] else "FAIL", "I9", url, "%dpx after scrolling to the end, animations NOT forced: %d reveal/animated elements checked, effective opacity below 1 on %d: %s" % (w, O["n"], len(O["bad"]), O["bad"][:5] or "none"))
    # --- contrast both themes
    if "contrast" in P:
        for scheme in ("light", "dark"):
            cdp.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": scheme}]})
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 780, "deviceScaleFactor": 2, "mobile": True})
            cdp.ev("try{localStorage.removeItem('aivis-theme')}catch(e){}")
            cdp.navigate(url, 0.8)
            theme = cdp.ev("document.documentElement.getAttribute('data-theme')")
            # scroll through so reveal-on-scroll items finish, then finish animations: contrast must be measured at rest
            cdp.ev("(async function(){var h=document.documentElement.scrollHeight;for(var y=0;y<h;y+=300){window.scrollTo(0,y);await new Promise(function(r){setTimeout(r,120)});}await new Promise(function(r){setTimeout(r,900)});document.getAnimations().forEach(function(a){try{a.finish()}catch(e){}});window.scrollTo(0,0);return 1})()")
            C = cdp.ev(CONTRAST_JS)
            rep("PASS" if theme == scheme else "FAIL", "H4", url, "%s: data-theme set before paint from system preference -> %s" % (scheme, theme))
            rep("PASS" if not C["fails"] else "FAIL", "B7", url, "%s theme contrast (flat backgrounds): %d text elements checked, %d not measurable (gradient/image), failing: %s" % (scheme, C["checked"], C["skipped"], C["fails"][:5] or "none"))
        cdp.call("Emulation.setEmulatedMedia", {"features": []})
    # --- reduced motion
    if "motion" in P:
        cdp.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
        cdp.navigate(url, 1.2)
        anims = cdp.ev("document.getAnimations().filter(function(a){return a.playState==='running' && (a.effect.getComputedTiming().iterations===Infinity || a.effect.getComputedTiming().duration>600)}).map(function(a){return (a.animationName||a.transitionProperty||a.constructor.name)+' '+a.effect.getComputedTiming().duration})")
        rep("PASS" if not anims else "FAIL", "B9", url, "reduce-motion: long or infinite animations still running: %s" % (anims or "none"))
        cdp.call("Emulation.setEmulatedMedia", {"features": []})
    # --- no-JS
    if "nojs" in P:
        cdp.call("Emulation.setScriptExecutionDisabled", {"value": True})
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 780, "deviceScaleFactor": 2, "mobile": True})
        cdp.navigate(url, 0.8)
        n = cdp.ev("(document.querySelector('main')||document.body).innerText.trim().length")
        rep("PASS" if n and n > 500 else "FAIL", "G4", url, "JavaScript disabled: main text still readable (%s chars)" % n)
        cdp.call("Emulation.setScriptExecutionDisabled", {"value": False})
    # --- text spacing 1.4.12 and RTL simulation
    if "textspacing" in P:
        for w in (390, 1280):
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": 800, "deviceScaleFactor": 1, "mobile": w < 768})
            cdp.navigate(url, 0.6)
            cdp.ev("(function(){var s=new CSSStyleSheet();s.replaceSync('*{line-height:1.5 !important;letter-spacing:.12em !important;word-spacing:.16em !important} p{margin-bottom:2em !important}');document.adoptedStyleSheets=[s];})()")
            L = cdp.ev(LAYOUT_JS.replace("__W__", str(w)))
            clip = cdp.ev("[].slice.call(document.querySelectorAll('main *')).filter(function(e){var c=getComputedStyle(e);var dt=e.closest('details');return (c.overflow==='hidden'||c.overflowY==='hidden')&&e.scrollHeight>e.clientHeight+2&&e.clientHeight>0&&!(dt&&!dt.open)}).slice(0,4).map(function(e){return e.tagName+'.'+e.className})")
            rep("PASS" if L["sw"] <= L["W"] + 1 and not clip else "FAIL", "A10", url, "%dpx text spacing 1.4.12 (lh 1.5, ls .12em, ws .16em): overflow %s, clipped %s" % (w, L["off"] or "none", clip or "none"))
            cdp.navigate(url, 0.6)
            cdp.ev("document.documentElement.setAttribute('dir','rtl')")
            L = cdp.ev(LAYOUT_JS.replace("__W__", str(w)))
            rep("PASS" if L["sw"] <= L["W"] + 1 and not L["off"] else "FAIL", "C8", url, "%dpx dir=rtl simulation: overflow %s (scrollWidth %d vs %d)" % (w, L["off"] or "none", L["sw"], L["W"]))
    # --- keyboard focus order
    if "kbd" in P:
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False})
        cdp.navigate(url, 0.6)
        seq, novis, covered, partial, seen, stop = [], [], [], [], set(), "60 presses reached"
        for i in range(60):
            cdp.key("Tab", "Tab", 9)
            cdp.pump(0.45)  # let smooth scrolling settle before measuring what covers the control
            f = cdp.ev(FOCUS_JS)
            if not f:
                stop = "focus left the document (end of tab order)"
                break
            if f["key"] in seen:
                stop = "focus cycled back to %s" % f["key"][:30]
                break
            seen.add(f["key"])
            seq.append(f["tag"] + ":" + f["name"])
            if not f["vis"]:
                novis.append("%s '%s'" % (f["tag"], f["name"]))
            if f["covered"]:
                covered.append("%s '%s'" % (f["tag"], f["name"]))
            elif f.get("partial"):
                partial.append("%s '%s'" % (f["tag"], f["name"]))
        rep("PASS" if len(seq) >= 5 else "FAIL", "B8", url, "keyboard: Tab reached %d distinct controls (%s); first %s, last %s" % (len(seq), stop, seq[:3], seq[-3:]))
        rep("PASS" if not novis else "FAIL", "B8", url, "focus indicator present (outline or box-shadow) on every stop; missing: %s" % (novis or "none"))
        rep("PASS" if not covered else "FAIL", "B8", url, "focused control never ENTIRELY covered by another element (2.4.11 AA): %s" % (covered or "none"))
        rep("PASS" if not partial else "WARN", "B8", url, "focused control partly covered (sticky header / overlay; 2.4.12 AAA, tune scroll-padding-top): %s" % (partial or "none"))
    # --- anchor offset under sticky header
    if "anchors" in P:
        cdp.navigate(url, 0.4)
        anc = cdp.ev("(function(){var a=[].slice.call(document.querySelectorAll('a[href^=\"#\"]')).map(function(x){return x.getAttribute('href')}).filter(function(h){return h.length>1&&document.querySelector(h)}); var out=[]; var hd=document.querySelector('header'); var hb=hd?hd.getBoundingClientRect().bottom:0; var pos=hd?getComputedStyle(hd).position:''; a.slice(0,6).forEach(function(h){document.querySelector(h).scrollIntoView(); var t=document.querySelector(h).getBoundingClientRect().top; out.push(h+' top '+Math.round(t)+' header '+Math.round(hb)+' '+pos+(t+1<hb&&(pos==='sticky'||pos==='fixed')?' HIDDEN':''));}); return out;})()")
        bad = [x for x in anc if "HIDDEN" in x]
        rep("PASS" if not bad else "FAIL", "H7", url, "section anchors not hidden under sticky header (scroll-margin-top): %s" % (bad or anc[:3]))
    # --- drawer, theme, language switch (mobile)
    if "ui" in P:
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 780, "deviceScaleFactor": 2, "mobile": True})
        cdp.navigate(url, 0.6)
        pt = cdp.ev("(function(){var b=document.querySelector('[data-ls-menu-open]'); if(!b) return null; var r=b.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]})()")
        if pt:
            cdp.click_xy(pt[0], pt[1]); cdp.pump(0.5)
            st = cdp.ev("(function(){var d=document.querySelector('[data-ls-drawer]'), b=document.querySelector('[data-ls-menu-open]'); var r=d.getBoundingClientRect(); return {exp:b.getAttribute('aria-expanded'), vis:r.width>0&&r.left<innerWidth&&r.right>0&&getComputedStyle(d).visibility!=='hidden', inside:d.contains(document.activeElement), links:d.querySelectorAll('a').length}})()")
            rep("PASS" if st["exp"] == "true" and st["vis"] else "FAIL", "H5", url, "drawer opens on tap: aria-expanded=%s visible=%s links=%s" % (st["exp"], st["vis"], st["links"]))
            rep("PASS" if st["inside"] else "WARN", "B12", url, "focus moves into the dialog on open: %s" % st["inside"])
            cdp.key("Escape", "Escape", 27); cdp.pump(0.5)
            st2 = cdp.ev("(function(){var d=document.querySelector('[data-ls-drawer]'), b=document.querySelector('[data-ls-menu-open]'); var r=d.getBoundingClientRect(); return {exp:b.getAttribute('aria-expanded'), vis:r.width>0&&r.left<innerWidth&&r.right>0&&getComputedStyle(d).visibility!=='hidden', back:document.activeElement===b}})()")
            rep("PASS" if st2["exp"] == "false" and not st2["vis"] else "FAIL", "B12", url, "Escape closes the drawer: aria-expanded=%s visible=%s" % (st2["exp"], st2["vis"]))
            rep("PASS" if st2["back"] else "WARN", "B12", url, "focus returns to the menu button after close: %s" % st2["back"])
        else:
            rep("INFO", "H5", url, "no [data-ls-menu-open] on this page; drawer check skipped")
        pt = cdp.ev("(function(){var b=document.querySelector('[data-ls-theme-toggle]'); if(!b) return null; var r=b.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2, document.documentElement.getAttribute('data-theme')]})()")
        if pt:
            cdp.click_xy(pt[0], pt[1]); cdp.pump(0.4)
            after = cdp.ev("({t:document.documentElement.getAttribute('data-theme'), p:document.querySelector('[data-ls-theme-toggle]').getAttribute('aria-pressed'), s:(function(){try{return localStorage.getItem('aivis-theme')}catch(e){return 'ERR'}})()})")
            rep("PASS" if after["t"] != pt[2] and after["s"] == after["t"] else "FAIL", "H4", url, "theme toggle flips %s->%s, saved to storage=%s, aria-pressed=%s" % (pt[2], after["t"], after["s"], after["p"]))
            cdp.navigate(url, 0.4)
            again = cdp.ev("document.documentElement.getAttribute('data-theme')")
            rep("PASS" if again == after["t"] else "FAIL", "H4", url, "theme persists across reload: %s" % again)
            cdp.ev("try{localStorage.removeItem('aivis-theme')}catch(e){}")
        sw = cdp.ev("(function(){var s=document.querySelector('[data-ls-lang-switch]'); if(!s) return null; var r=s.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]})()")
        if sw:
            cdp.click_xy(sw[0], sw[1]); cdp.pump(0.4)
            info = cdp.ev("(function(){var d=document.querySelector('[data-ls-lang]'); var l=[].slice.call(d.querySelectorAll('a')).map(function(a){var r=a.getBoundingClientRect();return a.getAttribute('hreflang')+' '+Math.round(r.width)+'x'+Math.round(r.height)+(a.getAttribute('aria-current')?' current':'')}); return {open:d.open||d.hasAttribute('open'), l:l}})()")
            rep("PASS" if info["open"] and len(info["l"]) >= 2 else "FAIL", "H3", url, "language menu opens on tap, entries %s" % info["l"])
    # --- spacing rhythm
    if "rhythm" in P:
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False})
        cdp.navigate(url, 0.6)
        S = cdp.ev(SPACING_JS)
        rep("PASS" if not S["bad"] else "WARN", "I3", url, "section padding on a 4px grid: off-grid %s; values in use %s" % (S["bad"][:4] or "none", S["vals"]))
        rep("PASS" if not S["cards"] else "WARN", "I4", url, "sibling cards in one row have equal height: %s" % (S["cards"][:4] or "ok"))
    return getattr(browser_checks, "hdr", {}).get(url, {})


def start_browser(args):
    chrome = find_chrome(args.chrome)
    if not chrome:
        return None
    prof = os.path.join(HERE, ".chrome-profile-%d" % os.getpid())
    os.makedirs(prof, exist_ok=True)
    proc = subprocess.Popen([chrome, "--headless=new", "--remote-debugging-port=0", "--remote-allow-origins=*", "--user-data-dir=" + prof,
                             "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--hide-scrollbars", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        portfile = os.path.join(prof, "DevToolsActivePort")
        for _ in range(100):
            if os.path.exists(portfile) and open(portfile).read().strip():
                break
            time.sleep(0.2)
        port = int(open(portfile).read().split()[0])
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=10).read())
        page = [t for t in tabs if t.get("type") == "page"][0]
        cdp = CDP(WS("127.0.0.1", port, "/devtools/page/" + page["id"]))
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": INIT_JS})
        ver = cdp.call("Browser.getVersion")
        return proc, prof, cdp, ver.get("product")
    except Exception:
        stop_browser((proc, prof, None, None))
        raise


def stop_browser(h):
    proc, prof = h[0], h[1]
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.terminate()
    time.sleep(1.0)
    shutil.rmtree(prof, ignore_errors=True)


def static_run(u, args, docs, live_hdrs=None):
    st, h, body = fetch(u)
    if st == 0:
        rep("FAIL", "H0", u, "unreachable: %s" % body.decode(errors="replace"))
        return None
    d = static_checks(u, body.decode("utf-8", "replace"), h, st, args, docs)
    if live_hdrs is not None:
        live_hdrs[u] = h
    typography(u, d, locale_of(u))
    link_checks(u, d, args)
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*", default=DEFAULT_URLS)
    ap.add_argument("--chrome")
    ap.add_argument("--headers-file", default=os.path.join(HERE, "..", "site", "dist", "_headers"))
    ap.add_argument("--skip-browser", action="store_true")
    ap.add_argument("--shots", action="store_true", help="save full-page PNGs per viewport to guides/shots/")
    ap.add_argument("--no-external", action="store_true", help="do not HEAD external links")
    ap.add_argument("--self-test", action="store_true", help="run every FAIL-class check against planted-defect fixtures and a clean control")
    args = ap.parse_args()
    args.headers_file = os.path.normpath(args.headers_file)
    if args.self_test:
        sys.exit(self_test(args))
    print("run-checks: %s | headers file: %s (%s)" % (", ".join(args.urls), args.headers_file, "found" if os.path.exists(args.headers_file) else "not found"))
    docs, live_hdrs = {}, {}
    for u in args.urls:
        static_run(u, args, docs, live_hdrs)
    i18n_checks(args.urls, docs)
    if args.urls and args.urls[0] in docs:
        p = urllib.parse.urlparse(args.urls[0])
        site_files("%s://%s/" % (p.scheme, p.netloc), docs)
        headers_checks(args.urls[0], live_hdrs[args.urls[0]], args.headers_file)
    if not args.skip_browser:
        h = None
        try:
            h = start_browser(args)
            if not h:
                rep("FAIL", "G2", "-", "Chrome/Edge not found; pass --chrome PATH or use --skip-browser")
            else:
                cdp = h[2]
                rep("INFO", "G1", "-", "engine under test: %s (Chromium only; Gecko and WebKit are manual, see guide G1)" % h[3])
                for u in args.urls:
                    if u not in docs:
                        continue
                    try:
                        browser_checks(cdp, u, args, locale_of(u))
                    except Exception as e:  # keep going, but never silently
                        rep("FAIL", "G2", u, "browser checks aborted: %s: %s" % (type(e).__name__, str(e)[:160]))
                cdp.call("Emulation.clearDeviceMetricsOverride")
        except Exception as e:
            rep("FAIL", "G2", "-", "browser harness failed: %s: %s" % (type(e).__name__, str(e)[:200]))
        finally:
            if h:
                stop_browser(h)
    n = {}
    for s, *_ in RESULTS:
        n[s] = n.get(s, 0) + 1
    print("\nSUMMARY: %s" % ", ".join("%s %d" % (k, n[k]) for k in ("PASS", "FAIL", "WARN", "INFO") if k in n))
    fails = [(c, u, m) for s, c, u, m in RESULTS if s == "FAIL"]
    for c, u, m in fails:
        print("FAIL %-4s %-26s %s" % (c, short(u), m))
    sys.exit(1 if fails else 0)


# ----------------------------------------------------------------- self-test: planted defects
FIXDIR = os.path.join(HERE, "fixtures")


def _png(w, h, noise):
    raw = b"".join(b"\x00" + (os.urandom(w * 3) if noise else b"\xff" * (w * 3)) for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 0 if noise else 6)) + chunk(b"IEND", b"")


def _fill_hashes(text):
    def h(x):
        return "'sha256-%s'" % base64.b64encode(hashlib.sha256(x.replace("\r\n", "\n").encode("utf-8")).digest()).decode()
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", text, re.S)
    styles = re.findall(r"<style[^>]*>(.*?)</style>", text, re.S)
    return text.replace("__H_SCRIPT__", " ".join(h(x) for x in scripts) or "'none'").replace("__H_STYLE__", " ".join(h(x) for x in styles) or "'none'")


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    PNG_SLOW = None
    PNG_NOISE = None
    PORT = 0

    def log_message(self, *a):
        pass

    def _send(self, code, ctype, data):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.endswith("/slow.png"):
            time.sleep(3.0)
            return self._send(200, "image/png", FixtureHandler.PNG_SLOW)
        if path.endswith("/weight.png"):
            return self._send(200, "image/png", FixtureHandler.PNG_NOISE)
        if path.endswith(".ttf"):
            return self._send(200, "font/ttf", b"\x00" * 300)
        fp = os.path.normpath(os.path.join(FIXDIR, path.lstrip("/").replace("/", os.sep)))
        if not fp.startswith(FIXDIR) or not os.path.isfile(fp):
            return self._send(404, "text/plain", b"not found")
        data = open(fp, "rb").read()
        if fp.endswith(".html"):
            text = data.decode("utf-8").replace("__PORT__", str(FixtureHandler.PORT))
            return self._send(200, "text/html; charset=utf-8", _fill_hashes(text).encode("utf-8"))
        ctype = "text/plain" if fp.endswith(".txt") else "application/xml" if fp.endswith(".xml") else "application/octet-stream"
        return self._send(200, ctype, data)


# (check id, status that must fire, fixture key, message substring, planted defect)
EXPECT = [
    ("H0", "FAIL", "missing", "HTTP status", "page does not exist (404)"),
    ("B1", "FAIL", "en", "lang=", 'html lang="fr" on an English page'),
    ("E2", "FAIL", "en", "meta description", "no meta description"),
    ("E3", "FAIL", "en", "canonical", "no canonical link"),
    ("E4", "FAIL", "en", "hreflang set", "hreflang lists only en"),
    ("E6", "FAIL", "en", "og:image", "no og:image"),
    ("E8", "FAIL", "en", "robots meta", "meta robots noindex"),
    ("A1", "FAIL", "en", "viewport", "viewport has user-scalable=no"),
    ("A4", "FAIL", "en", "viewport-fit", "viewport-fit=cover without env(safe-area-inset-*)"),
    ("B3", "FAIL", "en", "h1 count", "two h1 elements"),
    ("B3", "FAIL", "en", "never skip", "h1 to h4 level jump"),
    ("B4", "FAIL", "en", "landmarks", "no nav and no footer landmark"),
    ("B5", "FAIL", "en", "missing alt", "img without alt"),
    ("D7", "FAIL", "en", "width+height", "img without width and height"),
    ("B11", "FAIL", "en", "duplicates", "duplicate id"),
    ("B11", "FAIL", "en", "aria-controls", "aria-controls pointing at nothing"),
    ("H1", "FAIL", "en", "anchors", "href=#nope"),
    ("H1", "FAIL", "en", "internal file links", "link to a missing page"),
    ("F1", "FAIL", "en", "unsafe", "CSP with 'unsafe-inline' in script-src"),
    ("F2", "FAIL", "en", "object-src", "CSP without object-src none"),
    ("F2", "FAIL", "en", "base-uri", "CSP without base-uri"),
    ("F9", "FAIL", "en", "event handlers", "inline onclick"),
    ("F9", "FAIL", "en", "style=", "style attribute"),
    ("F10", "FAIL", "en", "unhashed", "inline blocks not covered by a CSP hash"),
    ("D5", "FAIL", "en", "markup", "image from another host in the markup"),
    ("B9", "FAIL", "en", "CSS has motion", "infinite animation, no prefers-reduced-motion rule"),
    ("A2", "FAIL", "en", "320px", "900 px wide block"),
    ("A8", "FAIL", "en", "landscape", "900 px wide block, landscape phone"),
    ("A3", "FAIL", "en", "24x24", "10x10 px link target"),
    ("A5", "FAIL", "en", "under 12px", "9 px text"),
    ("A6", "WARN", "en", "longest line", "paragraph about 150 characters per line"),
    ("A10", "FAIL", "en", "text spacing", "fixed-height box with overflow hidden"),
    ("C8", "FAIL", "en", "dir=rtl", "block that is 1500 px wide only under dir=rtl"),
    ("B7", "FAIL", "en", "contrast", "#bbb text on white"),
    ("B8", "FAIL", "en", "indicator", "link with outline:none on focus"),
    ("B8", "FAIL", "en", "ENTIRELY", "focusable link fully covered by a fixed box"),
    ("D1", "FAIL", "en", "LCP", "hero image delayed 3 s"),
    ("D3", "FAIL", "en", "CLS", "400 px banner inserted at the top after 400 ms"),
    ("D4", "FAIL", "en", "transferred", "1.3 MB image"),
    ("D5", "FAIL", "en", "hosts contacted", "request to localhost:PORT, another origin"),
    ("D6", "FAIL", "en", "fonts loaded", "font served as .ttf"),
    ("H1", "FAIL", "en", "sub-resource", "image that returns 404"),
    ("H11", "FAIL", "en", "uncaught", "script that throws"),
    ("G4", "FAIL", "en", "JavaScript disabled", "main content created by script"),
    ("H4", "FAIL", "en", "before paint", "no theme preboot script"),
    ("H4", "FAIL", "en", "theme toggle", "toggle that does not save the choice"),
    ("H5", "FAIL", "en", "drawer opens", "menu button sets aria-expanded but nothing opens"),
    ("B12", "FAIL", "en", "Escape", "drawer state never closes on Escape"),
    ("H3", "FAIL", "en", "language menu", "language switch that never opens"),
    ("H7", "FAIL", "en", "anchors not hidden", "sticky header without scroll-margin"),
    ("I9", "FAIL", "en", "effective opacity", "element with a reveal class stuck at opacity .6"),
    ("I10", "FAIL", "en", "counsel/review marker", "an HTML comment carrying a [COUNSEL ...] marker"),
    ("I10", "FAIL", "en", "draft word", "the word draft in an HTML comment"),
    ("I10", "FAIL", "en", "TODO marker", "TODO in an HTML comment"),
    ("I10", "FAIL", "en", "row/task number", "row 12 in an HTML comment"),
    ("I10", "FAIL", "en", "internal skill or record id", "W-PROM-C-1 in an HTML comment"),
    ("I10", "FAIL", "en", "version stamp", "Version 0.3 in an HTML comment"),
    ("I10", "FAIL", "en", "file path", "a repository path in an HTML comment"),
    ("B9", "FAIL", "en", "reduce-motion", "animation still running under reduce"),
    ("F1", "FAIL", "nocsp", "present", "no CSP at all"),
    ("F11", "FAIL", "cspv", "CSP violations", "inline script that the page's own CSP forbids"),
    ("C1", "FAIL", "ru", "structure parity", "RU page has fewer elements than EN"),
    ("C3", "FAIL", "ru", "accessible names", 'aria-label="Open menu" on the RU page'),
    ("C5", "FAIL", "ru", "straight", 'straight " quotes in Russian text'),
    ("C5", "FAIL", "ru", "hyphen", "hyphen with spaces as a dash"),
    ("C5", "FAIL", "ru", "balanced", "unbalanced guillemet"),
    ("C11", "FAIL", "ru", "brand terms", "SANKORD missing from the RU text"),
    ("C13", "FAIL", "ru", "translated", "RU title and description equal to EN"),
    ("F3", "FAIL", "hbad", "clickjacking", "_headers without frame-ancestors"),
    ("F4", "FAIL", "hbad", "strict-transport", "_headers without HSTS"),
    ("F5", "FAIL", "hbad", "x-content-type", "nosniff replaced by a wrong value"),
    ("F6", "FAIL", "hbad", "referrer-policy", "_headers without Referrer-Policy"),
    ("F7", "FAIL", "hbad", "permissions-policy", "_headers without Permissions-Policy"),
    ("F8", "FAIL", "hbad", "cross-origin-opener", "_headers without COOP"),
    ("E5", "FAIL", "sbad", "robots.txt", "no robots.txt"),
    ("E5", "FAIL", "sbad", "sitemap.xml status", "no sitemap.xml"),
]


def self_test(args):
    global VIEWPORTS
    VIEWPORTS = [320, 1280]
    args.no_external = True
    FixtureHandler.PNG_SLOW = _png(300, 100, True)  # not flat: Chrome ignores low-entropy images as LCP candidates
    FixtureHandler.PNG_NOISE = _png(700, 600, True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    FixtureHandler.PORT = port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port
    U = {"en": base + "/bad/en.html", "ru": base + "/bad/ru.html", "nocsp": base + "/bad/nocsp.html", "cspv": base + "/bad/cspviol.html",
         "missing": base + "/bad/missing.html", "gen": base + "/good/en.html", "gru": base + "/good/ru.html",
         "hbad": base + "/bad/_headers", "hgood": base + "/good/_headers", "sbad": base + "/bad/", "sgood": base + "/good/"}
    CONTROL = {"en": "gen", "ru": "gru", "nocsp": "gen", "cspv": "gen", "missing": "gen", "hbad": "hgood", "sbad": "sgood"}
    print("self-test: fixture server http://127.0.0.1:%d (own thread, stopped at the end); viewports %s" % (port, VIEWPORTS), flush=True)
    docs = {}
    h = None
    try:
        for k in ("en", "ru", "nocsp", "cspv", "missing", "gen", "gru"):
            static_run(U[k], args, docs)
        i18n_checks([U["en"], U["ru"]], docs)
        i18n_checks([U["gen"], U["gru"]], docs)
        site_files(U["sbad"], docs)
        site_files(U["sgood"], docs)
        headers_checks(U["hbad"], {}, os.path.join(FIXDIR, "_headers.bad"))
        headers_checks(U["hgood"], {}, os.path.join(FIXDIR, "_headers.good"))
        h = start_browser(args)
        if not h:
            print("self-test: Chrome/Edge not found")
            return 2
        cdp = h[2]
        for k, parts in (("en", None), ("cspv", {"load"}), ("gen", None)):
            try:
                browser_checks(cdp, U[k], args, locale_of(U[k]), parts)
            except Exception as e:
                rep("FAIL", "G2", U[k], "browser checks aborted: %s: %s" % (type(e).__name__, str(e)[:160]))
    finally:
        if h:
            stop_browser(h)
        srv.shutdown()
    print("\nSELF-TEST: one planted defect per FAIL-class check (WARN-class rows marked)\n")
    print("%-9s %-5s %-5s %-8s %-52s %s" % ("RESULT", "CHECK", "WANT", "FIXTURE", "PLANTED DEFECT", "CONTROL (good fixture)"))
    fired_n = clean_n = 0
    bad_rows = []
    for cid, status, key, sub, defect in EXPECT:
        fired = any(s == status and c == cid and u == U[key] and sub.lower() in m.lower() for s, c, u, m in RESULTS)
        ctl = U[CONTROL[key]]
        dirty = [m for s, c, u, m in RESULTS if s == status and c == cid and u == ctl]
        fired_n += fired
        clean_n += (not dirty)
        print("%-9s %-5s %-5s %-8s %-52s %s" % ("FIRED" if fired else "NOT FIRED", cid, status, key, defect[:52], "clean" if not dirty else "DIRTY: " + dirty[0][:60]))
        if not fired or dirty:
            bad_rows.append((cid, status, key, sub))
    total = len(EXPECT)
    print("\nSELF-TEST SUMMARY: %d expectations over %d distinct checks; fired %d, not fired %d; controls clean %d, dirty %d" % (
        total, len(set(e[0] for e in EXPECT)), fired_n, total - fired_n, clean_n, total - clean_n))
    for cid, status, key, sub in bad_rows:
        near = [(s, m[:110]) for s, c, u, m in RESULTS if c == cid and u in (U[key], U[CONTROL[key]])][:3]
        print("  PROBLEM %s %s on %s (%s): nearby results %s" % (cid, status, key, sub, near))
    return 0 if not bad_rows else 1


if __name__ == "__main__":
    main()
