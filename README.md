# nexus

Nexus is a full-stack application with a Python backend and a React + TypeScript frontend powered by Vite.

## Project Structure

```text
nexus/
├── .github/                      # CI workflows (add later)
├── backend/
│   ├── src/
│   │   └── nexus/
│   │       ├── __init__.py
│   │       └── main.py
│   ├── tests/                    # Add when implementation begins
│   └── pyproject.toml
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── docs/                         # Add as documentation grows
├── .editorconfig
├── .gitignore
└── README.md
```

## Getting Started

### Backend
Navigate to the backend directory:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
python -m nexus.main
```

### Frontend
Navigate to the frontend directory:
```bash
cd frontend
npm install
npm run dev
```
