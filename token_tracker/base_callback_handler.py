from langchain_core.callbacks import BaseCallbackHandler

class TokenTrackerHandler(BaseCallbackHandler):
    def __init__(self):
        self.prompt_eval_count = 0
        self.eval_count = 0

    def on_llm_end(self, response, **kwargs):
        for generations in response.generations:
            for gen in generations:
                # Get Ollama metadata
                metadata = gen.generation_info or {}
                if "response_metadata" in metadata: 
                    metadata = metadata["response_metadata"]
                
                self.prompt_eval_count += metadata.get("prompt_eval_count", 0)
                self.eval_count += metadata.get("eval_count", 0)