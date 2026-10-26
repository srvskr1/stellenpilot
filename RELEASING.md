# Releasing a new version

1. Raise `version` in `pyproject.toml` (for example 0.1.0 to 0.2.0), commit and push to `main`.
2. The `publish to PyPI` workflow sees the new version, builds the package and uploads it. A few minutes later `pip install -U stellenpilot` gets it. Pushes that keep the same version publish nothing.
3. When PyPI has it, the `homebrew` workflow points the formula in [srvskr1/homebrew-stellenpilot](https://github.com/srvskr1/homebrew-stellenpilot) at the new version, refreshes its dependencies, installs and tests it on a Mac runner, then pushes. `brew upgrade stellenpilot` gets it from then on.
4. Optional: write release notes under **Releases** on GitHub.

## One time Homebrew setup

1. Create the public repository `srvskr1/homebrew-stellenpilot` and push the `Formula/stellenpilot.rb` and `README.md` for it.
2. Make a fine grained token (GitHub, Settings, Developer settings, Fine-grained tokens) with access to `homebrew-stellenpilot` only and **Contents: Read and write**.
3. Save it in this repository under Settings, Secrets and variables, Actions as `HOMEBREW_TAP_TOKEN`.
4. Run the `homebrew` workflow once from the Actions tab to check it.

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
