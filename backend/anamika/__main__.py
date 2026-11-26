"""Allow ``python -m anamika``."""
import sys

from .cli import main

sys.exit(main())
