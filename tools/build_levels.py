#!/usr/bin/env python3
"""把 assets/levels/level*.png 转成 src/levels.js（1 像素 = 1 格，吸附 16 色调色板）。"""
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PALETTE = {
    'white': '#FFFFFF', 'black': '#1A1A1A', 'gray': '#8A8A8A', 'red': '#E23B3B',
    'orange': '#F28C28', 'yellow': '#F7D13E', 'green': '#3FA34D', 'darkgreen': '#1F6E43',
    'lightblue': '#7EC8F0', 'blue': '#2F80ED', 'purple': '#8E5BD9', 'pink': '#F06AA8',
    'brown': '#8C5A2B', 'beige': '#EAD9B8',
}
PAL_RGB = {name: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for name, h in PALETTE.items()}


def nearest_name(rgb):
    best, best_d = None, 1e9
    for name, p in PAL_RGB.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, p))
        if d < best_d:
            best, best_d = name, d
    return best


def main():
    levels = []
    for i in range(1, 11):
        path = os.path.join(ROOT, 'assets', 'levels', f'level{i:02d}.png')
        im = Image.open(path).convert('RGB')
        w, h = im.size
        px = im.load()
        counts = {}
        char_of_color = {}
        chars = []
        for y in range(h):
            for x in range(w):
                name = nearest_name(px[x, y])
                counts[name] = counts.get(name, 0) + 1
                if name not in char_of_color:
                    char_of_color[name] = chr(ord('a') + len(char_of_color))
                chars.append(char_of_color[name])
        levels.append({
            'w': w, 'h': h,
            'colors': list(char_of_color.keys()),
            'cells': ''.join(chars),
            'counts': counts,
        })
        print(f'level{i:02d} {w}x{h} colors={len(counts)}')

    js = '// 由 tools/build_levels.py 自动生成，勿手改\nconst LEVELS = '
    js += json.dumps(levels, separators=(',', ':'))
    js += ';\n'
    out = os.path.join(ROOT, 'src', 'levels.js')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(js)
    print(f'-> {out}')


if __name__ == '__main__':
    main()
