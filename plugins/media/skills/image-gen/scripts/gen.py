#!/usr/bin/env python3
"""Generate images with the Codex CLI built-in image generator and deliver them into a project folder.

The Codex image tool always writes its result to ~/.codex/generated_images/<session-id>/.
So Codex runs read-only and only generates; this script finds the file by session id,
verifies it (real alpha when transparency is required) and MOVES it to the target folder.

Usage:
    python gen.py spec.json [--parallel 4] [--retries 1] [--effort low] [--keep-source] [--overwrite]

spec.json:
{
  "out": "D:/project/public/images/stickers",      # absolute target folder (created if missing)
  "style": "sticker",                              # preset name from STYLES or free text
  "transparent": true,                             # default for items
  "size": "1024x1024",                             # 1024x1024 | 1536x1024 | 1024x1536
  "trim": false,                                   # crop to the non-transparent area (+pad)
  "items": [
    {"name": "cat-astronaut.png", "prompt": "a cat astronaut waving"},
    {"name": "cat-sad.png", "prompt": "the same cat, sad", "ref": "cat-astronaut.png"},   # waits for that item
    {"name": "space-bg.png", "prompt": "starry sky", "transparent": false, "size": "1536x1024"}
  ]
}
"ref" is an absolute path, a path relative to the spec file, or the name of another item of the same
spec: such items run in a later wave, after their reference exists.
"size" is only a hint for the generator: real output is usually ~1254 px; resize with postfx.py if exact size matters.
Prints a JSON summary; also writes a QA contact sheet (checkerboard behind transparent images).
"""
import argparse, concurrent.futures as cf, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Needs Pillow and numpy:  python -m pip install pillow numpy")

sys.stdout.reconfigure(encoding="utf-8")
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
GEN_DIR = CODEX_HOME / "generated_images"

STYLES = {
    "sticker": ("Cute kawaii cartoon sticker illustration. Chunky rounded shapes, thick dark navy (#2B2350) outlines, "
                "flat bright candy colors with one soft highlight and one-tone cel shading, big glossy eyes with white "
                "sparkle, rosy cheeks."),
    "flat": ("Clean modern flat vector illustration, geometric shapes, limited harmonious palette, no outlines or thin "
             "consistent outlines, subtle gradients only, crisp edges."),
    "clay": ("Soft 3D clay / plasticine render, rounded chunky forms, pastel colors, soft studio lighting, "
             "subtle subsurface glow, playful toy-like look."),
    "icon": ("Polished app-icon style glossy 3D icon, single bold object, simple readable silhouette, "
             "soft top light, vivid colors."),
    "watercolor": ("Delicate children's book watercolor illustration, soft paper texture, gentle washes, "
                   "fine ink linework."),
    "pixel": "Crisp 32-bit pixel art, limited palette, clean pixel clusters, no anti-aliasing blur.",
    "photo": "Photorealistic high-quality photograph, natural light, sharp focus, realistic materials.",
}

TRANSPARENT = ("The output PNG must have a REAL transparent background: alpha channel, every background pixel fully "
               "transparent. Request a transparent background from the image generator directly. No checkerboard "
               "pattern, no white or coloured backdrop, no ground shadow, no scenery. One isolated subject, fully "
               "inside the frame with a small margin.")
OPAQUE = "Full-bleed image that fills the whole canvas; no transparency needed."

PROMPT = """Use your built-in image generation tool to create exactly ONE image.
Do not run shell commands, do not read or write files, do not save or copy anything: just generate the image once and reply "done".

{bg}
Canvas size: {size}.
Style: {style}
No text, letters or numbers in the image unless the subject explicitly asks for them.
{ref}
Subject: {prompt}
"""


FATAL = re.compile(r"not logged in|please log ?in|unauthori[sz]ed|\b401\b|usage limit|rate limit|quota|insufficient", re.I)
IMG_EXT = ("*.png", "*.webp", "*.jpg", "*.jpeg")


def session_images(folder):
    if not folder.exists():
        return []
    files = [f for pat in IMG_EXT for f in folder.glob(pat)]
    return sorted(files, key=lambda f: f.stat().st_mtime)


def drop_session(folder):
    """The session folder is Codex's intermediate store: clear it so nothing piles up."""
    for f in session_images(folder):
        f.unlink()
    try:
        folder.rmdir()
    except OSError:
        pass


def codex_bin():
    exe = shutil.which("codex")
    if not exe:
        sys.exit("codex CLI not found in PATH")
    return exe


def check(path, transparent):
    im = Image.open(path)
    info = {"mode": im.mode, "size": list(im.size)}
    if not transparent:
        return True, info
    if "A" not in im.getbands() and "transparency" not in im.info:
        return False, {**info, "why": "no alpha channel"}
    a = np.array(im.convert("RGBA"))[:, :, 3]
    frac = float((a == 0).mean())
    info.update(transparent_share=round(frac, 4))
    # one fully transparent pixel is enough: the subject may legitimately touch the edges or corners
    if frac == 0:
        return False, {**info, "why": "no fully transparent pixels"}
    return True, info


def trim(path, pad=12):
    im = Image.open(path).convert("RGBA")
    box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not box:
        return
    im = im.crop(box)
    out = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    out.paste(im, (pad, pad))
    out.save(path, optimize=True)


def free_name(dest, overwrite):
    if overwrite or not dest.exists():
        return dest
    i = 2
    while (dest.with_name(f"{dest.stem}-{i}{dest.suffix}")).exists():
        i += 1
    return dest.with_name(f"{dest.stem}-{i}{dest.suffix}")


def run_one(item, spec, args, logdir):
    name = item["name"] if item["name"].lower().endswith(".png") else item["name"] + ".png"
    transparent = item.get("transparent", spec.get("transparent", True))
    size = item.get("size", spec.get("size", "1024x1024"))
    style = item.get("style", spec.get("style", "sticker"))
    style = STYLES.get(style, style)
    ref = item.get("_ref")
    prompt = PROMPT.format(bg=TRANSPARENT if transparent else OPAQUE, size=size, style=style, prompt=item["prompt"],
                           ref=("Use the attached image as the reference: keep the same character design, proportions, "
                                "colors and rendering style." if ref else ""))
    out_dir = Path(spec["out"])
    result = {"name": name, "ok": False, "attempts": 0}
    if ref and not Path(ref).exists():
        result["why"] = f"reference not found: {ref}"
        return result
    for attempt in range(args.retries + 1):
        result["attempts"] = attempt + 1
        work = tempfile.mkdtemp(prefix="imagegen-")
        cmd = [codex_bin(), "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--cd", work,
               "-c", f'model_reasoning_effort="{args.effort}"']
        if ref:
            cmd.append(f"--image={ref}")
        cmd.append("-")
        try:
            p = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, timeout=args.timeout)
            log = (p.stdout + p.stderr).decode("utf-8", "replace")
        except subprocess.TimeoutExpired as e:
            log = f"TIMEOUT after {args.timeout}s\n" + ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", "replace")
        logfile = logdir / f"{Path(name).stem}-try{attempt + 1}.log"
        logfile.write_text(log, encoding="utf-8")
        result["log"] = str(logfile)
        shutil.rmtree(work, ignore_errors=True)
        m = re.search(r"session id:\s*([0-9a-fA-F-]{36})", log)
        folder = GEN_DIR / m.group(1) if m else None
        imgs = session_images(folder) if folder else []
        if not imgs:
            result["why"] = "no session id in codex output" if not m else f"no image produced in {folder}"
            fatal = FATAL.search(log)
            if fatal:
                result["why"] += f" (codex error: '{fatal.group(0)}', not retrying)"
                break
            continue
        src = imgs[-1]
        ok, info = check(src, transparent)
        result["check"] = info
        if not ok:
            result["why"] = info.get("why")
            if not args.keep_source:
                drop_session(folder)
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = free_name(out_dir / name, args.overwrite)
        if src.suffix.lower() != ".png":
            Image.open(src).save(dest)
        elif args.keep_source:
            shutil.copy2(src, dest)
        else:
            shutil.move(str(src), dest)
        if not args.keep_source:
            drop_session(folder)
        if transparent and item.get("trim", spec.get("trim", False)):
            trim(dest)
        result.update(ok=True, path=str(dest), why=None)
        break
    return result


def plan_waves(spec, spec_path):
    """Resolve refs; items whose ref is another item of this spec go to a later wave."""
    out = Path(spec["out"])
    names = {(i["name"] if i["name"].lower().endswith(".png") else i["name"] + ".png"): i for i in spec["items"]}
    deps = {}
    for it in spec["items"]:
        r = it.get("ref")
        it["_ref"] = None
        if not r:
            continue
        rn = r if r.lower().endswith(".png") else r + ".png"
        if rn in names and names[rn] is not it and not Path(r).is_absolute():
            it["_ref"] = str(out / rn)
            deps[id(it)] = names[rn]
        else:
            p = Path(r).expanduser()
            it["_ref"] = str(p if p.is_absolute() else (spec_path.parent / p).resolve())
    waves, done = [], set()
    pending = list(spec["items"])
    while pending:
        wave = [it for it in pending if id(it) not in deps or id(deps[id(it)]) in done]
        if not wave:  # circular refs: just run the rest
            wave = pending
        waves.append(wave)
        done |= {id(it) for it in wave}
        pending = [it for it in pending if id(it) not in done]
    return waves


def contact_sheet(paths, out):
    ims = [Image.open(p).convert("RGBA") for p in paths]
    if not ims:
        return None
    cell = 300
    sheet = Image.new("RGB", (cell * min(4, len(ims)), (cell + 30) * ((len(ims) + 3) // 4)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (p, im) in enumerate(zip(paths, ims)):
        x, y = (i % 4) * cell, (i // 4) * (cell + 30)
        for cy in range(0, cell, 20):  # checkerboard shows real transparency
            for cx in range(0, cell, 20):
                if (cx // 20 + cy // 20) % 2:
                    d.rectangle([x + cx, y + cy, x + cx + 19, y + cy + 19], fill=(225, 225, 225))
        im.thumbnail((cell - 20, cell - 20))
        tile = sheet.crop((x, y, x + cell, y + cell)).convert("RGBA")
        tile.alpha_composite(im, ((cell - im.width) // 2, (cell - im.height) // 2))
        sheet.paste(tile.convert("RGB"), (x, y))
        d.text((x + 8, y + cell + 8), Path(p).name[:40], fill=(0, 0, 0))
    sheet.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--effort", default="low", help="Codex reasoning effort for the (trivial) orchestration turn")
    ap.add_argument("--keep-source", action="store_true", help="copy instead of move out of generated_images")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    spec_path = Path(args.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out = Path(spec["out"]).expanduser()
    spec["out"] = str(out if out.is_absolute() else (spec_path.parent / out).resolve())
    logdir = Path(tempfile.mkdtemp(prefix="imagegen-logs-"))
    t0 = time.time()
    by_item = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
        for wave in plan_waves(spec, spec_path):
            for it, r in zip(wave, ex.map(lambda it: run_one(it, spec, args, logdir), wave)):
                by_item[id(it)] = r
    results = [by_item[id(it)] for it in spec["items"]]
    ok = [r["path"] for r in results if r["ok"]]
    sheet = contact_sheet(ok, logdir / "contact-sheet.png")
    print(json.dumps({"out": spec["out"], "seconds": round(time.time() - t0), "ok": len(ok),
                      "failed": len(results) - len(ok), "contact_sheet": str(sheet) if sheet else None,
                      "results": results}, ensure_ascii=False, indent=2))
    sys.exit(0 if len(ok) == len(results) else 1)


if __name__ == "__main__":
    main()
