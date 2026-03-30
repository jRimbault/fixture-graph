"""Verbosity type for ``-v``/``-q`` count flags with log level computation.

Inspired by `clap-verbosity-flag <https://docs.rs/clap-verbosity-flag>`_ from the
Rust/clap ecosystem, which provides the same pattern for Rust CLIs.

Adapted from `tyro PR #445 <https://github.com/brentyi/tyro/pull/445>`_.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import tyro
from typing_extensions import Annotated

# Shared mutex group: at most one of --verbose / --quiet can be specified.
_verbosity_mutex: object = tyro.conf.create_mutex_group(
    required=False,
    title="verbosity",
)

# Annotated field types for concise dataclass field declarations.
_VerboseField = Annotated[
    tyro.conf.UseCounterAction[int],
    tyro.conf.arg(aliases=["-v"], help="Increase log verbosity."),
    _verbosity_mutex,
]
_QuietField = Annotated[
    tyro.conf.UseCounterAction[int],
    tyro.conf.arg(aliases=["-q"], help="Decrease log verbosity."),
    _verbosity_mutex,
]


@dataclass(frozen=True)
class Verbosity:
    """Parsed verbosity counters from ``-v``/``-q`` CLI flags.

    Drop into any tyro CLI struct to get standard ``--verbose``/``-v`` and
    ``--quiet``/``-q`` count flags that map to Python :mod:`logging` levels.
    The two flags are mutually exclusive.

    Default level mapping (baseline: ``logging.WARNING``):

    .. code-block:: text

        (none)  -> WARNING  (30)
        -v      -> INFO     (20)
        -vv     -> DEBUG    (10)
        -q      -> ERROR    (40)
        -qq     -> CRITICAL (50)

    Values are clamped to the ``DEBUG``..``CRITICAL`` range.
    """

    verbose: _VerboseField = 0
    quiet: _QuietField = 0

    def log_level(self, *, default: int = logging.WARNING) -> int:
        """Compute the effective logging level, clamped to ``DEBUG``..``CRITICAL``.

        Formula: ``default + (quiet - verbose) * 10``.

        Args:
            default: Baseline logging level. Defaults to ``logging.WARNING``.

        Returns:
            An integer logging level suitable for :func:`logging.basicConfig`.
        """
        level = default + (self.quiet - self.verbose) * 10
        return max(logging.DEBUG, min(logging.CRITICAL, level))
