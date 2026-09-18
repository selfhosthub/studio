# api/app/presentation/api/uploads.py

"""Hand an uploaded file to a service without reading it into memory."""

import os
from typing import BinaryIO, Tuple

from fastapi import UploadFile


def spooled_upload(file: UploadFile) -> Tuple[BinaryIO, int]:
    """The upload's spooled file rewound to the start, and its size in bytes."""
    stream = file.file
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return stream, size
