"""Pytest plugin with Windows-safe temporary directory handling."""

from __future__ import annotations

import os
import tempfile

if os.name == "nt":
    _original_temporary_directory_init = tempfile.TemporaryDirectory.__init__

    def _temporary_directory_init_windows(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        ignore_cleanup_errors: bool = False,
        *,
        delete: bool = True,
    ) -> None:
        _original_temporary_directory_init(
            self,
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            ignore_cleanup_errors=True,
            delete=False,
        )

    tempfile.TemporaryDirectory.__init__ = _temporary_directory_init_windows
