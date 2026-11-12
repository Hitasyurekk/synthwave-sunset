# coolest-art-01 entry (MIT): a synthwave sunset over a neon grid, computed per
# pixel with the standard library only and written to /output/entry.png. Deterministic.
import math, os, struct, zlib

W = H = 1024
HOR = 640          # horizon line
SUN = (512, 470, 250)


def mix(a, b, t):
    return [a[k] + (b[k] - a[k]) * t for k in range(3)]


def hexc(s):
    return [int(s[i:i + 2], 16) / 255 for i in (1, 3, 5)]


SKY = [hexc("#0b0221"), hexc("#2a0845"), hexc("#6a0f6b"), hexc("#d4246f"), hexc("#ff7b54")]
SUN_TOP, SUN_BOT = hexc("#ffe66d"), hexc("#ff2e88")
MAGENTA, CYAN = hexc("#ff3cac"), hexc("#2bd2ff")


def ramp(cols, t):
    t = max(0.0, min(1.0, t)) * (len(cols) - 1)
    i = min(int(t), len(cols) - 2)
    return mix(cols[i], cols[i + 1], t - i)


def hash2(x, y):
    n = (x * 374761393 + y * 668265263) & 0xffffffff
    n = ((n ^ (n >> 13)) * 1274126177) & 0xffffffff
    return (n ^ (n >> 16)) / 0xffffffff


def ridge(x, seed, amp, base):
    s = 0.0
    for k, (f, a) in enumerate(((0.004, 1.0), (0.011, 0.45), (0.027, 0.2), (0.06, 0.08))):
        s += a * math.sin(x * f + seed * (k + 1.7)) + a * 0.5 * math.sin(x * f * 2.3 + seed * 3.1 + k)
    # keep the valley in the middle so the sun shows through
    v = 0.35 + 0.65 * min(1.0, abs(x - 512) / 360) ** 1.5
    return base - amp * (0.6 + 0.4 * s) * v


def sky(x, y):
    c = ramp(SKY, (y / HOR) ** 1.6)
    # stars, fading toward the horizon
    if y < HOR - 160:
        h = hash2(x, y)
        if h > 0.9975:
            tw = (h - 0.9975) / 0.0025
            c = mix(c, [1, 1, 1], tw * (1 - y / (HOR - 160)))
    sx, sy, sr = SUN
    d = math.hypot(x - sx, y - sy)
    # glow around the sun
    c = mix(c, hexc("#ff4f9a"), 0.55 * math.exp(-max(0.0, d - sr) / 90))
    if d < sr:
        t = (y - (sy - sr)) / (2 * sr)
        band = True
        if t > 0.52:
            # horizontal cut-outs that thicken toward the bottom
            u = (t - 0.52) / 0.48
            period = 34
            gap = 6 + 14 * u
            band = ((y - (sy - sr)) % period) > gap
        if band:
            edge = min(1.0, sr - d)
            c = mix(c, ramp([SUN_TOP, hexc("#ffb347"), SUN_BOT], t), edge)
    return c


def ground(x, y):
    dy = y - HOR + 0.5
    z = 220.0 / dy                     # distance along the floor
    gx = (x - 512) * z / 220.0         # world x
    c = mix(hexc("#1a0433"), hexc("#05010f"), min(1.0, dy / 380))
    fade = min(1.0, dy / 140)
    # grid lines: exact distance in screen pixels to the nearest line of each family
    k = max(1, round(z * 2.2))
    dz = abs(dy - 220.0 * 2.2 / k)                 # to the nearest cross line (constant z)
    m = round(gx * 3.0)
    dxl = abs(x - (512 + m / 3.0 * dy))            # to the nearest line running to the horizon
    w = 0.6 + dy / 260                             # lines get wider as they come closer
    line = max(max(0.0, 1 - max(0.0, dz - w) / 1.0) * min(1.0, dy / 90),
               max(0.0, 1 - max(0.0, dxl - w) / 1.0))
    glow = max(math.exp(-dz / (2 + dy / 60)) * min(1.0, dy / 90), math.exp(-dxl / (2 + dy / 60)))
    neon = mix(MAGENTA, CYAN, min(1.0, abs(x - 512) / 600))
    c = mix(c, neon, 0.45 * glow * (0.3 + 0.7 * fade))
    c = mix(c, mix(neon, [1, 1, 1], 0.3), line * (0.55 + 0.45 * fade))
    # sun reflection streaks
    sx, _, sr = SUN
    if abs(x - sx) < sr * 0.9 and dy < 260:
        r = (1 - abs(x - sx) / (sr * 0.9)) * (1 - dy / 260)
        if int(dy) % 9 < 4:
            c = mix(c, hexc("#ff6fa8"), 0.35 * r)
    return c


def pixel(x, y):
    if y >= HOR:
        c = ground(x, y)
    else:
        c = sky(x, y)
        far, near = ridge(x, 1.3, 120, HOR), ridge(x, 4.1, 70, HOR)
        if y > far:
            c = mix(hexc("#3b0d5c"), hexc("#1c0533"), (y - far) / max(1.0, HOR - far))
            c = mix(c, MAGENTA, max(0.0, 1 - (y - far) / 3.0) * 0.9)
        if y > near:
            c = mix(hexc("#14022a"), hexc("#090114"), (y - near) / max(1.0, HOR - near))
            c = mix(c, CYAN, max(0.0, 1 - (y - near) / 2.5) * 0.85)
    # horizon haze
    c = mix(c, hexc("#ff3c8e"), 0.5 * math.exp(-abs(y - HOR) / 18))
    # scanlines and vignette
    v = 1 - 0.55 * (math.hypot(x - 512, y - 512) / 724) ** 2.2
    s = 0.93 if y % 3 == 0 else 1.0
    return [ch * v * s for ch in c]


def write_png(path):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        for x in range(W):
            raw.extend(max(0, min(255, int(ch * 255 + 0.5))) for ch in pixel(x, y))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


write_png(os.environ.get("ENTRY_OUT", "/output/entry.png"))
