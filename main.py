"""Convenience entry point: `python main.py <domain> ...`.

The real CLI lives in `unidata.cli`; installing the package also exposes it as the
`unidata` console command (see pyproject.toml).
"""

from unidata.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
