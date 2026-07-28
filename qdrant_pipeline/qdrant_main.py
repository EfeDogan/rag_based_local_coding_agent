import os
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from uuid import uuid4
from dotenv import load_dotenv
from splitters.text_splitters import parse_all_repositories


load_dotenv()
EMBED_URL = os.getenv("EMBED_URL")

# create client 
client = QdrantClient(url="http://localhost:6333/")

REPOS_DIR = "/tmp/Repos"
VECTOR_SIZE = 1024
COLLECTION_NAME = "codebase"


def get_client():
    return client


if __name__ == "__main__":

    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)


    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE, 
            distance=Distance.COSINE
        ),
    )

    point_id = 1
    for chunk in parse_all_repositories(REPOS_DIR):
        text_to_embed = chunk["embedding_text"]
        metadata = chunk["metadata"]
        raw_code = chunk["code"]
        raw_comment = chunk["comment"]
    

        # send to embedding model and get response 
        response = requests.post(
            EMBED_URL,
            json={
                "model": "qwen3-embedding:0.6b",
                "input": text_to_embed
            }
        )

        embeddings = response.json()["embeddings"][0]
        
        # Prepare QDrant payload 
        payload = {
            **metadata,
            "code": raw_code,
            "comment": raw_comment
        }

        # Save into QDrant db         
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embeddings,
                    payload=payload
                )
            ]
        )
        point_id += 1
        print(f"Eklendi: {metadata['language']} -> {metadata['file_path']} | {metadata['name']}")

    print("Tüm kodlar başarıyla indekslendi!")
    client.close()