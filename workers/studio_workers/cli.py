# workers/studio_workers/cli.py

"""studio-workers console entrypoint: `doctor` (environment check) and `run` (start a worker)."""

import argparse
import platform
import shutil
import sys

from studio_workers.contracts.version import WORKERS_VERSION

# Engines whose inference runs torch locally; the others need no GPU here
# (comfyui proxies to an external ComfyUI server, general/transfer are CPU).
TORCH_ENGINES = {"audio", "video"}


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


def doctor(engine: str | None) -> int:
    """Report the environment and fail loudly when a GPU host would silently run on CPU."""
    print(f"studio-workers {WORKERS_VERSION}")
    print(f"python {platform.python_version()} on {sys.platform}/{platform.machine()}")

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
        return 0

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
    return 0


def run(worker_type: str | None) -> int:
    """Start the worker loop; --type overrides SHS_WORKER_TYPE."""
    import os

    if worker_type:
        os.environ["SHS_WORKER_TYPE"] = worker_type

    from studio_workers import worker

    worker.main()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="studio-workers")
    parser.add_argument("--version", action="version", version=WORKERS_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="check this host can run a worker")
    p_doctor.add_argument(
        "--engine",
        choices=["general", "transfer", "video", "audio", "comfyui"],
        help="engine you intend to run; makes torch mandatory for audio/video",
    )

    p_run = sub.add_parser("run", help="start a worker (same loop as python -m studio_workers.worker)")
    p_run.add_argument("--type", dest="worker_type", help="worker type; overrides SHS_WORKER_TYPE")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args.engine)
    return run(args.worker_type)


if __name__ == "__main__":
    sys.exit(main())
