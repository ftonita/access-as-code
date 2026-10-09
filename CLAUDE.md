# Working rules for this repository

* **Every completed task is pushed straight to `main`, automatically** - no need to ask first, no pull request unless
  explicitly requested. Before pushing: `ruff check .` and `pytest` must pass and the change must have been reviewed.
* **Commits are authored by the repository owner only**: set `git config user.name/user.email` to the identity of
  the initial commit's author (Iskander Safin) before committing, and add no `Co-Authored-By` or other attribution
  trailers (no `Claude-Session` either) to commit messages.
* Keep `README.md` and `README.ru.md` in sync, and update `CHANGELOG.md` for user-visible changes.
