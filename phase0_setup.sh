#!/bin/bash
# Phase 0: Foundation Setup
# Creates folder structure and performs low-risk file moves

set -e  # Exit on error

echo "======================================"
echo "Phase 0: Foundation Setup"
echo "======================================"
echo ""

# Navigate to project root
cd "$(dirname "$0")"
PROJECT_ROOT="/home/llhama-usr/Local_LLHAMA"
cd "$PROJECT_ROOT/local_llhama"

echo "Step 1: Creating new folder structure..."
mkdir -p core services factories utils config audio system domain
echo "✓ Folders created"

echo ""
echo "Step 2: Creating __init__.py files..."
touch core/__init__.py
touch services/__init__.py
touch factories/__init__.py
touch utils/__init__.py
touch config/__init__.py
touch audio/__init__.py
touch system/__init__.py
touch domain/__init__.py
echo "✓ __init__.py files created"

echo ""
echo "Step 3: Moving utility files (LOW RISK)..."
if [ -f "memory_search_helpers.py" ]; then
    git mv memory_search_helpers.py utils/
    echo "✓ Moved memory_search_helpers.py → utils/"
else
    echo "⚠ memory_search_helpers.py already moved or missing"
fi

if [ -f "simple_functions_helpers.py" ]; then
    git mv simple_functions_helpers.py utils/
    echo "✓ Moved simple_functions_helpers.py → utils/"
else
    echo "⚠ simple_functions_helpers.py already moved or missing"
fi

echo ""
echo "Step 4: Moving audio files (LOW RISK)..."
if [ -f "audio_input.py" ]; then
    git mv audio_input.py audio/
    echo "✓ Moved audio_input.py → audio/"
else
    echo "⚠ audio_input.py already moved or missing"
fi

if [ -f "audio_output.py" ]; then
    git mv audio_output.py audio/
    echo "✓ Moved audio_output.py → audio/"
else
    echo "⚠ audio_output.py already moved or missing"
fi

echo ""
echo "======================================"
echo "Phase 0 Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Update imports for moved files:"
echo "   - memory_search_helpers.py"
echo "   - simple_functions_helpers.py"
echo "   - audio_input.py"
echo "   - audio_output.py"
echo ""
echo "2. Run tests:"
echo "   pytest tests/ -v"
echo ""
echo "3. Commit changes:"
echo "   git add -A"
echo "   git commit -m 'refactor: Phase 0 - Create folder structure and move utilities/audio'"
echo ""
echo "4. Proceed to Phase 1 (see IMPLEMENTATION_PLAN_COMBINED.md)"
echo ""
