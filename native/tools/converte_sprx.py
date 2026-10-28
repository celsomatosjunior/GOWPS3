"""Pede ao RPCS3 do usuário que converta um módulo do firmware (cópia local), como o analisador faz com o EBOOT."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "GOWPS3" / "native" / "analyzer"))
from gow3_analyzer import decrypt  # noqa: E402

src, rpcs3 = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
out = decrypt.decrypt_with_rpcs3(src, rpcs3, src.parent, print)
print("OK", out, out.stat().st_size)
