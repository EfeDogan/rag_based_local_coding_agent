import os, requests, glob, argparse
from langchain_core.tools import tool
from uuid import uuid4 
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, RemoveMessage
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from dotenv import load_dotenv
from qdrant_pipeline.qdrant_main import get_client
from prompts.prompts2 import SYSTEM_PROMPT
from token_tracker.base_callback_handler import TokenTrackerHandler
from typing import Any



load_dotenv()
OLLAMA_URL = os.getenv("OLLAMA_URL")
ORNITH_URL = os.getenv("ORNITH_URL")
SESSION_PATH = os.getenv("SESSION_PATH")
EMBED_URL = os.getenv("EMBED_URL")
client = get_client()
contextmd_count = 0

parser = argparse.ArgumentParser(description="Sohbete devam etmek için id girin.")

# Take id argument 
parser.add_argument(
    "-id",
    "--id",
    type=str,
    help="İşlem yapılacak ID bilgisi",
)

# Read argument 
args = parser.parse_args()

# Get input 
input_id = None
if args.id is not None:
    if os.path.exists(os.path.join(SESSION_PATH, str(args.id))):
        input_id = args.id
    else:
        print("Böyle bir sohbet kaydı bulunamadı!")

def continue_session(session_id:str, config:dict):
    folder_path  = os.path.join(SESSION_PATH, str(session_id))
    file_path = os.path.join(folder_path, f"CONTEXT{contextmd_count}.md")

    # Find all context*.md files
    files = sorted(glob.glob(os.path.join(folder_path, "CONTEXT*.md")))

    contents = {}

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            contents[file_path] = f.read()

    formatted_contents = "\n\n".join([f"--- {dosya} ---\n{icerik}" for dosya, icerik in contents.items()])

    initial_messages = [
        SystemMessage(content=f"Aşağıdaki Markdown belgesi/belgeleri bu sohbetin temel bağlamıdır:\n\n{formatted_contents}")
    ]
                
    # run agent with new updated state
    agent_executor.update_state(config, {"messages": initial_messages})
    print(f"{len(files)} adet Context.md belgesi okundu sohbete devam edebilirsiniz.")


def create_session_id():
    session_id = uuid4()
    return str(session_id)


def run_compaction(memory_text: str, session_id: str):
    # Read compaction file and generate summary of context 
    with open("compaction.md", 'r', encoding='utf-8') as f:
        compaction_instr = f.read()
        
    compaction_prompt = (
        f"{compaction_instr}\n\n"
        f"--- ÖZETLENECEK SOHBET GEÇMİŞİ VE DÖKÜMANLAR ---\n"
        f"{memory_text}"
    )
    response = llm.invoke(compaction_prompt)

    folder_path = os.path.join(SESSION_PATH, session_id)
    os.makedirs(folder_path, exist_ok=True)
    
    # Count context files and name new one 
    existing_files = sorted(glob.glob(os.path.join(folder_path, "CONTEXT*.md")))
    new_context_index = len(existing_files)
    file_path = os.path.join(folder_path, f"CONTEXT{new_context_index}.md")

    # Save summary 
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(response.content)
    
    # Clean old message history
    current_state = agent_executor.get_state(config)
    existing_messages = current_state.values.get("messages", [])
    
    if existing_messages:
        delete_messages = [RemoveMessage(id=m.id) for m in existing_messages if hasattr(m, 'id') and m.id]
        if delete_messages:
            agent_executor.update_state(config, {"messages": delete_messages})

    # Read all context files at folder path 
    all_context_files = sorted(glob.glob(os.path.join(folder_path, "CONTEXT*.md")))
    contents = {}
    for fp in all_context_files:
        with open(fp, "r", encoding="utf-8") as f:
            contents[fp] = f.read()

    formatted_contents = "\n\n".join([f"--- {dosya} ---\n{icerik}" for dosya, icerik in contents.items()])

    # Create new inital message according to context files 
    initial_messages = [
        SystemMessage(content=f"Aşağıdaki Markdown belgesi/belgeleri bu sohbetin geçmiş bağlamıdır:\n\n{formatted_contents}")
    ]

    # Update agent state    
    agent_executor.update_state(config, {"messages": initial_messages})
    print(f"Compaction çalıştırıldı ve memory sıfırlandı, CONTEXT{new_context_index}.md memory'e eklendi.")
    
    return new_context_index + 1


#Create new file and write response into it
@tool
def create_file(response: Any, 
                file_name: str = None
                ) -> dict:
    """
    Yanıtı uygun dosyaya kaydeder.
    
    Args:
        response Any: Kaydedilecek yanıt metni

    
    Returns:
        dict: Sonuç bilgisi {dosya_adi, dosya_yolu, durum}
    
    Examples:
        >>> create_file("Merhaba!", "python")
        {'dosya_adi': 'cevap.py', 'dosya_yolu': 'cevap.py', 'durum': True}
        
        >>> create_file("Merhaba!")
        {'dosya_adi': 'cevap.txt', 'dosya_yolu': 'cevap.txt', 'durum': True}
    """

    
    if file_name == None:
        dosya_adi = f"file_name"
    else:
        dosya_adi = file_name

    folder_path = os.path.join(SESSION_PATH, session_id)

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    file_path = os.path.join(folder_path, dosya_adi)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(str(response))
        
        return {
            'dosya_adi': dosya_adi,
            'dosya_yolu': os.path.abspath(file_path),
            'durum': True,
            'mesaj': f'Dosya oluşturuldu: {file_path}'
        }
    except Exception as e:
        return {
            'durum': False,
            'hata': str(e)
        }

# Update user question if necessary
@tool
def update_query(user_question: str) -> str :
    """Daha iyi cevap verebilmek için kullanıcının sorduğu soruda iyileştirmeler yapar."""
    new_question = ""
    return new_question

# Searching codebase tool
@tool
def search_codebase(new_question: str, limit: int) -> str:
    """Kod tabanında (Qdrant) kullanıcının sorusuyla eşleşen ilgili kodları ve dokümanları arar."""
    response = requests.post(
        EMBED_URL,
        json={
            "model": "qwen3-embedding:0.6b",
            "input": new_question
        }
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

# tool list
tools = [search_codebase, update_query, create_file]

# Define model
llm = ChatOllama(
    base_url=OLLAMA_URL,
    #base_url=ORNITH_URL,
    #model="ornith:9b",
    model ="glm-5.2:cloud" ,
    temperature=0.4,
    num_ctx= 262144,
    #num_ctx=32000,
    verbose=True
)

# prompt template
prompt_template = ChatPromptTemplate.from_messages([
    (
        "system", 
        f'{SYSTEM_PROMPT}'
    ),
   ("placeholder", "{chat_history}"),
    ("human", "{input}" ),
    ("placeholder", "{agent_scratchpad}"),
])

# Create memory
checkpointer = MemorySaver()

agent_executor = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer
)

if input_id is None:
    session_id = create_session_id()
    config = {"configurable": {"thread_id": session_id}}
else:
    config = {"configurable": {"thread_id": input_id}}
    continue_session(session_id=input_id, config=config)
    session_id = input_id
    

memory_text = ""

print("Agent çalışıyor ne öğrenmek istersiniz: ")


while True:
    try:
        
        query = input()
        if query.strip() == "/compact":
                contextmd_count=run_compaction(memory_text=memory_text, contextmd_count=contextmd_count, session_id=session_id)
                memory_text=""

        else:

            token_tracker = TokenTrackerHandler()

            result = agent_executor.invoke({"messages": [("human", query)]},
                config={**config, "callbacks": [token_tracker]})
            
            # Get current state of session
            current_state = agent_executor.get_state(config)

            for i, msg in enumerate(current_state.values.get("messages", [])):
                msg_type = msg.__class__.__name__
                
                if msg_type == "HumanMessage":
                    print(f"[{i}] 👤 Kullanıcı: {msg.content}")
                    memory_text += f"[{i}] 👤 Kullanıcı: {msg.content}"
                    
                elif msg_type == "AIMessage":
                    if msg.tool_calls:
                        print(f"[{i}] ⚙️ AI (Tool Çağrısı): {msg.tool_calls[0]['name']}")
                        memory_text += f"[{i}] ⚙️ AI (Tool Çağrısı): {msg.tool_calls[0]['name']}"
                    else:
                        print(f"[{i}] 🤖 AI (Cevap): {msg.content}...")
                        memory_text += f"[{i}] 🤖 AI (Cevap): {msg.content}..."
                        
                elif msg_type == "ToolMessage":
                    print(f"[{i}] 📄 Tool (RAG Dökümanı): {msg.name} -> Uzunluk: {len(msg.content)} karakter")
                    memory_text += f"[{i}] 📄 Tool (RAG Dökümanı): {msg.name} {msg.content}"
                    
            # How many input tokens were processed
            print(f"prompt eval count: {token_tracker.prompt_eval_count}")
        
            # How many output tokens were processes
            print(f"eval count: {token_tracker.eval_count}")

        print("=========================================\n")
        print(" > Başka merak ettiğiniz bir konu var mı?")

        if token_tracker.prompt_eval_count >= 60000:
            contextmd_count=run_compaction(memory_text=memory_text, contextmd_count=contextmd_count, session_id=session_id)
            memory_text=""
    
    except KeyboardInterrupt:
        print("\nSohbet sonlandırıldı.")
        break
    except Exception as e:
        print(f"\nBir hata oluştu: {e}")

