"""Entry point of the action: `python -m setup_graphcal`."""

import sys

# Check before importing the rest, which needs Python 3.10.
if sys.version_info < (3, 10):  # noqa: UP036
    version = sys.version.split()[0]
    print(f"::error title=setup-graphcal::Python 3.10 or later is required, found {version}")  # noqa: T201
    sys.exit(1)

from setup_graphcal.install import main

sys.exit(main())
