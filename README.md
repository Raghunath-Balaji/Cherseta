# Cherseta
Cherseta is a tool that unifies all that a curious learner needs to ensure a frictionless learning experience through agentic AI usage and RAG implementation

Cherseta Studio is a high-performance research platform that combines the reasoning power of **Gemini 2.0**, the speed of **Groq (Llama 3.1)**, and live web intelligence via **Tavily**. 

## 🚀 Features
- **Deep Research Agent:** Multi-step web analysis using Tavily and Llama-3.1.
- **YouTube Intelligence:** Automatic transcript extraction and AI summarization.
- **Notion Integration:** One-click "Sync to Workspace" for all research findings.
- **Crumbs System:** A built-in credit system managed via Firebase Firestore.
- **Dynamic Mascot:** Interactive AI companion that reacts to system states.

## 🛠️ Tech Stack
- **Backend:** FastAPI (Python 3.10+)
- **AI:** Google GenAI, Groq SDK
- **Database/Auth:** Firebase (Admin SDK & Firestore)
- **Frontend:** Jinja2 Templates, Tailwind CSS

## 📦 Installation & Setup
1. Clone the repo: `git clone https://github.com/YOUR_USERNAME/cherseta.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with your API keys (see `.env.example`).
4. Run locally: `uvicorn main:app --reload`

## 📄 License
This project is licensed under the MIT License.
