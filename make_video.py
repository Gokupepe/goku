#!/usr/bin/env python3
"""Dựng video Reels 9:16 cho affiliate từ một file kịch bản JSON.

Cách dùng:
    python3 make_video.py scripts/den-ngu-cam-bien.json

Cấu trúc JSON (xem scripts/den-ngu-cam-bien.json):
    hooks      : danh sách hook 3 giây đầu, mỗi hook dựng ra 1 bản video để A/B test
    hook_pick  : id hook dùng cho bản chính (output/<slug>.mp4)
    scenes     : các cảnh thân bài, mỗi cảnh có
        section : attention | interest | desire | action ... (ghi chú)
        text    : chữ tiêu đề trên màn hình
        vo      : lời đọc
        clips   : danh sách clip nền, cắt đều theo thời lượng lời đọc. Mỗi clip là
                  {"pix": <id Pixabay>} | {"file": "đường/dẫn.mp4"} | {"q": "từ khóa"}
                  thêm "focus": 0..1 để chọn vùng cắt ngang (0 trái, 1 phải),
                  "start": giây bắt đầu trong clip.
        (định dạng cũ "query": "..." vẫn dùng được)
    bgm        : (tùy chọn) đường dẫn nhạc nền, "bgm_volume" mặc định 0.12

Video nền lấy từ Pixabay qua biến PIXABAY_API_KEY (hoặc file ~/.pixabay_key).
Không có key / mạng lỗi thì dùng nền gradient động.
"""
import asyncio
import hashlib
import json
import os
import random
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
FONT_CANDIDATES = [ROOT / "assets/fonts/BeVietnamPro-Bold.ttf",
                   Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
FONT = str(next(p for p in FONT_CANDIDATES if p.exists()))
VOICE_DEFAULT = "vi-VN-HoaiMyNeural"
YELLOW = (255, 214, 10)
UA = {"User-Agent": "aff-video/1.0"}
SUB_Y, SUB_H = 1330, 330


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Lỗi lệnh: {' '.join(map(str, cmd[:6]))}...\n{r.stderr[-1500:]}")
    return r.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", str(path)]).strip())


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()[:12]


# ---------- Giọng đọc + mốc thời gian từng từ ----------
def tts(text, voice, rate):
    """Trả về (mp3, [(từ, bắt_đầu, kết_thúc), ...]); có cache."""
    import edge_tts
    CACHE.mkdir(exist_ok=True)
    h = md5(f"{voice}|{rate}|{text}")
    mp3, js = CACHE / f"tts_{h}.mp3", CACHE / f"tts_{h}.json"
    if not (mp3.exists() and js.exists()):
        async def go():
            c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary",
                                     proxy=os.environ.get("HTTPS_PROXY"))
            words = []
            with open(mp3, "wb") as f:
                async for ch in c.stream():
                    if ch["type"] == "audio":
                        f.write(ch["data"])
                    elif ch["type"] == "WordBoundary":
                        s = ch["offset"] / 1e7
                        words.append((ch["text"], s, s + ch["duration"] / 1e7))
            return words
        js.write_text(json.dumps(asyncio.run(go()), ensure_ascii=False))
    return mp3, [tuple(w) for w in json.loads(js.read_text())]


# ---------- Pixabay ----------
def pixabay_key():
    k = os.environ.get("PIXABAY_API_KEY")
    p = Path.home() / ".pixabay_key"
    if not k and p.exists():
        k = p.read_text().strip()
    return k


def _api(params):
    key = pixabay_key()
    if not key:
        return []
    meta = CACHE / f"q_{md5(json.dumps(params, sort_keys=True))}.json"
    if meta.exists():
        return json.loads(meta.read_text())
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": key, **params})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        hits = json.load(r).get("hits", [])
    meta.write_text(json.dumps(hits))
    return hits


def _download(hit):
    v = hit["videos"].get("medium") or hit["videos"].get("small")
    if not v or not v.get("url"):
        return None
    f = CACHE / f"pix_{hit['id']}.mp4"
    if not f.exists():
        with urllib.request.urlopen(urllib.request.Request(v["url"], headers=UA), timeout=120) as r:
            f.write_bytes(r.read())
    return f


def resolve_clip(spec, need_sec, used):
    """Trả về đường dẫn file video cho một clip spec, hoặc None."""
    CACHE.mkdir(exist_ok=True)
    if "file" in spec:
        p = Path(spec["file"])
        p = p if p.is_absolute() else ROOT / p
        if p.exists():
            return p
        print(f"  ! không thấy file {p}, bỏ qua")
        return None
    if "pix" in spec:
        hits = _api({"id": spec["pix"]})
        return _download(hits[0]) if hits else None
    hits = _api({"q": spec["q"], "per_page": 20, "safesearch": "true"})

    def score(h):
        v = h["videos"]["medium"]
        return (h["id"] not in used, v["height"] > v["width"], h["duration"] >= need_sec,
                h.get("likes", 0))
    for h in sorted(hits, key=score, reverse=True):
        f = _download(h)
        if f:
            used.add(h["id"])
            return f
    return None


def gradient_bg(path, seed):
    rnd = random.Random(seed)
    palettes = [((20, 20, 40), (90, 30, 120)), ((10, 40, 60), (0, 120, 140)),
                ((40, 10, 10), (160, 60, 20)), ((15, 15, 15), (70, 70, 90))]
    a, b = rnd.choice(palettes)
    img = Image.new("RGB", (W + 200, H + 350))
    d = ImageDraw.Draw(img)
    for y in range(img.height):
        t = y / img.height
        d.line([(0, y), (img.width, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    img.save(path)


# ---------- Chữ ----------
def wrap(draw, words, font, max_w):
    lines, cur = [], []
    for w in words:
        if cur and draw.textlength(" ".join(cur + [w]), font=font) > max_w:
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def text_png(path, text, size, y_center, color=YELLOW, box=False, max_w=940):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, size)
    lines = [" ".join(l) for l in wrap(d, text.split(), font, max_w)]
    lh = int(size * 1.25)
    top = y_center - lh * len(lines) // 2
    if box:
        bw = max(d.textlength(l, font=font) for l in lines) + 70
        d.rounded_rectangle([(W - bw) / 2, top - 26, (W + bw) / 2, top + lh * len(lines) + 18],
                            radius=28, fill=(0, 0, 0, 175))
    for i, l in enumerate(lines):
        x = (W - d.textlength(l, font=font)) / 2
        d.text((x, top + i * lh), l, font=font, fill=color,
               stroke_width=max(4, size // 14), stroke_fill=(0, 0, 0))
    img.save(path)


def karaoke_png(path, words, active, size=74):
    """Một nhóm từ, từ thứ `active` tô vàng, còn lại trắng. Ảnh cao SUB_H."""
    img = Image.new("RGBA", (W, SUB_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, size)
    lines = wrap(d, words, font, 960)
    lh = int(size * 1.3)
    top = (SUB_H - lh * len(lines)) // 2
    space = d.textlength(" ", font=font)
    k = 0
    for i, line in enumerate(lines):
        x = (W - d.textlength(" ".join(line), font=font)) / 2
        for w in line:
            d.text((x, top + i * lh), w, font=font, fill=YELLOW if k == active else (255, 255, 255),
                   stroke_width=6, stroke_fill=(0, 0, 0))
            x += d.textlength(w, font=font) + space
            k += 1
    img.save(path)


def group_words(words, vo, max_words=5):
    """Chia từ thành nhóm phụ đề: ngắt ở dấu câu, mỗi nhóm tối đa max_words từ,
    vế dài thì chia đều để không cắt đôi một cụm ngắn."""
    import math
    toks = vo.split()
    if len(toks) != len(words):  # không khớp được dấu câu: chia theo số từ
        return [words[i:i + max_words] for i in range(0, len(words), max_words)]
    groups, clause = [], []
    for tok, w in zip(toks, words):
        clause.append(w)
        if tok[-1] in ",.!?:;" or w is words[-1]:
            n = math.ceil(len(clause) / max_words)
            size = math.ceil(len(clause) / n)
            groups += [clause[i:i + size] for i in range(0, len(clause), size)]
            clause = []
    return groups


# ---------- Dựng một cảnh ----------
def clip_specs(sc):
    if "clips" in sc:
        return sc["clips"]
    return [{"q": sc["query"]}] if sc.get("query") else []


def render_scene(name, sc, work, cfg, used, is_hook=False):
    voice = cfg.get("voice", VOICE_DEFAULT)
    rate = sc.get("rate", cfg.get("rate", "+12%"))
    mp3, words = tts(sc["vo"], voice, rate)
    vo_d = duration(mp3)
    # edge-tts để lại ~0.5s im lặng cuối câu: cắt theo từ cuối cùng cho nhịp nhanh hơn
    spoken = words[-1][2] if words else vo_d
    D = round(min(vo_d, spoken + (0.1 if is_hook else 0.25)), 3)

    # --- nền: cắt đều nhiều clip ---
    specs = clip_specs(sc)
    files = []
    for s in specs:
        try:
            f = resolve_clip(s, D / max(1, len(specs)), used)
        except Exception as e:  # mạng lỗi thì bỏ clip này
            print(f"  ! Pixabay lỗi ({e})")
            f = None
        if f:
            files.append((f, s))
    inputs, fc = [], []
    if files:
        n = len(files)
        seg = D / n
        for k, (f, s) in enumerate(files):
            cd = duration(f)
            start = s.get("start", min(1.0, max(0.0, cd - seg - 0.1)))
            focus = s.get("focus", 0.5)
            inputs += ["-stream_loop", "-1", "-ss", f"{start:.2f}", "-t", f"{seg + 0.1:.3f}", "-i", str(f)]
            fc.append(f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H}:x='(iw-{W})*{focus}':y='(ih-{H})/2',setsar=1,fps={FPS},"
                      f"trim=duration={seg:.3f},setpts=PTS-STARTPTS,"
                      f"eq=brightness=-0.05:saturation=1.15[c{k}]")
        fc.append("".join(f"[c{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[bg0]")
        nin = n
    else:
        g = work / f"grad_{name}.png"
        gradient_bg(g, md5(name))
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(D), "-i", str(g)]
        fc.append(f"[0:v]crop={W}:{H}:x='100*t/{D}':y='300*t/{D}',setsar=1,fps={FPS}[bg0]")
        nin = 1
    if is_hook:  # zoom nhẹ cho 3 giây đầu để tạo chuyển động
        fc.append(f"[bg0]scale=w='trunc({W}*(1+0.10*t/{D})/2)*2':h=-2:eval=frame,"
                  f"crop={W}:{H}[bg]")
    else:
        fc.append("[bg0]null[bg]")

    # --- âm thanh ---
    inputs += ["-i", str(mp3)]
    ia = nin
    nin += 1

    # --- tiêu đề ---
    head = work / f"head_{name}.png"
    if is_hook:
        text_png(head, sc["text"], 112, 700, max_w=980)
    else:
        text_png(head, sc["text"], 80, 400, box=True)
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(D), "-i", str(head)]
    fc.append(f"[bg][{nin}:v]overlay=0:0[v0]")
    nin += 1
    last = "v0"

    # --- phụ đề karaoke ---
    k = 0
    groups = group_words(words, sc["vo"])
    for gi, grp in enumerate(groups):
        texts = [w[0] for w in grp]
        # nhóm sau bắt đầu thì nhóm trước phải tắt, tránh hai dòng chồng lên nhau
        g_end = groups[gi + 1][0][1] - 0.01 if gi + 1 < len(groups) else D
        for wi, (_, ws, we) in enumerate(grp):
            end = grp[wi + 1][1] - 0.01 if wi + 1 < len(grp) else min(we + 0.4, g_end)
            p = work / f"sub_{name}_{gi}_{wi}.png"
            karaoke_png(p, texts, wi)
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(D), "-i", str(p)]
            fc.append(f"[{last}][{nin}:v]overlay=0:{SUB_Y}:"
                      f"enable='between(t,{ws:.3f},{end:.3f})'[s{k}]")
            last = f"s{k}"
            nin += 1
            k += 1
    fc.append(f"[{ia}:a]apad,atrim=0:{D},aresample=44100[a]")
    out = work / f"scene_{name}.mp4"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{last}]",
         "-map", "[a]", "-t", str(D), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ac", "2",
         str(out)])
    print(f"  cảnh {name} [{sc.get('section', 'hook')}] {D:.1f}s, {len(files)} clip")
    return out


# ---------- Ghép ----------
def assemble(scenes, out, work, cfg):
    lst = work / f"list_{out.stem}.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in scenes))
    raw = work / f"raw_{out.stem}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(raw)])
    T = duration(raw)
    # thanh tiến trình vàng ở đáy: người xem thấy video sắp hết nên xem tiếp
    inputs = ["-i", str(raw), "-f", "lavfi", "-i", f"color=c=0xFFD60A:s={W}x12:r={FPS}"]
    fc = [f"[0:v][1:v]overlay=x='-w+w*t/{T:.3f}':y={H - 12}:shortest=1[v]"]
    amap = "0:a"
    bgm = cfg.get("bgm")
    if bgm and (ROOT / bgm).exists():
        inputs += ["-stream_loop", "-1", "-i", str(ROOT / bgm)]
        vol = cfg.get("bgm_volume", 0.12)
        fc.append(f"[2:a]volume={vol},atrim=0:{T:.3f}[m];"
                  f"[0:a][m]amix=inputs=2:duration=first:normalize=0[a]")
        amap = "[a]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", amap,
         "-t", f"{T:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
         str(out)])
    return T


def main(spec_path):
    cfg = json.loads(Path(spec_path).read_text())
    work = ROOT / "build" / cfg["slug"]
    work.mkdir(parents=True, exist_ok=True)
    outdir = ROOT / "output"
    outdir.mkdir(exist_ok=True)
    used = set()
    print(f"Dựng: {cfg['title']}")

    hooks = cfg.get("hooks") or []
    scenes = cfg["scenes"]
    if not hooks:  # định dạng cũ: cảnh đầu section=hook
        if scenes and scenes[0].get("section") == "hook":
            hooks = [dict(scenes[0], id="A")]
            scenes = scenes[1:]
    body = [render_scene(f"b{i}", sc, work, cfg, used) for i, sc in enumerate(scenes)]

    pick = cfg.get("hook_pick", hooks[0]["id"] if hooks else None)
    for hk in hooks:
        hs = render_scene(f"h{hk['id']}", hk, work, cfg, set(), is_hook=True)
        name = cfg["slug"] if hk["id"] == pick else f"{cfg['slug']}-hook{hk['id']}"
        out = outdir / f"{name}.mp4"
        T = assemble([hs, *body], out, work, cfg)
        print(f"Xong: {out} ({T:.1f}s) hook {hk['id']}{' (bản chính)' if hk['id'] == pick else ''}")
    if not hooks:
        out = outdir / f"{cfg['slug']}.mp4"
        print(f"Xong: {out} ({assemble(body, out, work, cfg):.1f}s)")

    cap = outdir / f"{cfg['slug']}.txt"
    cap.write_text(f"CAPTION:\n{cfg['caption']}\n\nBÌNH LUẬN GHIM:\n{cfg['pinned_comment']}\n")
    print(f"Caption: {cap}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
