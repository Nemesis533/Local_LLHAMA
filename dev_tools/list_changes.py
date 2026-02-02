#!/usr/bin/env python3
"""
List all files changed since a specified commit.
Useful for tracking which files need manual review.
"""

import subprocess
import sys
from datetime import datetime


def get_changed_files(commit_hash):
    """
    Get list of changed files since the specified commit.
    
    @param commit_hash: Git commit hash to compare against
    @return: Dictionary with lists of added, modified, renamed, and deleted files
    """
    try:
        # Run git diff to get file changes
        result = subprocess.run(
            ['git', 'diff', '--name-status', commit_hash, 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().split('\n')
        
        changes = {
            'added': [],
            'modified': [],
            'renamed': [],
            'deleted': []
        }
        
        for line in lines:
            if not line:
                continue
                
            parts = line.split('\t')
            status = parts[0]
            
            if status == 'A':
                changes['added'].append(parts[1])
            elif status == 'M':
                changes['modified'].append(parts[1])
            elif status.startswith('R'):
                # Renamed files show as R100 old_name new_name
                changes['renamed'].append(f"{parts[1]} → {parts[2]}")
            elif status == 'D':
                changes['deleted'].append(parts[1])
        
        return changes
        
    except subprocess.CalledProcessError as e:
        print(f"Error running git command: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def write_to_file(changes, commit_hash, output_file='CHANGES_SINCE_COMMIT.md'):
    """Write changes to a markdown file."""
    with open(output_file, 'w') as f:
        f.write(f"# Files Changed Since Commit {commit_hash[:8]}\n\n")
        
        if changes['added']:
            f.write(f"## New Files ({len(changes['added'])})\n")
            for file in sorted(changes['added']):
                f.write(f"- {file}\n")
            f.write("\n")
        
        if changes['modified']:
            f.write(f"## Modified Files ({len(changes['modified'])})\n")
            for file in sorted(changes['modified']):
                f.write(f"- {file}\n")
            f.write("\n")
        
        if changes['renamed']:
            f.write(f"## Renamed Files ({len(changes['renamed'])})\n")
            for file in sorted(changes['renamed']):
                f.write(f"- {file}\n")
            f.write("\n")
        
        if changes['deleted']:
            f.write(f"## Deleted Files ({len(changes['deleted'])})\n")
            for file in sorted(changes['deleted']):
                f.write(f"- {file}\n")
            f.write("\n")
        
        total = sum(len(v) for v in changes.values())
        f.write(f"---\n**Total: {total} files**\n")


def print_summary(changes):
    """Print summary to console."""
    print("\n" + "="*60)
    print("FILE CHANGES SUMMARY")
    print("="*60 + "\n")
    
    if changes['added']:
        print(f"New Files: {len(changes['added'])}")
        for file in sorted(changes['added']):
            print(f"  + {file}")
        print()
    
    if changes['modified']:
        print(f"Modified Files: {len(changes['modified'])}")
        for file in sorted(changes['modified']):
            print(f"  M {file}")
        print()
    
    if changes['renamed']:
        print(f"Renamed Files: {len(changes['renamed'])}")
        for file in sorted(changes['renamed']):
            print(f"  R {file}")
        print()
    
    if changes['deleted']:
        print(f"Deleted Files: {len(changes['deleted'])}")
        for file in sorted(changes['deleted']):
            print(f"  - {file}")
        print()
    
    total = sum(len(v) for v in changes.values())
    print("="*60)
    print(f"Total: {total} files changed")
    print("="*60 + "\n")


def main():
    """Main entry point."""
    # Get commit hash from command line or use default
    if len(sys.argv) > 1:
        commit_hash = sys.argv[1]
    else:
        print("Usage: python list_changes.py <commit_hash> [output_file]")
        print("\nExample:")
        print("  python list_changes.py b5ddf91a5c717276a40911f7b2e2f6fecf3c7126")
        print("  python list_changes.py HEAD~5 my_changes.md")
        sys.exit(1)
    
    # Get optional output file
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'CHANGES_SINCE_COMMIT.md'
    
    print(f"Analyzing changes since commit {commit_hash[:8]}...")
    
    # Get the changes
    changes = get_changed_files(commit_hash)
    
    # Print to console
    print_summary(changes)
    
    # Write to file
    write_to_file(changes, commit_hash, output_file)
    print(f"Changes written to: {output_file}")


if __name__ == '__main__':
    main()
