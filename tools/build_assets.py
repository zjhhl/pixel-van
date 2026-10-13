#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量生成正式素材：原始图 -> 去背景 -> 裁切到目标尺寸 -> 写入 assets/"""

import os
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from process_assets import remove_bg, fit_canvas, make_level  # noqa

ROOT = "/Users/zhujinhui/claudeProject5/pixel-van"
RAW = os.path.join(ROOT, "assets/_raw")
OUT = os.path.join(ROOT, "assets")
TMP = "/tmp/pv_stage"
os.makedirs(TMP, exist_ok=True)

VANS = [
    # (color, closed_raw, open_raw)
    ("red",    "base_red_closed.png",
     "OpenRedBox__Same_exact_cute_ro_2026-10-12T10-55-44.png"),
    ("white",  "Same_exact_cute_rounded_toy_mi_2026-10-12T10-53-25.png",
     "OpenWhite__Same_exact_cute_rou_2026-10-12T10-55-17.png"),
    ("black",  "VariantBlack__Same_exact_cute__2026-10-12T10-54-07.png",
     "OpenBlack__Same_exact_cute_rou_2026-10-12T10-55-16.png"),
    ("orange", "Same_exact_cute_rounded_toy_mi_2026-10-12T10-53-29.png",
     "OpenOrange__Same_exact_cute_ro_2026-10-12T10-55-15.png"),
    ("yellow", "VariantYellow__Same_exact_cute_2026-10-12T10-54-04.png",
     "OpenYellow__Same_exact_cute_ro_2026-10-12T10-55-17.png"),
    ("green",  "VariantGreen__Same_exact_cute__2026-10-12T10-54-13.png",
     "OpenGreen__Same_exact_cute_rou_2026-10-12T10-55-39.png"),
    ("blue",   "VariantBlue__Same_exact_cute_r_2026-10-12T10-54-13.png",
     "OpenBlue__Same_exact_cute_roun_2026-10-12T10-55-38.png"),
    ("purple", "VariantPurple__Same_exact_cute_2026-10-12T10-54-40.png",
     "OpenPurple__Same_exact_cute_ro_2026-10-12T10-55-44.png"),
    ("pink",   "VariantPink__Same_exact_cute_r_2026-10-12T10-54-38.png",
     "OpenPink__Same_exact_cute_roun_2026-10-12T10-55-44.png"),
]


def fg_ratio(path):
    a = np.array(Image.open(path).convert("RGBA"))[..., 3]
    return (a > 8).mean()


def check_body_color(path):
    """取车身主体色（前景中出现最多的偏饱和色）用于人工核对。"""
    a = np.array(Image.open(path).convert("RGBA")).astype(np.int16)
    m = a[..., 3] > 200
    px = a[m][:, :3]
    if len(px) == 0:
        return None
    mx, mn = px.max(axis=1), px.min(axis=1)
    sat = mx - mn
    body = px[sat > 40]
    if len(body) < 50:
        body = px
    q = (body // 24 * 24)
    vals, counts = np.unique(q, axis=0, return_counts=True)
    top = vals[counts.argmax()]
    return "#%02X%02X%02X" % tuple(top)


def bbox_area(path):
    a = np.array(Image.open(path).convert("RGBA"))[..., 3] > 8
    ys, xs = np.where(a)
    if len(ys) == 0:
        return 0
    return (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)


def build_tol_probe(raw_path, staged, label=""):
    """本批 AI 底图是「灰底 + 大范围柔光投影 + 暗角 + 右下角水印」，
    实测 tol≈50（欧氏色差）能把背景/投影/水印全部抠净，且不侵蚀车身
    （绿色车身最大通道差只有 50，欧氏距离约 61，仍安全）。
    这里做一次保险：占比异常时前后各退一档。"""
    for tol in (50, 44, 56, 40, 62):
        remove_bg(raw_path, staged, tol=tol, feather=1, verbose=False)
        r = fg_ratio(staged)
        if 0.15 <= r <= 0.70:
            return tol
    return 50


def main():
    print("=== 小车 ===")
    for color, closed_raw, open_raw in VANS:
        for state, raw in (("closed", closed_raw), ("open", open_raw)):
            src = os.path.join(RAW, "vans", raw)
            if not os.path.exists(src):
                print(f"  [!] 缺失 {src}")
                continue
            staged = os.path.join(TMP, f"{color}_{state}_keyed.png")
            final = os.path.join(OUT, "vans", f"van_{color}_{state}.png")
            tol = build_tol_probe(src, staged, f"{color}_{state}")
            fit_canvas(staged, final, 256, 320, 0.72)
            print(f"  {color:7s} {state:6s} tol={tol:2d} fg={fg_ratio(staged):.3f} "
                  f"body={check_body_color(staged)}")
    print("=== 完成 ===")


if __name__ == "__main__":
    main()
