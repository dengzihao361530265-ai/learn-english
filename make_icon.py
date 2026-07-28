# -*- coding: utf-8 -*-
"""生成背单词应用图标：蓝紫渐变圆角方块 + 白色 Aa 字样"""
import os
from PIL import Image, ImageDraw, ImageFont

SIZE = 256
RADIUS = 56

img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))

# 渐变底色（从 #0A84FF 到 #5E5CE6，对角线渐变）
grad = Image.new('RGBA', (SIZE, SIZE))
top = (10, 132, 255)    # #0A84FF
bot = (94, 92, 230)     # #5E5CE6
px = grad.load()
for y in range(SIZE):
    for x in range(0, SIZE, 4):
        t = (x + y) / (2 * SIZE)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,)
        for dx in range(4):
            if x + dx < SIZE:
                px[x + dx, y] = c

# 圆角蒙版
mask = Image.new('L', (SIZE, SIZE), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=RADIUS, fill=255)
img.paste(grad, (0, 0), mask)

# 文字 “Aa”
d = ImageDraw.Draw(img)
font = None
for name in ('segoeuib.ttf', 'arialbd.ttf', 'msyhbd.ttc'):
    p = os.path.join(r'C:\Windows\Fonts', name)
    if os.path.exists(p):
        font = ImageFont.truetype(p, 118)
        break
if font is None:
    font = ImageFont.load_default()

text = 'Aa'
bbox = d.textbbox((0, 0), text, font=font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
d.text(((SIZE - tw) / 2 - bbox[0], (SIZE - th) / 2 - bbox[1]), text, font=font, fill=(255, 255, 255, 255))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
img.save(out, format='ICO', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print('saved:', out)
