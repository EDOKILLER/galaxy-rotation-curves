#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Icona di Curve di rotazione: una galassia a spirale vista di taglio (disco azzurro, nucleo dorato,
banda di polvere) attraversata da due curve: quella misurata, dorata e piatta, e quella che darebbe la
sola materia visibile, tratteggiata, che scende. Fondo blu notte stellato con un alone viola (la
materia oscura). © 2026 Edoardo Battistel"""
import math
import random
from PIL import Image, ImageDraw, ImageFilter

LATO = 512
S = 4


def crea(png="curve_rotazione.png", ico="curve_rotazione.ico"):
    L = LATO * S
    fondo = Image.new("RGBA", (L, L))
    d = ImageDraw.Draw(fondo)
    for y in range(L):
        u = y / L
        d.line([(0, y), (L, y)], fill=(int(10 + 8 * u), int(14 + 6 * u), int(46 - 16 * u), 255))
    maschera = Image.new("L", (L, L), 0)
    ImageDraw.Draw(maschera).rounded_rectangle([0, 0, L - 1, L - 1], radius=int(0.18 * L), fill=255)
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    img.paste(fondo, (0, 0), maschera)
    vuoto = Image.new("RGBA", (L, L), (0, 0, 0, 0))

    # alone di materia oscura: grande nebbia viola attorno alla galassia
    alone = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    da = ImageDraw.Draw(alone)
    cx, cy = 0.5 * L, 0.56 * L
    for k in range(40, 0, -1):
        r = 0.46 * L * k / 40
        da.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=(140, 90, 230, 9))
    alone = alone.filter(ImageFilter.GaussianBlur(S * 12))
    img = Image.alpha_composite(img, Image.composite(alone, vuoto, maschera))

    d = ImageDraw.Draw(img)
    rnd = random.Random(3198)
    for _ in range(160):
        x, y = rnd.uniform(0.05, 0.95) * L, rnd.uniform(0.05, 0.95) * L
        r = rnd.choice([1, 1, 1, 2, 2, 3]) * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=(225, 235, 255, rnd.randint(80, 220)))

    # galassia vista di taglio
    gal = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    dg = ImageDraw.Draw(gal)
    for k in range(30, 0, -1):
        w = 0.42 * L * k / 30
        h = 0.075 * L * k / 30
        a = int(30 + 45 * (30 - k) / 30)
        dg.ellipse([cx - w, cy - h, cx + w, cy + h], fill=(165, 210, 255, a))
    for k in range(20, 0, -1):
        r = 0.09 * L * k / 20
        dg.ellipse([cx - r, cy - r * 0.75, cx + r, cy + r * 0.75], fill=(255, 215, 140, 45))
    gal = gal.filter(ImageFilter.GaussianBlur(S * 2))
    img = Image.alpha_composite(img, gal)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - 0.035 * L, cy - 0.028 * L, cx + 0.035 * L, cy + 0.028 * L], fill=(255, 245, 220, 255))
    polvere = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    ImageDraw.Draw(polvere).ellipse([cx - 0.33 * L, cy - 0.006 * L, cx + 0.33 * L, cy + 0.010 * L], fill=(40, 25, 35, 170))
    img = Image.alpha_composite(img, polvere.filter(ImageFilter.GaussianBlur(S * 2)))
    d = ImageDraw.Draw(img)

    # le due curve: piatta (misurata, dorata) e che scende (materia visibile, tratteggiata)
    x0, x1 = 0.10 * L, 0.90 * L
    ybase = 0.84 * L
    alto = 0.62 * L

    def punto(u, f):
        return (x0 + u * (x1 - x0), ybase - f * alto)
    misurata = [punto(u / 300, (1 - math.exp(-u / 300 * 9)) * 0.92) for u in range(301)]
    visibile = [punto(u / 300, 1.25 * (u / 300 * 6) * math.exp(-u / 300 * 3.2) * 0.62) for u in range(301)]
    luce = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    dl = ImageDraw.Draw(luce)
    dl.line(misurata, fill=(255, 200, 80, 255), width=18 * S, joint="curve")
    luce = luce.filter(ImageFilter.GaussianBlur(S * 7))
    img = Image.alpha_composite(img, luce)
    d = ImageDraw.Draw(img)
    d.line(misurata, fill=(255, 210, 95, 255), width=7 * S, joint="curve")
    for i in range(0, 300, 18):
        d.line(visibile[i:i + 10], fill=(170, 215, 255, 255), width=5 * S)
    for p in misurata[30::45]:
        r = 7 * S
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(255, 240, 200, 255), outline=(120, 70, 10, 255),
                  width=S)

    img.putalpha(Image.fromarray(__import__("numpy").minimum(__import__("numpy").asarray(img.split()[3]),
                                                            __import__("numpy").asarray(maschera))))
    piccola = img.resize((LATO, LATO), Image.LANCZOS)
    piccola.save(png)
    piccola.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return png


if __name__ == "__main__":
    print(crea())
