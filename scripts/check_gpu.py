"""Day 1 check: can this machine load the model and use the GPU?

Run from the project root:
    python scripts/check_gpu.py
The first run downloads about 3 GB.
"""
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

print("PyTorch version:", torch.__version__)
print("CUDA available: ", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:            ", torch.cuda.get_device_name(0))
    device, dtype = "cuda", torch.float16
else:
    print("No GPU found: running on CPU (slower, but works).")
    device, dtype = "cpu", torch.float32

t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=dtype).to(device)
print(f"Model loaded in {time.time() - t0:.1f} s")

messages = [
    {"role": "system", "content": "You are a helpful banking assistant. Answer in one sentence."},
    {"role": "user", "content": "Say hello and explain what a savings account is."},
]
prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to(device)

t0 = time.time()
with torch.no_grad():
    output = model.generate(**inputs, max_new_tokens=60, do_sample=False)
answer = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(f"Answer ({time.time() - t0:.1f} s): {answer}")

if device == "cuda":
    print(f"Peak GPU memory: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
