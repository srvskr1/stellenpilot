# Entry point for the Windows and Mac apps built with PyInstaller (.github/workflows/windows.yml, macos.yml).
from stellenpilot.app import main

raise SystemExit(main())
