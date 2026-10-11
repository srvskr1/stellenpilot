# Releasing a new version

1. Raise `version` in `pyproject.toml` (for example 0.1.0 to 0.2.0) and push.
2. On GitHub: **Releases**, **Draft a new release**, tag `v0.2.0`, write what changed, **Publish release**.
3. The `publish to PyPI` workflow builds the package and uploads it. A few minutes later `pip install -U jobradar` gets the new version.

## One time PyPI setup (already done once per project)

On https://pypi.org/manage/account/publishing/ add a **pending publisher**:

| field | value |
|---|---|
| PyPI project name | `jobradar` |
| Owner | `srvskr1` |
| Repository name | `jobradar` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |
