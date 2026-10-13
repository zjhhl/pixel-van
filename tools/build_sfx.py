#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二批：音效合成。

文档 §6 的 4 个音效没有现成素材，这里用纯代码合成（numpy 造波形 -> wav -> lame 转 mp3）。
好处是体积小、无版权问题，后续想换直接替换 assets/sfx/*.mp3 即可。

  click.mp3  点击     短促高频 click
  drop.mp3   方块落格 短促 pop，会高频播放，所以音量刻意压低
  drive.mp3  车启动   低频引擎渐起
  win.mp3    过关     上行琶音 + 泛音
"""

import os
import subprocess
import wave
import numpy as np

ROOT = "/Users/zhujinhui/claudeProject5/pixel-van"
OUT = os.path.join(ROOT, "assets/sfx")
TMP = "/tmp/pv_sfx"
os.makedirs(OUT, exist_ok=True)
os.makedirs(TMP, exist_ok=True)
SR = 44100


# ---------------------------------------------------------------- 基础工具
def t(dur):
    return np.linspace(0, dur, int(SR * dur), endpoint=False)


def env_exp(dur, tau, attack=0.002):
    """快起 + 指数衰减包络。"""
    e = np.exp(-t(dur) / tau)
    a = int(SR * attack)
    if a > 1:
        e[:a] *= np.linspace(0, 1, a)
    return e


def sine(freq, dur, phase=0.0):
    if np.isscalar(freq):
        return np.sin(2 * np.pi * freq * t(dur) + phase)
    # 频率随时间线性变化（扫频）
    f = np.linspace(freq[0], freq[1], int(SR * dur), endpoint=False)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph + phase)


def trail(x, ms=6.0):
    """统一加一个很短的淡出，避免结尾爆音。"""
    n = int(SR * ms / 1000)
    if n > 0 and len(x) > n:
        x = x.copy()
        x[-n:] *= np.linspace(1, 0, n)
    return x


def norm(x, peak=0.9):
    m = np.abs(x).max()
    return x if m < 1e-9 else x / m * peak


def save_wav(path, x):
    x = np.clip(x, -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


# ---------------------------------------------------------------- 音效
def make_click():
    """点击：极短的木质 click，2000Hz 主体 + 一点点噪声瞬态。"""
    d = 0.055
    body = sine(2000, d) * env_exp(d, 0.010)
    body += 0.35 * sine(4000, d) * env_exp(d, 0.005)
    rng = np.random.default_rng(7)
    n = int(SR * 0.004)
    noise = np.zeros(int(SR * d))
    noise[:n] = rng.normal(0, 1, n) * np.linspace(1, 0, n)
    return trail(norm(body * 0.85 + noise * 0.15, 0.85))


def make_drop():
    """方块落格：短促 pop，音高从 720 滑到 400。会高频播放，压到 0.55 峰值。"""
    d = 0.085
    body = sine((720, 400), d) * env_exp(d, 0.022)
    body += 0.25 * sine((1440, 800), d) * env_exp(d, 0.012)
    return trail(norm(body, 0.55))          # ← 刻意比别的轻


def make_drive():
    """车启动：低频锯齿渐起 + 轻微起伏，营造引擎感。"""
    d = 0.75
    n = int(SR * d)
    f = np.linspace(95, 205, n, endpoint=False)
    ph = 2 * np.pi * np.cumsum(f) / SR
    saw = 2 * (ph / (2 * np.pi) % 1.0) - 1.0            # 锯齿波
    body = 0.55 * saw + 0.45 * np.sin(ph)               # 加点正弦让它不那么刺
    tt = np.linspace(0, d, n, endpoint=False)
    wob = 1.0 + 0.12 * np.sin(2 * np.pi * 7.5 * tt)     # 7.5Hz 抖动
    attack = 0.06
    e = np.where(tt < attack, tt / attack, np.exp(-(tt - attack) / 0.42))
    return trail(norm(body * wob * e, 0.72))


def make_win():
    """过关：C5-E5-G5-C6 上行琶音，带二次谐波，尾音留一点余韵。"""
    notes = [523.25, 659.25, 783.99, 1046.50]
    start = [0.0, 0.11, 0.22, 0.33]
    total = 1.15
    buf = np.zeros(int(SR * total))
    for f, s in zip(notes, start):
        i0 = int(SR * s)
        d = total - s
        tone = sine(f, d) * env_exp(d, 0.30)
        tone += 0.30 * sine(2 * f, d) * env_exp(d, 0.16)
        tone += 0.14 * sine(3 * f, d) * env_exp(d, 0.10)
        buf[i0:i0 + len(tone)] += tone[:len(buf) - i0]
    return trail(norm(buf, 0.86))


# ---------------------------------------------------------------- 主流程
SFX = [
    ("click.mp3", "点击",       make_click, 128),
    ("drop.mp3",  "方块落格",   make_drop,  128),
    ("drive.mp3", "车启动",     make_drive, 128),
    ("win.mp3",   "过关",       make_win,   160),
]


def main():
    print("=== 音效合成 ===")
    for name, desc, fn, bitrate in SFX:
        wav = os.path.join(TMP, name.replace(".mp3", ".wav"))
        mp3 = os.path.join(OUT, name)
        save_wav(wav, fn())
        subprocess.run(
            ["lame", "--quiet", "-b", str(bitrate), "-h", wav, mp3],
            check=True,
        )
        size = os.path.getsize(mp3)
        print(f"  {name:10s} {desc:6s} {size/1024:6.1f} KB")
    print("=== 完成 ===")


if __name__ == "__main__":
    main()
