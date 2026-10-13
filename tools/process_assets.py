#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材后处理：去背景 / 去水印 / 裁切缩放 / 调色板量化
用法示例见文件末尾 __main__ 区块。

依赖: Pillow, numpy
python: /Users/zhujinhui/.workbuddy/binaries/python/envs/default/bin/python
"""

import os
import sys
import glob
import numpy as np
from PIL import Image
from scipy import ndimage


# ---------------------------------------------------------------- 调色板
PALETTE = {
    "white":   (0xFF, 0xFF, 0xFF),
    "black":   (0x1A, 0x1A, 0x1A),
    "gray":    (0x8A, 0x8A, 0x8A),
    "red":     (0xE2, 0x3B, 0x3B),
    "orange":  (0xF2, 0x8C, 0x28),
    "yellow":  (0xF7, 0xD1, 0x3E),
    "green":   (0x3F, 0xA3, 0x4D),
    "lightblue": (0x7E, 0xC8, 0xF0),
    "blue":    (0x2F, 0x80, 0xED),
    "purple":  (0x8E, 0x5B, 0xD9),
    "pink":    (0xF0, 0x6A, 0xA8),
    "brown":   (0x8C, 0x5A, 0x2B),
    "beige":   (0xEA, 0xD9, 0xB8),
    "darkgreen": (0x1F, 0x6E, 0x43),
}
PALETTE_16 = list(PALETTE.values())


# ---------------------------------------------------------------- 背景移除
def _design(ny, nx, order):
    cols = [np.ones_like(ny), nx, ny]
    if order >= 2:
        cols += [nx * nx, ny * ny, nx * ny]
    if order >= 3:
        cols += [nx ** 3, ny ** 3, nx * nx * ny, nx * ny * ny]
    return np.stack(cols, axis=-1)


def _fit_bg_gradient(rgb, margin_ratio=0.05, order=3, passes=3):
    """用画布四周边缘像素拟合一个 order 阶多项式背景（AI 生成的灰底通常带渐变）。
    两轮以上做鲁棒重加权，排除边缘上的水印等离群样本。
    返回整幅图的背景预测 (h,w,3) float32。"""
    h, w, _ = rgb.shape
    m = max(4, int(min(h, w) * margin_ratio))
    ys, xs = np.mgrid[0:h, 0:w]
    ring = np.zeros((h, w), dtype=bool)
    ring[:m, :] = ring[-m:, :] = ring[:, :m] = ring[:, -m:] = True

    sy, sx = ys[ring].astype(np.float32) / h, xs[ring].astype(np.float32) / w
    A = _design(sy, sx, order)
    samples = rgb[ring].astype(np.float32)

    keep = np.ones(len(samples), dtype=bool)
    coef = None
    for _ in range(passes):
        coef, *_ = np.linalg.lstsq(A[keep], samples[keep], rcond=None)
        resid = np.sqrt(((samples - A @ coef) ** 2).sum(axis=1))
        thr = max(12.0, float(np.percentile(resid, 80)))
        keep = resid <= thr
        if keep.sum() < 200:
            break

    NY, NX = ys.astype(np.float32) / h, xs.astype(np.float32) / w
    return _design(NY, NX, order) @ coef


def _flood_bg_mask(rgb, tol):
    """背景掩码 = 「与拟合背景的欧氏色差足够小」的像素中，能连通到画布边界的部分。
    返回 bool 数组，True = 背景。"""
    h, w, _ = rgb.shape
    pred = _fit_bg_gradient(rgb)
    resid = np.sqrt(((rgb.astype(np.float32) - pred) ** 2).sum(axis=2))
    similar = resid <= tol

    lab, n = ndimage.label(similar, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    if n == 0:
        return np.zeros((h, w), dtype=bool)
    border_labels = set(lab[0, :].tolist()) | set(lab[-1, :].tolist()) \
        | set(lab[:, 0].tolist()) | set(lab[:, -1].tolist())
    border_labels.discard(0)
    return np.isin(lab, list(border_labels))


def _largest_component(mask):
    """保留 mask 中最大的 4-连通分量（去掉投影、水印等孤立块）。"""
    lab, n = ndimage.label(mask, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, index=range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


def _despeckle(mask, min_neighbors=3):
    """去掉孤立细点（含边缘残留），2 轮 3x3 邻域投票。"""
    m = mask.copy()
    k = np.ones((3, 3), dtype=np.uint8)
    for _ in range(2):
        cnt = ndimage.convolve(m.astype(np.uint8), k, mode="constant", cval=0)
        m = m & (cnt >= min_neighbors)
    return m


def _smooth_alpha(alpha, radius=1):
    """对 alpha 做轻微羽化，消除锯齿硬边。"""
    a = alpha.astype(np.float32)
    for _ in range(radius):
        p = np.pad(a, 1, mode="edge")
        a = (p[0:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, 0:-2] + p[1:-1, 2:] + a) / 5.0
    return np.clip(a, 0, 255).astype(np.uint8)


def remove_bg(src_path, out_path, tol=22, feather=1, verbose=True, crop_bottom=0.0,
              global_thresh=False):
    """global_thresh=True 时不再要求背景与画布边界连通，
    而是把「所有与拟合背景色差足够小」的像素都当背景。
    用于图标这类中心可能被主体围出一个“孔洞”的素材（否则孔洞会被当成前景留下灰块）。"""
    im = Image.open(src_path).convert("RGB")
    if crop_bottom > 0:
        w, h = im.size
        im = im.crop((0, 0, w, int(h * (1 - crop_bottom))))
    rgb = np.array(im)
    if global_thresh:
        pred = _fit_bg_gradient(rgb.astype(np.float32))
        resid = np.sqrt(((rgb.astype(np.float32) - pred) ** 2).sum(axis=2))
        bg = resid <= tol
    else:
        bg = _flood_bg_mask(rgb, tol)
    fg = ~bg
    fg = _largest_component(fg)
    fg = _despeckle(fg, 3)

    alpha = np.where(fg, 255, 0).astype(np.uint8)
    alpha = _smooth_alpha(alpha, feather)

    out = np.dstack([rgb, alpha])
    Image.fromarray(out, "RGBA").save(out_path)
    if verbose:
        ys, xs = np.where(fg)
        if len(ys):
            print(f"  [bg] {os.path.basename(out_path)} bbox=({xs.min()},{ys.min()})-({xs.max()},{ys.max()})")
    return out_path


def remove_bg_soft(src_path, out_path, lo=16.0, hi=74.0, crop_bottom=0.0):
    """柔和版抠图：alpha 随“与背景的色差”连续变化，而不是非 0 即 255。
    专给发光/光晕类素材用（例如过关横幅的金色光芒），硬切会把光晕切出难看的边。"""
    im = Image.open(src_path).convert("RGB")
    if crop_bottom > 0:
        w, h = im.size
        im = im.crop((0, 0, w, int(h * (1 - crop_bottom))))
    rgb = np.array(im).astype(np.float32)
    pred = _fit_bg_gradient(rgb)
    resid = np.sqrt(((rgb - pred) ** 2).sum(axis=2))
    alpha = np.clip((resid - lo) / max(hi - lo, 1e-6), 0.0, 1.0) * 255.0
    out = np.dstack([rgb.astype(np.uint8), alpha.astype(np.uint8)])
    Image.fromarray(out, "RGBA").save(out_path)
    return out_path


# ---------------------------------------------------------------- 裁切缩放
def fit_canvas(src_path, out_path, W, H, fill=0.70, align="center"):
    """把前景收缩到画布内，前景最长边占画布 fill 比例。"""
    im = Image.open(src_path).convert("RGBA")
    a = np.array(im)
    alpha = a[..., 3]
    ys, xs = np.where(alpha > 8)
    if len(ys) == 0:
        print(f"  [!] {out_path} 前景为空，跳过裁切")
        im.save(out_path)
        return out_path
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop = im.crop((x0, y0, x1, y1))
    cw, ch = crop.size

    box_w, box_h = int(W * fill), int(H * fill)
    scale = min(box_w / cw, box_h / ch)
    nw, nh = max(1, int(round(cw * scale))), max(1, int(round(ch * scale)))
    crop = crop.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ox = (W - nw) // 2
    if align == "bottom":
        oy = H - nh - int(H * 0.02)
    else:
        oy = (H - nh) // 2
    canvas.paste(crop, (ox, oy), crop)
    canvas.save(out_path)
    print(f"  [fit] {os.path.basename(out_path)} {cw}x{ch} -> {nw}x{nh} in {W}x{H}")
    return out_path


# ---------------------------------------------------------------- 像素画处理
def _nearest_palette(rgb, palette, tol=32):
    """把每个像素映射到最近调色板色。返回 (h,w,3) uint8。"""
    h, w, _ = rgb.shape
    px = rgb.reshape(-1, 3).astype(np.int32)
    pal = np.array(palette, dtype=np.int32)
    d = ((px[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
    idx = d.argmin(axis=1)
    return pal[idx].reshape(h, w, 3).astype(np.uint8)


def _merge_tiny_regions(q, min_ratio=0.025, rounds=6):
    """把占比过小的颜色块并入相邻最多的颜色，避免出现只有一两格的“碎色”
    （碎色会让代码生成一堆 1~2 载货量的小车关卡）。"""
    q = q.copy()
    h, w, _ = q.shape
    total = h * w
    for _ in range(rounds):
        flat = q.reshape(-1, 3)
        vals, counts = np.unique(flat, axis=0, return_counts=True)
        small = {tuple(v) for v, c in zip(vals, counts) if c < min_ratio * total}

        # 同时把只占 1~2 格的孤立单点也清掉
        changed = False
        for y in range(h):
            for x in range(w):
                cur = tuple(int(v) for v in q[y, x])
                if cur not in small:
                    continue
                nb = {}
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        c = tuple(int(v) for v in q[ny, nx])
                        if c != cur:
                            nb[c] = nb.get(c, 0) + 1
                if nb:
                    q[y, x] = np.array(max(nb.items(), key=lambda kv: kv[1])[0], dtype=np.uint8)
                    changed = True
        if not changed:
            break
    return q


def _boost_for_palette(arr, gain=0.95, gamma=0.90):
    """量化前先把 AI 那种“柔和浅色”推向调色板的鲜艳区间。
    否则浅绿 #80C070 会被吸成灰、浅青 #D0F0F0 会被吸成白。
    做法：HSV 空间做 vibrance（低饱和提得多、高饱和提得少）+ gamma 提亮，
    纯黑轮廓 v=0 不受影响。"""
    a = arr.astype(np.float32) / 255.0
    mx, mn = a.max(axis=2), a.min(axis=2)
    v = mx
    s = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    s2 = np.clip(s * (1.0 + gain * (1.0 - s)), 0.0, 1.0)
    v2 = np.clip(np.power(v, gamma), 0.0, 1.0)
    span = np.maximum(mx - mn, 1e-6)
    k = np.where(mx > 1e-6, (v2 * s2) / span, 0.0)
    out = (a - mn[..., None]) * k[..., None] + (v2 * (1.0 - s2))[..., None]
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


def _quantize_then_downsample(im, gw, gh, palette, boost=True):
    """先在全分辨率把每个像素吸附到最近的调色板色，再对每个格子取“众数”。
    这样比先缩放再量化干净得多——缩放产生的过渡色会被邻居投票淘汰，
    心形的深红不会被错吸成棕色。"""
    W, H = im.size
    arr = np.array(im.convert("RGB"))
    if boost:
        arr = _boost_for_palette(arr)
    arr = arr.astype(np.int32)
    pal = np.array(palette, dtype=np.int32)

    # 全分辨率最近邻吸附（按块计算，避免 (H*W, K) 的巨型中间数组）
    idx = np.empty((H, W), dtype=np.uint8)
    step = 256
    for y0 in range(0, H, step):
        y1 = min(H, y0 + step)
        block = arr[y0:y1].reshape(-1, 3)
        d = ((block[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
        idx[y0:y1] = d.argmin(axis=1).reshape(y1 - y0, W).astype(np.uint8)

    # 每格各调色板色的占比（BOX 缩放 = 面积平均 = 占比）
    votes = np.empty((len(palette), gh, gw), dtype=np.float32)
    for k in range(len(palette)):
        m = (idx == k).astype(np.float32)
        votes[k] = np.array(
            Image.fromarray(m, "F").resize((gw, gh), Image.Resampling.BOX)
        )
    best = votes.argmax(axis=0)
    return pal[best].astype(np.uint8)


def make_level(src_path, out_path, gw, gh, scale=16, tol=32, verbose=True,
               crop_to_aspect=True, min_ratio=0.012, boost=True):
    """把生成的像素画整理成 gw x gh 的关卡底图（1 像素 = 1 格），
    再按 scale 放大导出便于肉眼检查。同时打印颜色统计。"""
    im = Image.open(src_path).convert("RGB")
    # 0) 可选：先居中裁到目标宽高比，避免缩放拉伸变形
    if crop_to_aspect:
        W, H = im.size
        target = gw / gh
        cur = W / H
        if cur > target:               # 太宽，裁左右
            nw = int(round(H * target))
            x0 = (W - nw) // 2
            im = im.crop((x0, 0, x0 + nw, H))
        elif cur < target:             # 太高，裁上下
            nh = int(round(W / target))
            y0 = (H - nh) // 2
            im = im.crop((0, y0, W, y0 + nh))
    # 1) 全分辨率吸附调色板 + 按格众数降采样
    q = _quantize_then_downsample(im, gw, gh, PALETTE_16, boost=boost)
    # 2.5) 合并碎色块
    q = _merge_tiny_regions(q, min_ratio=min_ratio)

    # 3) 统计
    counts = {}
    for c in q.reshape(-1, 3):
        counts[tuple(int(v) for v in c)] = counts.get(tuple(int(v) for v in c), 0) + 1

    name_of = {v: k for k, v in PALETTE.items()}
    if verbose:
        total = gw * gh
        print(f"  [level] {os.path.basename(out_path)} {gw}x{gh} = {total} 格")
        for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"      {name_of.get(c,'?'):10s} #{c[0]:02X}{c[1]:02X}{c[2]:02X}  {n:5d} 格  {n/total*100:5.1f}%")
        print(f"      颜色种类: {len(counts)}")

    # 4) 导出：1x 原始 + scale 倍检查图
    Image.fromarray(q, "RGB").save(out_path)
    big = Image.fromarray(q, "RGB").resize((gw * scale, gh * scale), Image.Resampling.NEAREST)
    big.save(out_path.replace(".png", f"@{scale}x.png"))
    return out_path, counts


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "bg":
        # bg <in> <out> [tol]
        remove_bg(sys.argv[2], sys.argv[3], tol=int(sys.argv[4]) if len(sys.argv) > 4 else 22)
    elif cmd == "fit":
        # fit <in> <out> <W> <H> <fill>
        fit_canvas(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]),
                   fill=float(sys.argv[6]))
    elif cmd == "level":
        # level <in> <out> <gw> <gh> [min_ratio]
        make_level(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]),
                   min_ratio=float(sys.argv[6]) if len(sys.argv) > 6 else 0.012)
    else:
        print(__doc__)
