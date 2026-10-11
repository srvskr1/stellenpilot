# Releasing a new version

1. Raise `version` in `pyproject.toml` (for example 0.1.0 to 0.2.0) and push.
2. Tag it and push the tag: `git tag v0.2.0 && git push origin v0.2.0`
3. The `publish to PyPI` workflow checks that the tag matches the version, builds the package and uploads it. Optionally write release notes under **Releases** on GitHub. A few minutes later `pip install -U stellenpilot` gets the new version.

## One time PyPI setup (already done once per project)

On https://pypi.org/manage/account/publishing/ add a **pending publisher**:

| field | value |
|---|---|
| PyPI project name | `stellenpilot` |
| Owner | `srvskr1` |
| Repository name | `stellenpilot` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |
