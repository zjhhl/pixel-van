#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成第二批素材的核对总览图 assets/_review/overview2.png"""

import os
import wave
import glob
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = "/Users/zhujinhui/claudeProject5/pixel-van"
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "assets/_review/overview2.png")
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"

BG = (246, 247, 250)
TXT = (28, 30, 38)
SUB = (105, 112, 130)
ACCENT = (47, 128, 237)

F1 = ImageFont.truetype(FONT, 30)
F2 = ImageFont.truetype(FONT, 20)
F3 = ImageFont.truetype(FONT, 17)

W = 2400
PAD = 30


def load(p):
    return Image.open(p).convert("RGBA")


def paste_alpha(canvas, im, xy):
    canvas.paste(im, xy, im)


def block_levels(cv, d, y):
    d.text((PAD, y), "关卡底图 level04 ~ level10（左侧 8× 原始格，右侧 16× 预览）", font=F1, fill=TXT)
    y += 52
    items = [
        ("04", "熊猫头", 896), ("05", "长颈鹿", 1008), ("06", "像素小狗", 1008),
        ("07", "樱花树", 1064), ("08", "城堡", 1140), ("09", "巨龙", 1200),
        ("10", "宇航员", 1280),
    ]
    per_row = 4
    row_h = 372
    for i, (num, theme, cells) in enumerate(items):
        row, col = divmod(i, per_row)
        x = PAD + col * 590
        yy = y + row * row_h
        raw = load(f"{ASSETS}/levels/level{num}.png")
        big = load(f"{ASSETS}/levels/level{num}@16x.png")
        big.thumbnail((140, 230))
        raw2 = raw.resize((raw.width * 8, raw.height * 8), Image.NEAREST)
        paste_alpha(cv, raw2, (x, yy))
        paste_alpha(cv, big, (x + raw2.width + 10, yy))
        d.text((x, yy + 336), f"level{num} {theme}  {raw.width}×{raw.height}（{cells} 格）",
               font=F3, fill=SUB)
    rows = (len(items) + per_row - 1) // per_row
    return y + rows * row_h


def block_bg(cv, d, y):
    d.text((PAD, y), "背景与装饰（slot.png 为代码绘制的虚线车位框，AI 画不准虚线）", font=F1, fill=TXT)
    y += 52
    x = PAD
    entries = [
        ("ground.png 720×1280", "bg/ground.png", 300),
        ("tree.png 160×200", "bg/tree.png", 300),
        ("tree2.png 160×200", "bg/tree2.png", 300),
        ("sign.png 140×220", "bg/sign.png", 300),
        ("slot.png 200×260", "bg/slot.png", 300),
    ]
    for label, rel, hh in entries:
        im = load(os.path.join(ASSETS, rel))
        scale = hh / im.height
        im = im.resize((max(1, int(im.width * scale)), hh), Image.LANCZOS)
        paste_alpha(cv, im, (x, y))
        d.text((x, y + hh + 8), label, font=F3, fill=SUB)
        x += im.width + 44
    return y + 340


def block_ui(cv, d, y):
    d.text((PAD, y), "UI 素材（全部无字，文字与数字由代码绘制）", font=F1, fill=TXT)
    y += 52
    x = PAD
    for rel in ["ui/btn_start.png", "ui/btn_next.png", "ui/btn_retry.png", "ui/panel.png",
                "ui/icon_brush.png", "ui/icon_refresh.png", "ui/banner_win.png"]:
        im = load(os.path.join(ASSETS, rel))
        scale = 120 / im.height
        im = im.resize((max(1, int(im.width * scale)), 120), Image.LANCZOS)
        paste_alpha(cv, im, (x, y))
        name = os.path.basename(rel)
        d.text((x, y + 130), name, font=F3, fill=SUB)
        x += im.width + 46
    return y + 190


def block_sfx(cv, d, y):
    d.text((PAD, y), "音效（代码合成，lame 转 mp3）", font=F1, fill=TXT)
    y += 52
    x = PAD
    for name, desc in [("click", "点击"), ("drop", "落格（轻）"),
                       ("drive", "启动"), ("win", "过关")]:
        wav = f"/tmp/pv_sfx/{name}.wav"
        mp3 = f"{ASSETS}/sfx/{name}.mp3"
        box_w, box_h = 420, 110
        panel = Image.new("RGB", (box_w, box_h), (238, 240, 246))
        if os.path.exists(wav):
            with wave.open(wav, "rb") as w:
                n = w.getnframes()
                data = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
            step = max(1, len(data) // box_w)
            mid = box_h // 2
            for i in range(box_w):
                seg = data[i * step:(i + 1) * step]
                if len(seg) == 0:
                    continue
                amp = int(np.abs(seg).max() * (box_h / 2 - 6))
                panel.putpixel((i, mid), ACCENT)
                for k in range(1, amp + 1):
                    panel.putpixel((i, mid - k), ACCENT)
                    panel.putpixel((i, mid + k), ACCENT)
        cv.paste(panel, (x, y))
        size = os.path.getsize(mp3) / 1024 if os.path.exists(mp3) else 0
        d.text((x, y + box_h + 8), f"{name}.mp3  {desc}  {size:.1f} KB", font=F3, fill=SUB)
        x += box_w + 30
    return y + 180


def main():
    H = 60 + 750 + 350 + 200 + 190 + 80
    cv = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(cv)
    d.text((PAD, 18), "pixel-van 第二批素材｜关卡 04~10 · 背景装饰 · UI · 音效", font=F1, fill=TXT)

    y = 70
    y = block_levels(cv, d, y) + 24
    y = block_bg(cv, d, y) + 24
    y = block_ui(cv, d, y) + 24
    y = block_sfx(cv, d, y)

    cv = cv.crop((0, 0, W, min(H, y + 20)))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cv.save(OUT)
    print(f"saved {OUT}  {cv.size}")


if __name__ == "__main__":
    main()
