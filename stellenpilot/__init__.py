"""Local job hunt pipeline."""

try:  # one place for the version: pyproject.toml
    from importlib.metadata import version as _v
    __version__ = _v("stellenpilot")
except Exception:  # running from a source folder without installing
    __version__ = "dev"
