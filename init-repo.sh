#!/bin/bash
set -e

# Initialize cp-paas-iac-reference
cd /home/user/.gemini/antigravity/scratch/srtumkur/2025/k8s-iac/cp-paas-iac-reference

# Setup git if not already
if [ ! -d ".git" ]; then
    git init
    git checkout -b main
fi

git config user.email "antigravity@gemini.google.com"
git config user.name "Antigravity Agent"

git add .
git commit -m "Refactor to Monorepo Architecture" || echo "Nothing to commit"

# Push to Gitea
# Note: Using Gitea Admin credentials we just reset
git remote remove origin 2>/dev/null || true
git remote add origin http://gitea_admin:r8sA84!L^s@192.168.100.10:30300/gitea_admin/cp-paas-iac-reference.git

echo "Pushing to Gitea..."
git push -u origin main
