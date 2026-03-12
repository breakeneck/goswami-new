git pull origin main || git pull origin master || echo "Git pull skipped (not a git repo or no remote)"
git log -1 --pretty=%B