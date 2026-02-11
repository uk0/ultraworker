---
name: gemini-x-image-post
description: Generate a custom 20+ line image prompt, create an image with Gemini Nano Banana Pro (gemini-3-pro-image-preview) or gemini-2.5-flash-image, then upload media and post to X/Twitter with OAuth 1.0a. Use when a user asks to create an image with Gemini and post it to X, or to build/run an end-to-end Gemini image-to-X posting workflow.
---

# Gemini -> X Image Post

## Collect inputs (ask if missing)
- Goal: what the image should achieve (announce, explain, inspire, meme, product).
- Target audience + tone.
- Subject, scene, and any required text in the image.
- Visual style (photoreal, illustration, vector, 3D, anime, etc.).
- Aspect ratio and size (square, portrait, landscape).
- Brand constraints (colors, logo usage, typography), if any.
- X post copy, hashtags, and desired CTA.

## Build the 20+ line prompt
Create a minimum 20-line prompt. Each line must be its own line (not bullet wrapped).

Prompt template (fill all lines, add more if needed):
Line 01: Purpose of the image and target audience.
Line 02: Primary subject and action.
Line 03: Scene environment and setting.
Line 04: Time of day and lighting style.
Line 05: Camera or framing (wide, medium, close-up) and angle.
Line 06: Composition rule (rule of thirds, centered, symmetry, leading lines).
Line 07: Key props or supporting elements.
Line 08: Color palette (3-5 colors) and contrast notes.
Line 09: Texture and material details.
Line 10: Mood and emotional tone.
Line 11: Style references (photoreal, cinematic, editorial, vector, etc.).
Line 12: Background details and depth of field.
Line 13: Foreground details or focal accent.
Line 14: Any text overlay requirements (exact text, placement, style).
Line 15: Typography guidance (font style, weight, spacing) if text exists.
Line 16: Negative constraints (avoid artifacts, blur, extra limbs, clutter).
Line 17: Quality requirements (sharpness, high detail, clean edges).
Line 18: Output aspect ratio and resolution.
Line 19: Safety or content limits (no violence, no adult, no logos if needed).
Line 20: Final emphasis (what must be most noticeable).
Line 21+: Extra instructions as needed (branding, variants, localization).

## Generate image with Gemini (Python)
Use the official Google GenAI client. Prefer the Nano Banana Pro model, then fallback to gemini-2.5-flash-image if needed.

Required env vars:
- GEMINI_API_KEY

Example script snippet (adjust prompt, aspect ratio, and size):

```python
import os
from pathlib import Path
from google import genai
from google.genai import types

PROMPT = """
<YOUR 20+ LINE PROMPT>
""".strip()

OUTPUT_DIR = Path("data/assets/x_posts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=PROMPT,
    config=types.GenerateContentConfig(
        image_config=types.ImageConfig(
            aspect_ratio="1:1",
            image_size="1024x1024",
        )
    ),
)

image_path = OUTPUT_DIR / "gemini_x_post.png"
for part in response.parts:
    if getattr(part, "inline_data", None):
        image = part.as_image()
        image.save(image_path)
        break

print(f"Saved image: {image_path}")
```

If the model is unavailable, switch to:
- model="gemini-2.5-flash-image"

## Prepare X post content
- Load and follow the style guide in `references/x_post_human_style_prompt.md`.
- Write a concise post (<= 280 chars), include 1-2 hashtags.
- Generate alt text describing the image for accessibility.

## Upload media and post to X

Use the `data/assets/x_posts/post_to_x.py` script to upload the image and post to X.

### Prerequisites

Set up X API authentication in your `.env` file.

**OAuth 1.0a (Recommended):**
```
X_CONSUMER_KEY=your_consumer_key
X_CONSUMER_SECRET=your_consumer_secret
X_ACCESS_TOKEN=your_access_token
X_ACCESS_TOKEN_SECRET=your_access_token_secret
```

**OAuth 2.0 (Alternative):**
```
X_OAUTH2_ACCESS_TOKEN=your_oauth2_token
X_OAUTH2_REFRESH_TOKEN=your_refresh_token  # Optional
X_CLIENT_ID=your_client_id                  # Optional
X_CLIENT_SECRET=your_client_secret          # Optional
```

Auth mode selection: Choose `oauth1`, `oauth2`, or `auto` with `X_AUTH_MODE` environment variable (default: auto)

### Post Command

```bash
# Basic usage (uses defaults)
uv run python data/assets/x_posts/post_to_x.py

# Custom image and text
uv run python data/assets/x_posts/post_to_x.py \
  --image "data/assets/x_posts/storm_parse_promo.png" \
  --text "STORM PARSE improves document accuracy! #AI #DocumentAI" \
  --alt "STORM PARSE VLM-based document parsing performance comparison image"

# View help
uv run python data/assets/x_posts/post_to_x.py --help
```

**CLI Options:**
- `--image`, `-i`: Image file path
- `--text`, `-t`: Tweet text (280 chars recommended)
- `--alt`, `-a`: Alt text for image accessibility

### Error Handling

**403 Forbidden:**
1. X Developer Portal -> App settings -> User authentication settings
2. Verify App permissions: "Read and write"
3. Consider upgrading from Free tier to Basic/Pro tier
4. Regenerate tokens and update `.env` file

**Token Expired:**
- OAuth 2.0: Issue new token with `data/assets/x_posts/oauth2_token.py`
- OAuth 1.0a: Regenerate tokens in X Developer Portal

**Note:**
- OAuth 1.0a supports alt text setting
- OAuth 2.0 v2 media upload does not support alt text

## Output summary
Always respond with:
- Final 20+ line prompt (verbatim)
- Image file path
- Post text and hashtags
- Confirmation of upload/post action (or a clear error)

## Safety and validation
- Never log or echo API keys.
- Confirm with the user before posting if not explicitly authorized.
- If posting fails, include the error and suggested fix.
