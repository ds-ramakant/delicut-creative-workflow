import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

IMAGES_DIR   = Path("outputs/images")
SESSION_LOG  = Path("outputs/session_log.xlsx")
ADCOPY_LOG   = Path("outputs/adcopy_log.xlsx")
DIMENSIONS   = "1080x1080"
ASPECT_RATIO = "1:1"
ENGINE       = "Imagen4Ultra"
PERSONA      = "healthy-harry"

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# ── Session ───────────────────────────────────────────────────────────────────

def make_session_id() -> str:
    now = datetime.now()
    return f"harry_{now.strftime('%m%d-%H%M')}"

# ── Variants ──────────────────────────────────────────────────────────────────

def get_variants(session_id: str) -> list[dict]:
    return [
        {
            "variant": "A",
            "slug": "locker-room-male",
            "prompt": (
                "Athletic male, 25–35, lean muscular build, sitting on a wooden gym locker room bench "
                "in a moment of quiet focus post-workout. Wearing dark fitted gym shorts and a compression top. "
                "Head slightly bowed, elbows resting on knees, composed and determined expression. "
                "Gym bag on the bench beside him. Soft natural light from a high window. "
                "Clean, minimal locker room background, shallow depth of field. "
                "No text. No branding. No logos. "
                "Photorealistic, shot on 35mm, muted tones, cinematic quality. 1080x1080."
            ),
            "text_on_image": (
                "Headline [29 chars]: 'You track reps. Track macros.'\n"
                "Subline [66 chars]: 'Low Carb High Protein meal plans. Macro-accurate. Delivered daily.'\n"
                "CTA: 'Start eating right'\n"
                "Offer: '25% Off your first plan | Use code: BETTERYOU'"
            ),
        },
        {
            "variant": "B",
            "slug": "hands-contrast",
            "prompt": (
                "Extreme close-up of two hands against a dark gym floor background. "
                "Left hand holds a clear protein shaker bottle with whey residue. "
                "Right hand holds a clean sealed meal prep container. "
                "Hands are athletic, slightly worn — suggest active use. "
                "Lighting is dramatic, single source from above, deep shadows. "
                "No face visible. No text. No branding. No logos. "
                "Photorealistic, commercial photography style, high contrast, sharp focus on hands. 1080x1080."
            ),
            "text_on_image": (
                "Headline [29 chars]: 'You track reps. Track macros.'\n"
                "Subline [57 chars]: 'Macro-balanced Low Carb High Protein meals. No guesswork.'\n"
                "CTA: 'Order now'\n"
                "Offer: '25% Off your first plan | Use code: BETTERYOU'"
            ),
        },
        {
            "variant": "C",
            "slug": "treadmill-female",
            "prompt": (
                "Lean athletic female, mid-20s, running on a treadmill in a modern gym. "
                "Wearing a two-piece gym outfit — sports bra and fitted shorts — with midriff visible. "
                "Hair tied back, focused forward gaze, slight motion blur on legs suggesting speed. "
                "Gym environment visible in background — mirrors, equipment, soft overhead lighting. "
                "Shot from a slight side angle. Natural athletic body proportions. "
                "No text. No branding. No logos. "
                "Photorealistic, candid energy, shot on 50mm, warm gym lighting. 1080x1080."
            ),
            "text_on_image": (
                "Headline [29 chars]: 'You track reps. Track macros.'\n"
                "Subline [55 chars]: 'Low Carb High Protein plans built for people who train.'\n"
                "CTA: 'Get your plan'\n"
                "Offer: '25% Off your first plan | Use code: BETTERYOU'"
            ),
        },
        {
            "variant": "D",
            "slug": "abstract-green",
            "prompt": (
                "Abstract flat-lay composition. Deep spinach green background, hex #043F12. "
                "Scattered minimalist fitness props — a single white chalk-dusted weight plate, "
                "a folded white gym towel, a clean stainless steel water bottle — "
                "arranged with generous negative space. "
                "Top-down overhead shot. Hard studio lighting, crisp shadows. "
                "No human presence. No text. No branding. No logos. "
                "Commercial product photography aesthetic, ultra-clean, high resolution. 1080x1080."
            ),
            "text_on_image": (
                "Headline [29 chars]: 'You track reps. Track macros.'\n"
                "Subline [60 chars]: 'Macro-perfect Low Carb High Protein meals. Every single day.'\n"
                "CTA: 'Order now'\n"
                "Offer: '25% Off your first plan | Use code: BETTERYOU'"
            ),
        },
    ]

# ── Excel helpers ─────────────────────────────────────────────────────────────

SESSION_HEADERS = [
    "session_id", "persona", "iteration", "variant",
    "engine", "dimensions", "prompt", "image_file",
    "score", "notes", "status",
]

ADCOPY_HEADERS = [
    "session_id", "persona", "iteration", "variant",
    "engine", "dimensions", "prompt", "image_file",
    "text_on_image",
]

HEADER_FILL  = PatternFill("solid", fgColor="043F12")
HEADER_FONT  = Font(bold=True, color="F9F4ED")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _apply_headers(ws, headers: list[str]):
    ws.row_dimensions[1].height = 20
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill  = HEADER_FILL
        cell.font  = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        ws.column_dimensions[cell.column_letter].width = 22


def get_or_create_workbook(path: Path, headers: list[str]) -> openpyxl.Workbook:
    if path.exists():
        return openpyxl.load_workbook(path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "log"
    _apply_headers(ws, headers)
    return wb


def append_row(ws, values: list):
    ws.append(values)
    # wrap text in prompt and text_on_image cells
    for cell in ws[ws.max_row]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")


# ── Image generation ──────────────────────────────────────────────────────────

def generate_image(prompt: str, output_path: Path) -> bool:
    response = client.models.generate_images(
        model="imagen-4.0-ultra-generate-001",
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=ASPECT_RATIO,
            person_generation="allow_adult",
        ),
    )
    if not response.generated_images:
        return False
    output_path.write_bytes(response.generated_images[0].image.image_bytes)
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Step 6: Generating images with Gemini Imagen\n")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    session_id = make_session_id()
    iteration  = 1
    variants   = get_variants(session_id)

    print(f"Session ID : {session_id}")
    print(f"Variants   : {len(variants)}")
    print(f"Engine     : {ENGINE}")
    print(f"Dimensions : {DIMENSIONS}\n")

    # Open or create both workbooks
    wb_session = get_or_create_workbook(SESSION_LOG, SESSION_HEADERS)
    wb_adcopy  = get_or_create_workbook(ADCOPY_LOG,  ADCOPY_HEADERS)
    ws_session = wb_session.active
    ws_adcopy  = wb_adcopy.active

    for v in variants:
        label      = v["variant"]
        prompt     = v["prompt"]
        image_name = f"{session_id}_{v['slug']}_{ENGINE}.png"
        image_path = IMAGES_DIR / image_name

        print(f"[Variant {label}] Generating...")

        try:
            success = generate_image(prompt, image_path)
            if success:
                print(f"  Saved → {image_path}")
            else:
                print(f"  WARNING: No image returned for variant {label}")
                image_path = Path("ERROR - no image returned")
        except Exception as e:
            print(f"  ERROR: {e}")
            image_path = Path(f"ERROR: {e}")

        # Write to session_log
        append_row(ws_session, [
            session_id, PERSONA, iteration, label,
            ENGINE, DIMENSIONS, prompt, str(image_path),
            "", "", "pending",
        ])

        # Write to adcopy_log
        append_row(ws_adcopy, [
            session_id, PERSONA, iteration, label,
            ENGINE, DIMENSIONS, prompt, str(image_path),
            v["text_on_image"],
        ])

        if label != variants[-1]["variant"]:
            time.sleep(1)

    # Save both files
    SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
    wb_session.save(SESSION_LOG)
    wb_adcopy.save(ADCOPY_LOG)

    print(f"\nDone.")
    print(f"Images saved to  : {IMAGES_DIR}")
    print(f"Session log      : {SESSION_LOG}")
    print(f"Ad copy log      : {ADCOPY_LOG}")
    print(f"\nNext step: open session_log.xlsx, score each image (1–5),")
    print(f"add notes, set status to 'needs-refinement' or 'approved', save.")


if __name__ == "__main__":
    main()
