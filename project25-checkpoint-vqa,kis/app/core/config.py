import os


class Settings:
    PROJECT_NAME: str = "AIC 2026 Backend Engine"
    STATIC_DIR: str = "static"
    DATA_DIR: str = "data"
    FAISS_INDEX_PATH: str = os.path.join(DATA_DIR, "faiss_index.bin")
    METADATA_PATH: str = os.path.join(DATA_DIR, "metadata.json")
    
    # CLIP checkpoint used for the shared text/image embedding space.
    CLIP_MODEL_NAME: str = "sentence-transformers/clip-ViT-B-32"

    # OpenAI Vision-Language Model used by the VQA endpoint.  The API key is
    # read from the OPENAI_API_KEY environment variable, never source code.
    OPENAI_VQA_MODEL: str = "gpt-4o"
    
    # URL tĩnh trả về cho Frontend
    BACKEND_HOST: str = "http://localhost:8000"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "models/gemini-1.5-flash-latest")
settings = Settings()
