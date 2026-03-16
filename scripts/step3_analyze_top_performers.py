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

TOP_PERFORMERS_DIR = Path("ads/top-performers")
AVG_PERFORMERS_DIR = Path("ads/average-performers")
OUTPUT_FILE = Path("outputs/creative_dna.json")

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def parse_filename(filename: str, performance_tier: str) -> dict:
    stem = Path(filename).stem
    parts = stem.split("_")

    persona = parts[0]

    metric_match = re.match(r"(CTR|ROI)([\d.]+)", parts[-1], re.IGNORECASE)
    if metric_match:
        metric = {"type": metric_match.group(1).upper(), "value": float(metric_match.group(2))}
        creative_id = "_".join(parts[1:-1])
    else:
        metric = None
        creative_id = "_".join(parts[1:])

    return {
        "filename": filename,
        "persona": persona,
        "performance_tier": performance_tier,
        "creative_id": creative_id,
        "performance_metric": metric,
    }


def encode_image(image_path: Path) -> tuple:
    media_type = MEDIA_TYPES.get(image_path.suffix.lower(), "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def analyze_image(image_path: Path, meta: dict) -> dict:
    image_data, media_type = encode_image(image_path)

    metric_info = (
        f"{meta['performance_metric']['type']}{meta['performance_metric']['value']}"
        if meta["performance_metric"]
        else "unknown"
    )

    prompt = f"""You are analysing a performance marketing ad image for Delicut, a UAE-based healthy meal plan brand.

Brand colors: #043F12 (Spinach green), #F9F4ED (Cream), #FF3F1F (Grenade red), #EA5D29 (Pumpkin orange).

This image is a **{meta['performance_tier']}** with metric: {metric_info}
Persona: {meta['persona']}

Analyse this ad and return ONLY a valid JSON object with these exact fields:

{{
  "visual_composition": "describe layout, hero subject, visual hierarchy, use of negative space",
  "color_palette": "dominant colors used, whether and how brand colors appear",
  "emotion_tone": "emotional energy, lifestyle vibe, aspiration level this ad conveys",
  "ad_format": "one of: static, carousel-card, whatsapp-image",
  "copy_style": "describe visible text — headline style, CTA, tone. Write 'no visible copy' if none",
  "persona_fit": "why this creative fits or doesn't fit the {meta['persona']} persona",
  "human_to_text_area_ratio": <float 0.0-1.0 — fraction of frame occupied by human or food imagery vs text blocks. 0.0 = entirely text, 1.0 = entirely imagery>,
  "ai_image_index": <float 0.0-1.0 — how AI-generated the image looks. 0.0 = clearly a real photograph, 1.0 = clearly AI-generated>,
  "patterns": "the specific visual and creative patterns that explain this ad's performance level — be concrete"
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


def collect_images(directory: Path, performance_tier: str) -> list:
    if not directory.exists():
        print(f"  Warning: {directory} not found, skipping.")
        return []
    images = []
    for f in sorted(directory.iterdir()):
        if f.suffix.lower() in SUPPORTED_EXTENSIONS:
            images.append((f, parse_filename(f.name, performance_tier)))
    return images


def build_persona_summaries(images: list) -> dict:
    personas = defaultdict(lambda: {"top-performer": [], "average-performer": []})

    for img in images:
        if "error" not in img:
            personas[img["persona"]][img["performance_tier"]].append(img)

    summaries = {}
    for persona, tiers in personas.items():
        top = tiers["top-performer"]
        avg = tiers["average-performer"]
        all_imgs = top + avg

        def safe_avg(lst, key):
            vals = [i[key] for i in lst if isinstance(i.get(key), (int, float))]
            return round(sum(vals) / len(vals), 2) if vals else None

        summaries[persona] = {
            "top_performer_count": len(top),
            "average_performer_count": len(avg),
            "avg_human_to_text_ratio": safe_avg(all_imgs, "human_to_text_area_ratio"),
            "avg_ai_index": safe_avg(all_imgs, "ai_image_index"),
            "top_performer_avg_human_to_text_ratio": safe_avg(top, "human_to_text_area_ratio"),
            "average_performer_avg_human_to_text_ratio": safe_avg(avg, "human_to_text_area_ratio"),
            "top_performer_avg_ai_index": safe_avg(top, "ai_image_index"),
            "average_performer_avg_ai_index": safe_avg(avg, "ai_image_index"),
            "emotion_tones": list({i["emotion_tone"] for i in all_imgs if i.get("emotion_tone")}),
            "top_performer_patterns": [i["patterns"] for i in top if i.get("patterns")],
            "average_performer_patterns": [i["patterns"] for i in avg if i.get("patterns")],
        }

    return summaries


def main():
    print("Step 3: Analysing Delicut ads with Claude Vision\n")

    all_images = []
    all_images += collect_images(TOP_PERFORMERS_DIR, "top-performer")
    all_images += collect_images(AVG_PERFORMERS_DIR, "average-performer")

    print(f"Found {len(all_images)} images to analyse.\n")

    results = []
    for i, (image_path, meta) in enumerate(all_images):
        print(f"[{i + 1}/{len(all_images)}] {image_path.name}")
        try:
            result = analyze_image(image_path, meta)
            results.append(result)
            print(f"  ratio={result.get('human_to_text_area_ratio')}  ai={result.get('ai_image_index')}")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({**meta, "error": str(e)})

        if i < len(all_images) - 1:
            time.sleep(0.3)

    persona_summaries = build_persona_summaries(results)

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_images_analysed": len(results),
        "images": results,
        "persona_summaries": persona_summaries,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Saved to {OUTPUT_FILE}")
    print(f"Personas found: {list(persona_summaries.keys())}")
    for persona, summary in persona_summaries.items():
        print(
            f"  {persona}: {summary['top_performer_count']} top / "
            f"{summary['average_performer_count']} average — "
            f"avg ratio={summary['avg_human_to_text_ratio']} "
            f"avg ai={summary['avg_ai_index']}"
        )


if __name__ == "__main__":
    main()
