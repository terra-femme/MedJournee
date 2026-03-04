# CI Security Pipeline — Errors, Fixes & How to Think About Them

A living log of every error hit while building the 4-loop security pipeline,
why it happened, how it was fixed, and what to check next time.

---

## How to Read a CI Failure

1. Go to your PR on GitHub → click the red ✗ next to the failing check
2. Click **Details** → expand the failed step (the red one)
3. Read the **last few lines** — that's almost always the actual error
4. Copy the error message and match it to a section below

---

## Error 1 — `.secrets.baseline` Not Found

### What you saw
```
detect-secrets scan --baseline .secrets.baseline
Error: Invalid path: .secrets.baseline
Process completed with exit code 1
```

### Why it happened
`detect-secrets audit --baseline <file>` requires the baseline file to
already exist before it can compare against it. The file `.secrets.baseline`
was listed in `.gitignore`, so it was never pushed to GitHub. CI checks out
your repo and the file simply isn't there.

### The fix
Add a bootstrap step in `security.yml` **before** the detect-secrets step:
```yaml
- name: Ensure secrets baseline exists
  run: |
    if [ ! -f .secrets.baseline ]; then
      detect-secrets scan > .secrets.baseline
    fi
```
This generates a fresh baseline on first run so the audit step has something
to compare against.

### What to check next time
- Is the file in `.gitignore`? Run `git check-ignore -v <filename>`
- Does the file exist locally? Does it exist on the branch you pushed?
- Any tool that requires a pre-existing config/baseline file will fail this
  way if that file is gitignored or just not committed

---

## Error 2 — Bandit Can't Read Config File

### What you saw
```
bandit -r . -c .bandit -f json -o bandit-report.json -ll || true
[main]  ERROR  .bandit : Could not read config file.
[main]  ERROR  .bandit : Could not read config file.
Error: Process completed with exit code 2
```

### Why it happened
The `-c .bandit` flag tells Bandit to use `.bandit` as its config file.
That file existed locally but was in `.gitignore`, so it was never pushed.
CI checks out the repo, `.bandit` isn't there, Bandit throws an error and
exits with code 2 (which is a hard failure).

The lesson: **any file you reference with a `-c` / `--config` flag must be
tracked in git** or CI will never find it.

### The fix
Remove `.bandit` from `.gitignore` and commit it:
```bash
# In .gitignore — DELETE this line:
.bandit

# Then:
git add .bandit
git commit -m "Track .bandit config for CI"
git push
```

### What to check next time
- If a tool says "Could not read config file" or "No such file", the config
  file is either gitignored or was never committed
- Run `git ls-files .bandit` — if it returns nothing, the file isn't tracked
- Run `git check-ignore -v .bandit` — if it prints a rule, that rule is the problem
- Other files that follow this same pattern: `.bandit`, `pyproject.toml`,
  `setup.cfg`, `.semgrepignore`, `codecov.yml`

---

## Error 3 — `audioop-lts` Requires Python 3.13

### What you saw
```
ERROR: Could not find a version that satisfies the requirement audioop-lts==0.2.2
(from versions: none)
ERROR: No matching distribution found for audioop-lts==0.2.2
```

### Why it happened
`audioop-lts==0.2.2` is a backport of Python's `audioop` module that was
removed in 3.13. The package only installs on Python 3.13+. The CI workflow
was set to `python-version: "3.11"`, so pip couldn't find a compatible wheel.

### The fix
Two options — pick the one that matches your production environment:

**Option A — Match Python version to your dependency:**
```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.13"
```

**Option B — Don't install app dependencies in the security scan job:**
The security scan (bandit, detect-secrets, pip-audit) doesn't need your app
to run. Remove `pip install -r requirements.txt` from the workflow entirely.
The tools only scan the source files.

We used Option A (Python 3.13) since that matches the app's runtime.

### What to check next time
- `Could not find a version that satisfies the requirement` = version/platform
  mismatch between CI Python and the package
- Check the package's PyPI page for "Requires: Python >=X.X"
- Run `python --version` locally vs what's in `python-version:` in the workflow

---

## Error 4 — `safety check` Deprecated

### What you saw
```
safety check
Warning: `safety check` has been deprecated. Please use `safety scan` instead.
```

### Why it happened
The `safety` CLI replaced `safety check` with `safety scan` in a newer
version. The old command still runs but produces warnings and will eventually
stop working.

### The fix
Replace in `security.yml`:
```yaml
# Before
safety check

# After
safety scan
```

### What to check next time
- CLI tools deprecate subcommands regularly. If you see "deprecated" in output,
  update the command — don't ignore it
- Check the tool's changelog or run `safety --help` to see current commands

---

## Error 5 — Log Injection (CodeQL High Severity)

### What you saw in GitHub PR
```
Log Injection — High
This log entry depends on a user-provided value
routes/costs.py line 88
routes/live_translation.py lines 359, 372
```

### Why it happened
When you log a value that came from the user (URL path parameter, query
string, request body), an attacker can inject fake log entries by including
newline characters (`\n`) in their input.

Example attack — if `user_id` is set to:
```
admin\nINFO 2026-03-04 00:00:00 Logged in successfully
```
Your log file would show a fake "Logged in successfully" line as if it came
from your app. This can be used to hide attacks or manipulate audit trails —
critical for a HIPAA-relevant app.

### The fix
Sanitize user-controlled values before logging them:
```python
def _sanitize_for_log(value: str) -> str:
    """Strip newlines to prevent log injection."""
    if not isinstance(value, str):
        value = str(value)
    return value.replace("\r", "").replace("\n", "")

# Then use it:
logger.exception("Error for user %s", _sanitize_for_log(user_id))
```

**Every path parameter, query parameter, and request body field is
user-controlled.** Always sanitize before logging.

### What to check next time
- CodeQL traces "taint" — it follows where user input goes through your code
- If you log `user_id`, `session_id`, `patient_name`, or anything from a
  request, wrap it with your sanitize helper
- The fix must be applied at the logger call — defining the helper function
  is not enough, you must call it on the argument

---

## Error 6 — `str(e)` Returned to API Clients (Information Exposure)

### What you saw in GitHub PR
```
Information Exposure Through an Error Message — High
routes/costs.py line 88: return {"error": str(e)}
```

### Why it happened
`str(e)` on a Python exception can contain:
- Database connection strings
- File paths on your server
- Internal variable names
- Stack traces

Returning this to an API client leaks internal architecture details that
help attackers target your system. For a medical app, it could also leak
patient-adjacent data from DB errors.

### The fix
```python
# Before — leaks internals
except Exception as e:
    return {"error": str(e)}

# After — safe
except Exception as e:
    logger.exception("Descriptive message about what failed")
    return {"error": "Internal server error"}
```

`logger.exception()` logs the full traceback server-side (where only you can
see it) while the client gets a generic message.

### What to check next time
- Search your codebase: `grep -r "str(e)" routes/`
- Any `str(e)` in a return statement is a potential information leak
- It's fine to use `str(e)` in your logs — just not in API responses

---

## Error 7 — `.bandit` INI Format vs YAML

### What you saw (local)
```
bandit -r . -c .bandit
[main]  ERROR  .bandit : Could not read config file.
```
(Even though the file existed locally)

### Why it happened
The initial `.bandit` file was written in INI format:
```ini
[bandit]
skips = B101,B311
```
Bandit 1.7.x expects YAML format, not INI. The parser silently failed.

### The fix
Rewrite `.bandit` as valid YAML:
```yaml
skips:
  - B101
  - B311
exclude_dirs:
  - tests
  - migrations
```

### What to check next time
- When a tool says "Could not read config file" and the file EXISTS, the
  issue is the format, not the path
- Check the tool's documentation for the expected config format — it often
  changes between major versions
- Run `bandit --help` and look for `--configfile` format notes

---

## Error 8 — Semgrep Failures Hidden by `|| true`

### What you saw
Semgrep step always showed green even when it found issues.

### Why it happened
The workflow had:
```yaml
run: semgrep scan ... || true
```
`|| true` means "if the command fails, pretend it succeeded." Semgrep was
finding issues but the CI step never went red, so findings were invisible.

### The fix
```yaml
# Before — silently eats failures
run: semgrep scan ... || true

# After — failures surface in GitHub UI
run: semgrep scan ...
continue-on-error: true  # shows as red but doesn't block merge
```

`continue-on-error: true` marks the step as failed (red ✗ in the UI) without
blocking subsequent steps or the overall job. You see the problem, the report
still uploads.

### What to check next time
- `|| true` in CI run steps is a red flag — it hides failures
- Use `continue-on-error: true` at the step level instead — it's visible,
  controllable, and doesn't swallow errors
- Grep your workflows: `grep -r "|| true" .github/`

---

---

## Error 9 — Bandit TOML Parser Not Available in Pre-commit

### What you saw (local pre-commit hook)
```
bandit...................................................................Failed
[main]  ERROR  pyproject.toml : toml parser not available, reinstall with toml extra
```

### Why it happened
Pre-commit runs each hook in its **own isolated virtual environment** — separate
from your local Python environment. Even if you have `bandit[toml]` installed
globally, the hook's environment only has plain `bandit`. It can't read
`pyproject.toml` without the `toml` extra.

### The fix
Add `additional_dependencies` to the bandit hook in `.pre-commit-config.yaml`:
```yaml
- id: bandit
  args: ['-c', 'pyproject.toml', '-ll']
  additional_dependencies: ['bandit[toml]']
```
This tells pre-commit to install `bandit[toml]` (with the TOML parser) into
the hook's isolated environment.

### What to check next time
- Any pre-commit hook that references `pyproject.toml` needs `bandit[toml]`
  in `additional_dependencies`
- This applies to other tools too — if a hook needs a plugin or extra, declare
  it in `additional_dependencies`, not just in your local environment
- Pre-commit isolates every hook: your local `pip install X` doesn't affect them

---

## Error 10 — `.bandit` YAML Format (Invalid for Bandit)

### What you saw
```
[utils]  WARNING  Unable to parse config file ./.bandit or missing [bandit] section
```

### Why it happened
Bandit has two config parsers:
- When it **auto-discovers** `.bandit` as a project file → uses INI parser
- When you pass `-c pyproject.toml` → uses TOML parser

YAML was never a valid format for `.bandit`. The skips still worked because
bandit fell back to CLI defaults, but the warning was always there.

### The fix
Delete `.bandit` and move config to `pyproject.toml`:
```toml
[tool.bandit]
skips = ["B101", "B311"]
exclude_dirs = ["tests", "migrations", "alembic"]
```
Then reference it explicitly: `bandit -r . -c pyproject.toml`

`pyproject.toml` is the modern standard for Python tool config — bandit,
mypy, pytest, black, ruff all read from it.

### What to check next time
- If a tool says "Unable to parse config file", check the expected format
  in that tool's documentation — it's often changed between major versions
- `pyproject.toml` with `[tool.<name>]` sections is now the standard for
  most Python tools; prefer it over tool-specific dotfiles

---

## Error 11 — `end-of-file-fixer` / `trim-trailing-whitespace` Auto-Fixed Then Failed

### What you saw
```
fix end of files.........................................................Failed
- files were modified by this hook
Fixing services/cloud_speaker_service.py

trim trailing whitespace.................................................Failed
- files were modified by this hook
```

### Why it happened
These hooks **auto-fix** the files they find problems in. They modify the file
on disk, then exit with code 1 to force you to re-stage and commit again.
This is intentional — the hook fixed the problem for you.

### The fix
Just run `git commit` again. The hooks already fixed the files. On the second
run everything passes.

### What to check next time
- This is **expected behavior** for formatting hooks, not a real error
- If you see "files were modified by this hook", just re-run the commit
- These hooks never require you to manually edit anything — they self-fix

---

## General Debugging Checklist

When any CI step fails, run through this in order:

1. **Is the file missing?**
   `git ls-files <filename>` — if empty, it's not tracked
   `git check-ignore -v <filename>` — if it prints something, it's gitignored

2. **Is the format wrong?**
   Read the tool's docs for expected config format. Try running locally with
   the same command CI uses.

3. **Is the Python version wrong?**
   Check `python-version:` in the workflow vs what your packages require.

4. **Is the command deprecated?**
   Run the tool with `--help` locally. Look for deprecation warnings.

5. **Is a failure being swallowed?**
   Look for `|| true` in your workflow `run:` blocks.

6. **What's the actual error?**
   Always read the **last 5-10 lines** of a failed step's output. The first
   lines are often just tool startup noise.

---

## Files That Must Be Tracked in Git (Never Gitignore)

| File | Why |
|------|-----|
| `.bandit` | Bandit reads it with `-c` flag — CI breaks without it |
| `.semgrepignore` | Semgrep rule exclusions |
| `pyproject.toml` | Used by multiple tools (bandit, mypy, pytest) |
| `.github/workflows/*.yml` | The workflows themselves |
| `codecov.yml` | Coverage config |

## Files That Should Stay in `.gitignore`

| File | Why |
|------|-----|
| `.env` | Contains real secrets |
| `.secrets.baseline` | May contain hashed representations of secrets |
| `*.pyc`, `__pycache__/` | Build artifacts |
| `venv/`, `env/` | Local virtual environments |
