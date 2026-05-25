# Image Prompt SOP

Use this SOP from Cursor Chat or Composer by referencing `@image_prompt_sop.md`.

## Cursor Execution Prompt

```text
Act as a senior creative strategist and prompt engineer. Follow @image_prompt_sop.md exactly. Generate production-ready image prompts for this campaign:
[PASTE PRODUCT, ANGLE, AND PLATFORM]
```

## Objective

Create ad-ready image prompts that align with direct-response angles and platform context.

## Inputs Required

- Product and use case
- Target audience persona
- Primary angle and emotional tone
- Platform/context (Meta feed, story, advertorial hero, PDP image)
- Brand constraints (colors, style, forbidden visuals)

## Prompt Workflow

### Step 1: Define Creative Intent

- Clarify the single message the image must communicate.
- Clarify emotional response target: urgency, trust, relief, aspiration, curiosity.

### Step 2: Visual Strategy Selection

Pick one dominant style per prompt:
- UGC realism
- Studio product hero
- Lifestyle outcome shot
- Problem/solution split scene
- Infographic-style explainer

### Step 3: Scene Construction

Specify:
- Subject and action
- Environment and context
- Lighting and camera angle
- Composition (close-up, medium, wide)
- Props and product placement

### Step 4: Conversion Layer

Add direct-response intent:
- Pre- and post-state cues
- Trust markers (social proof style elements when allowed)
- Benefit clarity through visual storytelling

### Step 5: Prompt Hardening

Include:
- Style constraints
- Negative prompt constraints (things to avoid)
- Aspect ratio variants by channel
- Versioning tags for testing (v1, v2, v3)

## Required Output Format

For each angle, provide:

1. Creative strategy name
2. Primary prompt (production-ready)
3. Negative prompt
4. Channel variants:
   - 1:1
   - 4:5
   - 9:16
5. 3 test variants with one variable changed each
6. Rationale for likely conversion effect

## Quality Standards

- Product must be visually clear, not ambiguous.
- Prompt must avoid contradictory instructions.
- Background details should support message, not distract.
- Each variant must test one clear hypothesis.

## Non-Negotiables

- Do not over-style at the expense of clarity.
- Do not include unrealistic body results or prohibited claim visuals.
- Do not mix conflicting art directions in one prompt.
