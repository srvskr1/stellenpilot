# Releasing a new version

1. Raise `version` in `pyproject.toml` (for example 0.1.0 to 0.2.0), commit and push to `main`.
2. The `publish to PyPI` workflow sees the new version, builds the package and uploads it. A few minutes later `pip install -U stellenpilot` gets it. Pushes that keep the same version publish nothing.
3. Optional: write release notes under **Releases** on GitHub.

You can also start the workflow by hand: **Actions**, **publish to PyPI**, **Run workflow**.

## One time PyPI setup (already done)

On https://pypi.org/manage/account/publishing/ a **pending publisher** (later a normal publisher) with:

| field | value |
|---|---|
| PyPI project name | `stellenpilot` |
| Owner | `srvskr1` |
| Repository name | `stellenpilot` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |
