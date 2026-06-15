#!/bin/bash
# sync-upstream.sh — 同步上游 Hermes 仓库到 fork
#
# 用法: ./scripts/sync-upstream.sh
#
# 功能:
#   1. 从 upstream/main 拉取最新代码
#   2. 合并到本地 main 分支
#   3. 推送到 origin
#   4. 检查是否有文件修改到了保护目录

set -euo pipefail

PROTECTED_DIRS=(
  "hermes_cli/"
  "agent/"
  "gateway/"
  "tools/"
  "plugins/"
  "cron/"
  "tests/"
  "run_agent.py"
  "model_tools.py"
  "toolsets.py"
  "cli.py"
  "hermes_state.py"
)

ALLOWED_DIRS=(
  "apps/desktop/src/"
  "apps/desktop/electron/"
  "apps/desktop/assets/"
  "apps/desktop/public/"
  "apps/desktop/scripts/"
  "scripts/sync-upstream.sh"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Hermes Upstream Sync ===${NC}"
echo ""

# Step 1: Fetch upstream
echo -e "${YELLOW}[1/4] Fetching upstream...${NC}"
git fetch upstream main

# Step 2: Check current branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo -e "${YELLOW}Switching to main (was on $CURRENT_BRANCH)...${NC}"
  git checkout main
fi

# Step 3: Merge upstream
echo -e "${YELLOW}[2/4] Merging upstream/main...${NC}"
BEFORE_SHA=$(git rev-parse HEAD)
git merge upstream/main --no-edit 2>&1 || {
  echo -e "${RED}Merge conflict! Please resolve manually.${NC}"
  exit 1
}
AFTER_SHA=$(git rev-parse HEAD)

# Step 4: Check for protected directory changes
echo -e "${YELLOW}[3/4] Checking for protected directory changes...${NC}"
CHANGED_FILES=$(git diff --name-only "$BEFORE_SHA".."$AFTER_SHA" 2>/dev/null || echo "")

if [ -n "$CHANGED_FILES" ]; then
  VIOLATIONS=()
  for file in $CHANGED_FILES; do
    for protected in "${PROTECTED_DIRS[@]}"; do
      if [[ "$file" == "$protected"* ]]; then
        VIOLATIONS+=("$file")
      fi
    done
  done

  if [ ${#VIOLATIONS[@]} -gt 0 ]; then
    echo -e "${RED}WARNING: Upstream changed files in protected directories:${NC}"
    for v in "${VIOLATIONS[@]}"; do
      echo -e "  ${RED}✗ $v${NC}"
    done
    echo ""
    echo -e "${YELLOW}These changes will be pulled in automatically.${NC}"
    echo -e "${YELLOW}If you have custom changes in these files, you may need to resolve conflicts.${NC}"
  else
    echo -e "${GREEN}No protected directory changes detected.${NC}"
  fi
else
  echo -e "${GREEN}No file changes in this merge.${NC}"
fi

# Step 5: Push to origin
echo -e "${YELLOW}[4/4] Pushing to origin...${NC}"
git push origin main 2>&1

echo ""
echo -e "${GREEN}=== Sync complete! ===${NC}"
echo -e "Current branch: $(git branch --show-current)"
echo -e "HEAD: $(git log --oneline -1)"
echo ""
echo -e "${YELLOW}Don't forget to rebase your custom branch:${NC}"
echo -e "  git checkout custom/huaqing-desktop"
echo -e "  git rebase main"
