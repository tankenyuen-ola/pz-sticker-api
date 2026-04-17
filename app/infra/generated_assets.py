import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


def build_local_image_destination(source: str | Path, prefix: str, base_dir: Path | None = None) -> Path:
    out_dir = (base_dir or Path("generated")).resolve()
    parsed = urlparse(str(source))
    suffix = Path(parsed.path).suffix or ".png"
    filename = f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}{suffix}"
    return out_dir / filename
