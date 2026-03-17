import anthropic
import base64
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

COMPETITOR_DIR = Path("ads/competitor")
OUTPUT_FILE = Path("outputs/competitor_audit.json")

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def parse_filename(filename: str) -> dict:
    stem = Path(filename).stem
    parts = stem.split("_")

    brand = parts[0]

    ctr_match = re.search(r"CTR([\d.]+)", stem, re.IGNORECASE)
    ctr = float(ctr_match.group(1)) if ctr_match else None

    creative_id = "_".join(p for p in parts[1:] if not re.match(r"CTR[\d.]+", p, re.IGNORECASE))

    return {
        "filename": filename,
        "brand": brand,
        "creative_id": creative_id,
        "ctr": ctr,
    }


def encode_image(image_path: Path) -> tuple:
    media_type = MEDIA_TYPES.get(image_path.suffix.lower(), "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def analyze_image(image_path: Path, meta: dict) -> dict:
    image_data, media_type = encode_image(image_path)

    ctr_info = f"CTR {meta['ctr']}" if meta["ctr"] is not None else "CTR unknown"

    prompt = f"""You are analysing a competitor performance marketing ad image for a UAE-based healthy meal plan brand called Delicut.

The ad belongs to competitor brand: **{meta['brand']}**
Creative ID: {meta['creative_id']}
Performance metric: {ctr_info}

Delicut's brand colors for reference: #043F12 (Spinach green), #F9F4ED (Cream), #FF3F1F (Grenade red), #EA5D29 (Pumpkin orange).
Delicut's personas: healthy-harry (fitness-driven male), new-nikky (young female, new to healthy eating), mid-life-mansoon (mid-life male, health-conscious).

Analyse this competitor ad and return ONLY a valid JSON object with these exact fields:

{{
  "visual_composition": "describe layout, hero subject, visual hierarchy, use of negative space",
  "color_palette": "dominant colors used and overall color strategy",
  "emotion_tone": "emotional energy, lifestyle vibe, aspiration level this ad conveys",
  "ad_format": "one of: static, carousel-card, whatsapp-image",
  "copy_style": "describe visible text — headline style, CTA, tone, key message. Write 'no visible copy' if none",
  "target_audience": "who this ad appears to be targeting based on visual and copy cues",
  "positioning": "how this brand is positioning itself — premium, value, health, convenience, taste, etc.",
  "human_to_text_area_ratio": <float 0.0-1.0 — fraction of frame occupied by human or food imagery vs text blocks. 0.0 = entirely text, 1.0 = entirely imagery>,
  "ai_image_index": <float 0.0-1.0 — how AI-generated the image looks. 0.0 = clearly a real photograph, 1.0 = clearly AI-generated>,
  "differentiation_gaps": "specific visual, emotional, or messaging gaps that Delicut could exploit to stand out from this ad",
  "steal_worthy": "one specific creative pattern or technique from this ad that Delicut could adapt"
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
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    analysis = json.loads(response.content[0].text.strip())
    return {**meta, **analysis}


def collect_images(directory: Path) -> list:
    if not directory.exists():
        print(f"  Warning: {directory} not found, skipping.")
        return []
    images = []
    for f in sorted(directory.iterdir()):
        if f.suffix.lower() in SUPPORTED_EXTENSIONS:
            images.append((f, parse_filename(f.name)))
    return images


def build_brand_summaries(results: list) -> dict:
    brands = defaultdict(list)
    for img in results:
        if "error" not in img:
            brands[img["brand"]].append(img)

    summaries = {}
    for brand, ads in brands.items():
        def safe_avg(lst, key):
            vals = [i[key] for i in lst if isinstance(i.get(key), (int, float))]
            return round(sum(vals) / len(vals), 2) if vals else None

        ctrs = [i["ctr"] for i in ads if i.get("ctr") is not None]

        summaries[brand] = {
            "ad_count": len(ads),
            "avg_ctr": round(sum(ctrs) / len(ctrs), 2) if ctrs else None,
            "avg_human_to_text_ratio": safe_avg(ads, "human_to_text_area_ratio"),
            "avg_ai_index": safe_avg(ads, "ai_image_index"),
            "positioning_styles": list({i["positioning"] for i in ads if i.get("positioning")}),
            "emotion_tones": list({i["emotion_tone"] for i in ads if i.get("emotion_tone")}),
            "differentiation_gaps": [i["differentiation_gaps"] for i in ads if i.get("differentiation_gaps")],
            "steal_worthy_patterns": [i["steal_worthy"] for i in ads if i.get("steal_worthy")],
        }

    return summaries


def main():
    print("Step 4: Analysing competitor ads with Claude Vision\n")

    all_images = collect_images(COMPETITOR_DIR)
    print(f"Found {len(all_images)} competitor images to analyse.\n")

    results = []
    for i, (image_path, meta) in enumerate(all_images):
        print(f"[{i + 1}/{len(all_images)}] {image_path.name}  (brand: {meta['brand']}, CTR: {meta['ctr']})")
        try:
            result = analyze_image(image_path, meta)
            results.append(result)
            print(f"  ratio={result.get('human_to_text_area_ratio')}  ai={result.get('ai_image_index')}")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({**meta, "error": str(e)})

        if i < len(all_images) - 1:
            time.sleep(0.3)

    brand_summaries = build_brand_summaries(results)

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_images_analysed": len(results),
        "images": results,
        "brand_summaries": brand_summaries,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Saved to {OUTPUT_FILE}")
    print(f"Brands analysed: {list(brand_summaries.keys())}")
    for brand, summary in brand_summaries.items():
        print(
            f"  {brand}: {summary['ad_count']} ads — "
            f"avg CTR={summary['avg_ctr']} "
            f"avg ratio={summary['avg_human_to_text_ratio']} "
            f"avg ai={summary['avg_ai_index']}"
        )


if __name__ == "__main__":
    main()
