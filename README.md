# SecureBank AI

A privacy-preserving Generative AI assistant for banking information retrieval
(university Generative AI course project). All data is synthetic.

## Setup (Windows, PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python -m securebank.db.seed      # builds data/bank.db
python -m pytest                  # runs the tests
python scripts/check_gpu.py       # checks the model runs on the GPU
```

## Demo accounts (fictional)

| Username  | Password       | Role     |
|-----------|----------------|----------|
| manager1  | Manager!2026   | manager  |
| employee1 | Employee!2026  | employee |
| customer1 | Customer!2026  | customer |
