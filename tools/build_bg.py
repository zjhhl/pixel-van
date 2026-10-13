#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二批：背景与装饰素材处理。

- ground.png 720x1280  ：AI 竖版路面 -> 清右下角水印 -> 裁 9:16 -> 缩放
- tree.png / tree2.png  ：160x200 抠图透明底
- sign.png              ：140x220 抠图透明底
- slot.png              ：虚线圆角停车位框，用代码精确绘制（AI 画不准虚线）
"""

import os
import sys
import glob
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from process_assets import remove_bg, fit_canvas  # noqa

ROOT = "/Users/zhujinhui/claudeProject5/pixel-van"
RAW = os.path.join(ROOT, "assets/_raw/bg")
OUT = os.path.join(ROOT, "assets/bg")
TMP = "/tmp/pv_stage"
os.makedirs(TMP, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def find_raw(prefix):
    hits = sorted(glob.glob(os.path.join(RAW, prefix + "*")))
    return hits[0] if hits else None


# ---------------------------------------------------------------- 水印清理
def wipe_corner_watermark(im, x_from=0.68, y_from=0.88):
    """AI 图右下角被塞了半透明水印。背景是平滑渐变，
    直接用右侧区域左边界的像素水平外推填充即可，看不出来。"""
    a = np.array(im.convert("RGB")).copy()
    h, w, _ = a.shape
    x0, y0 = int(w * x_from), int(h * y_from)
    strip = a[y0:, x0 - 1:x0, :]                 # (h', 1, 3)
    a[y0:, x0:, :] = np.repeat(strip, w - x0, axis=1)
    return Image.fromarray(a, "RGB")


def crop_to_ratio(im, tw, th):
    W, H = im.size
    target = tw / th
    cur = W / H
    if cur > target:
        nw = int(round(H * target)); x0 = (W - nw) // 2
        return im.crop((x0, 0, x0 + nw, H))
    if cur < target:
        nh = int(round(W / target)); y0 = (H - nh) // 2
        return im.crop((0, y0, W, y0 + nh))
    return im


# ---------------------------------------------------------------- ground
def build_ground():
    src = find_raw("GroundBaseV2")
    if not src:
        print("[!] 缺少 GroundBaseV2 原图"); return
    im = Image.open(src)
    im = wipe_corner_watermark(im)
    im = crop_to_ratio(im, 720, 1280)
    im = im.resize((720, 1280), Image.LANCZOS)
    im.convert("RGB").save(os.path.join(OUT, "ground.png"))
    print(f"  ground.png  720x1280  <- {os.path.basename(src)}")


# ---------------------------------------------------------------- 装饰
DECOR = [
    # (原图前缀, 输出名, 宽, 高, 填充比, 抠图容差)
    ("DecorTreeA", "tree.png",  160, 200, 0.92, 30),
    ("DecorTreeB", "tree2.png", 160, 200, 0.92, 30),
    ("SignPostV2", "sign.png",  140, 220, 0.94, 50),   # 银柱/底座接近灰底，容差要大
]


def build_decor():
    for prefix, name, W, H, fill, tol in DECOR:
        src = find_raw(prefix)
        if not src:
            print(f"[!] 缺少 {prefix} 原图"); continue
        staged = os.path.join(TMP, name)
        remove_bg(src, staged, tol=tol, feather=1, verbose=False)
        fit_canvas(staged, os.path.join(OUT, name), W, H, fill=fill)
        print(f"  {name:11s} {W}x{H} tol={tol}  <- {os.path.basename(src)}")


# ---------------------------------------------------------------- slot 虚线框
def build_slot(W=200, H=260, radius=26, dash=16, gap=11, lw=7):
    """白色半透明虚线圆角框。AI 画不准虚线，这里用代码画，保证像素级整齐。"""
    SS = 4                                        # 超采样倍数，抗锯齿
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = lw * SS / 2, lw * SS / 2, W * SS - lw * SS / 2, H * SS - lw * SS / 2
    r = radius * SS
    lwv = lw * SS

    # 生成圆角矩形路径（四边直线 + 四段圆弧）
    def arc_path(cx, cy, a0, a1, steps=60):
        return [(cx + r * np.cos(np.radians(t)), cy + r * np.sin(np.radians(t)))
                for t in np.linspace(a0, a1, steps)]

    pts = []
    pts += [(x0 + r + t * (x1 - x0 - 2 * r), y0) for t in np.linspace(0, 1, 200)]      # 上
    pts += arc_path(x1 - r, y0 + r, -90, 0)                                          # 右上
    pts += [(x1, y0 + r + t * (y1 - y0 - 2 * r)) for t in np.linspace(0, 1, 200)]     # 右
    pts += arc_path(x1 - r, y1 - r, 0, 90)                                            # 右下
    pts += [(x1 - r - t * (x1 - x0 - 2 * r), y1) for t in np.linspace(0, 1, 200)]     # 下
    pts += arc_path(x0 + r, y1 - r, 90, 180)                                          # 左下
    pts += [(x0, y1 - r - t * (y1 - y0 - 2 * r)) for t in np.linspace(0, 1, 200)]     # 左
    pts += arc_path(x0 + r, y0 + r, 180, 270)                                         # 左上

    # 按累计弧长切虚线段
    arr = np.array(pts, dtype=np.float64)
    seg = np.sqrt(((np.diff(arr, axis=0)) ** 2).sum(axis=1))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    period = (dash + gap) * SS
    t = 0.0
    while t < total:
        a, b = t, min(t + dash * SS, total)
        idx = (s >= a) & (s <= b)
        if idx.sum() > 1:
            p = arr[idx]
            d.line([tuple(v) for v in p], fill=(255, 255, 255, 210),
                   width=int(lwv), joint="curve")
        t += period

    img = img.resize((W, H), Image.LANCZOS)
    img.save(os.path.join(OUT, "slot.png"))
    print(f"  slot.png    {W}x{H} (虚线圆角框，代码绘制)")


if __name__ == "__main__":
    print("=== 背景与装饰 ===")
    build_ground()
    build_decor()
    build_slot()
    print("=== 完成 ===")
