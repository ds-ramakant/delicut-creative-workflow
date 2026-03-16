You are helping build a performance marketing creative pipeline for Delicut (delicut.ae), a UAE-based meal plan brand.

Project location: C:\Users\Ramakant\VSCode-projects\delicut-creative-workflow
IDE: VS Code with PowerShell terminal
Stack: Python, Anthropic Claude Vision API, Figma API

Brand colors: #043F12 (Spinach), #F9F4ED (Cream), #FF3F1F (Grenade), #EA5D29 (Pumpkin)

Output formats: 1080x1080, 1080x1920, 1920x1080, 1200x628, 1080x1350, 960x1200

Pipeline steps:
1. Excel brief with persona, hook, image description
2. Claude generates image prompts per persona
3. Analyse Delicut top-performing ads using Claude Vision — output creative_dna.json
4. Analyse competitor ads — output competitor_audit.json
5. Enrich prompts with outputs from steps 3 and 4
6. Generate images across Midjourney / Ideogram / Magic Media/ Nano Banana
7. Figma API auto-populates master templates with approved images and copy
8. Batch export all 6 size formats per persona
