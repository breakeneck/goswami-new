git fetch origin &&
git reset --hard origin/main &&
git clean -fd &&
git log -1 --pretty=format:"%h %s"

docker compose exec -T web python manage.py migrate --run-syncdb || true