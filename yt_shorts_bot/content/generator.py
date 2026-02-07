"""Content / script generator for 'Nano Banana' style YouTube Shorts.

A 'Nano Banana' short follows a pattern:
  1. Hook line (attention-grabbing first 2 seconds)
  2. A series of surreal / fascinating visual scenes with short narration
  3. Call-to-action outro

This module produces a *script* — a list of scenes, each with:
  - a Midjourney image prompt
  - a narration line (for TTS)
  - on-screen caption text
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Scene:
    """One scene in a short video."""

    image_prompt: str
    narration: str
    caption: str
    duration: float = 3.0  # seconds


@dataclass
class Script:
    """Full script for a single YouTube Short."""

    title: str
    description: str
    tags: list[str]
    scenes: list[Scene] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.scenes)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "Script":
        data = json.loads(path.read_text())
        scenes = [Scene(**s) for s in data.pop("scenes", [])]
        return cls(**data, scenes=scenes)


# ---------------------------------------------------------------------------
# Built-in "Nano Banana" theme packs
# ---------------------------------------------------------------------------

THEMES: dict[str, dict] = {
    "nano_banana": {
        "name": "Nano Banana",
        "hook_templates": [
            "This banana is only {size} nanometers — and it's alive.",
            "Scientists just discovered a banana smaller than an atom.",
            "What happens when you shrink a banana to nano scale?",
            "You won't believe what a nano banana can do.",
            "The tiniest banana in the universe just broke physics.",
        ],
        "scene_templates": [
            {
                "image_prompt": (
                    "ultra-realistic macro photograph of a glowing miniature banana "
                    "on a scientist's fingertip, bioluminescent, tilt-shift, "
                    "cinematic lighting, 8k"
                ),
                "narration": "At just {size} nanometers, this banana emits its own light.",
                "caption": "nano banana glows ✨",
            },
            {
                "image_prompt": (
                    "nano-scale banana next to a DNA helix for size comparison, "
                    "electron microscope style, scientific illustration, hyper-detailed"
                ),
                "narration": "It's smaller than a strand of DNA.",
                "caption": "smaller than DNA 🧬",
            },
            {
                "image_prompt": (
                    "cute cartoon banana wearing a tiny lab coat inside a petri dish, "
                    "Pixar style, soft lighting, adorable, 4k"
                ),
                "narration": "Scientists gave it a lab coat — because why not.",
                "caption": "scientist banana 🔬",
            },
            {
                "image_prompt": (
                    "a giant banana-shaped spaceship orbiting Earth, "
                    "photorealistic, NASA photography style, epic, volumetric clouds"
                ),
                "narration": "If you scaled it up, it would be bigger than a spaceship.",
                "caption": "banana spaceship 🚀",
            },
            {
                "image_prompt": (
                    "split banana revealing a galaxy inside, surreal digital art, "
                    "cosmic, nebula colors, dreamlike, trending on artstation"
                ),
                "narration": "Inside every nano banana is an entire universe.",
                "caption": "banana galaxy 🌌",
            },
            {
                "image_prompt": (
                    "thousands of tiny glowing bananas forming a wave pattern, "
                    "abstract art, neon colors, dark background, mesmerizing"
                ),
                "narration": "When millions of them gather, they create patterns like this.",
                "caption": "nano banana swarm 🌊",
            },
        ],
        "outro_templates": [
            "Follow for more nano banana facts.",
            "Subscribe for the tiniest content on YouTube.",
            "Like if you want a nano banana of your own.",
        ],
        "tag_pool": [
            "shorts", "nanobanana", "science", "ai", "midjourney",
            "surreal", "banana", "nano", "viral", "facts",
        ],
    },
    "cosmic_fruit": {
        "name": "Cosmic Fruit",
        "hook_templates": [
            "NASA just found a {fruit} floating in space.",
            "This {fruit} survived re-entry into Earth's atmosphere.",
            "What if fruits were actually alien life forms?",
        ],
        "scene_templates": [
            {
                "image_prompt": (
                    "a giant {fruit} floating in outer space with Earth in the "
                    "background, photorealistic, cinematic, NASA style"
                ),
                "narration": "A {fruit} was spotted 400 km above Earth.",
                "caption": "space {fruit} 🪐",
            },
            {
                "image_prompt": (
                    "{fruit} cross-section revealing a miniature city inside, "
                    "isometric art, detailed, fantasy, magical lighting"
                ),
                "narration": "Inside, there's an entire civilization.",
                "caption": "{fruit} city 🏙️",
            },
            {
                "image_prompt": (
                    "astronaut holding a glowing {fruit} on the surface of Mars, "
                    "photorealistic, red dust, cinematic, epic"
                ),
                "narration": "The first fruit ever found on another planet.",
                "caption": "Mars {fruit} 🔴",
            },
        ],
        "outro_templates": [
            "Follow for more cosmic fruit discoveries.",
            "Subscribe — the universe is delicious.",
        ],
        "tag_pool": [
            "shorts", "space", "fruit", "ai", "midjourney",
            "cosmic", "nasa", "viral", "surreal",
        ],
    },
}


def generate_script(
    theme_name: str = "nano_banana",
    num_scenes: int = 5,
    custom_vars: Optional[dict] = None,
) -> Script:
    """Generate a randomised script from a theme.

    Parameters
    ----------
    theme_name:
        Key in ``THEMES`` dict.
    num_scenes:
        How many middle scenes (excluding hook + outro).
    custom_vars:
        Extra template variables, e.g. ``{"size": "42", "fruit": "mango"}``.
    """
    theme = THEMES[theme_name]
    variables: dict[str, str] = {
        "size": str(random.randint(1, 999)),
        "fruit": random.choice(["mango", "strawberry", "watermelon", "kiwi", "grape"]),
    }
    if custom_vars:
        variables.update(custom_vars)

    def _fmt(template: str) -> str:
        return template.format_map(variables)

    # Build scenes
    scenes: list[Scene] = []

    # Hook scene
    hook_line = _fmt(random.choice(theme["hook_templates"]))
    scenes.append(
        Scene(
            image_prompt=(
                "extreme close-up of a mysterious glowing object, dark background, "
                "cinematic, dramatic lighting, 8k, photorealistic"
            ),
            narration=hook_line,
            caption=hook_line,
            duration=3.0,
        )
    )

    # Middle scenes (randomly pick from pool)
    pool = theme["scene_templates"]
    chosen = random.sample(pool, min(num_scenes, len(pool)))
    for tmpl in chosen:
        scenes.append(
            Scene(
                image_prompt=_fmt(tmpl["image_prompt"]),
                narration=_fmt(tmpl["narration"]),
                caption=_fmt(tmpl["caption"]),
                duration=3.0,
            )
        )

    # Outro scene
    outro_line = _fmt(random.choice(theme["outro_templates"]))
    scenes.append(
        Scene(
            image_prompt=(
                "subscribe button animation, neon glow, dark background, "
                "modern YouTube aesthetic, motion graphics style"
            ),
            narration=outro_line,
            caption=outro_line,
            duration=3.0,
        )
    )

    # Trim to fit under 59 s
    while sum(s.duration for s in scenes) > 59:
        if len(scenes) > 2:
            scenes.pop(-2)  # remove last middle scene
        else:
            break

    title = hook_line[:80]
    description = f"{hook_line}\n\n#shorts #ai #midjourney #{theme_name}"
    tags = random.sample(theme["tag_pool"], min(6, len(theme["tag_pool"])))

    return Script(title=title, description=description, tags=tags, scenes=scenes)


def load_custom_theme(yaml_path: Path) -> None:
    """Load a custom theme from a YAML file and register it."""
    data = yaml.safe_load(yaml_path.read_text())
    name = data.get("name", yaml_path.stem)
    THEMES[name] = data
