#!/usr/bin/env python3
"""Post-processing for transparent PNGs.

    python postfx.py sticker in.png out.png [--border 12] [--shadow 0.3]   # white die-cut border + soft shadow
    python postfx.py trim    in.png out.png [--pad 12]                     # crop to visible area
    python postfx.py resize  in.png out.png --height 512 | --width 512     # proportional resize (LANCZOS)
"""
import argparse
from PIL import Image, ImageChops, ImageFilter

NAVY = (43, 35, 80)


def trim(im, pad=12):
    box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    im = im.crop(box) if box else im
    out = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    out.paste(im, (pad, pad))
    return out


def sticker(img, border=12, shadow_alpha=0.30, offset=(0, 10), blur=10, color=(255, 255, 255)):
    pad = border + blur * 2 + max(map(abs, offset)) + 4
    base = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    base.paste(img, (pad, pad), img)
    hard = base.getchannel("A").point(lambda v: 255 if v > 100 else 0)
    soft = hard.filter(ImageFilter.GaussianBlur(border / 2.0))  # round dilation
    outline = soft.point(lambda v: 0 if v <= 4 else 255 if v >= 22 else int((v - 4) * 255 / 18))
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    if shadow_alpha:
        sh = Image.new("RGBA", base.size, NAVY + (0,))
        sh.putalpha(outline.point(lambda v: int(v * shadow_alpha)))
        out.alpha_composite(ImageChops.offset(sh.filter(ImageFilter.GaussianBlur(blur / 2)), *offset))
    rim = Image.new("RGBA", base.size, color + (0,))
    rim.putalpha(outline)
    out.alpha_composite(rim)
    out.alpha_composite(base)
    return out.crop(out.getchannel("A").point(lambda v: 255 if v > 2 else 0).getbbox())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sticker", "trim", "resize"])
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--border", type=int, default=12)
    ap.add_argument("--shadow", type=float, default=0.30)
    ap.add_argument("--pad", type=int, default=12)
    ap.add_argument("--height", type=int)
    ap.add_argument("--width", type=int)
    a = ap.parse_args()
    im = Image.open(a.src).convert("RGBA")
    if a.cmd == "sticker":
        im = sticker(im, a.border, a.shadow)
    elif a.cmd == "trim":
        im = trim(im, a.pad)
    elif a.height:
        im = im.resize((round(im.width * a.height / im.height), a.height), Image.LANCZOS)
    elif a.width:
        im = im.resize((a.width, round(im.height * a.width / im.width)), Image.LANCZOS)
    else:
        ap.error("resize needs --height or --width")
    im.save(a.dst, optimize=True)
