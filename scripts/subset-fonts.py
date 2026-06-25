#!/usr/bin/env python3
"""Subset the web fonts in the built site down to the glyphs it actually uses.

The fonts shipped with the theme are Google's "latin" subset (~14 KB each),
but a German club site only ever renders ~120 of those glyphs. This rewrites
each referenced .woff2 in-place containing just the glyphs found in the built
HTML, plus a full German alphabet + common punctuation safety net so that
content edits (and JS-injected text like team/player names) never tofu.

Filenames are left unchanged, so the @font-face `url()`s and the
<link rel="preload"> hrefs in the templates keep resolving.

Run AFTER `hugo` has populated ./public and BEFORE the artifact is uploaded:

    python3 scripts/subset-fonts.py public

No-ops with a warning (exit 0) if fontTools isn't installed, so a plain local
`hugo` build without the Python toolchain still succeeds.
"""

import glob
import html
import os
import re
import sys

# Every glyph we want to guarantee is present even if it never appears in the
# current build — the German alphabet, digits and the punctuation/typography
# the site is likely to grow into.
SAFETY = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "ÄÖÜäöüß"
    "0123456789"
    " .,;:!?'\"-–—…()[]{}/\\@&%§€$+*=#°„“”‚‘’«»·•→"
)

# OpenType features worth keeping for body copy; everything else is dropped.
LAYOUT_FEATURES = "kern,liga,clig,calt"


def referenced_fonts(public_dir):
    """Basenames of .woff2 files referenced from the compiled CSS."""
    names = set()
    for css in glob.glob(os.path.join(public_dir, "css", "*.css")):
        with open(css, encoding="utf-8") as fh:
            for m in re.finditer(r"/fonts/([^\"')]+\.woff2)", fh.read()):
                names.add(m.group(1))
    return names


def glyphs_in_site(public_dir):
    """Every printable character rendered across the built HTML pages."""
    chars = set(SAFETY)
    for page in glob.glob(os.path.join(public_dir, "**", "*.html"), recursive=True):
        with open(page, encoding="utf-8") as fh:
            text = fh.read()
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        chars |= set(html.unescape(text))
    return {c for c in chars if c.isprintable()}


def main():
    public_dir = sys.argv[1] if len(sys.argv) > 1 else "public"

    try:
        from fontTools.subset import Options, Subsetter
        from fontTools.ttLib import TTFont
    except ImportError:
        print("subset-fonts: fontTools not installed — skipping font subsetting.")
        return 0

    fonts_dir = os.path.join(public_dir, "fonts")
    referenced = referenced_fonts(public_dir)
    if not referenced:
        print(f"subset-fonts: no fonts referenced from {public_dir}/css — nothing to do.")
        return 0

    unicodes = sorted(ord(c) for c in glyphs_in_site(public_dir))

    opts = Options()
    opts.flavor = "woff2"
    opts.layout_features = LAYOUT_FEATURES.split(",")
    opts.notdef_outline = True
    opts.recalc_bounds = True

    total_before = total_after = 0
    for name in sorted(referenced):
        path = os.path.join(fonts_dir, name)
        if not os.path.exists(path):
            print(f"subset-fonts: WARNING referenced font missing: {path}")
            continue
        before = os.path.getsize(path)

        font = TTFont(path)
        subsetter = Subsetter(options=opts)
        subsetter.populate(unicodes=unicodes)
        subsetter.subset(font)
        font.save(path)

        after = os.path.getsize(path)
        total_before += before
        total_after += after
        pct = (before - after) * 100 // before if before else 0
        print(f"subset-fonts: {name:<34} {before:>6} -> {after:>6} B  ({pct}% smaller)")

    if total_before:
        pct = (total_before - total_after) * 100 // total_before
        print(
            f"subset-fonts: {len(referenced)} fonts, {len(unicodes)} glyphs, "
            f"{total_before} -> {total_after} B ({pct}% smaller)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
