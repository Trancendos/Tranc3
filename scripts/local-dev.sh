# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Data Preparation
python scripts/prepare_data.py
python scripts/train_tokenizer.py

# Training
python scripts/train.py

# Testing
python scripts/chat.py
