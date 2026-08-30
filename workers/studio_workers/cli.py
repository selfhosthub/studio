# workers/studio_workers/cli.py

"""studio-workers console entrypoint: `doctor` (environment check), `enroll`
(exchange a join token for this worker's credential) and `run` (start a worker)."""

import argparse
import platform
import shutil
import subprocess
import sys

from studio_workers.contracts.version import WORKERS_VERSION

# Engines whose inference runs torch locally; the others need no GPU here
# (comfyui proxies to an external ComfyUI server, general/transfer are CPU).
TORCH_ENGINES = {"audio", "video"}

FFMPEG_FIX = (
    "Any ffmpeg build with the filter works; check with: ffmpeg -filters | grep ass. "
    "On macOS, core Homebrew ffmpeg no longer includes libass; use the tap: "
    "brew trust homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg"
)


def _expected_accelerator() -> str | None:
    """The accelerator this host should expose: mps on Apple Silicon, cuda when
    an NVIDIA driver is present, else None (CPU is legitimate)."""
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return "mps"
    if sys.platform.startswith("linux") and shutil.which("nvidia-smi"):
        return "cuda"
    return None


def _torch_device() -> tuple[str | None, str | None]:
    """(device, torch version); device None when torch is not installed."""
    try:
        import torch
    except ImportError:
        return None, None
    if torch.cuda.is_available():
        return "cuda", torch.__version__
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", torch.__version__
    return "cpu", torch.__version__


def _ffmpeg_error() -> str | None:
    """Error text when ffmpeg is missing or its build lacks the libass 'ass'
    filter (subtitle burn); None when usable."""
    if not shutil.which("ffmpeg"):
        return f"ffmpeg is not installed but the video engine needs it. {FFMPEG_FIX}"
    filters = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True
    ).stdout
    if not any(line.split()[1:2] == ["ass"] for line in filters.splitlines()):
        return (
            "this ffmpeg build lacks the libass 'ass' filter; subtitle burn "
            f"would fail at render time. {FFMPEG_FIX}"
        )
    return None


def doctor(engine: str | None) -> int:
    """Report the environment and fail loudly when a GPU host would silently run on CPU."""
    print(f"studio-workers {WORKERS_VERSION}")
    print(f"python {platform.python_version()} on {sys.platform}/{platform.machine()}")

    failures = 0
    if engine == "video":
        ffmpeg_error = _ffmpeg_error()
        if ffmpeg_error:
            print(f"ERROR: {ffmpeg_error}")
            failures = 1
        else:
            print("ffmpeg: ok (libass 'ass' filter present)")

    expected = _expected_accelerator()
    device, torch_version = _torch_device()

    if device is None:
        if engine in TORCH_ENGINES:
            print(
                f"ERROR: torch is not installed but the {engine} engine needs it. "
                f'Install the engine extra: pip install "studio-workers[{engine}]=={WORKERS_VERSION}"'
            )
            return 1
        print("torch: not installed (not required for this engine)")
        return failures

    print(f"torch {torch_version}, device={device}")
    if expected and device == "cpu":
        hint = (
            "Docker cannot reach the Mac GPU; run natively (this install) with an MPS-enabled torch wheel."
            if expected == "mps"
            else "Reinstall torch from the matching CUDA index (https://download.pytorch.org/whl/) for your driver."
        )
        print(
            f"ERROR: this host exposes {expected} but torch only sees the CPU; "
            f"generation would run uselessly slow instead of failing. {hint}"
        )
        return 1
    return failures


def run(worker_type: str | None, queues: str | None = None) -> int:
    """Start the worker loop; --type overrides SHS_WORKER_TYPE, --queues the
    served queue list (ordered, comma-separated)."""
    import os

    if worker_type:
        os.environ["SHS_WORKER_TYPE"] = worker_type
    if queues:
        os.environ["SHS_WORKER_QUEUES"] = queues

    from studio_workers import worker

    worker.main()
    return 0


def enroll(join_token: str, label: str | None) -> int:
    """Exchange a join token for this worker's credential and print it."""
    import httpx

    from studio_workers.settings import settings

    body: dict[str, str] = {"join_token": join_token}
    if label:
        body["label"] = label

    try:
        response = httpx.post(
            f"{settings.API_BASE_URL.rstrip('/')}/api/v1/workers/enroll",
            json=body,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        print(f"FAIL  cannot reach {settings.API_BASE_URL}: {exc}", file=sys.stderr)
        return 1

    if response.status_code != 201:
        detail = response.json().get("detail", response.text)
        print(f"FAIL  {response.status_code}: {detail}", file=sys.stderr)
        return 1

    data = response.json()
    print("Enrolled. Set this on the worker and keep it secret:")
    print()
    print(f"SHS_WORKER_CREDENTIAL={data['credential']}")
    print()
    print(f"Queues this worker may serve: {', '.join(data['queues']) or 'none'}")
    print("The credential is shown once. Re-enrol with a new join token if it is lost.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="studio-workers")
    parser.add_argument("--version", action="version", version=WORKERS_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="check this host can run a worker")
    p_doctor.add_argument(
        "--engine",
        choices=["general", "transfer", "video", "audio", "comfyui"],
        help="engine you intend to run; makes torch mandatory for audio/video and ffmpeg (libass) for video",
    )

    p_enroll = sub.add_parser(
        "enroll", help="exchange a join token for this worker's own credential"
    )
    p_enroll.add_argument("--join-token", required=True, help="token from a super admin")
    p_enroll.add_argument("--label", help="name for this worker; defaults to the token's label")

    p_run = sub.add_parser("run", help="start a worker (same loop as python -m studio_workers.worker)")
    p_run.add_argument("--type", dest="worker_type", help="worker type; overrides SHS_WORKER_TYPE")
    p_run.add_argument(
        "--queues",
        help="ordered comma-separated queue list to serve; overrides the type default (SHS_WORKER_QUEUES)",
    )

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args.engine)
    if args.command == "enroll":
        return enroll(args.join_token, args.label)
    return run(args.worker_type, args.queues)


if __name__ == "__main__":
    sys.exit(main())
