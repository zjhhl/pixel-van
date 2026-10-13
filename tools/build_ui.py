#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二批：UI 素材处理。

统一流程：先裁掉底部 7%（AI 图右下角有半透明水印）-> 抠图 -> 缩放到目标尺寸。
- 按钮 / 图标 / 面板：硬边抠图
- 过关横幅：柔和 alpha 抠图（保住金色光晕），并按 2:1 裁切后缩放

文字全部由代码绘制，这些图里不带任何字。
"""

import os
import sys
import glob
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from process_assets import remove_bg, remove_bg_soft, fit_canvas  # noqa

ROOT = "/Users/zhujinhui/claudeProject5/pixel-van"
RAW = os.path.join(ROOT, "assets/_raw/ui")
OUT = os.path.join(ROOT, "assets/ui")
TMP = "/tmp/pv_stage"
os.makedirs(TMP, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# (原图前缀, 输出名, 宽, 高, 填充比, 抠图容差, 是否全局阈值)
# 图标用全局阈值是为了把“被箭头围出来的中心孔洞”也抠掉，
# 但容差必须比按钮小，否则主体自身的浅色也会被削成半透明。
ITEMS = [
    ("BtnGold",     "btn_start.png",   400, 120, 0.97, 46, False),
    ("BtnGreen",    "btn_next.png",    400, 120, 0.97, 46, False),
    ("BtnOrange",   "btn_retry.png",   200, 120, 0.97, 46, False),
    ("IconBrush",   "icon_brush.png",  128, 128, 0.88, 24, True),
    ("IconRefresh", "icon_refresh.png", 128, 128, 0.88, 22, True),
    ("PanelBase",   "panel.png",       600, 400, 0.96, 38, False),
]


def find_raw(prefix):
    hits = sorted(glob.glob(os.path.join(RAW, prefix + "*")))
    return hits[0] if hits else None


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


def build_banner():
    src = find_raw("BannerWin")
    if not src:
        print("[!] 缺少 BannerWin 原图"); return
    staged = os.path.join(TMP, "banner.png")
    remove_bg_soft(src, staged, lo=14, hi=70, crop_bottom=0.07)

    # 中心那块是 AI 画的一片低饱和灰米色，留着会显得脏。
    # 按饱和度再削一次 alpha：低饱和（灰）-> 透明，饱和的彩色/金色光带照旧保留。
    im = Image.open(staged).convert("RGBA")
    a = np.array(im).astype(np.float32)
    rgb = a[..., :3]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    key = np.clip((sat - 0.06) / (0.28 - 0.06), 0.0, 1.0)
    a[..., 3] = np.clip(a[..., 3] * key, 0, 255)
    im = Image.fromarray(a.astype(np.uint8), "RGBA")

    im = crop_to_ratio(im, 600, 300)
    im = im.resize((600, 300), Image.LANCZOS)
    im.save(os.path.join(OUT, "banner_win.png"))
    print("  banner_win.png   600x300  (柔和 alpha + 中心低饱和区域透明化)")


def build_items():
    for prefix, name, W, H, fill, tol, gt in ITEMS:
        src = find_raw(prefix)
        if not src:
            print(f"[!] 缺少 {prefix} 原图"); continue
        staged = os.path.join(TMP, name)
        remove_bg(src, staged, tol=tol, feather=1, verbose=False,
                  crop_bottom=0.07, global_thresh=gt)
        fit_canvas(staged, os.path.join(OUT, name), W, H, fill=fill)
        print(f"  {name:16s} {W}x{H} tol={tol} {'全局阈值' if gt else ''}")


if __name__ == "__main__":
    print("=== UI 素材 ===")
    build_items()
    build_banner()
    print("=== 完成 ===")
