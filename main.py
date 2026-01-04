import os
import uvicorn
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from youtube_transcript_api import YouTubeTranscriptApi
import re
from datetime import datetime
from google import genai
from fastapi import HTTPException
import json
from fastapi.responses import StreamingResponse
import httpx
from fastapi import Body
from groq import Groq
from tavily import TavilyClient
import yt_dlp
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

CRUMBS_PROJECT = 10
CRUMBS_RESEARCH = 25
CRUMBS_TRANSCRIPT = 5

# 1. Get your API Key (Render uses Environment Variables)
# Locally, you can set this in your terminal: export GEMINI_API_KEY='your_key'
ai_client = None

def get_video_title(url):
    print(f"🍞 [BREADCRUMB 1] Entering get_video_title for: {url}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True, # Only fetch metadata, don't process video
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("🍞 [BREADCRUMB 2] yt_dlp is now fetching metadata...")
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Untitled Video')
            print(f"🍞 [BREADCRUMB 3] Success! Found title: {title}")
            return title
    except Exception as e:
        print(f"🍞 [BREADCRUMB ERROR] Title fetch failed: {str(e)}")
        return "Untitled Video"

def add_crumbs(uid, amount):
    try:
        # Reference the user document
        user_ref = db.collection("users").document(uid)
        
        # .set with merge=True is the "Safe" way to do this
        user_ref.set({
            "crumbs": firestore.Increment(amount),
            "last_active": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        print(f"✨ [XP] Added {amount} crumbs to {uid}")
    except Exception as e:
        # This print ensures that even if XP fails, we know why, 
        # but we don't 'raise' the error so the main app keeps running.
        print(f"⚠️ [XP ERR] System glitch: {e}")

def get_ai_client():
    global ai_client
    # If the client hasn't been created yet, create it now
    if ai_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        print("api key =", api_key)
        if not api_key:
            return None
        
        # This is the point where initialization actually happens
        ai_client = genai.Client(api_key=api_key)
        print("🚀 Gemini Client initialized on first use!")
    
    return ai_client


# --- 1. FIREBASE INITIALIZATION ---
# Ensure your serviceAccountKey.json is in the same folder as main.py
# if not firebase_admin._apps:

#     cred = credentials.Certificate(os.getenv("SERVICE_ACC_KEY"))#

#     firebase_admin.initialize_app(cred)

# else:

#     firebase_admin.get_app()



# db = firestore.client()



# this is my existing code for initiation

# Get the absolute path to the directory where main.py is located
base_dir = os.path.dirname(os.path.abspath(__file__))
local_key_path = os.path.join(base_dir, "serviceAccountKey.json")

service_key_content = os.getenv("SERVICE_ACC_KEY")

if not firebase_admin._apps:
    if service_key_content:
        try:
            cleaned_json = service_key_content.strip().replace('\\n', '\n')
            cred_dict = json.loads(cleaned_json)
            if 'private_key' in cred_dict:
                cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
                
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized from Env Var!")
        except Exception as e:
            print(f"⚠️ Env Var failing, using file: {e}")
            # USE ABSOLUTE PATH HERE
            cred = credentials.Certificate(local_key_path)
            firebase_admin.initialize_app(cred)
    else:
        # USE ABSOLUTE PATH HERE
        cred = credentials.Certificate(local_key_path)
        firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. INITIALIZE APP & TEMPLATES ---
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows your Render URL to talk to your API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. THE FIRESTORE API ENDPOINTS (PRIORITY) ---
# We move these to the top so FastAPI matches these specific paths first
#dummy delete it later
@app.post("/ping")
async def ping():
    print("!!! PING RECEIVED !!!")
    return {"message": "pong"}
# CREATE: Saves a project to the specific user's folder

@app.post("/api/{uid}/projects")
@app.post("/api/{uid}/projects/") # Catch trailing slash
async def create_project(uid: str, request: Request):


    try:
        add_crumbs(uid, 10)
    except:
        pass
    # add_crumbs(uid, CRUMBS_PROJECT)

    print(f"--- 1. ENTERED FUNCTION for UID: {uid} ---") # Check if it even starts
    try:
        data = await request.json()
        print(f"--- 2. DATA UNPACKED: {data} ---") # Check if Handshake worked
        
        project_name = data.get("name")
        print(f"--- 3. NAME EXTRACTED: {project_name} ---") # Check for null values
        
        if not project_name:
             print("--- 3a. ERROR: No name provided! ---")
             return {"error": "No name provided"}, 400

        # This is where the Firebase interaction starts
        project_ref = db.collection("users").document(uid).collection("projects").document()
        print(f"--- 4. FIREBASE REF CREATED: {project_ref.id} ---") # Check Firebase connection
        
        database_payload = {
            "id": project_ref.id,
            "name": project_name,
            "createdAt": firestore.SERVER_TIMESTAMP 
        }
        
        project_ref.set(database_payload)
        print("--- 5. FIREBASE SAVE SUCCESSFUL ---") # Final confirmation
        
        return {"id": project_ref.id, "name": project_name}
        
    except Exception as e:
        print(f"--- ❌ CRASHED AT: {e} ---") # This tells you WHY
        raise HTTPException(status_code=500, detail=str(e))

# LIST: Fetches only the folders belonging to the logged-in UID
@app.get("/api/{uid}/projects/list")
@app.get("/api/{uid}/projects/list/") # Catch trailing slash
async def list_projects(uid: str):
    try:
        print(f"📂 FETCHING LIST: Request for UID: {uid}")
        docs = db.collection("users").document(uid).collection("projects").stream()
        
        projects_list = []
        for doc in docs:
            d = doc.to_dict()
            if 'createdAt' in d:
                del d['createdAt']
            projects_list.append(d)
            
        return {"projects": projects_list}
    except Exception as e:
        print(f"❌ LIST ERROR for user {uid}: {e}")
        return {"projects": []}

# GET ONE: Fetches specific project info
from fastapi import HTTPException
from datetime import datetime

@app.get("/api/{uid}/projects/{project_id}")
@app.get("/api/{uid}/projects/{project_id}/")
async def get_project_data(uid: str, project_id: str):

    try:

        doc_ref = db.collection("users").document(uid).collection("projects").document(project_id)

        doc = doc_ref.get()

       

        if doc.exists:

            d = doc.to_dict()

            if 'createdAt' in d:

                del d['createdAt']

            return d

        raise HTTPException(status_code=404, detail="Project not found")

    except Exception as e:

        print(f"❌ GET ERROR: {e}")

        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        print(f"❌ GET ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 4. AUTH GATE ---

@app.post("/verify-token")
async def verify_token(request: Request):
    data = await request.json()
    # Using 'uid' to match the key sent by login.html
    uid = data.get("uid", "guest_user")
    print(f"👤 AUTH VERIFIED: Received UID [{uid}]")
    
    return {
        "status": "success", 
        "uid": uid,
        "message": "Session verified"
    }

# --- 5. PAGE NAVIGATION ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("get_started.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/project_view/{project_id}", response_class=HTMLResponse)
async def project_view(request: Request, project_id: str):
    return templates.TemplateResponse("project_view.html", {
        "request": request,
        "project_id": project_id
    })

# --- 6. routes for projectview ---
# Note: Ensure your frontend fetch URL matches this structure
# @app.get("/api/projects/{project_id}")
# async def get_project(project_id: str):
#     # Search all users for this project or pass UID from frontend if preferred
#     # For now, let's assume a global project lookup or specific path
#     try:
#         # This is a simplified lookup. Ideally, you'd pass the UID too.
#         project_ref = db.collection_group("projects").where("id", "==", project_id).limit(1).get()
        
#         if not project_ref:
#             raise HTTPException(status_code=404, detail="Project not found")
            
#         return project_ref[0].to_dict()
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# 3. The Transcriber

# --- 7. Bookmarking --- remember this

@app.get("/api/{uid}/projects/{project_id}/bookmarks")
async def get_bookmarks(uid: str, project_id: str):
    # Match the same nested path
    bookmarks_ref = db.collection("users").document(uid)\
                      .collection("projects").document(project_id)\
                      .collection("bookmarks")
    
    docs = bookmarks_ref.stream()
    return {"bookmarks": [{"id": d.id, **d.to_dict()} for d in docs]}

@app.post("/api/{uid}/projects/{project_id}/bookmarks/toggle")
async def toggle_bookmark(uid: str, project_id: str, payload: dict):
    print(f"DEBUG [1]: Target User: {uid} | Project: {project_id}")
    
    url = payload.get("url")
    title = payload.get("title")

    try:
        # CORRECT PATH: users -> {uid} -> projects -> {project_id} -> bookmarks
        bookmarks_ref = db.collection("users").document(uid)\
                          .collection("projects").document(project_id)\
                          .collection("bookmarks")
        
        print(f"DEBUG [2]: Checking nested path for URL: {url}")
        
        # Check if URL exists in this specific project's bookmarks
        existing = bookmarks_ref.where("url", "==", url).limit(1).get()
        
        if len(existing) > 0:
            print(f"DEBUG [3]: Found existing. Removing from {project_id}...")
            bookmarks_ref.document(existing[0].id).delete()
            return {"status": "removed"}
        else:
            print(f"DEBUG [4]: Not found. Adding to {project_id}...")
            bookmarks_ref.add({
                "url": url,
                "title": title,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return {"status": "added"}

    except Exception as e:
        print(f"DEBUG [CRASH]: {str(e)}")
        return {"status": "error", "message": str(e)}





@app.post("/api/{uid}/projects/{project_id}/transcribe")
async def transcribe_video(uid: str, project_id: str, request: Request):
    print(f"📥 [BREADCRUMB] Transcribe request received for project: {project_id}")
    data = await request.json()
    video_url = data.get("url")

    # 1. Fetch Actual Video Title using yt-dlp
    actual_title = get_video_title(video_url)

    try:
        add_crumbs(uid, 30)
    except:
        pass
    
    # Extract YouTube Video ID using Regex
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_url)
    if not match:
        print("🍞 [BREADCRUMB ERROR] Invalid YouTube URL detected.")
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    video_id = match.group(1)

    try:
        print(f"🍞 [BREADCRUMB] Attempting to fetch transcript for ID: {video_id}")
        # 1. Fetch using the verified instance method
        ytt_api = YouTubeTranscriptApi()
        fetched_transcript = ytt_api.fetch(video_id)
        
        # Join snippets into one string
        full_text = " ".join([t.text for t in fetched_transcript])
        print("🍞 [BREADCRUMB] Transcript successfully joined.")

        # 2. Create the "Source" object
        # UPDATED: Replaced placeholder title with actual_title
        new_source = {
            "id": video_id,
            "url": video_url,
            "transcript": full_text,
            "title": actual_title, 
            "timestamp": datetime.now().isoformat() 
        }

        # 3. Update Firestore using ArrayUnion
        print("🍞 [BREADCRUMB] Updating Firestore ArrayUnion...")
        project_ref = db.collection("users").document(uid).collection("projects").document(project_id)
        project_ref.update({
            "sources": firestore.ArrayUnion([new_source])
        })

        print(f"✅ [BREADCRUMB] Success! Source added: {actual_title}")
        # Return the object so the frontend can add the squircle instantly
        return {"status": "success", "new_source": new_source}

    except Exception as e:
        print(f"❌ [BREADCRUMB ERROR] Transcribe Error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")      

# --- 7. Chatbot integration ---

# --- NEW CHAT ENDPOINT ---
@app.post("/api/{uid}/projects/{project_id}/chat")
async def chat_with_project(uid: str, project_id: str, request: Request):
    # STEP 0: Lazy Initialization
    client = get_ai_client()
    if not client:
        return {"response": "AI Assistant is offline."}

    data = await request.json()
    user_message = data.get("message")
    selected_ids = data.get("selectedIds", [])

    # STEP A: Context Retrieval (Selected Transcripts)
    project_ref = db.collection("users").document(uid).collection("projects").document(project_id)
    project_data = project_ref.get().to_dict()
    all_sources = project_data.get('sources', [])
    
    context_list = [s['transcript'] for s in all_sources if (s.get('id') or s.get('video_id')) in selected_ids]
    context_text = " ".join(context_list) if context_list else "No specific context selected."

    # STEP B: Memory (History) Formatting
    chat_docs = project_ref.collection("chats").order_by("timestamp").stream()
    history = []
    for doc in chat_docs:
        d = doc.to_dict()
        history.append({
            "role": "user" if d["role"] == "user" else "model",
            "parts": [{"text": d["text"]}]
        })

    # STEP C: Streaming Generator
    async def generate_stream():

        system_rules = """
            You are a Research Assistant for Cherseta Studio. Your name is Chersey
            When answering, use the following citation rules:
            1. If the information is found in the provided 'Context' (the video transcript), 
            append to the sentence.
            2. If the information is from your own general knowledge, append.
            3. If you are combining both, use.
            4. Always prioritize facts from the 'Context' over your own memory.
            """
        full_response = ""
        try:
            # We bundle history + current message into one 'contents' list
            # Note: gemini-2.5-flash is correct for Dec 2025
            response_stream = client.models.generate_content_stream(
                model="gemini-2.5-flash-lite", 
                contents=history + [{
                    "role": "user", 
                    "parts": [{"text": f"System instructions : {system_rules}\n\nContext: {context_text}\n\nQuestion: {user_message}"}]
                }]
            )

            for chunk in response_stream:
                if chunk.text:
                    full_response += chunk.text
                    # Standard SSE format: data: {...}\n\n
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"
            
            # STEP D: Save once the loop finishes successfully
            project_ref.collection("chats").add({
                "role": "user", "text": user_message, "timestamp": firestore.SERVER_TIMESTAMP
            })
            project_ref.collection("chats").add({
                "role": "model", "text": full_response, "timestamp": firestore.SERVER_TIMESTAMP
            })

        except Exception as e:
            print(f"❌ Streaming Error: {e}")
            yield f"data: {json.dumps({'text': chunk.text})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")

@app.get("/api/{uid}/projects/{project_id}/chats")
async def get_all_chats(uid: str, project_id: str):
    """
    Fetches every message document from the 'chats' sub-collection 
    inside a specific project for a specific user.
    """
    try:
        # Path: users -> {uid} -> projects -> {project_id} -> chats
        project_ref = db.collection("users").document(uid).collection("projects").document(project_id)
        
        # We target the 'chats' collection and order by timestamp to keep the flow correct
        chat_docs = project_ref.collection("chats").order_by("timestamp").stream()

        history = []
        for doc in chat_docs:
            d = doc.to_dict()
            history.append({
                "role": d.get("role", "user"), # Defaults to 'user' if role is missing
                "text": d.get("text", ""),
                "timestamp": str(d.get("timestamp", "")) # Convert to string for JSON safety
            })

        print(f"📦 [DB] Successfully loaded {len(history)} messages from chats collection.")
        return {"history": history}

    except Exception as e:
        print(f"❌ [DB ERROR] History fetch failed: {e}")
        # Return an empty list so the frontend doesn't crash
        return {"history": []}


@app.post("/api/{uid}/projects/{project_id}/notes")
async def update_notes(uid: str, project_id: str, data: dict):
    # Locate the specific project in your Firestore hierarchy
    # (Matches the structure we set up: users -> {uid} -> projects -> {id})
    project_ref = db.collection("users").document(uid).collection("projects").document(project_id)
    
    try:
        # We use .update() so we don't accidentally delete the transcript or video data
        project_ref.update({
            "notes_html": data.get("content", ""),
            "notes_title": data.get("title", "Untitled Note"),
            "updated_at": datetime.now()
        })
        return {"status": "success"}
    except Exception as e:
        print(f"❌ Firebase Error: {e}")
        return {"status": "error", "message": str(e)}

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
PARENT_PAGE_ID = os.getenv("PARENT_PAGE_ID")

@app.post("/api/export/notion")
async def export_to_notion(payload: dict = Body(...)):
    title = payload.get("title", "Chersey Research Log")
    content = payload.get("content", "")

    # Headers required by Notion
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # Structure the Notion page with a title and a paragraph block
    notion_data = {
        "parent": { "page_id": PARENT_PAGE_ID },
        "properties": {
            "title": {
                "title": [{"text": {"content": title}}]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": content}}]
                }
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/pages", 
            headers=headers, 
            json=notion_data
        )
        return response.json()


# --- 8. Deep Research Agent ---
groq_client = Groq(api_key= os.getenv("GROQ_API_KE"))
tavily_client = TavilyClient(api_key= os.getenv("TAVILY_API_KEY"))

@app.post("/api/research/agent")
async def generate_research(payload: dict = Body(...)):

    uid = payload.get("uid") 
    
    # ... your existing AI research logic ...
    
    # 2. Research Complete! Add 25 Crumbs
    if uid:
        try:
            add_crumbs(uid, 15)
        except:
            pass

    context_text = payload.get("text", "")
    
    if not context_text.strip():
        # Fallback query if no context is provided to prevent Tavily crash
        return {"results": []}

    try:
        
        # 1. Groq generates 3 targeted queries with a strict System Prompt
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a research assistant. Output ONLY search queries, one per line. No numbers, no intro, no chatter."
                },
                {
                    "role": "user", 
                    "content": f"Generate 3 deep-dive search queries for this text:\n\n{context_text[:4000]}"
                }
            ],
            temperature=0.3 # Lower temperature for more consistent formatting
        )
        
        raw_output = completion.choices[0].message.content.strip()
        
        # --- THE SANITIZER ---
        # 1. Split by newline
        # 2. Use regex to remove "1. ", "2) ", etc.
        # 3. Filter out any empty strings to satisfy Tavily
        queries = []
        for line in raw_output.split('\n'):
            clean_line = re.sub(r'^\d+[\.\)\-\s]+', '', line).strip() 
            if clean_line:
                queries.append(clean_line)

        # 2. Tavily searches for each query (Top 3 each = 9 total)
        final_results = []
        for query in queries[:3]:
            print(f"🚀 [AGENT] Searching for: {query}")
            print(os.getenv("TAVILY_API_KEY"))
            try:
                # Basic depth is faster for hackathon speed
                search = tavily_client.search(query=query, search_depth="basic", max_results=3)
                if "results" in search:
                    final_results.extend(search['results'])
            except Exception as e:
                print(f"⚠️ [TAVILY SKIP] Query '{query}' failed: {e}")

        return {"results": final_results}

    except Exception as e:
        print(f"🔥 [CRASH] Research Agent Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# CRUMBSSSS

# def calculate_level(total_crumbs):
#     # Level 1: 0-99, Level 2: 100-249, Level 3: 250-499, etc.
#     if total_crumbs < 100: return "LIL BIT OF CRUMBS"
#     if total_crumbs < 250: return "CRUMB!"
#     if total_crumbs < 500: return "YAYY WE HAVE MORE CRUMBS"
#     return "LOTTA CRUMBS"

def calculate_level(crumbs):
    if crumbs <= 0: return "Starved"
    if crumbs < 100: return "Newbie"
    if crumbs < 300: return "Bread Maker"
    return "Master Chef"

@app.get("/api/users/{uid}/xp")
async def get_user_xp(uid: str):
    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return {"crumbs": 0, "level": "Newbie", "status": "dead"}

    data = user_doc.to_dict()
    crumbs = data.get("crumbs", 0)
    last_active = data.get("last_active") # Should be a Firestore Timestamp or ISO string

    # --- CRUMBS DECAY LOGIC ---
    if last_active:
        # 1. Parse the last active time
        if isinstance(last_active, str):
            last_time = datetime.fromisoformat(last_active)
        else:
            # If it's a Firestore Timestamp object
            last_time = last_active 

        # 2. Calculate time passed in hours
        now = datetime.now(timezone.utc)
        time_diff = now - last_time
        hours_passed = time_diff.total_seconds() / 3600
        
        # 3. Calculate decay (5 crumbs per hour)
        decay = int(hours_passed * 5)
        
        if decay > 0:
            # Subtract decay but allow it to hit 0 or slightly below for 'dead' state
            crumbs = max(-1, crumbs - decay)
            
            # Update database with new decayed value and reset last_active to 'now'
            # to prevent decay from compounding on every single refresh
            user_ref.update({
                "crumbs": crumbs,
                "last_active": firestore.SERVER_TIMESTAMP
            })

    # Determine mascot state
    status = "alive" if crumbs > 0 else "dead"

    return {
        "crumbs": crumbs,
        "level": calculate_level(crumbs),
        "status": status
    }

@app.delete("/api/{uid}/projects/{project_id}")
async def delete_project(uid: str, project_id: str):
    try:
        # Reference the specific project document
        project_ref = db.collection("users").document(uid).collection("projects").document(project_id)
        
        # Delete the document
        project_ref.delete()
        
        return {"status": "success", "message": f"Project {project_id} deleted."}
    except Exception as e:
        print(f"Error deleting project: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")



# --- Final. START THE ENGINE ---
if __name__ == "__main__":
# import uvicorn
#     import os
    # MANDATORY: Render sets the 'PORT' environment variable
    port = int(os.environ.get("PORT", 10000))
    # MANDATORY: host must be 0.0.0.0 for external access
    uvicorn.run("main:app", host="0.0.0.0", port=port)