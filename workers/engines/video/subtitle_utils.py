# workers/engines/video/subtitle_utils.py

"""
Subtitle Utilities

Whisper transcription and karaoke-style ASS subtitle generation.
"""

import re
import logging
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Whisper/torch availability
try:
    import torch  # pragma: no cover

    TORCH_AVAILABLE = True  # pragma: no cover
except ImportError:
    TORCH_AVAILABLE = False

try:
    import whisper  # pragma: no cover

    WHISPER_AVAILABLE = True  # pragma: no cover
except ImportError:
    WHISPER_AVAILABLE = False

# Cache loaded Whisper models to avoid reloading ~3GB per job
_whisper_model_cache: Dict[tuple, Any] = {}


def transcribe_audio(
    audio_path: str,
    language: str = "en",
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcribe audio with Whisper; returns result dict with word-level timestamps."""
    if not WHISPER_AVAILABLE:
        raise RuntimeError("Whisper not installed. Run: pip install openai-whisper")

    # Determine model
    if not model_name:
        from engines.video.settings import settings as video_settings

        model_name = video_settings.WHISPER_MODEL

    # Determine device
    device = "cpu"
    if TORCH_AVAILABLE and torch.cuda.is_available():
        device = "cuda"
        logger.debug("Using CUDA GPU for Whisper transcription")
    elif (
        TORCH_AVAILABLE
        and hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    ):
        device = "mps"
        logger.debug("Using Apple Silicon GPU for Whisper transcription")
    else:
        logger.debug("Using CPU for Whisper transcription")

    # Whisper's DTW alignment calls x.double().cpu().numpy() - the .double()
    # (float64) fails on MPS tensors. Monkey-patch to move to CPU first.
    if device == "mps":
        import whisper.timing as _timing

        _original_dtw = _timing.dtw

        def _dtw_mps_safe(x):
            if hasattr(x, "device") and "mps" in str(x.device):
                x = x.cpu()
            return _original_dtw(x)

        _timing.dtw = _dtw_mps_safe

    cache_key = (model_name, str(device))
    if cache_key in _whisper_model_cache:
        logger.debug(f"Using cached Whisper model: {model_name} ({device})")
        model = _whisper_model_cache[cache_key]
    else:
        logger.debug(f"Loading Whisper model: {model_name} ({device})")
        model = whisper.load_model(model_name, device=device)
        _whisper_model_cache[cache_key] = model

    logger.debug(f"Transcribing: {audio_path}")
    result = model.transcribe(
        audio_path,
        word_timestamps=True,
        language=language,
        fp16=False,  # MPS doesn't support fp16; use fp32
    )

    return result


def generate_ass_subtitles(
    transcription: Dict[str, Any],
    output_path: str,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate ASS subtitle file with karaoke-style word highlighting.

    params keys: all_caps, font_size, font_family, font_color, highlight_color,
    outline_color, outline_width, shadow_offset, position, max_words_per_phrase,
    edge_padding.
    """
    params = params or {}

    # Subtitle settings
    all_caps = params.get("all_caps", False)
    font_size = params.get("font_size", 24)
    font_family = params.get("font_family", "Luckiest Guy")
    font_color = params.get("font_color", "FFFFFF")
    highlight_color = params.get("highlight_color", "FFFF00")
    outline_color = params.get("outline_color", "000000")
    outline_width = params.get("outline_width", 2)
    shadow_offset = params.get("shadow_offset", 1)
    background_color = params.get("background_color", "")
    position = params.get("position", "bottom")
    max_words_per_phrase = params.get("max_words_per_phrase", 5)
    edge_padding = params.get("edge_padding", 20)

    # Position to alignment mapping (ASS format uses numpad layout)
    # 7=top-left, 8=top-center, 9=top-right
    # 4=mid-left, 5=mid-center, 6=mid-right
    # 1=bot-left, 2=bot-center, 3=bot-right
    alignment_map = {
        "top": (8, edge_padding),
        "center": (5, 0),  # Alias for middle
        "middle": (5, 0),
        "bottom": (2, edge_padding),
    }
    alignment, margin_v = alignment_map.get(position, (2, edge_padding))

    # Convert hex colors to ASS format (BGR)
    def to_ass_color(hex_color: str) -> str:
        """Convert RRGGBB to BBGGRR for ASS."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) < 6:
            hex_color = hex_color.ljust(6, "0")
        return f"{hex_color[4:6]}{hex_color[2:4]}{hex_color[0:2]}"

    def to_ass_back_color(hex_color: str) -> str:
        """
        Convert background color to ASS format with alpha.

        Supports:
        - AARRGGBB (8 chars): Full alpha + color
        - RRGGBB (6 chars): Opaque (alpha=00)
        - Empty/None: Fully transparent (alpha=FF)

        ASS format: AABBGGRR
        """
        if not hex_color:
            return "FF000000"  # Fully transparent black

        hex_color = hex_color.lstrip("#")

        if len(hex_color) == 8:
            # AARRGGBB format
            aa = hex_color[0:2]
            rr = hex_color[2:4]
            gg = hex_color[4:6]
            bb = hex_color[6:8]
        elif len(hex_color) == 6:
            # RRGGBB format (assume opaque)
            aa = "00"
            rr = hex_color[0:2]
            gg = hex_color[2:4]
            bb = hex_color[4:6]
        else:
            return "FF000000"  # Default: transparent

        return f"{aa}{bb}{gg}{rr}"

    font_color_ass = to_ass_color(font_color)
    highlight_color_ass = to_ass_color(highlight_color)
    outline_color_ass = to_ass_color(outline_color)
    background_color_ass = to_ass_back_color(background_color)

    # BorderStyle: 1 = outline + shadow, 3 = opaque box (shows BackColour)
    # Use opaque box when background color is specified
    border_style = 3 if background_color else 1

    # Style name
    style_name = "Bold" if "Bold" in font_family else "Default"

    # Extract all words from segments
    all_words = []
    for segment in transcription.get("segments", []):
        words = segment.get("words", [])
        all_words.extend(words)

    # Group words into phrases
    phrases = _group_words_into_phrases(all_words, max_words_per_phrase)

    # Write ASS file
    with open(output_path, "w") as f:
        # Script info
        f.write("[Script Info]\n")
        f.write("Title: shs-video subtitles\n")
        f.write("ScriptType: v4.00+\n\n")

        # Styles
        f.write("[V4+ Styles]\n")
        f.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )
        f.write(
            f"Style: {style_name},{font_family},{font_size},&H{font_color_ass},&H{font_color_ass},&H{outline_color_ass},&H{background_color_ass},0,0,0,0,100,100,0,0.00,{border_style},{outline_width},{shadow_offset},{alignment},10,10,{margin_v},1\n\n"
        )

        # Events
        f.write("[Events]\n")
        f.write(
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        # Generate dialogue lines with word highlighting
        for phrase_idx, phrase in enumerate(phrases):
            phrase_text = _escape_ass_text(" ".join(w["word"] for w in phrase))
            if all_caps:
                phrase_text = phrase_text.upper()

            for word_idx, word in enumerate(phrase):
                word_start = word.get("start", 0.0)
                word_end = word.get("end", word_start)
                raw_word = word.get("word", "")
                if not raw_word:
                    logger.warning(
                        f"Whisper word missing 'word' key at index {word_idx}"
                    )
                word_text = _escape_ass_text(raw_word.upper() if all_caps else raw_word)

                # Determine end time for this subtitle line
                if word_idx < len(phrase) - 1:
                    next_start = phrase[word_idx + 1]["start"]
                elif phrase_idx < len(phrases) - 1:
                    next_start = phrases[phrase_idx + 1][0]["start"]
                else:
                    # Last word - use segment end
                    next_start = (
                        transcription["segments"][-1]["end"]
                        if transcription.get("segments")
                        else word_end
                    )

                # Highlight current word
                highlighted_text = phrase_text.replace(
                    word_text,
                    f"{{\\c&H{highlight_color_ass}&\\3c&H{outline_color_ass}&\\bord{outline_width * 2}}}{word_text}{{\\r}}",
                )

                # Format timestamps
                start_ts = _format_ass_timestamp(word_start)
                end_ts = _format_ass_timestamp(next_start)

                f.write(
                    f"Dialogue: 0,{start_ts},{end_ts},{style_name},,0,0,0,,{highlighted_text}\n"
                )

    logger.debug(f"Generated subtitles: {output_path}")
    return output_path


# Words that should stay attached to a preceding number
_NUMBER_SUFFIXES = {
    "thousand",
    "million",
    "billion",
    "trillion",
    "hundred",
    "cents",
    "dollars",
    "percent",
    "k",
    "m",
    "b",
}


def _is_numeric(word: str) -> bool:
    """Word starts with a digit or currency symbol+digit."""
    return bool(re.match(r"^[\$€£¥₹]?\d", word))


def _is_number_suffix(word: str) -> bool:
    """Word is a magnitude/unit that should stay with its number."""
    return word.lower().rstrip(".,!?;:") in _NUMBER_SUFFIXES


def _group_words_into_phrases(
    words: List[Dict[str, Any]],
    max_words: int,
    max_chars: int = 40,
) -> List[List[Dict[str, Any]]]:
    """
    Group words into phrases for subtitle display.

    Splits on:
    - Sentence-ending punctuation (. ! ?)
    - Max words per phrase
    - Max characters per phrase (prevents overflow with long words)

    Keeps numbers with their suffix words (e.g. "$22 billion" stays together).
    """
    phrases = []
    current_phrase = []
    word_count = 0
    char_count = 0

    def should_split(word_text: str) -> bool:
        # Don't split on periods in abbreviations (U.S.A.)
        if re.match(r"\b(?:[A-Za-z]\.){1,}[A-Za-z]?\.?", word_text):
            return False
        # Don't split on numbers/currency/percentages
        if re.match(r"^[\$€£¥₹]?\d[\d,.]*%?$", word_text):
            return False
        # Split on sentence-ending punctuation
        if re.search(r"[.!?]$", word_text):
            return True
        return False

    for i, word in enumerate(words):
        word_text = word.get("word", "")
        current_phrase.append(word)
        word_count += 1
        char_count += len(word_text) + (1 if word_count > 1 else 0)

        wants_split = (
            should_split(word_text)
            or word_count >= max_words
            or char_count >= max_chars
        )

        if wants_split:
            # Don't split if next word is a number suffix attached to this number
            if i + 1 < len(words):
                next_text = words[i + 1].get("word", "")
                if _is_numeric(word_text) and _is_number_suffix(next_text):
                    continue

            phrases.append(current_phrase)
            current_phrase = []
            word_count = 0
            char_count = 0

    if current_phrase:
        phrases.append(current_phrase)

    return phrases


def _escape_ass_text(text: str) -> str:
    """Escape ASS override tag delimiters in user-supplied text.

    ASS uses {\\tag} for override tags. User text containing { or } would be
    misinterpreted. Replace with full-width equivalents which render visually
    similar but aren't parsed as tags.
    """
    return text.replace("{", "\uff5b").replace("}", "\uff5d")


def _format_ass_timestamp(seconds: float) -> str:
    """Format seconds to ASS timestamp format (H:MM:SS.cc)."""
    milliseconds = int((seconds % 1) * 100)
    total_seconds = int(seconds)
    minutes = total_seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    secs = total_seconds % 60
    return f"{hours:01}:{minutes:02}:{secs:02}.{milliseconds:02}"


# =============================================================================
# Forced Alignment (replace Whisper words with known-correct text)
# =============================================================================


def align_words_to_text(
    whisper_words: List[Dict[str, Any]],
    reference_text: str,
) -> List[Dict[str, Any]]:
    """Keep Whisper's timing but replace words with correct text via sequence alignment."""
    if not whisper_words or not reference_text or not reference_text.strip():
        return whisper_words

    # Normalize for comparison
    w_texts = [w["word"].strip().lower() for w in whisper_words]
    ref_words = reference_text.split()
    r_texts = [w.lower() for w in ref_words]

    matcher = SequenceMatcher(None, w_texts, r_texts)
    aligned = []

    for op, w_start, w_end, r_start, r_end in matcher.get_opcodes():
        w_slice = whisper_words[w_start:w_end]
        r_slice = ref_words[r_start:r_end]

        if op == "equal":
            # Words match - use reference text with Whisper timestamps
            for i, ref_word in enumerate(r_slice):
                aligned.append(
                    {
                        "word": ref_word,
                        "start": w_slice[i]["start"],
                        "end": w_slice[i]["end"],
                    }
                )

        elif op == "replace":
            # Different word counts - distribute timestamps proportionally
            if w_slice:
                time_start = w_slice[0]["start"]
                time_end = w_slice[-1]["end"]
                total_duration = time_end - time_start

                if len(r_slice) == 1:
                    aligned.append(
                        {
                            "word": r_slice[0],
                            "start": time_start,
                            "end": time_end,
                        }
                    )
                else:
                    per_word = total_duration / len(r_slice)
                    for i, ref_word in enumerate(r_slice):
                        aligned.append(
                            {
                                "word": ref_word,
                                "start": time_start + i * per_word,
                                "end": time_start + (i + 1) * per_word,
                            }
                        )

        elif op == "insert":
            # Reference words with no Whisper counterpart - interpolate
            if aligned:
                prev_end = aligned[-1]["end"]
            else:
                prev_end = 0.0

            # Look ahead for next Whisper word's start
            if w_end < len(whisper_words):
                next_start = whisper_words[w_end]["start"]
            elif aligned:
                next_start = prev_end
            else:
                next_start = 0.0

            gap = max(next_start - prev_end, 0.01 * len(r_slice))
            per_word = gap / len(r_slice)
            for i, ref_word in enumerate(r_slice):
                aligned.append(
                    {
                        "word": ref_word,
                        "start": prev_end + i * per_word,
                        "end": prev_end + (i + 1) * per_word,
                    }
                )

        else:  # delete: extra Whisper words with no reference counterpart - skip
            pass

    if aligned:
        logger.debug(
            f"Forced alignment: {len(whisper_words)} Whisper words → "
            f"{len(aligned)} aligned words"
        )
    return aligned


def align_transcription_words(
    transcription: Dict[str, Any],
    reference_text: str,
) -> Dict[str, Any]:
    """Replace Whisper-transcribed words with reference text, keeping timestamps."""
    all_words = []
    for segment in transcription.get("segments", []):
        all_words.extend(segment.get("words", []))

    if not all_words or not reference_text or not reference_text.strip():
        return transcription

    aligned_words = align_words_to_text(all_words, reference_text)

    if not aligned_words:
        return transcription

    return {
        "segments": [
            {
                "words": aligned_words,
                "end": aligned_words[-1]["end"],
            }
        ],
        "text": reference_text,
    }


# =============================================================================
# Subtitle Source Parsers
# =============================================================================


def parse_srt(content: str) -> List[Dict[str, Any]]:
    """
    Parse SRT subtitle format to captions array.

    SRT format:
        1
        00:00:01,000 --> 00:00:04,000
        First subtitle text

        2
        00:00:05,500 --> 00:00:08,000
        Second subtitle text

    Returns:
        List of {"start": float, "end": float, "text": str}
    """
    captions = []
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # Find timestamp line (skip index line if present)
        timestamp_line = None
        text_start_idx = 0

        for i, line in enumerate(lines):
            if "-->" in line:
                timestamp_line = line
                text_start_idx = i + 1
                break

        if not timestamp_line:
            continue

        # Parse timestamp: 00:00:01,000 --> 00:00:04,000
        match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            timestamp_line.strip(),
        )
        if not match:
            continue

        start = (
            int(match.group(1)) * 3600
            + int(match.group(2)) * 60
            + int(match.group(3))
            + int(match.group(4)) / 1000
        )
        end = (
            int(match.group(5)) * 3600
            + int(match.group(6)) * 60
            + int(match.group(7))
            + int(match.group(8)) / 1000
        )

        # Join remaining lines as text
        text = " ".join(lines[text_start_idx:]).strip()
        # Remove SRT formatting tags
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\{[^}]+\}", "", text)

        if text:
            captions.append({"start": start, "end": end, "text": text})

    logger.debug(f"Parsed {len(captions)} captions from SRT")
    return captions


def parse_vtt(content: str) -> List[Dict[str, Any]]:
    """
    Parse WebVTT subtitle format to captions array.

    WebVTT format:
        WEBVTT

        00:00:01.000 --> 00:00:04.000
        First subtitle text

        00:00:05.500 --> 00:00:08.000
        Second subtitle text

    Returns:
        List of {"start": float, "end": float, "text": str}
    """
    captions = []

    # Remove WEBVTT header and metadata
    content = re.sub(r"^WEBVTT[^\n]*\n", "", content.strip())
    content = re.sub(r"^NOTE[^\n]*\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^STYLE[^\n]*\n(?:.*\n)*?\n", "", content, flags=re.MULTILINE)

    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")

        # Find timestamp line (may have optional cue identifier before)
        timestamp_line = None
        text_start_idx = 0

        for i, line in enumerate(lines):
            if "-->" in line:
                timestamp_line = line
                text_start_idx = i + 1
                break

        if not timestamp_line:
            continue

        # Parse timestamp: 00:00:01.000 --> 00:00:04.000 (with optional settings)
        # VTT can be HH:MM:SS.mmm or MM:SS.mmm
        match = re.match(
            r"(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})",
            timestamp_line.strip(),
        )
        if not match:
            continue

        start_h = int(match.group(1) or 0)
        start_m = int(match.group(2))
        start_s = int(match.group(3))
        start_ms = int(match.group(4))

        end_h = int(match.group(5) or 0)
        end_m = int(match.group(6))
        end_s = int(match.group(7))
        end_ms = int(match.group(8))

        start = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
        end = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000

        # Join remaining lines as text
        text = " ".join(lines[text_start_idx:]).strip()
        # Remove VTT formatting tags
        text = re.sub(r"<[^>]+>", "", text)

        if text:
            captions.append({"start": start, "end": end, "text": text})

    logger.debug(f"Parsed {len(captions)} captions from VTT")
    return captions


def generate_ass_from_captions(
    captions: List[Dict[str, Any]],
    output_path: str,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate ASS subtitle file from pre-timed captions without word-level highlighting.

    captions: list of {"start": float, "end": float, "text": str}.
    params: same style keys as generate_ass_subtitles (minus highlight_color, max_words_per_phrase).
    """
    params = params or {}

    # Subtitle settings
    all_caps = params.get("all_caps", False)
    font_size = params.get("font_size", 24)
    font_family = params.get("font_family", "Luckiest Guy")
    font_color = params.get("font_color", "FFFFFF")
    outline_color = params.get("outline_color", "000000")
    outline_width = params.get("outline_width", 2)
    shadow_offset = params.get("shadow_offset", 1)
    background_color = params.get("background_color", "")
    position = params.get("position", "bottom")
    edge_padding = params.get("edge_padding", 20)

    # Position to alignment mapping (ASS format uses numpad layout)
    # 7=top-left, 8=top-center, 9=top-right
    # 4=mid-left, 5=mid-center, 6=mid-right
    # 1=bot-left, 2=bot-center, 3=bot-right
    alignment_map = {
        "top": (8, edge_padding),
        "center": (5, 0),  # Alias for middle
        "middle": (5, 0),
        "bottom": (2, edge_padding),
    }
    alignment, margin_v = alignment_map.get(position, (2, edge_padding))

    # Convert hex colors to ASS format (BGR)
    def to_ass_color(hex_color: str) -> str:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) < 6:
            hex_color = hex_color.ljust(6, "0")
        return f"{hex_color[4:6]}{hex_color[2:4]}{hex_color[0:2]}"

    def to_ass_back_color(hex_color: str) -> str:
        if not hex_color:
            return "FF000000"
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 8:
            aa, rr, gg, bb = (
                hex_color[0:2],
                hex_color[2:4],
                hex_color[4:6],
                hex_color[6:8],
            )
        elif len(hex_color) == 6:
            aa, rr, gg, bb = "00", hex_color[0:2], hex_color[2:4], hex_color[4:6]
        else:
            return "FF000000"
        return f"{aa}{bb}{gg}{rr}"

    font_color_ass = to_ass_color(font_color)
    outline_color_ass = to_ass_color(outline_color)
    background_color_ass = to_ass_back_color(background_color)

    # BorderStyle: 1 = outline + shadow, 3 = opaque box (shows BackColour)
    border_style = 3 if background_color else 1

    style_name = "Default"

    with open(output_path, "w") as f:
        # Script info
        f.write("[Script Info]\n")
        f.write("Title: shs-video subtitles\n")
        f.write("ScriptType: v4.00+\n\n")

        # Styles
        f.write("[V4+ Styles]\n")
        f.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )
        f.write(
            f"Style: {style_name},{font_family},{font_size},&H{font_color_ass},&H{font_color_ass},&H{outline_color_ass},&H{background_color_ass},0,0,0,0,100,100,0,0.00,{border_style},{outline_width},{shadow_offset},{alignment},10,10,{margin_v},1\n\n"
        )

        # Events
        f.write("[Events]\n")
        f.write(
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        for caption in captions:
            text = caption.get("text", "").strip()
            if not text:
                continue

            text = _escape_ass_text(text)
            if all_caps:
                text = text.upper()

            start_ts = _format_ass_timestamp(caption["start"])
            end_ts = _format_ass_timestamp(caption["end"])

            f.write(f"Dialogue: 0,{start_ts},{end_ts},{style_name},,0,0,0,,{text}\n")

    logger.debug(f"Generated subtitles from captions: {output_path}")
    return output_path


def auto_time_text(
    text: str, duration: float, words_per_caption: int = 5
) -> List[Dict[str, Any]]:
    """Distribute plain text evenly across the duration; returns timed caption list.

    words_per_caption: target words per caption (default 5).
    """
    # Split into words
    words = text.split()
    if not words:
        return []

    # Group words into captions
    captions = []
    current_words = []

    for i, word in enumerate(words):
        current_words.append(word)

        # Check for sentence end or word limit
        if len(current_words) >= words_per_caption or word.endswith(
            (".", "!", "?", ":", ";")
        ):
            # Don't split if next word is a number suffix attached to this number
            if (
                i + 1 < len(words)
                and _is_numeric(word)
                and _is_number_suffix(words[i + 1])
            ):
                continue
            captions.append(" ".join(current_words))
            current_words = []

    # Add remaining words
    if current_words:
        captions.append(" ".join(current_words))

    # Calculate timing
    caption_duration = duration / len(captions)
    result = []

    for i, caption_text in enumerate(captions):
        start = i * caption_duration
        end = (i + 1) * caption_duration
        result.append({"start": start, "end": end, "text": caption_text})

    logger.debug(f"Auto-timed {len(result)} captions over {duration:.2f}s")
    return result


def fetch_and_parse_subtitle_file(url: str) -> List[Dict[str, Any]]:
    """
    Fetch and parse a subtitle file from URL.

    Supports SRT and VTT formats (detected by extension or content).

    Args:
        url: URL to subtitle file

    Returns:
        List of {"start": float, "end": float, "text": str}
    """
    import httpx
    from shared.utils.security import validate_url_scheme
    from shared.utils.redaction import redact_url

    from shared.settings import settings as _settings

    validate_url_scheme(url)
    logger.debug(f"Fetching subtitle file: {redact_url(url)}")
    response = httpx.get(
        url, follow_redirects=True, timeout=float(_settings.HTTP_DOWNLOAD_TIMEOUT_S)
    )
    response.raise_for_status()

    content = response.text

    # Detect format
    if url.lower().endswith(".vtt") or content.strip().startswith("WEBVTT"):
        return parse_vtt(content)
    else:
        # Default to SRT
        return parse_srt(content)
