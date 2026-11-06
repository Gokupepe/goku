#!/usr/bin/env python3
"""Dựng video Reels 9:16 cho affiliate từ một file kịch bản JSON (công thức AIDA).

Cách dùng:
    python3 make_video.py scripts/den-ngu-cam-bien.json

Mỗi cảnh trong JSON có:
    section : hook | attention | interest | desire | action   (chỉ để ghi chú)
    text    : chữ to trên màn hình (ngắn, <= 8 từ)
    vo      : lời đọc
    query   : từ khóa tiếng Anh để tìm video minh họa trên Pixabay

Video nền lấy từ Pixabay nếu có biến môi trường PIXABAY_API_KEY
(hoặc file ~/.pixabay_key). Không có key thì dùng nền gradient động.
"""
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
VOICE_DEFAULT = "vi-VN-HoaiMyNeural"
YELLOW = (255, 214, 10)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Lỗi lệnh: {' '.join(cmd[:6])}...\n{r.stderr[-1500:]}")
    return r.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", str(path)]).strip())


# ---------- Giọng đọc ----------
def tts(text, out, voice, rate):
    if out.exists() and out.stat().st_size > 0:
        return
    cmd = ["edge-tts", "--voice", voice, f"--rate={rate}", "--text", text,
           "--write-media", str(out)]
    if os.environ.get("HTTPS_PROXY"):
        cmd += ["--proxy", os.environ["HTTPS_PROXY"]]
    run(cmd)


# ---------- Pixabay ----------
def pixabay_key():
    k = os.environ.get("PIXABAY_API_KEY")
    p = Path.home() / ".pixabay_key"
    if not k and p.exists():
        k = p.read_text().strip()
    return k


def pixabay_clip(query, need_sec, used):
    key = pixabay_key()
    if not key:
        return None
    CACHE.mkdir(exist_ok=True)
    meta = CACHE / f"q_{hashlib.md5(query.encode()).hexdigest()}.json"
    if meta.exists():
        hits = json.loads(meta.read_text())
    else:
        url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(
            {"key": key, "q": query, "per_page": 20, "safesearch": "true"})
        with urllib.request.urlopen(url, timeout=30) as r:
            hits = json.load(r).get("hits", [])
        meta.write_text(json.dumps(hits))
    # ưu tiên clip dọc, đủ dài, chưa dùng trong video này
    def score(h):
        v = h["videos"]["medium"]
        vertical = v["height"] > v["width"]
        return (h["id"] not in used, vertical, h["duration"] >= need_sec, h.get("likes", 0))
    hits = sorted(hits, key=score, reverse=True)
    for h in hits:
        v = h["videos"].get("medium") or h["videos"].get("small")
        if not v or not v.get("url"):
            continue
        f = CACHE / f"pix_{h['id']}.mp4"
        if not f.exists():
            req = urllib.request.Request(v["url"], headers={"User-Agent": "aff-video/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                f.write_bytes(r.read())
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
def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def text_png(path, text, size, y_center, color=(255, 255, 255), box=False, max_w=940):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, size)
    lines = wrap(d, text, font, max_w)
    lh = int(size * 1.22)
    top = y_center - lh * len(lines) // 2
    if box:
        bw = max(d.textlength(l, font=font) for l in lines) + 70
        d.rounded_rectangle([(W - bw) / 2, top - 30, (W + bw) / 2, top + lh * len(lines) + 20],
                            radius=28, fill=(0, 0, 0, 170))
    for i, l in enumerate(lines):
        x = (W - d.textlength(l, font=font)) / 2
        d.text((x, top + i * lh), l, font=font, fill=color,
               stroke_width=max(4, size // 14), stroke_fill=(0, 0, 0))
    img.save(path)


def chunks(vo, max_words=7):
    parts = [p.strip() for p in re.split(r"(?<=[,.!?])\s+", vo) if p.strip()]
    out = []
    for p in parts:
        ws = p.split()
        while len(ws) > max_words:
            out.append(" ".join(ws[:max_words]))
            ws = ws[max_words:]
        if ws:
            out.append(" ".join(ws))
    return out


# ---------- Dựng ----------
def render_scene(i, sc, work, cfg, used):
    voice = cfg.get("voice", VOICE_DEFAULT)
    rate = sc.get("rate", cfg.get("rate", "+12%"))
    mp3 = work / f"vo_{i}.mp3"
    tts(sc["vo"], mp3, voice, rate)
    vo_d = duration(mp3)
    pad = 0.0 if sc["section"] == "hook" else 0.15
    D = round(vo_d + pad, 3)

    clip = None
    try:
        clip = pixabay_clip(sc["query"], D, used)
    except Exception as e:  # mạng lỗi thì dùng nền gradient
        print(f"  ! Pixabay lỗi ({e}), dùng nền gradient")

    is_hook = sc["section"] == "hook"
    # chữ chính
    head = work / f"head_{i}.png"
    if is_hook:
        text_png(head, sc["text"], 118, 760, YELLOW, box=False, max_w=980)
    else:
        text_png(head, sc["text"], 84, 430, YELLOW, box=True)
    # phụ đề lời đọc, chia theo độ dài chữ
    subs = chunks(sc["vo"])
    total_chars = sum(len(s) for s in subs)
    t, sub_specs = 0.0, []
    for j, s in enumerate(subs):
        dur = vo_d * len(s) / total_chars
        p = work / f"sub_{i}_{j}.png"
        text_png(p, s, 62, 1480)
        sub_specs.append((p, t, t + dur))
        t += dur

    inputs, base = [], ""
    zoom = f"scale=w='trunc({W}*(1+0.12*t/{D})/2)*2':h=-2:eval=frame,crop={W}:{H}"
    if clip:
        inputs += ["-stream_loop", "-1", "-i", str(clip)]
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"setsar=1,fps={FPS},eq=brightness=-0.06:saturation=1.15"
                + ("," + zoom if is_hook else "") + "[bg]")
    else:
        g = work / f"grad_{i}.png"
        gradient_bg(g, i + hash(cfg["slug"]))
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(g)]
        base = (f"[0:v]crop={W}:{H}:x='100*t/{D}':y='300*t/{D}',setsar=1,fps={FPS}"
                + ("," + zoom if is_hook else "") + "[bg]")
    inputs += ["-i", str(mp3), "-loop", "1", "-framerate", str(FPS), "-i", str(head)]
    fc = [base, "[bg][2:v]overlay=0:0:shortest=1[v0]"]
    last = "v0"
    for k, (p, a, b) in enumerate(sub_specs):
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(p)]
        fc.append(f"[{last}][{3 + k}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})':shortest=1[v{k + 1}]")
        last = f"v{k + 1}"
    fc.append(f"[1:a]apad,atrim=0:{D},aresample=44100[a]")
    out = work / f"scene_{i}.mp4"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{last}]",
         "-map", "[a]", "-t", str(D), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ac", "2",
         str(out)])
    print(f"  cảnh {i} [{sc['section']}] {D:.1f}s {'pixabay' if clip else 'gradient'}")
    return out


def main(spec_path):
    cfg = json.loads(Path(spec_path).read_text())
    work = ROOT / "build" / cfg["slug"]
    work.mkdir(parents=True, exist_ok=True)
    used = set()
    print(f"Dựng: {cfg['title']}")
    scenes = [render_scene(i, sc, work, cfg, used) for i, sc in enumerate(cfg["scenes"])]
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in scenes))
    outdir = ROOT / "output"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"{cfg['slug']}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
         "-movflags", "+faststart", str(out)])
    cap = outdir / f"{cfg['slug']}.txt"
    cap.write_text(f"CAPTION:\n{cfg['caption']}\n\nBÌNH LUẬN GHIM:\n{cfg['pinned_comment']}\n")
    print(f"Xong: {out} ({duration(out):.1f}s)\nCaption: {cap}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
