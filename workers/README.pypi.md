# studio-workers

Native (no-Docker) workers for [SelfHostHub Studio](https://www.skool.com/selfhosthub). Run any Studio worker engine directly on the host, pointed at your Studio API. This is the supported path for GPU work on Apple Silicon, where Docker cannot reach the Mac GPU, and for installing workers on demand inside a single GPU pod.

## Install

Pick the extra for the engine you want to run:

```bash
pip install "studio-workers[audio]"    # TTS (Chatterbox, torch)
pip install "studio-workers[video]"    # transcription and video (whisper)
pip install "studio-workers[comfyui]"  # ComfyUI bridge
pip install "studio-workers"           # general + transfer (CPU only)
```

The `[audio]` extra currently requires Python 3.12: its Chatterbox dependency chain does not yet resolve on 3.13 (the install fails with an `llvmlite` build error). The other extras run on 3.12+.

### `[video]` prerequisite: ffmpeg with libass

The video engine shells out to ffmpeg and burns subtitles with the libass `ass` filter. Any ffmpeg build that has the filter works; check yours:

```bash
ffmpeg -filters | grep ass
```

If nothing prints, install a build that includes libass. On macOS the core Homebrew formula no longer includes it; use the homebrew-ffmpeg tap:

```bash
brew trust homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg
```

`studio-workers doctor --engine video` verifies both ffmpeg and the filter.

## Version pinning

Install the `studio-workers` version that matches your Studio release; the release notes name it. The API checks the worker version at registration and refuses a mismatch.

## Check the install

```bash
studio-workers doctor --engine audio
```

`doctor` fails loudly when a GPU host would silently run on CPU: it asserts torch sees MPS on Apple Silicon and CUDA when an NVIDIA driver is present.

## Run

```bash
SHS_API_BASE_URL=https://your-studio-api \
SHS_PUBLIC_BASE_URL=https://your-studio \
SHS_WORKER_SHARED_SECRET=... \
SHS_WORKSPACE_ROOT=/path/to/workspace \
studio-workers run --type audio
```

(`python -m studio_workers.worker` with `SHS_WORKER_TYPE` set still works; `run` is the same loop.)

The worker polls the API for jobs over HTTP; no inbound port is required. See your Studio instance's worker access documentation for the sanctioned connection paths.

## Third-party software

Installing an engine extra pulls third-party packages (torch, Chatterbox TTS, whisper, ComfyUI dependencies) from their own upstreams under their own licenses; model weights download on first run.
