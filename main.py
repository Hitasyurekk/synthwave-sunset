# coolest-art-01 entry (MIT): "The Star Fisher". A small figure sits on the horn of a
# crescent moon and fishes a fallen star out of a night sea, while a giant whale drifts
# through the stars above. Background per pixel, then shapes painted as signed distance
# fields with anti-aliasing; standard library only, writes /output/entry.png. Deterministic.
import math, os, struct, zlib

W = H = 1024
HOR = 700  # the sea's horizon
img = [None] * (W * H)


def hexc(s):
    return [int(s[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def mix(a, b, t):
    return [a[k] + (b[k] - a[k]) * t for k in range(3)]


def ramp(cols, t):
    t = max(0.0, min(1.0, t)) * (len(cols) - 1)
    i = min(int(t), len(cols) - 2)
    return mix(cols[i], cols[i + 1], t - i)


def hash2(x, y):
    n = (x * 374761393 + y * 668265263) & 0xffffffff
    n = ((n ^ (n >> 13)) * 1274126177) & 0xffffffff
    return (n ^ (n >> 16)) / 0xffffffff


SKY = [hexc("#050a24"), hexc("#0c1a4a"), hexc("#16357a"), hexc("#2f6aa3"), hexc("#7fc4c9")]
MOON = (640, 300, 175)            # the crescent's outer circle
GOLD, GOLD_D = hexc("#ffe7a3"), hexc("#f2b84b")


def background():
    mx, my, mr = MOON
    for y in range(H):
        for x in range(W):
            if y < HOR:
                c = ramp(SKY, (y / HOR) ** 1.4)
                # aurora ribbons
                a = math.sin(x * 0.006 + 1.3) * 60 + math.sin(x * 0.017) * 18 + 250
                c = mix(c, hexc("#4ef0c0"), 0.28 * math.exp(-((y - a) / 38) ** 2) * (0.5 + 0.5 * math.sin(x * 0.03)))
                # stars, a few bright with a cross glint
                h = hash2(x, y)
                if h > 0.9978:
                    c = mix(c, [1, 1, 0.92], (h - 0.9978) / 0.0022 * (1 - y / HOR * 0.7))
                # moon glow
                d = math.hypot(x - mx, y - my)
                c = mix(c, GOLD, 0.38 * math.exp(-max(0.0, d - mr) / 110))
            else:
                dy = y - HOR
                c = mix(hexc("#123a6b"), hexc("#040b1f"), min(1.0, dy / 300))
                # moon path: shimmering streaks under the moon
                w = 120 + dy * 0.9
                k = math.exp(-((x - mx) / w) ** 2)
                ripple = 0.5 + 0.5 * math.sin(dy * 0.9 + math.sin(x * 0.05 + dy * 0.1) * 3)
                c = mix(c, GOLD, 0.55 * k * ripple * math.exp(-dy / 260))
                # reflected stars, stretched into short dashes
                h = hash2(x // 6, y)
                if h > 0.996:
                    c = mix(c, [0.9, 0.95, 1], 0.5 * (1 - dy / 330))
            img[y * W + x] = c


def paint(sdf, box, color, alpha=1.0, soft=1.0):
    """Blend color where sdf(x, y) < 0, anti-aliased over `soft` pixels."""
    pad = soft
    x0, y0, x1, y1 = (int(max(0, min(W - 1, v))) for v in (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad))
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            d = sdf(x + 0.5, y + 0.5)
            a = min(1.0, max(0.0, 0.5 - d / soft)) * alpha
            if a > 0:
                p = img[y * W + x]
                img[y * W + x] = [p[k] + (color[k] - p[k]) * a for k in range(3)]


def circle(cx, cy, r):
    return (lambda x, y: math.hypot(x - cx, y - cy) - r), (cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2)


def ellipse(cx, cy, rx, ry, rot=0.0):
    c, s = math.cos(rot), math.sin(rot)
    r = min(rx, ry)

    def f(x, y):
        dx, dy = x - cx, y - cy
        u, v = (dx * c + dy * s) / rx, (-dx * s + dy * c) / ry
        return (math.hypot(u, v) - 1) * r
    m = max(rx, ry) + 2
    return f, (cx - m, cy - m, cx + m, cy + m)


def capsule(ax, ay, bx, by, r):
    def f(x, y):
        px, py, qx, qy = x - ax, y - ay, bx - ax, by - ay
        h = max(0.0, min(1.0, (px * qx + py * qy) / (qx * qx + qy * qy)))
        return math.hypot(px - qx * h, py - qy * h) - r
    return f, (min(ax, bx) - r - 2, min(ay, by) - r - 2, max(ax, bx) + r + 2, max(ay, by) + r + 2)


def poly(pts, rnd=0.0):
    def f(x, y):
        d, inside, n = 1e9, False, len(pts)
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            qx, qy = bx - ax, by - ay
            h = max(0.0, min(1.0, ((x - ax) * qx + (y - ay) * qy) / (qx * qx + qy * qy)))
            d = min(d, math.hypot(x - ax - qx * h, y - ay - qy * h))
            if (ay > y) != (by > y) and x < ax + (y - ay) * qx / qy:
                inside = not inside
        return (-d if inside else d) - rnd
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return f, (min(xs) - rnd - 2, min(ys) - rnd - 2, max(xs) + rnd + 2, max(ys) + rnd + 2)


def star(cx, cy, r, inner=0.45, rot=-math.pi / 2):
    pts = []
    for k in range(10):
        a = rot + k * math.pi / 5
        rr = r if k % 2 == 0 else r * inner
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return poly(pts, r * 0.06)


def whale():
    # a giant whale drifting left through the sky, dotted with constellation lights
    body = ellipse(300, 170, 230, 78, 0.12)[0]
    head = ellipse(150, 150, 110, 70, 0.05)[0]
    tail = poly([(500, 190), (585, 120), (565, 175), (610, 230), (540, 215)], 6)[0]
    fin = poly([(270, 215), (330, 280), (300, 215)], 4)[0]

    def f(x, y):
        return min(body(x, y), head(x, y), tail(x, y), fin(x, y))
    box = (30, 70, 620, 290)
    paint(f, box, hexc("#0a1640"), 0.92)
    # pale belly and a rim of moonlight along the back
    paint(lambda x, y: max(f(x, y), 175 - y + (x - 300) * 0.12), box, hexc("#2a4a8a"), 0.5)
    paint(lambda x, y: abs(f(x, y) + 3) - 2.2 if y < 200 and x < 470 else 1e3, box, hexc("#bfe9ff"), 0.55)
    paint(*circle(118, 140, 7), hexc("#bfe9ff"))
    # constellation on its side
    pts = [(220, 160), (275, 140), (330, 158), (390, 145), (445, 170)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        paint(*capsule(ax, ay, bx, by, 1.2), hexc("#9fd8ff"), 0.6)
    for px, py in pts:
        paint(*circle(px, py, 4.5), [1, 1, 0.9])
        paint(*circle(px, py, 12), hexc("#9fd8ff"), 0.25, 8)
    # a spout of stardust
    for k in range(9):
        a = -1.9 + k * 0.1
        paint(*circle(160 + math.cos(a) * (40 + k * 6), 82 + math.sin(a) * (30 + k * 5), 3 + (k % 3)), GOLD, 0.7)


def moon_and_fisher():
    mx, my, mr = MOON
    outer = circle(mx, my, mr)[0]
    cut = circle(mx + 85, my - 55, mr * 0.88)[0]

    def crescent(x, y):
        return max(outer(x, y), -cut(x, y))
    box = (mx - mr, my - mr, mx + mr, my + mr)
    paint(crescent, box, GOLD)
    paint(lambda x, y: max(crescent(x, y), -(math.hypot(x - mx + 60, y - my - 30) - 120)), box, GOLD_D, 0.45, 30)
    for cx, cy, r in ((520, 310, 14), (560, 380, 10), (505, 250, 8)):
        paint(*circle(cx, cy, r), GOLD_D, 0.5, 2)
    # the fisher, sitting on the lower horn
    sx, sy = 728, 404  # seated on the inner edge of the lower horn
    dark = hexc("#111a33")
    paint(*ellipse(sx, sy - 30, 22, 30), dark)                       # body
    paint(*circle(sx + 4, sy - 72, 17), dark)                        # head
    paint(*poly([(sx - 14, sy - 84), (sx + 26, sy - 84), (sx + 4, sy - 132)], 3), hexc("#c0392b"))  # pointed hat
    paint(*circle(sx + 4, sy - 133, 5), GOLD)
    paint(*capsule(sx - 8, sy - 6, sx - 28, sy + 40, 6), dark)       # dangling legs
    paint(*capsule(sx + 10, sy - 6, sx + 2, sy + 44, 6), dark)
    paint(*capsule(sx, sy - 40, sx - 40, sy - 52, 5), dark)          # arm
    # the rod and the long line down to the sea
    tip = (sx - 190, sy - 150)
    paint(*capsule(sx - 40, sy - 52, tip[0], tip[1], 3), hexc("#6b4a2b"))
    lx, ly = 500, 860
    for k in range(60):
        t0, t1 = k / 60, (k + 1) / 60
        def pt(t):
            return (tip[0] + (lx - tip[0]) * t, tip[1] + (ly - tip[1]) * t + 60 * math.sin(math.pi * t))
        (ax, ay), (bx, by) = pt(t0), pt(t1)
        paint(*capsule(ax, ay, bx, by, 1.1), hexc("#e8f4ff"), 0.7)
    # the hooked star, half out of the water, with ripples and glow
    for r, a in ((140, 0.10), (90, 0.18), (55, 0.3)):
        paint(*circle(lx, ly, r), GOLD, a, r * 0.6)
    for k, rr in enumerate((60, 95, 135)):
        paint(lambda x, y, rr=rr: abs(math.hypot((x - lx) / 2.6, y - ly - 22) - rr / 2.6) - 1.6, (lx - rr - 4, ly - 40, lx + rr + 4, ly + 80),
              hexc("#cfe9ff"), 0.45 - k * 0.12)
    paint(*star(lx, ly, 46), [1, 0.97, 0.8])
    paint(*star(lx, ly, 30), [1, 1, 1], 0.7)
    for k in range(12):
        a = k * math.pi / 6 + 0.2
        d = 70 + (k % 3) * 18
        paint(*circle(lx + math.cos(a) * d, ly + math.sin(a) * d * 0.7, 2.5), GOLD, 0.9)


def lanterns():
    for x, y, s in ((140, 560, 16), (230, 480, 12), (880, 520, 14), (950, 430, 10), (820, 610, 11)):
        paint(*circle(x, y, s * 3), hexc("#ffb347"), 0.18, s * 2)
        paint(*ellipse(x, y, s, s * 1.3), hexc("#ff9f43"))
        paint(*ellipse(x, y - s * 0.3, s * 0.55, s * 0.6), hexc("#ffe7a3"), 0.8, 3)
        # reflection on the water
        paint(*capsule(x, 2 * HOR - y - 4, x, 2 * HOR - y + 22, s * 0.5), hexc("#ffb347"), 0.25, 4)


def glints():
    # a few bright stars with four-point flares
    for x, y, s in ((90, 60, 16), (450, 40, 12), (930, 70, 18), (820, 230, 10), (60, 420, 11), (380, 330, 9)):
        paint(*circle(x, y, s * 0.9), [1, 1, 0.95], 0.25, s)
        paint(*capsule(x - s * 2.2, y, x + s * 2.2, y, 1.1), [1, 1, 0.95], 0.8)
        paint(*capsule(x, y - s * 2.2, x, y + s * 2.2, 1.1), [1, 1, 0.95], 0.8)
        paint(*circle(x, y, 2.6), [1, 1, 1])


def clouds():
    # thin moonlit clouds drifting low across the sky
    for cx, cy, w, a in ((180, 470, 170, 0.22), (900, 610, 150, 0.2), (420, 600, 120, 0.14)):
        for dx, dy, r in ((-0.6, 0.1, 0.35), (-0.2, -0.15, 0.45), (0.25, -0.05, 0.4), (0.6, 0.12, 0.3)):
            paint(*ellipse(cx + dx * w, cy + dy * w * 0.4, r * w, r * w * 0.38), hexc("#9fb8e8"), a, 14)


def boat():
    # a little paper boat riding the moon path, with a lantern at the bow
    bx, by = 300, 800
    hull = poly([(bx - 70, by - 12), (bx + 70, by - 12), (bx + 46, by + 18), (bx - 46, by + 18)], 3)
    paint(*hull, hexc("#f4efe6"))
    paint(*poly([(bx - 4, by - 12), (bx - 4, by - 78), (bx + 44, by - 12)], 2), hexc("#ffffff"))
    paint(*poly([(bx - 10, by - 12), (bx - 10, by - 64), (bx - 52, by - 12)], 2), hexc("#e3dccd"))
    paint(*circle(bx + 62, by - 26, 26), hexc("#ffb347"), 0.25, 16)
    paint(*circle(bx + 62, by - 26, 7), hexc("#ffd27a"))
    # its wobbling reflection
    for k in range(6):
        y = by + 26 + k * 7
        paint(*capsule(bx - 40 + k * 3, y, bx + 40 - k * 3, y, 2), hexc("#f4efe6"), 0.18 - k * 0.025)


def vignette():
    for y in range(H):
        for x in range(W):
            v = 1 - 0.5 * (math.hypot(x - 512, y - 512) / 724) ** 2.4
            p = img[y * W + x]
            img[y * W + x] = [c * v for c in p]


def write_png(path):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        for x in range(W):
            raw.extend(max(0, min(255, int(c * 255 + 0.5))) for c in img[y * W + x])

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


background()
glints()
clouds()
whale()
lanterns()
moon_and_fisher()
boat()
vignette()
write_png(os.environ.get("ENTRY_OUT", "/output/entry.png"))
