---
name: image-gen
description: Generate raster images (illustrations, stickers, characters, mascots, icons, backgrounds, transparent PNGs, art for slides / sites / games / documents) through the Codex CLI image generator and save them into the right folder of the current project. Use whenever the user asks to draw, generate or create a picture, even in passing as part of a bigger task, e.g. "нарисуй", "сгенерируй картинку", "сделай стикер / иконку / иллюстрацию / персонажа / фон", "картинки для презентации", "прозрачный PNG", "generate an image", "make an illustration". Not for charts, diagrams or UI mockups; draw those in code.
---

# Image generation via Codex

Codex CLI (`codex exec`) has a built-in image generator (gpt-image). The generator always writes to
`~/.codex/generated_images/<session-id>/`. `scripts/gen.py` runs Codex **read-only** (it only generates),
finds the file by session id, verifies it and **moves** it into the project. Nothing is left in the Codex folder.
Don't ask Codex to save or copy files itself. Its sandbox falls back to read-only on this machine and the copy fails.

## Workflow

1. **Decide the parameters yourself.** Ask the user only when the subject itself is unclear.
   - Count and file names: latin, kebab-case (`cat-astronaut.png`), or the project's own convention.
   - **Transparency:** on by default for characters, objects, icons and stickers (anything placed over something else).
     Off for backgrounds, scenes, covers and photos.
   - **Size:** 1024x1024 for objects, 1536x1024 for landscape backgrounds and slides, 1024x1536 for portrait.
     This is a hint: landscape usually comes back exactly 1536x1024, square often as 1254x1254. If the project
     needs an exact size, check it and run `postfx.py resize` afterwards.
   - **Style:** a preset (`sticker`, `flat`, `clay`, `icon`, `watercolor`, `pixel`, `photo`) or your own text.
     Every image in one set gets the **same** style so the set looks consistent.
2. **Choose the output folder** (see below).
3. **Write the spec** to the scratchpad or a temp dir, not into the project, and run the script:
   ```bash
   python "<skill base directory>/scripts/gen.py" /path/to/spec.json --parallel 4
   ```
   `<skill base directory>` is the absolute path shown as "Base directory for this skill" when the skill is loaded.
   The skill ships as a plugin and lives in the plugin cache, so never hardcode a path under `~/.claude`.
   Spec format is in the docstring at the top of `gen.py`. One Codex session per image, running in parallel.
   An image whose `ref` points to another image from the same spec automatically waits for it (runs in the next wave).
   Codex runs with `--effort low`: its only job is to call the generator, and picture quality does not depend on this setting.
   Time is dominated by the generation itself, about 1–1.5 minutes per image. Each wave of dependent images adds that much
   again, so a series of "base + 5 variants" takes about 3 minutes.
   For more than 2–3 images, run it with `run_in_background` and keep working.
4. **QA.** The script prints JSON with `contact_sheet`, a sheet on a checkerboard. **Always look at it** with Read.
   - Regenerate a bad image with the same `name`, a revised prompt and `--overwrite`.
   - `ok: false` has a `why` and a `log`. The usual causes are no alpha, which is retried automatically,
     or a Codex timeout or error.
5. **Post-process if needed** with `scripts/postfx.py`:
   - `sticker` adds a white die-cut border and a soft shadow. It is handy when images sit on a colourful background.
   - `trim` crops to the visible area. `resize` resizes.
6. **Report the result.** Tell the user which folder you used and why, and give relative links to the files.

## Where to save: always inside the project, never in its root

Pick the first rule that applies:

1. **The user named a folder:** use it.
2. **The project already has a place for images:** keep its convention. Look for folders with png/jpg/webp/svg,
   excluding `node_modules`, `.git`, `dist`, `build`, `.next`, `venv`, and see how the code references them.
3. **Otherwise go by project type:**

   | Project | Folder |
   |---|---|
   | Next.js, Vite, CRA, Astro, static site (images referenced by URL) | `public/images/<set>/` |
   | Code imports images as modules (`import x from './a.png'`) | `src/assets/images/<set>/` |
   | Vue / Nuxt | `public/images/<set>/` or `assets/images/<set>/` (per project convention) |
   | Django / Flask / FastAPI | `static/images/<set>/` (Django: the app's `static/<app>/images/`) |
   | Game: Godot / pygame / generic | `assets/images/<set>/` (Godot: `assets/` inside `res://`) |
   | Unity | `Assets/Art/<set>/` |
   | Android | `app/src/main/res/drawable-nodpi/` (names: `lower_snake_case`, no subfolders) |
   | iOS / Xcode | an `.imageset` inside `Assets.xcassets` with a `Contents.json` |
   | Presentations, docs, Markdown, Obsidian | `assets/images/<set>/` next to the document |
   | No project (a folder the app made for the session, or an empty folder) | `images/<set>/` |

4. `<set>` is a short slug for the batch (`stickers-kids-deck`, `hero-backgrounds`). Group by batch, not one folder per file.
   If the project keeps images flat with no subfolders, don't create one.
5. Don't overwrite someone else's files without asking (the script adds a `-2` suffix by default).
6. For web projects, suggest converting to WebP or shrinking large PNGs if weight matters. Generated PNGs are about 1 MB.

## Prompt quality

- Write prompts in **English**, even if the user wrote in Russian: the results are better.
- **Don't ask for text inside the image**, because generators garble lettering, especially Cyrillic.
  Put text on top in code: slides, HTML, Pillow, fonts.
- One subject per image. Describe shape, colours, emotion and pose. Skip generic words like "beautiful" or "high quality".
- Keep a series consistent (the same character in different emotions):
  - generate the base image first;
  - use it as `"ref"` for the rest;
  - repeat the character's key features word for word.
- If it's for a composition over a background, use transparency plus `postfx.py sticker`. The white border hides alpha
  artifacts and pulls the set together.

## How it combines with other skills

If the final product is built by another skill (pptx, canvas-design, docx, a site in code), use this skill only
for its raster illustrations. Layout, text and charts belong to that other skill or to code.

## Environment facts

- `codex` is on PATH (Windows: `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe`). The user's model and profile come from `~/.codex/config.toml`.
- It needs `pillow` and `numpy` (`python -m pip install pillow numpy`).
- If Codex is not signed in or the quota is exhausted, the script sees it in the log and does not retry
  (`why` says "codex error"). Tell the user, don't restart it in a loop.
- In the logs Codex complains that its own imagegen skill (`~/.codex/skills/.system/imagegen`) cannot be read.
  That is expected in read-only mode and does not affect the result.
