#!/bin/bash
# Setup script to install Git hooks for OrganizePictures
# This script copies hooks from the hooks/ directory to .git/hooks/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/hooks"
GIT_HOOKS_DIR="$SCRIPT_DIR/.git/hooks"

echo "🔧 Setting up Git hooks for OrganizePictures..."

# Check if we're in a git repository
if [ ! -d "$SCRIPT_DIR/.git" ]; then
    echo "❌ Error: Not a git repository. Please run this from the repository root."
    exit 1
fi

# Check if hooks directory exists
if [ ! -d "$HOOKS_DIR" ]; then
    echo "❌ Error: hooks/ directory not found."
    exit 1
fi

# Create .git/hooks directory if it doesn't exist
mkdir -p "$GIT_HOOKS_DIR"

# Install each hook
HOOKS_INSTALLED=0
for hook in "$HOOKS_DIR"/*; do
    if [ -f "$hook" ]; then
        hook_name=$(basename "$hook")
        
        # Skip README files
        if [[ "$hook_name" == "README.md" ]]; then
            continue
        fi
        
        target="$GIT_HOOKS_DIR/$hook_name"
        
        # Copy the hook
        cp "$hook" "$target"
        chmod +x "$target"
        
        echo "✓ Installed: $hook_name"
        HOOKS_INSTALLED=$((HOOKS_INSTALLED + 1))
    fi
done

if [ $HOOKS_INSTALLED -eq 0 ]; then
    echo "⚠️  No hooks found to install."
else
    echo ""
    echo "✅ Successfully installed $HOOKS_INSTALLED hook(s)!"
    echo ""
    echo "📝 Installed hooks:"
    echo "   • pre-commit: Automatically bumps patch version in pyproject.toml"
    echo ""
    echo "💡 To skip a hook for a specific commit, use: git commit --no-verify"
fi

