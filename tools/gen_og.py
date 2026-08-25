#!/usr/bin/env python3
"""Generate public/assets/og.png (1200x630) — pure stdlib, no PIL."""
import math
import struct
import zlib

W, H = 1200, 630
BG = (0x15, 0x0E, 0x09)
CREAM = (0xF2, 0xE7, 0xD8)
COPPER = (0xCD, 0x7F, 0x42)
COPPER2 = (0xE3, 0xAC, 0x6D)
LINE = (0x3A, 0x2C, 0x1E)

img = bytearray(BG * (W * H))


def px(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        img[i:i+3] = bytes(c)


def disc(cx, cy, r, c):
    r2 = r * r
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                px(x, y, c)


def line(x0, y0, x1, y1, c, t=1):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        for ox in range(-(t // 2), t - t // 2):
            for oy in range(-(t // 2), t - t // 2):
                px(x + ox, y + oy, c)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def circle_arc(cx, cy, r, a0, a1, c, t=1, step=0.02):
    a = a0
    while a <= a1:
        x = int(round(cx + r * math.cos(a)))
        y = int(round(cy + r * math.sin(a)))
        disc(x, y, max(0, t // 2), c)
        a += step


def dotted_route(x0, y0, x1, y1, c, dots=26, sag=140):
    for i in range(dots + 1):
        f = i / dots
        x = int(x0 + (x1 - x0) * f)
        y = int(y0 + (y1 - y0) * f + sag * math.sin(math.pi * f) * -0.6)
        if i % 2 == 0:
            disc(x, y, 3, c)


# --- composition ---
# concentric harbor arcs, bottom center
for r, col in ((460, LINE), (380, LINE), (300, (0x4A, 0x38, 0x24))):
    circle_arc(600, 760, r, math.pi, 2 * math.pi, col, t=2)

# dotted trade route across the top
dotted_route(70, 130, 1130, 90, COPPER)
disc(70, 130, 6, COPPER)
disc(1130, 90, 6, COPPER)

# lateen-sail dhow, right of center
cx0 = 760
sail = [(cx0, 470), (cx0 + 60, 200), (cx0 + 200, 470)]
line(*sail[0], *sail[1], COPPER2, t=3)
line(*sail[1], *sail[2], COPPER2, t=3)
line(*sail[2], *sail[0], COPPER2, t=3)
# sail fill hint: a few inner lines
for f in (0.25, 0.5, 0.75):
    ax = int(sail[0][0] + (sail[1][0] - sail[0][0]) * f)
    ay = int(sail[0][1] + (sail[1][1] - sail[0][1]) * f)
    bx = int(sail[2][0] + (sail[1][0] - sail[2][0]) * f)
    by = int(sail[2][1] + (sail[1][1] - sail[2][1]) * f)
    line(ax, ay, bx, by, (0x5A, 0x3C, 0x20), t=1)
# mast + yard
line(cx0 + 60, 200, cx0 - 10, 490, COPPER2, t=3)
# hull
line(cx0 - 60, 500, cx0 + 260, 500, COPPER, t=4)
line(cx0 - 40, 530, cx0 + 240, 530, COPPER, t=4)
line(cx0 - 60, 500, cx0 - 40, 530, COPPER, t=4)
line(cx0 + 260, 500, cx0 + 240, 530, COPPER, t=4)

# waves under hull
for row, y in enumerate((565, 595)):
    for k in range(9):
        x = 600 + k * 52 + row * 26
        circle_arc(x, y, 22, math.pi, 2 * math.pi, (0x66, 0x52, 0x38), t=2, step=0.05)

# big M letterform, left
mx, my = 130, 200
mh, mw = 260, 170
line(mx, my + mh, mx, my, CREAM, t=9)
line(mx, my, mx + mw // 2, my + int(mh * 0.55), CREAM, t=9)
line(mx + mw // 2, my + int(mh * 0.55), mx + mw, my, CREAM, t=9)
line(mx + mw, my, mx + mw, my + mh, CREAM, t=9)
# copper wave mark under the M
for k in range(3):
    x = mx + 10 + k * 58
    circle_arc(x, my + mh + 60, 24, math.pi, 2 * math.pi, COPPER, t=4, step=0.05)

# stamp ring around the dhow
circle_arc(cx0 + 100, 385, 235, 0, 2 * math.pi, (0x6B, 0x45, 0x24), t=2, step=0.008)

# --- encode PNG ---
def chunk(tag, data):
    c = tag + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

raw = bytearray()
for y in range(H):
    raw.append(0)
    raw += img[y * W * 3:(y + 1) * W * 3]

png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
       + chunk(b"IEND", b""))

out = "/home/ubuntu/mokhacaffe/public/assets/og.png"
with open(out, "wb") as f:
    f.write(png)
print(f"wrote {out} ({len(png)} bytes)")
