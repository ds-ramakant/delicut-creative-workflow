import anthropic
import base64
import json
import os
from datetime import datetime
from pathlib import Path

import fitz  # pymupdf
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PDF_PATH    = Path("ads/reference/Delicut Brand Visuals - packaging.pdf")
OUTPUT_FILE = Path("outputs/reference_library.json")

# ── Page map ──────────────────────────────────────────────────────────────────
# Page index is 0-based. Page 0 = cover, skip.

PAGE_MAP = [
    {"page": 1,  "item_id": "labels",                      "category": "labels",       "size": None},
    {"page": 2,  "item_id": "stickers-and-tapes",          "category": "stickers",     "size": None},
    {"page": 3,  "item_id": "main-meal-tray-small-400ml",  "category": "main-meal",    "size": "400ml",  "view": "front"},
    {"page": 4,  "item_id": "main-meal-tray-small-400ml",  "category": "main-meal",    "size": "400ml",  "view": "detail"},
    {"page": 5,  "item_id": "main-meal-tray-standard-900ml","category": "main-meal",   "size": "900ml",  "view": "front", "hero": True},
    {"page": 6,  "item_id": "main-meal-tray-standard-900ml","category": "main-meal",   "size": "900ml",  "view": "detail"},
    {"page": 7,  "item_id": "main-meal-tray-big-1200ml",   "category": "main-meal",    "size": "1200ml", "view": "front"},
    {"page": 8,  "item_id": "main-meal-tray-big-1200ml",   "category": "main-meal",    "size": "1200ml", "view": "detail"},
    {"page": 9,  "item_id": "snacks-box-medium-12oz",      "category": "snacks",       "size": "12oz"},
    {"page": 10, "item_id": "snacks-box-big-16oz",         "category": "snacks",       "size": "16oz"},
    {"page": 11, "item_id": "healthy-drinks",              "category": "drinks",       "size": None,     "view": "label"},
    {"page": 12, "item_id": "healthy-drinks",              "category": "drinks",       "size": None,     "view": "sticker"},
    {"page": 13, "item_id": "breakfast-box",               "category": "breakfast",    "size": None},
    {"page": 14, "item_id": "snacks-box",                  "category": "snacks",       "size": None},
    {"page": 15, "item_id": "soup-box",                    "category": "soups",        "size": None},
]


def page_to_base64(doc: fitz.Document, page_index: int) -> str:
    page = doc[page_index]
    mat  = fitz.Matrix(2.0, 2.0)  # 2x zoom for higher resolution
    pix  = page.get_pixmap(matrix=mat)
    return base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")


def analyze_page(image_b64: str, meta: dict) -> dict:
    size_info  = f"Size: {meta['size']}" if meta.get("size") else ""
    view_info  = f"View: {meta.get('view', '')}" if meta.get("view") else ""
    hero_note  = "This is the DEFAULT HERO product for image generation prompts." if meta.get("hero") else ""

    prompt = f"""You are analysing a studio flat-lay page from Delicut's brand packaging guide.
Delicut is a UAE-based healthy meal plan brand.
Brand colors: #043F12 (Spinach green), #F9F4ED (Cream), #FF3F1F (Grenade red), #EA5D29 (Pumpkin orange).

Item: {meta['item_id']}
Category: {meta['category']}
{size_info}
{view_info}
{hero_note}

Analyse this page and return ONLY a valid JSON object with these exact fields:

{{
  "visual_description": "describe the packaging item in detail — shape, form factor, how it looks physically",
  "colors": "dominant colors on the packaging, label colors, any brand color usage",
  "material": "what the container appears to be made of — plastic, paper, cardboard, etc.",
  "branding_position": "where the Delicut label or branding appears on the packaging",
  "label_style": "describe the label design — font style, layout, what information it carries",
  "usage_instructions": "any instructions shown on the page about how to apply labels, seal, or use the packaging",
  "dimensions_noted": "any dimensions or measurements visible on the page",
  "prompt_inject": "a concise, vivid text snippet (2-3 sentences max) describing this packaging item as it would appear in an AI image generation prompt — focus on what it looks like physically, its color, branding, and how it would sit naturally in a scene. Write as if describing it to an image generator."
}}

Return ONLY the JSON object. No markdown fences, no explanation."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    return json.loads(response.content[0].text.strip())


def main():
    print("Step 2: Processing Delicut packaging reference PDF\n")

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        return

    doc = fitz.open(str(PDF_PATH))
    print(f"PDF loaded: {len(doc)} pages")
    print(f"Processing {len(PAGE_MAP)} packaging items (skipping cover)\n")

    results = []

    for i, meta in enumerate(PAGE_MAP):
        page_num = meta["page"]
        print(f"[{i + 1}/{len(PAGE_MAP)}] Page {page_num + 1} — {meta['item_id']}")

        try:
            image_b64 = page_to_base64(doc, page_num)
            analysis  = analyze_page(image_b64, meta)

            entry = {
                "item_id":   meta["item_id"],
                "page":      page_num + 1,
                "category":  meta["category"],
                "size":      meta.get("size"),
                "view":      meta.get("view"),
                "is_hero":   meta.get("hero", False),
                **analysis,
            }
            results.append(entry)
            print(f"  Done — {analysis.get('material', '')} | {analysis.get('colors', '')[:60]}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "item_id":  meta["item_id"],
                "page":     page_num + 1,
                "category": meta["category"],
                "size":     meta.get("size"),
                "view":     meta.get("view"),
                "is_hero":  meta.get("hero", False),
                "error":    str(e),
            })

    # Retry any failed items once
    failed = [r for r in results if "error" in r]
    if failed:
        print(f"\nRetrying {len(failed)} failed item(s)...\n")
        for entry in failed:
            meta = next(m for m in PAGE_MAP if m["item_id"] == entry["item_id"] and m.get("view") == entry.get("view"))
            page_num = meta["page"]
            print(f"  Retrying page {page_num + 1} — {meta['item_id']}")
            try:
                image_b64 = page_to_base64(doc, page_num)
                analysis  = analyze_page(image_b64, meta)
                new_entry = {
                    "item_id":  meta["item_id"],
                    "page":     page_num + 1,
                    "category": meta["category"],
                    "size":     meta.get("size"),
                    "view":     meta.get("view"),
                    "is_hero":  meta.get("hero", False),
                    **analysis,
                }
                idx = results.index(entry)
                results[idx] = new_entry
                print(f"  Retry OK — {analysis.get('material', '')[:60]}")
            except Exception as e:
                print(f"  Retry failed again: {e}")

    # Pull out the hero prompt_inject for easy access
    hero = next((r for r in results if r.get("is_hero")), None)
    hero_prompt_inject = hero["prompt_inject"] if hero else ""

    output = {
        "generated_at":      datetime.utcnow().isoformat() + "Z",
        "total_items":       len(results),
        "hero_product":      "main-meal-tray-standard-900ml",
        "hero_prompt_inject": hero_prompt_inject,
        "items":             results,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Saved to {OUTPUT_FILE}")
    print(f"Hero product prompt inject:\n  {hero_prompt_inject}")


if __name__ == "__main__":
    main()
