# PYTHONPATH problem in the shell

## What goes wrong

In a terminal opened through `~/.profile`, `uv run pytest` stops with:

```
ModuleNotFoundError: No module named 'platformdirs.pytest_plugin'
```

and `uv run python -c "import platformdirs; print(platformdirs.__file__)"` prints
`/usr/lib/python3/dist-packages/platformdirs/__init__.py` (version 4.2.0) instead of the copy
inside the project's `.venv` (version 4.13.0).

## Why

`~/.profile` line 34 contains:

```bash
export PYTHONPATH=$PATH:/usr/lib/python3/dist-packages
```

`PYTHONPATH` is a list of folders where Python looks for packages **first**, before the project's own
`.venv`. This line copies the whole `PATH` (all the program folders such as `/usr/bin` and
`~/.cargo/bin`) into it and then adds the system's Python packages. So every Python started from
this shell, including the one `uv` runs, can pick up old system packages instead of the versions the
project installed. Two copies of the same package then disagree (here `platformdirs`: the new
`pytest` plugin file is only in the `.venv` copy), and things break.

The line is probably a copy of a `PATH` line with the name changed by mistake.

## How to fix

The simplest fix is to remove the line. Python finds its own packages without it, and each project
gets its packages from its own `.venv`.

1. Open the file: `nano ~/.profile`
2. Delete line 34 (`export PYTHONPATH=$PATH:/usr/lib/python3/dist-packages`), or put `#` in front of it.
3. Log out and in again (or run `unset PYTHONPATH` in the open terminal).
4. Check: `echo "[$PYTHONPATH]"` should print `[]`, and `uv run pytest -q` should work.

If some system tool really needs the system packages, set `PYTHONPATH` only for that command, not
for the whole shell:

```bash
PYTHONPATH=/usr/lib/python3/dist-packages some-command
```

## Workaround without touching the profile

Start a single command with the variable removed:

```bash
env -u PYTHONPATH uv run pytest -q
```
