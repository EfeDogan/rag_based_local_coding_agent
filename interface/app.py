import os 
import sys 
import shutil 
import json 
import threading 
from pathlib import Path 

# Proje ana dizinini Python yoluna garanti olarak ekle 
ROOT_DIR = Path(__file__).resolve().parent.parent 
if str(ROOT_DIR) not in sys.path: 
    sys.path.insert(0, str(ROOT_DIR)) 

import glob 
import requests 
from uuid import uuid4 
from typing import Any, List 
from dotenv import load_dotenv 

import streamlit as st 

# LangChain & LangGraph 
from langchain_core.tools import tool 
from langchain_core.messages import SystemMessage, RemoveMessage, HumanMessage, AIMessage, ToolMessage 
from langgraph.checkpoint.memory import MemorySaver 
from langchain.agents import create_agent 
from langchain_ollama import ChatOllama 
from langchain_core.runnables import RunnableConfig 

# Mevcut modüller 
from qdrant_pipeline.qdrant_main import get_client 
from prompts.prompts2 import SYSTEM_PROMPT 
from token_tracker.base_callback_handler import TokenTrackerHandler 

# --- 1. ÇEVRE DEĞİŞKENLERİ VE DİZİN AYARLARI --- 
load_dotenv() 
OLLAMA_URL = os.getenv("OLLAMA_URL") 
EMBED_URL = os.getenv("EMBED_URL") 
ORNITH_URL = os.getenv("ORNITH_URL") 
SESSION_PATH = os.getenv("SESSION_PATH", "/tmp/RagLLM") 

st.set_page_config( 
    page_title="RAG Agent Chatbot", 
    page_icon="🤖", 
    layout="wide" 
) 

# --- 2. DİNAMİK TOOL TANIMLARI --- 
@tool 
def create_file(file_name: str, content: str, config: RunnableConfig) -> str: 
    """ 
    Belirtilen metin, kod veya içeriği verilen dosya adıyla diske kaydeder. 
     
    Args: 
        file_name: Kaydedilecek dosyanın adı (Örn: 'app.py', 'script.js', 'analiz.txt'). 
        content: Dosyanın içine yazılacak tam kod veya metin içeriği. 
    """ 
    configurable = config.get("configurable", {}) 
    session_id = configurable.get("thread_id") 
     
    if not session_id: 
        session_id = st.session_state.get("current_session_id") 

    if not session_id: 
        return "HATA: Aktif bir session ID bulunamadı." 

    file_name = Path(file_name).name 
    folder_path = Path(SESSION_PATH) / str(session_id) 
     
    try: 
        folder_path.mkdir(parents=True, exist_ok=True) 
        file_path = folder_path / file_name 

        with open(file_path, "w", encoding="utf-8") as f: 
            f.write(str(content)) 
             
        print(f"[SUCCESS] Dosya yazıldı: {file_path.resolve()}") 
        return f"BAŞARILI: '{file_name}' dosyası '{folder_path}' konumuna kaydedildi." 

    except Exception as e: 
        print(f"[ERROR] Dosya yazma hatası: {str(e)}") 
        return f"HATA: Dosya oluşturulurken bir hata oluştu: {str(e)}" 

@tool 
def update_query(user_question: str) -> str: 
    """Daha iyi cevap verebilmek için kullanıcının sorduğu soruda iyileştirmeler yapar.""" 
    return "" 

@tool 
def search_codebase(new_question: str, limit: int) -> str: 
    """Kod tabanında (Qdrant) kullanıcının sorusuyla eşleşen ilgili kodları ve dokümanları arar.""" 
    client = get_client() 
    response = requests.post( 
        EMBED_URL, 
        json={"model": "qwen3-embedding:0.6b", "input": new_question} 
    ) 
    query_vector = response.json()["embeddings"][0] 
    context = [] 
    hits = client.query_points( 
        collection_name="codebase", 
        query=query_vector, 
        limit=limit 
    ).points 

    for hit in hits: 
        if hit.score > 0.4: 
            context.append(str(hit.payload)) 
            context.append(f'Score: {hit.score:.3f}') 
            context.append("=" * 60) 
         
    return "\n".join(context) 

# --- 3. AGENT VE MODEL BİLEŞENLERİ --- 
@st.cache_resource 
def init_agent(): 
    tools = [search_codebase, update_query, create_file] 

    llm = ChatOllama( 
        base_url=OLLAMA_URL, 
        model="glm-5.2:cloud", 
        temperature=0.4, 
        num_ctx=1000000, 
        verbose=True 
    ) 

    checkpointer = MemorySaver() 

    agent_executor = create_agent( 
        model=llm, 
        tools=tools, 
        system_prompt=SYSTEM_PROMPT, 
        checkpointer=checkpointer 
    ) 
     
    return agent_executor, llm 

agent_executor, llm = init_agent() 

# --- 4. YARDIMCI FONKSİYONLAR VE BAŞLIK/GEÇMİŞ YÖNETİMİ --- 

def create_ornith(): 
    """Streamlit içinde konu başlığı belirlemek için bu modeli kullan""" 
    llm = ChatOllama( 
        base_url=OLLAMA_URL, 
        model="ornith:35b", 
        temperature=0.4, 
        num_ctx=32000, 
    ) 
    return llm 

def generate_session_title(user_message: str) -> str: 
    """Kullanıcının ilk mesajından Ornith modeli ile kısa bir sohbet başlığı üretir.""" 
    try: 
        ornith_llm = create_ornith() 
        prompt = ( 
            "Aşağıdaki kullanıcı mesajına göre bu sohbet için 3-5 kelimelik kısa, net " 
            "ve açıklayıcı bir başlık oluştur. Sadece başlığı yaz, tırnak işareti veya ek açıklama kullanma.\n\n" 
            f"Kullanıcı Mesajı: {user_message}" 
        ) 
        response = ornith_llm.invoke(prompt) 
        return response.content.strip().replace('"', '') 
    except Exception as e: 
        print(f"[ERROR] Başlık üretilirken hata: {e}") 
        return user_message[:20] + "..." 

def get_session_title(session_id: str) -> str: 
    """Session klasöründeki title.txt dosyasını okur, yoksa ID'nin ilk 8 karakterini döner.""" 
    title_file = os.path.join(SESSION_PATH, str(session_id), "title.txt") 
    if os.path.exists(title_file): 
        try: 
            with open(title_file, "r", encoding="utf-8") as f: 
                return f.read().strip() 
        except Exception: 
            pass 
    return f"💬 {session_id[:8]}..." 

def save_session_title(session_id: str, title: str): 
    """Üretilen başlığı session klasörüne title.txt olarak kaydeder.""" 
    folder_path = os.path.join(SESSION_PATH, str(session_id)) 
    os.makedirs(folder_path, exist_ok=True) 
    title_file = os.path.join(folder_path, "title.txt") 
    with open(title_file, "w", encoding="utf-8") as f: 
        f.write(title) 

def get_existing_sessions(): 
    if not os.path.exists(SESSION_PATH): 
        os.makedirs(SESSION_PATH, exist_ok=True) 
        return [] 
    return sorted([d for d in os.listdir(SESSION_PATH) if os.path.isdir(os.path.join(SESSION_PATH, d))]) 

def delete_session(session_id: str): 
    folder_path = os.path.join(SESSION_PATH, str(session_id)) 
    if os.path.exists(folder_path): 
        shutil.rmtree(folder_path) 

# --- MESAJLARI DİSKE KAYDETME VE YÜKLEME FONKSİYONLARI ---
def save_messages_to_disk(session_id: str, messages: List[Any]):
    """LangGraph mesaj nesnelerini session klasörüne history.json olarak kaydeder."""
    folder_path = os.path.join(SESSION_PATH, str(session_id))
    os.makedirs(folder_path, exist_ok=True)
    history_file = os.path.join(folder_path, "history.json")
    
    serialized_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            serialized_messages.append({"type": "human", "content": msg.content, "id": getattr(msg, "id", None)})
        elif isinstance(msg, AIMessage):
            serialized_messages.append({
                "type": "ai", 
                "content": msg.content, 
                "id": getattr(msg, "id", None),
                "tool_calls": getattr(msg, "tool_calls", [])
            })
        elif isinstance(msg, ToolMessage):
            serialized_messages.append({
                "type": "tool", 
                "content": msg.content, 
                "id": getattr(msg, "id", None),
                "name": getattr(msg, "name", "tool"),
                "tool_call_id": getattr(msg, "tool_call_id", None)  # <-- tool_call_id eklendi
            })
        elif isinstance(msg, SystemMessage):
            serialized_messages.append({"type": "system", "content": msg.content, "id": getattr(msg, "id", None)})

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(serialized_messages, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Geçmiş diske kaydedilemedi: {e}")

def load_messages_from_disk(session_id: str, config: dict):
    """Diskte kayıtlı history.json dosyasını okur hem LangGraph state'ine yükler hem nesne olarak döner."""
    folder_path = os.path.join(SESSION_PATH, str(session_id))
    history_file = os.path.join(folder_path, "history.json")
    
    if not os.path.exists(history_file):
        return []
        
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            serialized_messages = json.load(f)
            
        restored_messages = []
        for item in serialized_messages:
            m_type = item.get("type")
            content = item.get("content", "")
            m_id = item.get("id")
            
            if m_type == "human":
                restored_messages.append(HumanMessage(content=content, id=m_id))
            elif m_type == "ai":
                tool_calls = item.get("tool_calls", [])
                restored_messages.append(AIMessage(content=content, id=m_id, tool_calls=tool_calls))
            elif m_type == "tool":
                name = item.get("name", "tool")
                tool_call_id = item.get("tool_call_id")  # <-- tool_call_id okunuyor
                restored_messages.append(ToolMessage(content=content, id=m_id, name=name, tool_call_id=tool_call_id))
            elif m_type == "system":
                restored_messages.append(SystemMessage(content=content, id=m_id))
                
        if restored_messages:
            # LangGraph hafızasını da doldur
            current_state_msgs = agent_executor.get_state(config).values.get("messages", [])
            if not current_state_msgs:
                agent_executor.update_state(config, {"messages": restored_messages})
                
        return restored_messages
    except Exception as e:
        print(f"[ERROR] Geçmiş diskten yüklenemedi: {e}")
        
    return []

def load_session_context(session_id: str, config: dict): 
    folder_path = os.path.join(SESSION_PATH, str(session_id)) 
    files = sorted(glob.glob(os.path.join(folder_path, "CONTEXT*.md"))) 
    if not files: 
        return 
     
    contents = {} 
    for file_path in files: 
        with open(file_path, "r", encoding="utf-8") as f: 
            contents[file_path] = f.read() 

    formatted_contents = "\n\n".join([f"--- {os.path.basename(dosya)} ---\n{icerik}" for dosya, icerik in contents.items()]) 
     
    context_message = SystemMessage( 
        content=f"Aşağıdaki Markdown belgesi/belgeleri bu sohbetin geçmiş özetidir ve temel bağlamıdır:\n\n{formatted_contents}" 
    ) 
    agent_executor.update_state(config, {"messages": [context_message]}) 

def run_compaction(memory_text: str, session_id: str, config: dict): 
    compaction_instr = "" 
    if os.path.exists("compaction.md"): 
        with open("compaction.md", 'r', encoding='utf-8') as f: 
            compaction_instr = f.read() 
             
    compaction_prompt = ( 
        f"{compaction_instr}\n\n" 
        f"--- ÖZETLENECEK SOHBET GEÇMİŞİ VE DÖKÜMANLAR ---\n" 
        f"{memory_text}" 
    ) 
    response = llm.invoke(compaction_prompt) 

    folder_path = os.path.join(SESSION_PATH, str(session_id)) 
    os.makedirs(folder_path, exist_ok=True) 
     
    files = sorted(glob.glob(os.path.join(folder_path, "CONTEXT*.md"))) 
    contextmd_count = len(files) 
    file_path = os.path.join(folder_path, f"CONTEXT{contextmd_count}.md") 

    with open(file_path, 'w', encoding='utf-8') as f: 
        f.write(response.content) 
     
    current_state = agent_executor.get_state(config) 
    existing_messages = current_state.values.get("messages", []) 
     
    if existing_messages: 
        KEEP_LAST_N = 6 
        messages_to_delete = existing_messages[:-KEEP_LAST_N] if len(existing_messages) > KEEP_LAST_N else [] 
         
        if messages_to_delete: 
            delete_actions = [RemoveMessage(id=m.id) for m in messages_to_delete if hasattr(m, 'id') and m.id] 
            agent_executor.update_state(config, {"messages": delete_actions}) 

    load_session_context(session_id, config) 
    
    latest_state = agent_executor.get_state(config)
    save_messages_to_disk(session_id, latest_state.values.get("messages", []))
    
    st.toast(f"Compaction çalıştırıldı! `CONTEXT{contextmd_count}.md` kaydedildi.", icon="🧹") 

# --- 5. SOL SIDEBAR (OTURUM YÖNETİMİ) --- 
st.sidebar.title("💬 Sohbet Geçmişi") 

if st.sidebar.button("➕ Yeni Sohbet Başlat", use_container_width=True): 
    new_id = str(uuid4()) 
    os.makedirs(os.path.join(SESSION_PATH, new_id), exist_ok=True) 
    st.session_state["current_session_id"] = new_id 
    st.rerun() 

sessions = get_existing_sessions() 

if "current_session_id" not in st.session_state or st.session_state["current_session_id"] not in sessions: 
    if sessions: 
        st.session_state["current_session_id"] = sessions[-1] 
    else: 
        new_id = str(uuid4()) 
        os.makedirs(os.path.join(SESSION_PATH, new_id), exist_ok=True) 
        st.session_state["current_session_id"] = new_id 
        sessions = [new_id] 

st.sidebar.markdown("---") 
st.sidebar.subheader("Kayıtlı Oturumlar") 

for sess_id in sessions: 
    col_sess_btn, col_del_btn = st.sidebar.columns([0.8, 0.2]) 
     
    is_active = (sess_id == st.session_state["current_session_id"]) 
    session_title = get_session_title(sess_id) 
    label = f"👉 {session_title}" if is_active else session_title 
     
    if col_sess_btn.button(label, key=f"select_{sess_id}", use_container_width=True, type="primary" if is_active else "secondary"): 
        st.session_state["current_session_id"] = sess_id 
        st.rerun() 
         
    if col_del_btn.button("🗑️", key=f"del_{sess_id}", help="Oturumu sil"): 
        delete_session(sess_id) 
        if st.session_state["current_session_id"] == sess_id: 
            del st.session_state["current_session_id"] 
        st.toast(f"Oturum silindi!", icon="🗑️") 
        st.rerun() 

active_session_id = st.session_state["current_session_id"] 
config = {"configurable": {"thread_id": active_session_id}} 

# --- 6. SAYFA DÜZENİ VE SABİT İKİ KOLON --- 
file_ratio = 0.35  
chat_ratio = 1.0 - file_ratio 
col_chat, col_files = st.columns([chat_ratio, file_ratio], gap="large") 

# === SOL / ORTA TARAF: SOHBET EKRANI === 
with col_chat: 
    st.title("🤖 Codebase RAG & Agent") 
    st.caption(f"Aktif Session ID: `{active_session_id}`") 

    # 1. Önce LangGraph state'ine bak, boşsa diskten (history.json) yükle
    current_state = agent_executor.get_state(config) 
    messages = current_state.values.get("messages", []) 

    if not messages: 
        messages = load_messages_from_disk(active_session_id, config)
        if not messages:
            load_session_context(active_session_id, config) 
            current_state = agent_executor.get_state(config) 
            messages = current_state.values.get("messages", []) 

    # 2. Dahili Geçmişi Ekrana Bas (System mesajlarını filtreleyerek kullanıcı/asistan/tool akışını göster)
    for msg in messages: 
        if isinstance(msg, HumanMessage): 
            with st.chat_message("user"): 
                st.markdown(msg.content) 
        elif isinstance(msg, AIMessage): 
            if msg.tool_calls: 
                for tool_call in msg.tool_calls: 
                    with st.status(f"⚙️ Tool Çağrıldı: `{tool_call['name']}`", state="complete"): 
                        st.json(tool_call['args']) 
            if msg.content: 
                with st.chat_message("assistant"): 
                    st.markdown(msg.content) 
        elif isinstance(msg, ToolMessage): 
            with st.status(f"📄 Tool Yanıtı ({msg.name})", state="complete"): 
                st.text(f"{str(msg.content)}") 

# Girdi Kutusu Her Zaman En Altta Durur 
if user_input := st.chat_input("Bir soru sorun veya dosya oluşturmasını isteyin..."): 
    if user_input.strip() == "/compact": 
        human_msg = HumanMessage(content="/compact") 
        agent_executor.update_state(config, {"messages": [human_msg]}) 

        with st.status("compaction.md çalıştırılıyor...", expanded=True) as status: 
            latest_state = agent_executor.get_state(config) 
            latest_messages = latest_state.values.get("messages", []) 
            memory_text = "".join([f"[{i}] {m.__class__.__name__}: {m.content}\n" for i, m in enumerate(latest_messages)]) 
            
            run_compaction(memory_text=memory_text, session_id=active_session_id, config=config) 
            
            folder_path = os.path.join(SESSION_PATH, str(active_session_id)) 
            files = sorted(glob.glob(os.path.join(folder_path, "CONTEXT*.md"))) 
            latest_context_file = os.path.basename(files[-1]) if files else "CONTEXT.md" 

            status.update(label=f"`{latest_context_file}` başarıyla oluşturuldu.", state="complete", expanded=False) 

        success_content = f"🧹 **Compaction başarıyla tamamlandı!** Sohbet geçmişi özetlendi ve `{latest_context_file}` olarak diske kaydedildi."
        ai_msg = AIMessage(content=success_content) 
        agent_executor.update_state(config, {"messages": [ai_msg]}) 
         
        latest_state = agent_executor.get_state(config)
        save_messages_to_disk(active_session_id, latest_state.values.get("messages", []))
         
        st.rerun()
         
    else: 
        token_tracker = TokenTrackerHandler() 
        
        # Başlık oluşturma mantığı (Eğer yoksa arka planda (thread ile) hızlıca oluşturulur)
        title_file_path = os.path.join(SESSION_PATH, str(active_session_id), "title.txt")
        if not os.path.exists(title_file_path): 
            # İlk etapta geçici bir başlık atayalım ki arayüz hemen güncellenebilsin
            save_session_title(active_session_id, f"💬 {user_input[:20]}...")
            
            # Gerçek başlığı arka planda (thread içinde) üretelim ki kullanıcıyı bekletmesin
            def background_title_generation(sess_id, text):
                try:
                    new_title = generate_session_title(text) 
                    save_session_title(sess_id, f"💬 {new_title}")
                except Exception as e: 
                    print(f"Arka planda başlık oluşturulamadı: {e}")

            threading.Thread(
                target=background_title_generation, 
                args=(active_session_id, user_input), 
                daemon=True
            ).start()

        with st.chat_message("user"): 
            st.markdown(user_input) 

        with st.chat_message("assistant"): 
                with st.status("🤖 Agent düşünüyor ve çalışıyor...", expanded=True) as resp_status: 
                    event_stream = agent_executor.stream( 
                        {"messages": [("human", user_input)]}, 
                        config={**config, "callbacks": [token_tracker]}, 
                        stream_mode="values" 
                    ) 

                    for event in event_stream: 
                        latest_msg = event["messages"][-1] 

                        if isinstance(latest_msg, AIMessage) and latest_msg.tool_calls: 
                            for tool_call in latest_msg.tool_calls: 
                                resp_status.update(label=f"⚙️ Tool Çalıştırılıyor: `{tool_call['name']}`", state="running") 
                         
                        elif isinstance(latest_msg, ToolMessage): 
                            resp_status.update(label=f"📄 Tool Yanıtı Alındı: `{latest_msg.name}`", state="running") 

                    resp_status.update(label="Yanıt tamamlandı.", state="complete", expanded=False) 

                latest_state = agent_executor.get_state(config) 
                latest_messages = latest_state.values.get("messages", []) 
                
                # Mesajları hemen diske kaydet
                save_messages_to_disk(active_session_id, latest_messages)

                if latest_messages and isinstance(latest_messages[-1], AIMessage) and latest_messages[-1].content: 
                    st.markdown(latest_messages[-1].content) 

        if token_tracker.prompt_eval_count >= 750000: 
            memory_text = "".join([f"[{i}] {m.__class__.__name__}: {m.content}\n" for i, m in enumerate(latest_messages)]) 
            run_compaction(memory_text=memory_text, session_id=active_session_id, config=config) 
             
        st.rerun() 

# --- SAĞ PANEL ÖZEL CSS --- 
st.markdown(""" 
    <style> 
        [data-testid="column"]:nth-child(2) { 
            position: sticky; 
            top: 2rem; 
            align-self: flex-start; 
            max-height: calc(100vh - 4rem); 
            padding-right: 10px; 
        } 
         
        .file-scroll-container { 
            max-height: 500px; 
            overflow-y: auto; 
            border: 1px solid rgba(250, 250, 250, 0.15); 
            border-radius: 8px; 
            padding: 15px; 
            background-color: rgba(255, 255, 255, 0.02); 
            margin-bottom: 10px; 
        } 

        .stCodeBlock { 
            max-height: 450px; 
            overflow-y: auto; 
        } 
    </style> 
""", unsafe_allow_html=True) 

# === SAĞ TARAF: DOSYA PANELİ VE TAM EKRAN MODALI === 
if col_files: 
    with col_files: 
        with st.expander("📂 Session Dosya Paneli", expanded=True): 
            session_folder = os.path.join(SESSION_PATH, active_session_id) 
             
            if os.path.exists(session_folder): 
                all_files = sorted([f for f in os.listdir(session_folder) if f not in ["title.txt", "history.json"]]) 
                 
                if all_files: 
                    st.caption(f"📁 Toplam **{len(all_files)}** dosya mevcut.") 
                     
                    selected_file_key = f"selected_file_{active_session_id}" 
                    if selected_file_key not in st.session_state or st.session_state[selected_file_key] not in all_files: 
                        st.session_state[selected_file_key] = all_files[0] 

                    with st.popover("🗂️ Dosya Seçin", use_container_width=True): 
                        for file_name in all_files: 
                            f_path = os.path.join(session_folder, file_name) 
                            f_size = os.path.getsize(f_path) 
                             
                            ext = file_name.split(".")[-1].lower() if "." in file_name else "" 
                            icon = "🐍" if ext == "py" else "📝" if ext in ["txt", "md"] else "⚙️" if ext in ["json", "yaml"] else "📄" 
                             
                            is_selected = (file_name == st.session_state[selected_file_key]) 
                            btn_label = f"{'👉 ' if is_selected else ''}{icon} {file_name} ({f_size} B)" 
                             
                            if st.button(btn_label, key=f"file_btn_{file_name}", use_container_width=True, type="primary" if is_selected else "secondary"): 
                                st.session_state[selected_file_key] = file_name 
                                st.rerun() 

                    selected_file = st.session_state[selected_file_key] 
                    file_path = os.path.join(session_folder, selected_file) 
                    ext = selected_file.split(".")[-1].lower() if "." in selected_file else "" 

                    st.subheader(f"📄 `{selected_file}`") 

                    try: 
                        with open(file_path, "r", encoding="utf-8") as f: 
                            file_content = f.read() 

                        if ext in ["md", "txt", "markdown"]: 
                            tab_preview, tab_raw = st.tabs(["👁️ Önizleme", "💻 Ham Metin"]) 
                            with tab_preview: 
                                st.markdown(f"<div class='file-scroll-container'>{file_content}</div>", unsafe_allow_html=True) 
                            with tab_raw: 
                                with st.container(height=400): 
                                    st.code(file_content, language="markdown") 

                        elif ext in ["py", "json", "js", "html", "css", "cpp", "c", "sh", "sql"]: 
                            with st.container(height=400): 
                                st.code(file_content, language=ext, line_numbers=True) 

                        else: 
                            st.text_area("İçerik:", file_content, height=400) 

                        @st.dialog(f"🔍 Dosya Detayı: {selected_file}", width="large") 
                        def open_file_modal(f_name, f_content, f_ext): 
                            st.caption(f"Tam ekran modunda inceleniyor: `{f_name}`") 
                            m_tab1, m_tab2 = st.tabs(["📋 İçeriği Görüntüle", "🛠️ Kod / Ham Düzen"]) 
                            
                            with m_tab1: 
                                if f_ext in ["md", "txt", "markdown"]: 
                                    st.markdown(f_content) 
                                else: 
                                    st.code(f_content, language=f_ext if f_ext else "text", line_numbers=True) 
                            
                            with m_tab2: 
                                st.text_area("Ham Metin Kopyala:", f_content, height=350) 

                            st.download_button( 
                                label=f"📥 '{f_name}' Dosyasını İndir", 
                                data=f_content, 
                                file_name=f_name, 
                                use_container_width=True 
                            ) 

                        if st.button("🔎 Tam Ekran / Detaylı İncele", use_container_width=True): 
                            open_file_modal(selected_file, file_content, ext) 

                        st.download_button( 
                            label=f"📥 '{selected_file}' İndir", 
                            data=file_content, 
                            file_name=selected_file, 
                            use_container_width=True 
                        ) 

                    except Exception as e: 
                        st.error(f"Dosya okuma hatası: {e}") 
                else: 
                    st.info("Bu session içinde henüz oluşturulmuş bir dosya yok.") 
            else: 
                st.warning("Session klasörü henüz bulunamadı.")