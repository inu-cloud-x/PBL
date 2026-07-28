import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from typing import Optional
from ..config import MODEL_ID, DEVICE

class TextToCadQueryRunner:
    def __init__(self, model_id: str = MODEL_ID, device: Optional[str] = None):
        self.device = device or DEVICE
        self.model_id = model_id
        
        print(f"Loading model {model_id} on {self.device}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        
        # Load in bfloat16 for M4 Pro optimization as per plan
        load_args = {
            "torch_dtype": torch.bfloat16,
            "device_map": self.device
        }
        
        self.model = AutoModelForCausalLM.from_pretrained(model_id, **load_args)
        self.model.eval()
        
    def generate(self, prompt: str, seed: int = 42, max_new_tokens: int = 512) -> str:
        # Ensure determinism
        set_seed(seed)
        torch.manual_seed(seed)
        
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,  # Greedy decoding for reproducibility
                temperature=1.0,
                top_p=1.0,
                top_k=1,
                use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )
            
        raw_output = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return raw_output

    def get_revision(self) -> str:
        # Return the model's commit hash for provenance
        return self.model.config._commit_hash if hasattr(self.model.config, "_commit_hash") else "unknown"
