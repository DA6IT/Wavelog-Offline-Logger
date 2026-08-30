# Contributing

[Deutsch](CONTRIBUTING.md) · **English**

Bug reports and focused pull requests are welcome. Never attach real ADI logs, API tokens, passwords or private profile databases. Include the operating system, application version, expected result, actual result and reproducible steps.

Before submitting code, run `python selftest.py`. Changes to the GUI must remain usable in German and English, Light and Dark themes, and at the supported responsive window sizes. Add every new user-visible German string to `ui_preferences.py` with an English translation. Data-format and synchronization changes require migration and loss-safety tests because ADI remains the primary logbook.

Release builds are created only through the documented scripts and GitHub-hosted workflows. See [docs/en/ARCHITECTURE.md](docs/en/ARCHITECTURE.md) and [docs/en/RELEASING.md](docs/en/RELEASING.md).
