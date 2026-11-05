"""Vercel Serverless Function entrypoint for TypeVector Arena FastAPI backend."""

import sys
from pathlib import Path

# Add apps/api/src to sys.path so typevector modules can be resolved
root_dir = Path(__file__).resolve().parent.parent
src_dir = root_dir / "apps" / "api" / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from typevector.main import app  # noqa: E402

__all__ = ["app"]
