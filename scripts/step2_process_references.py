import anthropic
import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path

import fitz  # pymupdf
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

REFERENCE_DIR = Path("ads/reference")
OUTPUT_FILE   = Path("outputs/reference_library.json")

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_TYPES = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# ── PDF page map ───────────────────────────────────────────────────────────────
# Hardcoded to the Delicut packaging PDF. Page index is 0-based. Page 0 = cover, skip.

PDF_FILENAME = "Delicut Brand Visuals - packaging.pdf"

PAGE_MAP = [
    {"page": 1,  "item_id": "labels",                       "category": "labels",     "size": None},
    {"page": 2,  "item_id": "stickers-and-tapes",           "category": "stickers",   "size": None},
    {"page": 3,  "item_id": "main-meal-tray-small-400ml",   "category": "main-meal",  "size": "400ml",  "view": "front"},
    {"page": 4,  "item_id": "main-meal-tray-small-400ml",   "category": "main-meal",  "size": "400ml",  "view": "detail"},
    {"page": 5,  "item_id": "main-meal-tray-standard-900ml","category": "main-meal",  "size": "900ml",  "view": "front", "hero": True},
    {"page": 6,  "item_id": "main-meal-tray-standard-900ml","category": "main-meal",  "size": "900ml",  "view": "detail"},
    {"page": 7,  "item_id": "main-meal-tray-big-1200ml",    "category": "main-meal",  "size": "1200ml", "view": "front"},
    {"page": 8,  "item_id": "main-meal-tray-big-1200ml",    "category": "main-meal",  "size": "1200ml", "view": "detail"},
    {"page": 9,  "item_id": "snacks-box-medium-12oz",       "category": "snacks",     "size": "12oz"},
    {"page": 10, "item_id": "snacks-box-big-16oz",          "category": "snacks",     "size": "16oz"},
    {"page": 11, "item_id": "healthy-drinks",               "category": "drinks",     "size": None,     "view": "label"},
    {"page": 12, "item_id": "healthy-drinks",               "category": "drinks",     "size": None,     "view": "sticker"},
    {"page": 13, "item_id": "breakfast-box",                "category": "breakfast",  "size": None},
    {"page": 14, "item_id": "snacks-box",                   "category": "snacks",     "size": None},
    {"page": 15, "item_id": "soup-box",                     "category": "soups",      "size": None},
]


# ── Filename → metadata ────────────────────────────────────────────────────────

def derive_image_meta(filename: str) -> dict:
    """Infer item_id and category from the image filename."""
    stem  = Path(filename).stem.lower()
    # Normalise: remove "no bg", "(1)", "-2" suffixes, extra spaces
    clean = re.sub(r"\(?\d+\)?", "", stem)          # remove numbers in parens
    clean = re.sub(r"no\s*bg", "", clean)            # remove "no bg"
    clean = re.sub(r"[-\s]+", " ", clean).strip()   # collapse dashes/spaces

    if "bag" in clean:
        # Extract bag number from original stem
        num_match = re.search(r"bag\s*(\d+)", stem)
        num = num_match.group(1) if num_match else "x"
        return {
            "item_id":  f"delivery-bag-{num}",
            "category": "bag",
            "size":     None,
            "view":     "cut-out",
        }
    elif "meal tray" in clean or "meal-tray" in clean:
        num_match = re.search(r"(?:meal\s*tray)\s*(\d+)?", stem)
        num = num_match.group(1) if (num_match and num_match.group(1)) else None
        is_red = "red" in stem
        variant = "red-nobg" if is_red else f"{num}" if num else "x"
        return {
            "item_id":  f"meal-tray-{variant}",
            "category": "meal-tray",
            "size":     None,
            "view":     "cut-out",
        }
    else:
        slug = re.sub(r"\s+", "-", clean.strip("-"))
        return {
            "item_id":  slug or "unknown",
            "category": "other",
            "size":     None,
            "view":     "cut-out",
        }


# ── Analysis prompts ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are analysing Delicut product assets for a UAE-based healthy meal plan brand. "
    "Brand colors: #043F12 (Spinach green), #F9F4ED (Cream), #FF3F1F (Grenade red), #EA5D29 (Pumpkin orange). "
    "Return only valid JSON — no markdown fences, no explanation."
)

ANALYSIS_SCHEMA = """{
  "visual_description": "describe the product in detail — shape, form factor, physical appearance",
  "colors": "dominant colors, label colors, brand color usage",
  "material": "what the item appears to be made of",
  "branding_position": "where the Delicut logo or label appears",
  "label_style": "describe the label design — font, layout, information it carries",
  "dimensions_noted": "any visible dimensions or size indicators, or null",
  "prompt_inject": "2–3 sentence vivid description for use in an AI image generation prompt. Describe exactly how this product looks physically — its shape, color, branding, material — and how it would sit naturally in a scene. Write as if briefing an image generator."
}"""


def analyze_pdf_page(image_b64: str, meta: dict) -> dict:
    size_info = f"Size: {meta['size']}" if meta.get("size") else ""
    view_info = f"View: {meta.get('view', '')}" if meta.get("view") else ""
    hero_note = "This is the DEFAULT HERO product for image generation prompts." if meta.get("hero") else ""

    prompt = f"""Analyse this studio flat-lay page from Delicut's brand packaging guide.

Item: {meta['item_id']}
Category: {meta['category']}
{size_info}
{view_info}
{hero_note}

Return ONLY a JSON object with these fields:
{ANALYSIS_SCHEMA}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return json.loads(response.content[0].text.strip())


def analyze_image_file(image_b64: str, media_type: str, meta: dict) -> dict:
    prompt = f"""Analyse this Delicut product cut-out image.

Item: {meta['item_id']}
Category: {meta['category']}
View: {meta['view']}
Note: This is a cut-out image with no background — describe only the product itself.

Return ONLY a JSON object with these fields:
{ANALYSIS_SCHEMA}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return json.loads(response.content[0].text.strip())


# ── PDF processing ─────────────────────────────────────────────────────────────

def process_pdf(pdf_path: Path) -> list[dict]:
    print(f"\n[PDF] {pdf_path.name}")
    doc = fitz.open(str(pdf_path))
    print(f"  {len(doc)} pages — processing {len(PAGE_MAP)} items (skipping cover)\n")

    results = []
    for i, meta in enumerate(PAGE_MAP):
        page_num = meta["page"]
        print(f"  [{i+1}/{len(PAGE_MAP)}] Page {page_num+1} — {meta['item_id']}")
        try:
            page     = doc[page_num]
            mat      = fitz.Matrix(2.0, 2.0)
            pix      = page.get_pixmap(matrix=mat)
            b64      = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
            analysis = analyze_pdf_page(b64, meta)
            entry = {
                "source":   "pdf",
                "filename": pdf_path.name,
                "item_id":  meta["item_id"],
                "page":     page_num + 1,
                "category": meta["category"],
                "size":     meta.get("size"),
                "view":     meta.get("view"),
                "is_hero":  meta.get("hero", False),
                **analysis,
            }
            results.append(entry)
            print(f"    OK — {analysis.get('material', '')} | {analysis.get('colors', '')[:55]}")
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append({
                "source": "pdf", "filename": pdf_path.name,
                "item_id": meta["item_id"], "page": page_num + 1,
                "category": meta["category"], "size": meta.get("size"),
                "view": meta.get("view"), "is_hero": meta.get("hero", False),
                "error": str(e),
            })

    # Retry failed pages once
    failed = [r for r in results if "error" in r]
    if failed:
        print(f"\n  Retrying {len(failed)} failed page(s)...")
        for entry in failed:
            meta = next(
                m for m in PAGE_MAP
                if m["item_id"] == entry["item_id"] and m.get("view") == entry.get("view")
            )
            try:
                page     = doc[meta["page"]]
                mat      = fitz.Matrix(2.0, 2.0)
                pix      = page.get_pixmap(matrix=mat)
                b64      = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
                analysis = analyze_pdf_page(b64, meta)
                new_entry = {
                    "source": "pdf", "filename": pdf_path.name,
                    "item_id": meta["item_id"], "page": meta["page"] + 1,
                    "category": meta["category"], "size": meta.get("size"),
                    "view": meta.get("view"), "is_hero": meta.get("hero", False),
                    **analysis,
                }
                results[results.index(entry)] = new_entry
                print(f"    Retry OK — {meta['item_id']}")
            except Exception as e:
                print(f"    Retry failed: {e}")

    return results


# ── Image file processing ──────────────────────────────────────────────────────

def process_images(image_files: list[Path]) -> list[dict]:
    print(f"\n[Images] {len(image_files)} file(s)\n")

    # Deduplicate by item_id — keep the first occurrence
    seen_ids = {}
    deduped  = []
    for p in sorted(image_files, key=lambda x: x.name):
        meta = derive_image_meta(p.name)
        iid  = meta["item_id"]
        if iid not in seen_ids:
            seen_ids[iid] = p
            deduped.append((p, meta))
        else:
            print(f"  SKIP (duplicate item_id '{iid}'): {p.name}")

    results = []
    for i, (img_path, meta) in enumerate(deduped, 1):
        ext        = img_path.suffix.lower()
        media_type = MEDIA_TYPES.get(ext, "image/png")
        print(f"  [{i}/{len(deduped)}] {img_path.name}  →  {meta['item_id']}")
        try:
            b64      = base64.standard_b64encode(img_path.read_bytes()).decode("utf-8")
            analysis = analyze_image_file(b64, media_type, meta)
            entry = {
                "source":   "image",
                "filename": img_path.name,
                "item_id":  meta["item_id"],
                "category": meta["category"],
                "size":     meta["size"],
                "view":     meta["view"],
                "is_hero":  False,
                **analysis,
            }
            results.append(entry)
            print(f"    OK — {analysis.get('material', '')} | {analysis.get('colors', '')[:55]}")
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append({
                "source": "image", "filename": img_path.name,
                "item_id": meta["item_id"], "category": meta["category"],
                "size": meta["size"], "view": meta["view"],
                "is_hero": False, "error": str(e),
            })

    return results


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Step 2: Processing all reference assets\n")

    if not REFERENCE_DIR.exists():
        print(f"ERROR: {REFERENCE_DIR} not found")
        return

    all_files  = list(REFERENCE_DIR.iterdir())
    pdf_files  = [f for f in all_files if f.suffix.lower() == ".pdf"]
    img_files  = [f for f in all_files if f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS]

    print(f"Found in {REFERENCE_DIR}:")
    print(f"  PDFs   : {len(pdf_files)}")
    print(f"  Images : {len(img_files)}")

    all_results = []

    # Process PDFs
    for pdf_path in pdf_files:
        if pdf_path.name == PDF_FILENAME:
            all_results.extend(process_pdf(pdf_path))
        else:
            print(f"\n[PDF] Skipping unrecognised PDF: {pdf_path.name}")

    # Process standalone images
    if img_files:
        all_results.extend(process_images(img_files))

    # Pull hero prompt_inject
    hero = next((r for r in all_results if r.get("is_hero")), None)
    hero_prompt_inject = hero["prompt_inject"] if hero else ""

    output = {
        "generated_at":       datetime.utcnow().isoformat() + "Z",
        "total_items":        len(all_results),
        "hero_product":       "main-meal-tray-standard-900ml",
        "hero_prompt_inject": hero_prompt_inject,
        "items":              all_results,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(all_results)} items saved to {OUTPUT_FILE}")

    # Summary by category
    from collections import Counter
    cats = Counter(r["category"] for r in all_results)
    print("\nBy category:")
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
