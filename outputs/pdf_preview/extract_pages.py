import fitz  # PyMuPDF
import os

pdf_path = r"C:\Users\Ramakant\VSCode-projects\delicut-creative-workflow\ads\reference\Delicut Brand Visuals - packaging.pdf"
output_dir = r"C:\Users\Ramakant\VSCode-projects\delicut-creative-workflow\outputs\pdf_preview"

# Pages to extract (1-based), mapped to output filenames
pages_to_extract = {5: "page_05.png", 6: "page_06.png", 7: "page_07.png", 8: "page_08.png"}

doc = fitz.open(pdf_path)
total_pages = len(doc)
print(f"PDF opened successfully. Total pages: {total_pages}")

matrix = fitz.Matrix(2.0, 2.0)  # scale 2x for good resolution

for page_num_1based, filename in pages_to_extract.items():
    page_index = page_num_1based - 1  # convert to 0-based index
    if page_index >= total_pages:
        print(f"  WARNING: Page {page_num_1based} does not exist (PDF has {total_pages} pages). Skipping.")
        continue
    page = doc.load_page(page_index)
    pixmap = page.get_pixmap(matrix=matrix)
    out_path = os.path.join(output_dir, filename)
    pixmap.save(out_path)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  Saved page {page_num_1based} -> {filename}  ({size_kb:.1f} KB)")

doc.close()
print("Done.")
