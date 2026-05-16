#!/usr/bin/env bash
# Installs the annotate tool into the current project
# Usage: bash install.sh [project-dir]

PROJECT_DIR="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing design-annotate tool into: $PROJECT_DIR"

# Copy runner
cp "$SCRIPT_DIR/annotate.mjs" "$PROJECT_DIR/annotate.mjs"
echo "  + annotate.mjs"

# Create canonical folder structure
mkdir -p "$PROJECT_DIR/.design/prototypes"
mkdir -p "$PROJECT_DIR/.design/snapshots"
mkdir -p "$PROJECT_DIR/.design/screenshots"
mkdir -p "$PROJECT_DIR/.design/reviews"
mkdir -p "$PROJECT_DIR/.design/tools"
echo "  + .design/prototypes/"
echo "  + .design/snapshots/"
echo "  + .design/screenshots/"
echo "  + .design/reviews/"
echo "  + .design/tools/"

# Copy annotator UI
cp "$SCRIPT_DIR/annotator.html" "$PROJECT_DIR/.design/tools/annotator.html"
echo "  + .design/tools/annotator.html"

# Create manifest if it doesn't exist
if [ ! -f "$PROJECT_DIR/.design/manifest.json" ]; then
  echo '{ "pages": [] }' > "$PROJECT_DIR/.design/manifest.json"
  echo "  + .design/manifest.json"
fi

# Add to .gitignore if not already present
GITIGNORE="$PROJECT_DIR/.gitignore"
if [ -f "$GITIGNORE" ]; then
  grep -q ".design/snapshots/" "$GITIGNORE" || echo -e "\n# Design artifacts\n.design/snapshots/\n.design/screenshots/\n.design/reviews/" >> "$GITIGNORE"
else
  echo -e "# Design artifacts\n.design/snapshots/\n.design/screenshots/\n.design/reviews/" > "$GITIGNORE"
fi
echo "  + .gitignore updated"

# Check playwright
if [ -f "$PROJECT_DIR/package.json" ]; then
  if ! grep -q '"playwright"' "$PROJECT_DIR/package.json" 2>/dev/null; then
    echo ""
    echo "  playwright not found in package.json."
    echo "  Run: npm install --save-dev playwright && npx playwright install chromium"
  fi
fi

echo ""
echo "Folder convention:"
echo "  .design/manifest.json   <- Page registry (committed)"
echo "  .design/prototypes/     <- HTML prototypes (committed)"
echo "  .design/snapshots/      <- Auto-preserved before edits (gitignored)"
echo "  .design/screenshots/    <- Raw captures (gitignored)"
echo "  .design/reviews/        <- Annotated screenshots + JSON (gitignored)"
echo "  .design/tools/          <- Annotator UI (committed)"
echo ""
echo "Usage:"
echo "  node annotate.mjs                          # auto-loads from manifest"
echo "  node annotate.mjs .design/prototypes/*.html # ad-hoc targets"
echo "  node annotate.mjs http://localhost:3000     # live dev server"
