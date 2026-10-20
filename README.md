# Library Management System (DevOps Mini Project)

A simple Flask + SQLite web app to manage **books**, **members** and **issue/return records**,
with a complete DevOps setup: tests, Docker, Docker Compose, GitHub Actions and Jenkins.

## Features
- Add / edit / delete / search books (with copy tracking)
- Add / edit / delete / search members
- Issue a book (14-day loan), return a book, automatic fine for late returns (2 per day)
- Dashboard with totals and overdue count
- `/health` endpoint for health checks and monitoring

## Run locally (VS Code)
Open the folder in VS Code, open a terminal (Ctrl + `) and run:

```bash
python -m venv venv
# Windows:        venv\Scripts\activate
# macOS / Linux:  source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

## Run tests
```bash
pytest -v
```

## Run with Docker
```bash
docker compose up --build
```
Open http://localhost:5000 (data is kept in a Docker volume).

## CI/CD
- **GitHub Actions**: `.github/workflows/ci.yml` runs tests, then builds and pushes the Docker image.
  Add repo secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.
- **Jenkins**: `Jenkinsfile` has Checkout -> Test -> Build -> Push -> Deploy stages.
  Add a Jenkins credential with ID `dockerhub` and replace `YOUR_DOCKERHUB_USERNAME`.

## Project structure
```
library-management-system/
├── app.py              # Flask application (routes + logic)
├── schema.sql          # Database tables
├── templates/          # HTML pages (Jinja2)
├── static/style.css    # Styling
├── tests/test_app.py   # Automated tests (pytest)
├── Dockerfile
├── docker-compose.yml
├── Jenkinsfile
├── .github/workflows/ci.yml
├── requirements.txt
└── README.md
```
