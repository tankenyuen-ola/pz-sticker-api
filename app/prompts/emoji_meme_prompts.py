"""Prompt utilities for the 表情包生成 workflow."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence


REVIEW_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {
            "type": "boolean",
            "description": "是否通过审核。通过为 true，未通过为 false。",
        },
        "status_code": {
            "type": "string",
            "enum": ["0", "1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "9999"],
            "description": (
                "状态码。通过审核=\"0\"；"
                "未通过：\"1001\"=基础安全违规(涉黄/低俗/血腥/暴力/恐怖/涉政/违禁)，"
                "\"1002\"=公众人物风险，\"1003\"=无人脸，\"1004\"=多人脸，"
                "\"1005\"=光线异常(过曝/背光)，\"1006\"=人脸偏离中心或被裁剪，"
                "\"1007\"=五官遮挡(墨镜/口罩/手挡脸)，\"1008\"=角度/表情异常；"
                "\"9999\"=内部错误(兜底，当无法明确归类时使用)"
            ),
        },
        "reason": {
            "type": "string",
            "enum": [
                "AiCheckCompleted",
                "AiErrorCodeUnsafeContent",
                "AiErrorCodePublicFigure",
                "AiErrorCodeNoHumanFace",
                "AiErrorCodeMultipleFaces",
                "AiErrorCodeAbnormalLighting",
                "AiErrorCodeFaceNotCentered",
                "AiErrorCodeFaceOccluded",
                "AiErrorCodeFaceAngleAbnormal",
                "AiErrorCodeInternalError",
            ],
            "description": (
                "错误码标识。通过审核(result=true,status_code=0)时输出 \"AiCheckCompleted\"；"
                "未通过时输出对应标识："
                "1001=\"AiErrorCodeUnsafeContent\"，1002=\"AiErrorCodePublicFigure\"，"
                "1003=\"AiErrorCodeNoHumanFace\"，1004=\"AiErrorCodeMultipleFaces\"，"
                "1005=\"AiErrorCodeAbnormalLighting\"，1006=\"AiErrorCodeFaceNotCentered\"，"
                "1007=\"AiErrorCodeFaceOccluded\"，1008=\"AiErrorCodeFaceAngleAbnormal\"，"
                "9999=\"AiErrorCodeInternalError\""
            ),
        },
    },
    "required": ["result", "status_code", "reason"]
}


REVIEW_PROMPT = """# System Prompt: 卡通形象生成前置审核

**【角色设定】**
你是一个严格的图像质量评估与内容安全审核系统。你的任务是分析用户上传的照片，判断其是否适合用于“生成个人专属卡通形象”。

**【审核标准与状态码映射】**

请按优先级从高到低进行检查，一旦触碰标准，立即返回对应的 `status_code`：

1. **通过审核 (Success)**
   - 如果照片完全符合要求：`status_code: 0`, `result: true`

2. **基础安全与合规 (Unsafe Content)**
   - 包含涉黄、低俗、血腥、暴力、恐怖、涉政或违禁符号：`status_code: 1001`

3. **侵权与公众人物风险 (Public Figure)**
   - 识别出高度知名的公众人物（政客、皇室、明星、企业家）：`status_code: 1002`

4. **图像主体与技术指标 (Human Face & Tech)**
   - 画面中没有真实的人类面部：`status_code: 1003`
   - 画面中包含多张人脸（非单人照）：`status_code: 1004`
   - 严重过曝或大面积背光导致五官模糊：`status_code: 1005`
   - 人脸严重偏离中心或被画面边缘裁剪：`status_code: 1006`

5. **遮挡与面部清晰度 (Occlusion & Angle)**
   - 五官被严重遮挡（如墨镜、大号口罩、手部挡脸）：`status_code: 1007`
   - **注意：** 透明眼镜、Tudung/头巾等合理服饰不视为遮挡。
   - 侧脸角度过大或极度夸张的表情导致变形：`status_code: 1008`

6. **内部错误 / 兜底策略 (Internal Error / Fallback)**
   - 当审核过程中遇到无法归类的异常情况（如严重损坏的乱码图、无法解析的诡异图像等），**且无法明确归类于上述 1001-1008 的任何一项**：`status_code: 9999`, `result: false`

**【输出格式要求】**
请严格输出以下 JSON 格式，不要包含任何多余解释或代码块标记。

- `"result"`: 布尔值。通过为 `true`，未通过为 `false`。
- `"status_code"`: 字符串枚举。通过为 `"0"`，未通过则匹配上述错误码（"1001"-"1008"，或 "9999"）。
- `"reason"`: 字符串枚举。必须严格输出对应的错误码标识：
  - 0：`"AiCheckCompleted"`
  - 1001：`"AiErrorCodeUnsafeContent"`
  - 1002：`"AiErrorCodePublicFigure"`
  - 1003：`"AiErrorCodeNoHumanFace"`
  - 1004：`"AiErrorCodeMultipleFaces"`
  - 1005：`"AiErrorCodeAbnormalLighting"`
  - 1006：`"AiErrorCodeFaceNotCentered"`
  - 1007：`"AiErrorCodeFaceOccluded"`
  - 1008：`"AiErrorCodeFaceAngleAbnormal"`
  - 9999：`"AiErrorCodeInternalError"`

{
  "result": true,
  "status_code": "0",
  "reason": "AiCheckCompleted"
}"""


WEBTOON_REFERENCE_PROMPT = """A high-quality 2D character illustration in a modern, aesthetic Webtoon and anime art style.

[Identity & Beautification]: Accurately retain the identity and core features of the person in the provided photograph ( hairstyle, facial features, skin tone, makeup, and clothing design). Simultaneously, apply moderate beautification to make the character highly attractive while keeping the original likeness.

[Composition & Pose]: Direct frontal view, half-body portrait from the thighs up. Arms resting naturally at the sides. The expression is a natural, gentle smile. The character must be perfectly centered within a 1:1 square frame with equal negative space on both sides.

[Dynamic Background for Flawless Cutout]: Strictly analyze the colors present on the character (skin, hair, clothing, cheeks, etc.) in the reference photograph provided. Automatically generate a single, solid background color chosen ONLY from the following fixed set of four: Magenta (#FF00FF), Pure Green (#00FF00), Blue (#0000FF), or Yellow (#FFFF00). The chosen background MUST be the one with the highest contrast and must not be relevant to (must not match or be similar to) any color on the character to guarantee flawless automatic chroma-key background removal (cutout).

[Quality]: Precise clean lines, soft cinematic lighting, masterpiece, best quality, sharp focus."""


DEFAULT_SHEET_PROMPTS: Sequence[str] = (
    """A high-quality 2D sticker sheet featuring a 2x2 seamless arrangement of 4 different ultra-cute Chibi (Q-version) expressions of the same character. {Identity_Style_Intro}

[Critical Composition & Sizing]: Direct frontal view. Every single figure MUST be framed strictly as a half-body portrait from the thighs/waist up. DO NOT generate full-body figures. DO NOT draw legs or feet. Each character must be scaled down slightly within its respective quadrant, leaving plenty of empty negative space around each figure.

[Sticker Outline]: Every single figure MUST have a thick, clean, continuous solid white die-cut sticker border surrounding its entire outer silhouette.

[Critical Constraints (NO TEXT)]: There must be STRICTLY NO text, NO words, NO letters, NO typography, NO watermarks, and NO labels anywhere in the image. There must be STRICTLY NO grid lines, NO frames, NO borders, and NO separating lines between the figures. 

[Dynamic Background Selection]: Analyze the colors of the character's clothing, hair, and skin. You MUST automatically set the entire solid background to purely solid {Selected_Color} to guarantee flawless chroma-key cutout. DO NOT mix these colors; the background must be a single solid color.

Top-left (你好): Waving a friendly hand with a joyful cute smile.
Top-right (鼓掌): Enthusiastically clapping tiny hands with a broad, happy grin.
Bottom-left (喜欢): Making a heart shape with both hands over the chest with a beaming smile.
Bottom-right (害羞): Deep wide pink blush covering cheeks, shyly looking downward, bashful smile, tiny hands hovering nervously near cheeks.

{Style_Instructions}""",
    """A high-quality 2D sticker sheet featuring a 2x2 seamless arrangement of 4 different ultra-cute Chibi (Q-version) expressions of the same character. {Identity_Style_Intro}

[Critical Composition & Sizing]: Direct frontal view. Every single figure MUST be framed strictly as a half-body portrait from the thighs/waist up. DO NOT generate full-body figures. DO NOT draw legs or feet. Each character must be scaled down slightly within its respective quadrant, leaving plenty of empty negative space around each figure.

[Sticker Outline]: Every single figure MUST have a thick, clean, continuous solid white die-cut sticker border surrounding its entire outer silhouette.

[Critical Constraints (NO TEXT)]: There must be STRICTLY NO text, NO words, NO letters, NO typography, NO watermarks, and NO labels anywhere in the image. There must be STRICTLY NO grid lines, NO frames, NO borders, and NO separating lines between the figures. 

[Dynamic Background Selection]: Analyze the colors of the character's clothing, hair, and skin. You MUST automatically set the entire solid background to purely solid {Selected_Color} to guarantee flawless chroma-key cutout. DO NOT mix these colors; the background must be a single solid color.

Top-left (呜呜呜): Exaggerated large cartoon waterfall tears weeping down face, sad pouting expression.
Top-right (生气): Furrowed brow, crossed tiny arms, cartoon steam exhaling from nostrils or temples.
Bottom-left (色咪咪): Eyes replaced by large red hearts, deep wide pink blush covering cheeks, mouth agape in slack-jawed smile with visible drool droplet hanging from corner. Floating tiny hearts surround head.
Bottom-right (要抱抱): Stretching both tiny arms wide open forward, pleading puppy-dog expression.

{Style_Instructions}""",
    """A high-quality 2D sticker sheet featuring a 2x2 seamless arrangement of 4 different ultra-cute Chibi (Q-version) expressions of the same character. {Identity_Style_Intro}

[Critical Composition & Sizing]: Direct frontal view. Every single figure MUST be framed strictly as a half-body portrait from the thighs/waist up. DO NOT generate full-body figures. DO NOT draw legs or feet. Each character must be scaled down slightly within its respective quadrant, leaving plenty of empty negative space around each figure.

[Sticker Outline]: Every single figure MUST have a thick, clean, continuous solid white die-cut sticker border surrounding its entire outer silhouette.

[Critical Constraints (NO TEXT)]: There must be STRICTLY NO text, NO words, NO letters, NO typography, NO watermarks, and NO labels anywhere in the image. There must be STRICTLY NO grid lines, NO frames, NO borders, and NO separating lines between the figures. 

[Dynamic Background Selection]: Analyze the colors of the character's clothing, hair, and skin. You MUST automatically set the entire solid background to purely solid {Selected_Color} to guarantee flawless chroma-key cutout. DO NOT mix these colors; the background must be a single solid color.

Top-left (谢谢老板): Bowing slightly with palms pressed together respectfully and a grateful bright smile.
Top-right (加油): Pumping one tiny fist in the air in a determined, encouraging stance with a resolute face.
Bottom-left (飞吻): Blowing a single kiss with one hand on cheek and a playful wink.
Bottom-right (晚安): Resting head on folded hands like a pillow, closed eyes with a peaceful sleeping expression.

{Style_Instructions}""",
)

_SHEET_STYLE_WITH_REF = (
    "[CRITICAL STYLE TRANSFER INSTRUCTIONS - READ CAREFULL]:\n"
    "You MUST perform EXACT style transfer from the SECOND reference image. This is NOT optional - the final output MUST match the art style of the SECOND image perfectly.\n\n"
    "You have been provided with TWO reference images:\n"
    "- FIRST image = Character identity ONLY (face, hair, clothing)\n"
    "- SECOND image = Art style ONLY (line weight, coloring, shading, aesthetic)\n\n"
    "MANDATORY style traits to extract from the SECOND image:\n"
    "1. LINE WEIGHT: Match the exact thickness and continuity of outlines\n"
    "2. EYE DESIGN: Copy the exact eye shape, highlight style, and expression rendering\n"
    "3. SHADING TECHNIQUE: Use the SAME shading approach (flat colors vs gradients vs cel-shading)\n"
    "4. COLOR PALETTE: Match the saturation, brightness, and color harmony\n"
    "5. PROPORTIONS: Match the head-to-body ratio and feature sizing\n"
    "6. TEXTURE: Match the surface treatment (smooth vs textured vs patterned)\n"
    "7. OVERALL AESTHETIC: The final result must look like it was drawn by the SAME artist as the SECOND image\n\n"
    "STRICT RULES:\n"
    "- The character's FACE, HAIR, and CLOTHING come from the FIRST image\n"
    "- The ART STYLE, LINE WORK, and COLORING come from the SECOND image\n"
    "- If there is ANY conflict, STYLE ALWAYS WINS from the SECOND image\n"
    "- Do NOT use generic anime/kawaii/sticker styles unless the SECOND image uses them\n"
    "- Do NOT add text, logos, or clothing details that don't exist in the FIRST image\n\n"
    "The final sticker sheet MUST look like a direct style adaptation of the SECOND image, featuring the character from the FIRST image.\n\n"
    "Masterpiece, best quality, sharp focus."
)

_SHEET_STYLE_NO_REF = (
    "[Image Processing & Style Instructions]:\n"
    "You have been provided with ONE reference image only. Use it exclusively for character identity.\n\n"
    "Because NO art style reference image is provided, render the final sticker sheet using the following fallback style:\n"
    "- clean, polished 2D sticker illustration\n"
    "- ultra-cute Chibi (Q-version) proportions\n"
    "- expressive eyes and readable facial expressions\n"
    "- crisp, confident linework\n"
    "- simple flat-to-soft cel shading\n"
    "- appealing color harmony\n"
    "- neat, commercial-quality messaging-sticker finish\n\n"
    "The result should feel like a premium modern chat sticker pack. Keep the rendering highly consistent across all four expressions. Do NOT introduce realistic painting, complex textures, messy sketch lines, or generic low-quality anime rendering.\n\n"
    "Masterpiece, best quality, sharp focus."
)

EMOJI_MODE_SHEET = "sheet_4"
EMOJI_MODE_SINGLE = "single_1"
EMOJI_MODE_CHOICES: Sequence[tuple[str, str]] = (
    ("1 图 4 表情", EMOJI_MODE_SHEET),
    ("1 图 1 表情", EMOJI_MODE_SINGLE),
)

_SINGLE_STICKER_PROMPT_TEMPLATE = """A high-quality 2D anime sticker featuring a single centered ultra-cute Chibi (Q-version) character, accurately retaining the core features (hairstyle, facial features, skin tone, makeup, and clothing design) of the person in the provided reference photograph. Simultaneously, apply moderate beautification to translate them into a kawaii aesthetic.

[Critical Composition & Sizing]: Direct frontal view. The figure MUST be framed strictly as a close-up portrait from the chest up. DO NOT generate full-body figures. DO NOT draw legs or feet. The character must be scaled down slightly within the frame, leaving empty negative space around it.

[Sticker Outline]: The figure MUST have a thick, clean, continuous solid white die-cut sticker border surrounding its entire outer silhouette.

[Critical Constraints (NO TEXT)]: There must be STRICTLY NO text, NO words, NO letters, NO typography, NO watermarks, and NO labels anywhere in the image. There must be STRICTLY NO grid lines, NO frames, and NO borders.

[Dynamic Background Selection]: Analyze the colors of the character's clothing, hair, and skin. You MUST automatically set the entire solid background to EXACTLY ONE of the following four colors: Pure Yellow (#FFFF00), Pure Green (#00FF00), Bright Magenta (#FF00FF), or Pure Blue (#0000FF). Choose the ONE color that has the highest contrast and is completely absent from the character to guarantee flawless chroma-key cutout. DO NOT mix these colors; the background must be a single solid color.

[Action & Expression]: {action}

{Style_instructions}

Masterpiece, best quality, sharp focus."""

_DEFAULT_SINGLE_STICKERS: Sequence[tuple[str, str]] = (
    # Set 1: 日常正面 (Daily Positive)
    ("你好", "Waving a friendly hand with a joyful cute smile."),
    ("鼓掌", "Enthusiastically clapping tiny hands with a broad, happy grin."),
    ("喜欢", "Making a heart shape with both hands over the chest with a beaming smile."),
    ("害羞", "Deep wide pink blush covering cheeks, shyly looking downward, bashful smile, tiny hands hovering nervously near cheeks."),
    # Set 2: 情绪化表现 (Emotional Expressions)
    ("呜呜呜", "Exaggerated large cartoon waterfall tears weeping down face, sad pouting expression."),
    ("生气", "Furrowed brow, crossed tiny arms, cartoon steam exhaling from nostrils or temples."),
    ("色咪咪", "Eyes replaced by large red hearts, deep wide pink blush covering cheeks, mouth agape in slack-jawed smile with visible drool droplet hanging from corner. Floating tiny hearts surround head."),
    ("要抱抱", "Stretching both tiny arms wide open forward, pleading puppy-dog expression."),
    # Set 3: 工作与俏皮 (Work & Play)
    ("谢谢老板", "Bowing slightly forward, tiny palms pressed together respectfully, grateful bright smile."),
    ("加油", "Pumping one tiny fist in the air with determination, looking resolute."),
    ("飞吻", "Playful wink, blowing a simplified heart-shaped kiss forward from one hand."),
    ("晚安", "Eyes closed peacefully, sleeping expression, resting head on folded hands like a pillow."),
)

_SINGLE_STYLE_WITH_REF = """[Image Processing Instructions]: This request includes TWO input images. You MUST treat them as follows:
1. Use the FIRST image STRICTLY for character identity (facial features, hair, clothing).
2. Use the SECOND image STRICTLY as a style reference (Style Transfer). Extract the exact line weight, flat cel-shading coloring technique, and overall 2D aesthetic directly from this second image and apply it to the character from the first image. Ensure extremely thick, continuous white die-cut sticker borders and flat colors."""

_SINGLE_STYLE_NO_REF = """[Image Processing Instructions]: NO style reference image is provided. Rely ONLY on these text instructions for the Fallback Art Style: Classic 2D chat messenger sticker aesthetic. Ultra-simplified details, flat colors (cel-shading), absolutely NO complex or realistic 3D shading. Extremely thick and bold outlines. Highly exaggerated cartoon facial expressions. Maximum Q-version kawaii style."""


ADDITIONAL_META_PROMPT = """
**Role:** You are an expert AI prompt engineer and a Vision-Language Analyst specializing in creating prompts for 2D chat messenger stickers.

**Task:** Analyze the provided user reference photo(s) and generate a production-ready English prompt for a multimodal Image AI model.

**Input Variables Required from User Request:**
1. `{Number}`: The number of expressions to generate (1, 2, 3, or 4).
2. `{Expressions_List}`: The specific actions/emotions for each sticker.
3. `{Has_Style_Image}`: Boolean (True/False). True if a 2nd image for art style is provided; False if only the character image is uploaded.
*(Note: The reference photo(s) must be attached to this prompt for analysis).*

**[VISION TASK]: Automatic Background Color Selection**
You must look at the attached reference photo. Analyze the dominant colors of the character's clothing, hair, and accessories.
Based on your visual analysis, you MUST select exactly ONE color from this list that is COMPLETELY ABSENT from the character to guarantee high contrast:
* Pure Yellow (#FFFF00)
* Pure Green (#00FF00)
* Bright Magenta (#FF00FF)
* Pure Blue (#0000FF)
*(Store this selection internally as {Selected_Color}).*

**Dynamic Layout Logic:**
Adapt the layout description based on `{Number}`:
* **If 1:** "a single centered ultra-cute Chibi (Q-version) character"
* **If 2:** "a seamless side-by-side (1x2) arrangement of 2 different ultra-cute Chibi (Q-version) expressions"
* **If 3:** "a seamless arrangement of 3 different ultra-cute Chibi (Q-version) expressions evenly spaced in a single frame"
* **If 4:** "a 2x2 seamless arrangement of 4 different ultra-cute Chibi (Q-version) expressions"

**Dynamic Style Logic:**
Adapt the style description based on `{Has_Style_Image}`:
* **If True (Two images are fed to the image generator):**
  "[Image Processing Instructions]: You have been provided with TWO reference images. You MUST use the FIRST image strictly for character identity (facial features, hair, clothing). You MUST use the SECOND image strictly as a style reference (Style Transfer). Extract the line weight, flat cel-shading technique, eye drawing style, and overall 2D aesthetic directly from the SECOND image and apply it to the character from the FIRST image. Ensure extremely thick, bold outlines and flat colors."

* **If False (Only one image is fed to the image generator):**
  "[Image Processing Instructions]: You have been provided with ONE reference image. Use it exclusively for character identity. Because NO art style image was provided, you MUST rely ONLY on the following text instructions for the art style: Classic 2D chat messenger sticker aesthetic optimized for small screens. Maximum Q-version kawaii style with ultra-simplified details, flat colors (cel-shading), and absolutely NO complex or realistic 3D shading. Extremely thick, bold, and clean line art. Highly exaggerated and intuitive expressions."

**Core Prompt Structure to Generate:**
"A high-quality 2D vector-style illustration of a classic, simplified Chibi (Q-version) character. The character features a massive, oversized head that heavily dominates the tiny, simplified upper body.

[Character Reference]: You MUST accurately retain the key facial features, skin tone, makeup, hairstyle, and clothing design exclusively from the FIRST provided image (Character Reference), translating them into an ultra-simplified kawaii form.

[Insert Dynamic Layout Logic here]. The oversized head must fill the majority of its assigned space, with only the tiny upper torso visible. DO NOT generate full-body figures. DO NOT draw legs or feet.

[Sticker Outline]: Every single figure MUST have a thick, clean, continuous solid white die-cut sticker border surrounding its entire simplified outer silhouette.

[Critical Constraints (NO TEXT)]: There must be STRICTLY NO text, NO words, NO letters, NO typography, NO watermarks, and NO labels anywhere in the image. There must be STRICTLY NO grid lines, NO frames, and NO separating lines between the figures.

[Flawless Cutout Background]: All figures must float seamlessly on a SINGLE, continuous, solid [Insert {Selected_Color} here] background. The entire background MUST be purely [Insert {Selected_Color} here].

[Insert {Expressions_List} here. CRITICAL INSTRUCTION: Describe VISUAL face and body language ONLY. Remove emotional labels or text concepts.]

[Insert Dynamic Style Logic here]

Masterpiece, best quality, sharp focus."

**Output Requirement:** Output ONLY the final generated prompt text ready to be used by the Image AI. Do not output your color analysis thought process. Do not include any conversational filler or markdown code blocks.
"""

ADDITIONAL_SINGLE_META_PROMPT = """
**Role:** You are an expert AI prompt engineer and a Vision-Language Analyst.

**Task:** Analyze the provided user reference photo and generate a production-ready English prompt for creating one ultra-cute Chibi (Q-version) character sticker.

**Input Variables Required from User Request:**
1. `{Expression}`: The specific action/emotion for the sticker.
2. `{Has_Style_Image}`: Whether a style reference image is provided (True/False).
*(Note: The reference photo must be attached to this prompt for analysis).*

**[VISION TASK]: Automatic Background Color Selection**
You must look at the attached reference photo. Analyze the dominant colors of the character's clothing, hair, and accessories.
Based on your visual analysis, you MUST select exactly ONE color from this list that is COMPLETELY ABSENT from the character to guarantee high contrast:
* Pure Yellow (#FFFF00)
* Pure Green (#00FF00)
* Bright Magenta (#FF00FF)
* Pure Blue (#0000FF)
*(Store this selection internally as {Selected_Color}).*

**Dynamic Style Logic:**
Adapt the style description based on `{Has_Style_Image}`:
* **If True (Two images are fed to the image generator):**
  "[Image Processing Instructions]: You have been provided with TWO reference images. You MUST use the FIRST image strictly for character identity (facial features, hair, clothing). You MUST use the SECOND image strictly as a style reference (Style Transfer). Extract the line weight, flat cel-shading technique, eye drawing style, and overall 2D aesthetic directly from the SECOND image and apply it to the character from the FIRST image. Ensure extremely thick, bold outlines and flat colors."

* **If False (Only one image is fed to the image generator):**
  "[Image Processing Instructions]: You have been provided with ONE reference image. Use it exclusively for character identity. Because NO art style image was provided, you MUST rely ONLY on the following text instructions for the art style: Classic 2D chat messenger sticker aesthetic optimized for small screens. Maximum Q-version kawaii style with ultra-simplified details, flat colors (cel-shading), and absolutely NO complex or realistic 3D shading. Extremely thick, bold, and clean line art. Highly exaggerated and intuitive expressions."

**Core Prompt Structure to Generate:**
"A high-quality 2D anime sticker featuring a single centered ultra-cute Chibi (Q-version) character, accurately retaining the core features (hairstyle, facial features, skin tone, makeup, and clothing design) of the person in the provided reference photograph. Simultaneously, apply moderate beautification to translate them into a kawaii aesthetic.

[Critical Composition & Sizing]: Direct frontal view. The figure MUST be framed strictly as a close-up portrait from the chest up. DO NOT generate full-body figures. DO NOT draw legs or feet. The character must be scaled down slightly within the frame, leaving empty negative space around it.

[Sticker Outline]: The figure MUST have a thick, clean, continuous solid white die-cut sticker border surrounding its entire outer silhouette.

[Critical Constraints (NO TEXT)]: There must be STRICTLY NO text, NO words, NO letters, NO typography, NO watermarks, and NO labels anywhere in the image. There must be STRICTLY NO grid lines, NO frames, and NO borders.

[Flawless Cutout Background]: The entire background MUST be a SINGLE, solid [Insert {Selected_Color} here] background to guarantee flawless automatic chroma-key background removal.

[Action & Expression]: [Insert a purely visual description for {Expression} here. Describe facial expression, gesture, and body language only. Do not include text concepts or words that might be drawn into the image.]

[Insert Dynamic Style Logic here]

Masterpiece, best quality, sharp focus."

**Output Requirement:** Output ONLY the final generated prompt text ready to be used by the Image AI. Do not output your color analysis thought process. Do not include any conversational filler or markdown code blocks.
"""
@dataclass(frozen=True)
class StickerSheetPlan:
    title_cn: str
    caption_cn: str
    expressions: List[str]
    prompt: str | None = None
    is_default: bool = False


_DEFAULT_SHEETS: Sequence[tuple[str, Sequence[str], str]] = (
    ("默认表情包 1", ("你好", "鼓掌", "喜欢", "害羞"), DEFAULT_SHEET_PROMPTS[0]),
    ("默认表情包 2", ("呜呜呜", "生气", "色咪咪", "要抱抱"), DEFAULT_SHEET_PROMPTS[1]),
    ("默认表情包 3", ("谢谢老板", "加油", "飞吻", "晚安"), DEFAULT_SHEET_PROMPTS[2]),
)


def get_default_sheet_prompts(has_style_image: bool = False) -> List[str]:
    """Return the built-in sticker-sheet prompts as a mutable list.
    
    Args:
        has_style_image: Whether a style reference image is provided.
    """
    # Default selected color - will be replaced by AI analysis in actual usage
    selected_color = "Pure Green (#00FF00)"
    
    style_instructions = _SHEET_STYLE_WITH_REF if has_style_image else _SHEET_STYLE_NO_REF
    identity_style_intro = (
        "The character identity MUST be accurately preserved from the FIRST reference image, including hairstyle, facial features, skin tone, makeup, and clothing design. The final visual rendering style MUST be derived from the SECOND reference image. Apply tasteful beautification while preserving clear likeness."
        if has_style_image
        else "The character identity MUST be accurately preserved from the provided reference image, including hairstyle, facial features, skin tone, makeup, and clothing design. Apply tasteful beautification while preserving clear likeness."
    )
    
    return [
        prompt.format(
            Selected_Color=selected_color,
            Style_Instructions=style_instructions,
            Identity_Style_Intro=identity_style_intro,
        )
        for prompt in DEFAULT_SHEET_PROMPTS
    ]


def get_default_sheet_prompt(index: int, has_style_image: bool = False) -> str:
    """Return one built-in default sticker-sheet prompt by index."""
    return get_default_sheet_prompts(has_style_image=has_style_image)[index]


def get_default_single_prompt_labels() -> List[str]:
    """Return the built-in single-sticker labels in display order."""
    return [label for label, _action in _DEFAULT_SINGLE_STICKERS]


def get_default_single_prompts(has_style_image: bool = False) -> List[str]:
    """Return the built-in single-sticker prompts as a mutable list.
    
    Args:
        has_style_image: Whether a style reference image is provided.
    """
    style_instructions = _SINGLE_STYLE_WITH_REF if has_style_image else _SINGLE_STYLE_NO_REF
    
    return [_SINGLE_STICKER_PROMPT_TEMPLATE.format(action=action, Style_instructions=style_instructions) for _label, action in _DEFAULT_SINGLE_STICKERS]


def adapt_default_prompts_for_mode(
    mode: str,
    prompts: Sequence[str | None] | None,
    has_style_image: bool = False,
) -> List[str]:
    """Refresh untouched built-in prompts when style-image availability changes."""
    desired_defaults = get_default_prompts_for_mode(mode, has_style_image=has_style_image)
    if not prompts:
        return desired_defaults

    builtin_without_style = get_default_prompts_for_mode(mode, has_style_image=False)
    builtin_with_style = get_default_prompts_for_mode(mode, has_style_image=True)
    resolved: List[str] = list(desired_defaults)
    for index, prompt in enumerate(prompts[: len(desired_defaults)]):
        if prompt is None:
            continue
        cleaned = str(prompt).strip()
        if not cleaned:
            continue
        if cleaned in {builtin_without_style[index], builtin_with_style[index]}:
            resolved[index] = desired_defaults[index]
        else:
            resolved[index] = cleaned
    return resolved


def get_default_prompts_for_mode(mode: str, has_style_image: bool = False) -> List[str]:
    """Return built-in prompts for one emoji generation mode.
    
    Args:
        mode: The generation mode (EMOJI_MODE_SHEET or EMOJI_MODE_SINGLE).
        has_style_image: Whether a style reference image is provided.
    """
    if mode == EMOJI_MODE_SINGLE:
        return get_default_single_prompts(has_style_image=has_style_image)
    return get_default_sheet_prompts(has_style_image=has_style_image)


def get_default_prompt_for_mode(mode: str, index: int, has_style_image: bool = False) -> str:
    """Return one built-in prompt for the requested mode."""
    return get_default_prompts_for_mode(mode, has_style_image=has_style_image)[index]


def resolve_default_prompts_for_mode(
    mode: str,
    default_prompts: Sequence[str | None] | None = None,
    has_style_image: bool = False,
) -> List[str]:
    """Normalize user-provided prompts with fallback to built-ins for the selected mode.
    
    Args:
        mode: The generation mode (EMOJI_MODE_SHEET or EMOJI_MODE_SINGLE).
        default_prompts: User-provided prompts to merge with defaults.
        has_style_image: Whether a style reference image is provided (only affects single mode).
    """
    resolved = get_default_prompts_for_mode(mode, has_style_image=has_style_image)
    if not default_prompts:
        return resolved

    for index, prompt in enumerate(default_prompts[: len(resolved)]):
        if prompt is None:
            continue
        cleaned = str(prompt).strip()
        if cleaned:
            resolved[index] = cleaned
    return resolved


def resolve_default_sheet_prompts(default_prompts: Sequence[str | None] | None = None) -> List[str]:
    """Backward-compatible wrapper for sheet-mode default prompts."""
    return resolve_default_prompts_for_mode(EMOJI_MODE_SHEET, default_prompts)


def parse_additional_expressions(text: str) -> List[str]:
    """Parse extra expressions from user input while preserving order."""
    if not text:
        return []

    parts = re.split(r"[\n,;；，]+", text)
    values: List[str] = []
    seen = set()
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        lowered = cleaned.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        values.append(cleaned)
    return values


def _chunk(values: Iterable[str], size: int) -> List[List[str]]:
    chunked: List[List[str]] = []
    current: List[str] = []
    for value in values:
        current.append(value)
        if len(current) == size:
            chunked.append(current)
            current = []
    if current:
        chunked.append(current)
    return chunked


def build_sheet_plan(
    additional_expressions: Iterable[str],
    default_prompts: Sequence[str | None] | None = None,
) -> List[StickerSheetPlan]:
    """Build the full sticker-sheet plan including defaults and extras."""
    resolved_default_prompts = resolve_default_sheet_prompts(default_prompts)
    plan = [
        StickerSheetPlan(
            title_cn=title,
            caption_cn=f"{title}：" + "、".join(expressions),
            expressions=list(expressions),
            prompt=resolved_default_prompts[index],
            is_default=True,
        )
        for index, (title, expressions, _prompt) in enumerate(_DEFAULT_SHEETS)
    ]

    extra_groups = _chunk(list(additional_expressions), 4)
    for index, expressions in enumerate(extra_groups, start=1):
        title = f"其他表情包 {index}"
        plan.append(
            StickerSheetPlan(
                title_cn=title,
                caption_cn=f"{title}：" + "、".join(expressions),
                expressions=expressions,
            )
        )
    return plan


def build_single_sticker_plan(
    additional_expressions: Iterable[str] = (),
    default_prompts: Sequence[str | None] | None = None,
    selected_default_labels: Sequence[str] | None = None,
) -> List[StickerSheetPlan]:
    """Build the single-sticker plan using the 12 built-in expressions."""
    resolved_default_prompts = resolve_default_prompts_for_mode(EMOJI_MODE_SINGLE, default_prompts)
    selected_set = {str(label).strip() for label in (selected_default_labels or []) if str(label).strip()}
    plan = [
        StickerSheetPlan(
            title_cn=label,
            caption_cn=label,
            expressions=[label],
            prompt=resolved_default_prompts[index],
            is_default=True,
        )
        for index, (label, _action) in enumerate(_DEFAULT_SINGLE_STICKERS)
        if not selected_set or label in selected_set
    ]
    for expression in additional_expressions:
        plan.append(
            StickerSheetPlan(
                title_cn=expression,
                caption_cn=expression,
                expressions=[expression],
            )
        )
    return plan


def build_emoji_plan(
    mode: str,
    additional_expressions: Iterable[str],
    default_prompts: Sequence[str | None] | None = None,
    selected_default_labels: Sequence[str] | None = None,
) -> List[StickerSheetPlan]:
    """Build the generation plan for the selected emoji mode."""
    if mode == EMOJI_MODE_SINGLE:
        return build_single_sticker_plan(additional_expressions, default_prompts, selected_default_labels)
    return build_sheet_plan(additional_expressions, default_prompts)


def build_additional_prompt_request(expressions: Sequence[str], has_style_image: bool = False) -> str:
    """Build the meta-prompt request for extra expressions."""
    joined = ", ".join(expressions)
    has_style_str = "True" if has_style_image else "False"
    return (
        ADDITIONAL_META_PROMPT
        .replace("{Number}", str(len(expressions)))
        .replace("{Expressions_List}", joined)
        .replace("{Has_Style_Image}", has_style_str)
        + f"\n\nNumber: {len(expressions)}\nExpressions_List: {joined}\nHas_Style_Image: {has_style_str}"
    )


def build_additional_single_prompt_request(expression: str, has_style_image: bool = False) -> str:
    """Build the meta-prompt request for one extra single-sticker expression."""
    cleaned = str(expression).strip()
    has_style_str = "True" if has_style_image else "False"
    return (
        ADDITIONAL_SINGLE_META_PROMPT
        .replace("{Expression}", cleaned)
        .replace("{Has_Style_Image}", has_style_str)
        + f"\n\nExpression: {cleaned}\nHas_Style_Image: {has_style_str}"
    )


def format_additional_prompts_for_display(prompt_entries: Sequence[dict]) -> str:
    """Format generated extra prompts for frontend display."""
    if not prompt_entries:
        return ""

    sections: List[str] = []
    for entry in prompt_entries:
        title = str(entry.get("title_cn") or "其他表情包")
        expressions = entry.get("expressions") or []
        prompt = str(entry.get("prompt") or "").strip()
        expression_text = "、".join(str(item) for item in expressions if item)
        if expression_text:
            sections.append(f"{title}（{expression_text}）")
        else:
            sections.append(title)
        sections.append(prompt)
        sections.append("")
    return "\n".join(sections).strip()
