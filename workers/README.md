# Studio Worker

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

HTTP polling-based background job processor for Studio.

## Overview

Handles async tasks: image generation, video processing, webhook delivery.

## Local Development (Mac)

### Prerequisites

```bash
# ffmpeg with libass (required for subtitle burn)
# The default Homebrew bottle does NOT include libass.
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg

# Verify the ass filter is available
ffmpeg -filters 2>&1 | grep -w ass
```

If you previously installed the default `ffmpeg` formula, replace it:

```bash
brew uninstall ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg
```

### Video Worker

Run from the monorepo root:

```bash
make -f dev/Makefile.dev video-setup-local   # Creates venv, installs deps (fonts are bundled in the repo)
make -f dev/Makefile.dev video-run-local     # Starts worker (polls the dev API at localhost:8100)
```

**Apple Silicon GPU (MPS)**: Whisper transcription runs on the MPS GPU automatically. A monkey-patch handles Whisper's DTW alignment step which calls `.double()` (float64) - unsupported on MPS - by moving that tensor to CPU before conversion. Inference stays on GPU.

### Audio Worker

Run from the monorepo root:

```bash
make -f dev/Makefile.dev audio-setup-local   # Creates venv, installs Chatterbox TTS
make -f dev/Makefile.dev audio-run-local     # Starts worker (MPS/CPU)
```

## Documentation

See [docs/](../docs/) in the monorepo for full documentation.

## License

Studio Use License - See [LICENSE](LICENSE)

For operator responsibilities and legal notices, see [LEGAL.md](LEGAL.md).
