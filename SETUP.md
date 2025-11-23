# Quick Setup Guide for OrganizePictures

## First Time Setup

After cloning the repository, run these commands:

```bash
# 1. Install Git hooks (enables automatic version bumping)
./setup-hooks.sh

# 2. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install dependencies
uv sync --all-extras
```

That's it! You're ready to develop.

## What the Git Hooks Do

### pre-commit Hook
- **Automatically bumps the patch version** in `pyproject.toml` with every commit
- Example: `1.0.11` → `1.0.12`
- Skip for a specific commit: `git commit --no-verify -m "message"`

### post-checkout Hook
- **Automatically installs hooks** when you clone or checkout the repository
- Ensures all developers have the same hooks installed

## Verifying Setup

Check that hooks are installed:
```bash
ls -la .git/hooks/pre-commit .git/hooks/post-checkout
```

Both should be executable (have `x` permission).

## Testing the Version Bump

Create a test commit to see the version bump in action:

```bash
# Check current version
grep "version = " pyproject.toml

# Make a dummy change
echo "# test" >> test.txt
git add test.txt
git commit -m "Test version bump"

# You should see: ✓ Version bumped: X.Y.Z → X.Y.(Z+1)

# Check new version
grep "version = " pyproject.toml

# Clean up
git reset --soft HEAD~1
rm test.txt
```

## Troubleshooting

### Hooks not running?

1. Make sure they're executable:
   ```bash
   chmod +x .git/hooks/pre-commit .git/hooks/post-checkout
   ```

2. Re-run the setup script:
   ```bash
   ./setup-hooks.sh
   ```

### Want to update hooks?

If hooks are updated in the repository:
```bash
./setup-hooks.sh
```

This will overwrite your local hooks with the latest versions.

## For New Contributors

When you clone this repository, the hooks are **not** automatically installed (Git doesn't allow this for security reasons). You must run:

```bash
./setup-hooks.sh
```

This is a one-time setup per clone.

