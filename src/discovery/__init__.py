"""Deterministic landscape, gap and hypothesis release construction."""

from .builder import DiscoveryArtifacts, build_discovery_outputs, write_discovery_release


def validate_discovery_outputs(*args, **kwargs):
    """Lazily import the validator so ``python -m src.discovery.validate`` is clean."""

    from .validate import validate_discovery_outputs as _validate

    return _validate(*args, **kwargs)

__all__ = [
    "DiscoveryArtifacts",
    "build_discovery_outputs",
    "validate_discovery_outputs",
    "write_discovery_release",
]
