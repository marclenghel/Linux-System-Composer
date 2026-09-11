# GitHub Upload and Management Guide

## Table of Contents
- [Quick Reference](#quick-reference)
- [Understanding Git and GitHub](#understanding-git-and-github)
- [Initial Setup (First Time Only)](#initial-setup-first-time-only)
- [Daily Workflow](#daily-workflow)
- [How This Project Was Set Up](#how-this-project-was-set-up)
- [Common Tasks](#common-tasks)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Quick Reference

### Check Status
```bash
git status
```

### Add Changes
```bash
git add .                    # Add all changes
git add filename.txt         # Add specific file
```

### Commit Changes
```bash
git commit -m "Your message here"
```

### Push to GitHub
```bash
git push origin main
```

### Pull Latest Changes
```bash
git pull origin main
```

---

## Understanding Git and GitHub

### What is Git?
Git is a **version control system** that tracks changes to your code over time. Think of it as a sophisticated "undo" system that:
- Saves snapshots (commits) of your project at different points in time
- Lets you work on different features simultaneously (branches)
- Allows collaboration without overwriting others' work

### What is GitHub?
GitHub is a **cloud hosting service** for Git repositories. It:
- Stores your code online (backup + accessibility)
- Enables collaboration with others
- Provides tools for project management (issues, pull requests)
- Makes your code accessible from anywhere

### Key Concepts

**Repository (Repo)**: A project folder tracked by Git containing all your files and their history.

**Commit**: A snapshot of your project at a specific moment. Each commit has:
- A unique ID (hash)
- A message describing what changed
- Author information
- Timestamp

**Branch**: A parallel version of your code. The default branch is usually called `main` or `master`.

**Remote**: A version of your repository hosted elsewhere (like GitHub). Usually called `origin`.

**Push**: Upload your local commits to GitHub.

**Pull**: Download commits from GitHub to your local machine.

**Clone**: Create a local copy of a GitHub repository.

---

## Initial Setup (First Time Only)

### 1. Install Git
```bash
# On Arch Linux
sudo pacman -S git

# On Ubuntu/Debian
sudo apt install git

# Verify installation
git --version
```

### 2. Configure Git (Required for commits)
```bash
# Set your name
git config --global user.name "Your Name"

# Set your email (use your GitHub email)
git config --global user.email "your.email@example.com"

# Verify configuration
git config --list
```

### 3. Create a GitHub Account
1. Go to https://github.com
2. Sign up for a free account
3. Verify your email address

### 4. Set Up Authentication

#### Option A: SSH (Recommended)
```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your.email@example.com"

# Start SSH agent
eval "$(ssh-agent -s)"

# Add key to agent
ssh-add ~/.ssh/id_ed25519

# Copy public key
cat ~/.ssh/id_ed25519.pub
```

Then:
1. Go to GitHub → Settings → SSH and GPG keys
2. Click "New SSH key"
3. Paste your public key
4. Test connection: `ssh -T git@github.com`

#### Option B: HTTPS with Token
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Select scopes: `repo` (full control of private repositories)
4. Copy the token (save it securely!)
5. Use this token as password when pushing

---

## Daily Workflow

This is the typical cycle you'll follow when working on your project:

### Step 1: Check Current Status
```bash
# See what files have changed
git status

# See detailed changes
git diff
```

### Step 2: Add Your Changes
```bash
# Add all changed files
git add .

# OR add specific files
git add src/main.rs
git add README.md

# Check what's staged
git status
```

### Step 3: Commit Your Changes
```bash
# Commit with a descriptive message
git commit -m "Add compatibility engine foundation"

# Multi-line commit message
git commit -m "Add compatibility engine foundation" -m "- Implemented dependency resolution
- Added conflict detection
- Created validation system"
```

### Step 4: Push to GitHub
```bash
# Push to main branch
git push origin main

# First time pushing a new branch
git push -u origin main
```

### Complete Example
```bash
# 1. Make changes to your files
# 2. Check what changed
git status

# 3. Add changes
git add .

# 4. Commit
git commit -m "Implement hardware detection layer"

# 5. Push to GitHub
git push origin main
```

---

## How This Project Was Set Up

Your **Linux-System-Composer** project was set up with these steps:

### 1. Initialize Local Repository
```bash
cd /home/popica/code_and_stuff/Linux-System-Composer
git init
```
This created a `.git` folder that tracks all changes.

### 2. Add Files to Git
```bash
git add .
```
This staged all files for the first commit.

### 3. Create Initial Commit
```bash
git commit -m "Initial commit"
```
This created the first snapshot of your project.

### 4. Create GitHub Repository
1. Went to GitHub → New Repository
2. Named it: `Linux-System-Composer`
3. Left it empty (no README, .gitignore, or license)

### 5. Connect Local to GitHub
```bash
git remote add origin https://github.com/marclenghel/Linux-System-Composer
```
This linked your local repository to GitHub.

### 6. Push to GitHub
```bash
git push -u origin main
```
This uploaded all your code to GitHub.

### Current State
```bash
# Your repository is connected to:
origin: https://github.com/marclenghel/Linux-System-Composer

# You're on branch: main
# Status: up to date with GitHub
```

---

## Common Tasks

### View Commit History
```bash
# Simple history
git log

# One line per commit
git log --oneline

# With graph
git log --graph --oneline --all

# Last 5 commits
git log -5
```

### Undo Changes

#### Discard Uncommitted Changes
```bash
# Discard changes in specific file
git checkout -- filename.txt

# Discard all changes
git checkout -- .
```

#### Undo Last Commit (Keep Changes)
```bash
git reset --soft HEAD~1
```

#### Undo Last Commit (Discard Changes)
```bash
git reset --hard HEAD~1
```

### Create a New Branch
```bash
# Create and switch to new branch
git checkout -b feature-name

# Or with newer syntax
git switch -c feature-name

# List all branches
git branch

# Switch between branches
git checkout main
git checkout feature-name
```

### Merge Branches
```bash
# Switch to main
git checkout main

# Merge feature branch into main
git merge feature-name

# Delete merged branch
git branch -d feature-name
```

### Clone Your Repository (On Another Machine)
```bash
# Clone with HTTPS
git clone https://github.com/marclenghel/Linux-System-Composer

# Clone with SSH
git clone git@github.com:marclenghel/Linux-System-Composer.git

# Clone to specific folder
git clone https://github.com/marclenghel/Linux-System-Composer my-project
```

### Update From GitHub
```bash
# Fetch and merge changes
git pull origin main

# Just fetch (don't merge yet)
git fetch origin

# See what would be merged
git diff main origin/main
```

### Check Remote Connection
```bash
# View remote URLs
git remote -v

# Test connection
git remote show origin
```

### Change Remote URL
```bash
# Change to SSH
git remote set-url origin git@github.com:marclenghel/Linux-System-Composer.git

# Change to HTTPS
git remote set-url origin https://github.com/marclenghel/Linux-System-Composer
```

---

## Troubleshooting

### Problem: "fatal: not a git repository"
**Solution**: You're not in a Git-tracked directory.
```bash
cd /home/popica/code_and_stuff/Linux-System-Composer
```

### Problem: "error: failed to push some refs"
**Solution**: Remote has changes you don't have locally.
```bash
git pull origin main
# Resolve any conflicts
git push origin main
```

### Problem: Merge Conflict
**What it means**: Git can't automatically combine changes.

**Solution**:
1. Open conflicted files (marked with `<<<<<<<`, `=======`, `>>>>>>>`)
2. Edit to keep what you want
3. Remove conflict markers
4. Stage resolved files: `git add filename`
5. Commit: `git commit -m "Resolve merge conflict"`

### Problem: Accidentally Committed Sensitive Data
**Solution**:
```bash
# Remove from last commit
git rm --cached sensitive_file.txt
git commit --amend -m "Remove sensitive file"
git push --force origin main

# For older commits, use git filter-branch or BFG Repo-Cleaner
```

### Problem: Wrong Commit Message
**Solution** (if not pushed yet):
```bash
git commit --amend -m "Correct message"
```

### Problem: Forgot to Add Files to Commit
**Solution** (if not pushed yet):
```bash
git add forgotten_file.txt
git commit --amend --no-edit
```

### Problem: "Permission denied (publickey)"
**Solution**: SSH key not set up properly.
1. Check if key exists: `ls ~/.ssh/id_ed25519.pub`
2. If not, generate one (see Initial Setup)
3. Add to GitHub (Settings → SSH keys)
4. Test: `ssh -T git@github.com`

---

## Best Practices

### Commit Messages
✅ **Good**:
```
Add user authentication system
Implement compatibility validation
Fix crash when loading hardware profiles
```

❌ **Bad**:
```
fixed stuff
WIP
asdfasdf
```

**Tips**:
- Use imperative mood ("Add feature" not "Added feature")
- Be descriptive but concise
- Explain **why** if not obvious from code

### When to Commit
- Commit often (small, logical changes)
- Each commit should represent one complete change
- Commit before switching tasks
- Don't commit broken code to main branch

### What NOT to Commit
Add these to `.gitignore`:
```
# Build artifacts
/target/
*.exe
*.dll
*.so

# IDE files
.vscode/
.idea/
*.swp

# OS files
.DS_Store
Thumbs.db

# Sensitive data
.env
config.local
*.key
credentials.json

# Dependencies (language-specific)
node_modules/
__pycache__/
```

### Branch Strategy
- `main`: Stable, working code
- `dev`: Development branch
- `feature/feature-name`: Individual features
- `fix/bug-description`: Bug fixes

### Before Pushing
1. Review your changes: `git diff`
2. Test your code
3. Write clear commit message
4. Pull latest changes: `git pull origin main`
5. Resolve conflicts if any
6. Push: `git push origin main`

### Collaboration
- Pull before you start working
- Push frequently
- Use branches for features
- Write detailed commit messages
- Comment your code
- Update documentation

---

## Project-Specific Workflows

### For This Rust Project

#### After Editing Code
```bash
# 1. Test compilation
cargo build

# 2. Run tests (when you have them)
cargo test

# 3. Check for issues
cargo clippy

# 4. Format code
cargo fmt

# 5. Commit if everything works
git add .
git commit -m "Descriptive message"
git push origin main
```

#### Adding New Dependencies
```bash
# 1. Add to Cargo.toml or use cargo add
cargo add serde

# 2. Commit both Cargo.toml and Cargo.lock
git add Cargo.toml Cargo.lock
git commit -m "Add serde dependency for serialization"
git push origin main
```

---

## Useful Git Commands Cheat Sheet

| Command | Description |
|---------|-------------|
| `git init` | Create new repository |
| `git clone <url>` | Copy repository from GitHub |
| `git status` | Show changed files |
| `git add <file>` | Stage file for commit |
| `git add .` | Stage all changes |
| `git commit -m "msg"` | Create commit |
| `git push origin main` | Upload to GitHub |
| `git pull origin main` | Download from GitHub |
| `git log` | View commit history |
| `git diff` | Show unstaged changes |
| `git branch` | List branches |
| `git checkout -b <name>` | Create new branch |
| `git merge <branch>` | Merge branch |
| `git remote -v` | Show remote URLs |
| `git stash` | Temporarily save changes |
| `git stash pop` | Restore stashed changes |

---

## Additional Resources

### Official Documentation
- Git: https://git-scm.com/doc
- GitHub: https://docs.github.com

### Interactive Tutorials
- Learn Git Branching: https://learngitbranching.js.org
- GitHub Skills: https://skills.github.com

### Quick References
- Git Cheat Sheet: https://education.github.com/git-cheat-sheet-education.pdf
- Visual Git Reference: https://marklodato.github.io/visual-git-guide/index-en.html

### GitHub Features
- Issues: Track bugs and feature requests
- Pull Requests: Review code changes
- Actions: Automate workflows (CI/CD)
- Projects: Organize work with boards
- Wiki: Documentation

---

## Your Current Setup Summary

```
Repository: Linux-System-Composer
Location: /home/popica/code_and_stuff/Linux-System-Composer
GitHub: https://github.com/marclenghel/Linux-System-Composer
Branch: main
Status: Clean (up to date with GitHub)

Files:
├── Cargo.toml          # Rust project configuration
├── Cargo.lock          # Dependency lock file
├── README.md           # Project documentation
├── LICENSE             # GPL-3.0 license
├── .gitignore          # Ignored files
└── src/
    └── main.rs         # Main source code
```

**Your typical workflow**:
1. Edit files in your project
2. `git status` - see what changed
3. `git add .` - stage changes
4. `git commit -m "description"` - save snapshot
5. `git push origin main` - upload to GitHub

---

## Questions?

If you need help:
1. Check this guide first
2. Use `git --help` or `git <command> --help`
3. Search GitHub documentation
4. Ask in programming communities (Stack Overflow, Reddit)

Remember: Git is a powerful tool, but the basics are simple:
- **Add** → **Commit** → **Push**

Happy coding!
