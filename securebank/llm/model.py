"""Load the local LLM once and generate text with it.

Nothing is sent to an external API: the model runs on this machine.

Settings (environment variables, all optional):
    SECUREBANK_DEVICE=cpu   force the CPU even if a GPU is available
    SECUREBANK_4BIT=1       load the model in 4-bit (needs: pip install bitsandbytes)
"""
import os

from securebank.config import MODEL_NAME


class LocalLLM:
    """Any object with this generate() method can be used as the LLM (tests use a fake)."""

    def __init__(self, model_name: str = MODEL_NAME):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        want_cpu = os.environ.get("SECUREBANK_DEVICE", "").lower() == "cpu"
        self.device = "cuda" if torch.cuda.is_available() and not want_cpu else "cpu"
        four_bit = os.environ.get("SECUREBANK_4BIT") == "1" and self.device == "cuda"

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if four_bit:
            from transformers import BitsAndBytesConfig
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name, device_map="auto",
                quantization_config=BitsAndBytesConfig(load_in_4bit=True,
                                                       bnb_4bit_compute_dtype=torch.float16))
        else:
            dtype = torch.float16 if self.device == "cuda" else torch.float32
            self.model = AutoModelForCausalLM.from_pretrained(model_name, dtype=dtype).to(self.device)
        self.model.eval()
        self.description = f"{model_name} on {self.device}{' (4-bit)' if four_bit else ''}"

    def generate(self, messages: list[dict], max_new_tokens: int = 128) -> str:
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with self.torch.no_grad():
            output = self.model.generate(
                **inputs, max_new_tokens=max_new_tokens, do_sample=False,
                temperature=None, top_p=None, top_k=None,       # greedy: same answer every time
                pad_token_id=self.tokenizer.eos_token_id)
        new_tokens = output[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def model_available(model_name: str = MODEL_NAME) -> bool:
    """True if the model files are already downloaded (so loading needs no internet)."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    found = try_to_load_from_cache(model_name, "model.safetensors")
    return isinstance(found, str)


_cached: LocalLLM | None = None


def get_llm() -> LocalLLM:
    """Load the model the first time, then reuse it (loading takes several seconds)."""
    global _cached
    if _cached is None:
        _cached = LocalLLM()
    return _cached
