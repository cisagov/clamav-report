"""Code to run if this package is used as a Python module."""

# Standard Python Libraries
import logging

from .clamav_report import main

try:
    main()
finally:
    # Stop logging and clean up
    logging.shutdown()
