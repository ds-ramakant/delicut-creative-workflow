import anthropic
import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TOP_PERFORMERS_DIR = Path("ads/top-performers")
OUTPUT_FILE        = Path("outputs/copy_dna.json")

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_TYPES = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

SYSTEM_PROMPT = (
    "You are a performance marketing copy analyst specialising in UAE health and wellness brands. "
    "Extract ad copy with surgical precision — verbatim, not paraphrased."
)


def analyze_image_copy(image_path: Path) -> dict:
    ext        = image_path.suffix.lower()
    media_type = MEDIA_TYPES.get(ext, "image/jpeg")
    image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

    prompt = """Analyse this high-performing Delicut ad creative.

Extract ALL text that appears on the ad verbatim, then analyse the copy patterns.

Return ONLY a JSON object — no prose, no markdown fences:
{
  "verbatim_copy": {
    "headline":   "exact text or null",
    "subline":    "exact text or null",
    "cta":        "exact text or null",
    "offer":      "exact text or null",
    "other_text": []
  },
  "image_text_overlay":  "the single most prominent scroll-stopping line on the image, or null",
  "copy_structure":      "describe hierarchy — how many tiers, what each tier does",
  "emotional_angle":     "primary trigger: transformation / urgency / identity / convenience / social proof / etc.",
  "headline_char_count": 0,
  "subline_char_count":  0,
  "click_driver":        "the single most click-worthy element and why it works",
  "power_words":         []
}

Count characters accurately. Use null for any field not visible in the image."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_data},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )

    raw   = response.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {"error": "JSON parse failed", "raw": raw}
    return {"error": "No JSON found", "raw": raw}


def parse_filename(filename: str) -> dict:
    stem  = Path(filename).stem
    parts = stem.split("_")
    persona = parts[0]
    metric_match = re.match(r"(CTR|ROI)([\d.]+)", parts[-1], re.IGNORECASE)
    if metric_match:
        metric      = {"type": metric_match.group(1).upper(), "value": float(metric_match.group(2))}
        creative_id = "_".join(parts[1:-1])
    else:
        metric      = None
        creative_id = "_".join(parts[1:])
    return {"persona": persona, "creative_id": creative_id, "performance_metric": metric}


def main():
    print("Step 3b: Extracting copy DNA from top-performing ads\n")

    images = sorted(
        [p for p in TOP_PERFORMERS_DIR.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS],
        key=lambda p: p.name,
    )
    print(f"Found {len(images)} images in {TOP_PERFORMERS_DIR}\n")

    results = []
    for i, img_path in enumerate(images, 1):
        meta = parse_filename(img_path.name)
        print(f"[{i}/{len(images)}] {img_path.name}")
        copy_data = analyze_image_copy(img_path)
        if "error" in copy_data:
            print(f"  WARNING: {copy_data['error']}")
        else:
            overlay  = copy_data.get("image_text_overlay")
            headline = copy_data.get("verbatim_copy", {}).get("headline")
            print(f"  overlay  : {overlay}")
            print(f"  headline : {headline}  ({copy_data.get('headline_char_count')} chars)")
        results.append({
            "filename":           img_path.name,
            "persona":            meta["persona"],
            "creative_id":        meta["creative_id"],
            "performance_metric": meta["performance_metric"],
            **copy_data,
        })

    output = {
        "generated_at":          datetime.utcnow().isoformat() + "Z",
        "total_images_analysed": len(results),
        "images":                results,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. Copy DNA saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
