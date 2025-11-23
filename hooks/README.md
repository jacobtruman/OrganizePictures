# Git Hooks for OrganizePictures

This directory contains Git hooks that are automatically installed when you set up the repository.

## Available Hooks

### pre-commit
Automatically bumps the patch version in `pyproject.toml` with every commit.

**Example:**
- Before commit: `version = '1.0.11'`
- After commit: `version = '1.0.12'`

### post-checkout
Automatically installs all hooks when you clone or checkout the repository.

## Installation

### Automatic Installation (Recommended)

When you clone the repository, run:

```bash
./setup-hooks.sh
```

This will install all hooks from this directory to `.git/hooks/`.

### Manual Installation

If you prefer to install hooks manually:

```bash
cp hooks/* .git/hooks/
chmod +x .git/hooks/*
```

## Usage

Once installed, hooks run automatically:

- **pre-commit**: Runs before each commit
- **post-checkout**: Runs after git clone or git checkout

### Skipping Hooks

To skip hooks for a specific commit:

```bash
git commit --no-verify -m "Your message"
```

## For Repository Maintainers

When adding new hooks:

1. Create the hook script in this `hooks/` directory
2. Make it executable: `chmod +x hooks/your-hook`
3. Test it: `./hooks/your-hook`
4. Commit it to the repository
5. Update this README

Users will get the new hook when they run `./setup-hooks.sh` again.

