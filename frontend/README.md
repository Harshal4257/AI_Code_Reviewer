# AI Code Reviewer

AI-powered Python code reviewer using Groq LLaMA-3 — finds bugs, security issues and fixes them instantly.

## Features

- 🔴 **Security Detection** — finds vulnerabilities like hardcoded secrets, SQL injection, unsafe eval
- 🟡 **Bug Detection** — catches logic errors, runtime crashes, bad practices
- 🔵 **Code Quality** — suggests improvements for cleaner, better code
- ✨ **One-Click Fix** — apply all AI-suggested fixes with a single click

## How to Use

1. Open any `.py` file
2. Click the **▶ AI: Review Code** button in the editor toolbar (or open Command Palette → `AI: Review Code`)
3. View issues highlighted with color-coded severity
4. Click **Quick Fix** → **Apply AI Fix** to fix the entire file

## Color Coding

| Color | Meaning |
|---|---|
| 🔴 Red | Security vulnerabilities |
| 🟡 Yellow | Logic bugs, runtime errors |
| 🔵 Blue | Code quality, style suggestions |

## Settings

| Setting | Description | Default |
|---|---|---|
| `aiReviewer.backendUrl` | Backend API URL | `https://your-app-name.onrender.com` |

## Tech Stack

- **Frontend:** VS Code Extension (TypeScript)
- **Backend:** FastAPI (Python)
- **AI Model:** Groq LLaMA-3 70B
- **Analysis:** AST + Pylint + Bandit + Radon + AI Deep Analysis

## License

MIT