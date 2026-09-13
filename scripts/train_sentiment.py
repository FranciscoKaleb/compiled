import json
import os
import torch
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification, 
    Trainer, 
    TrainingArguments,
    DataCollatorWithPadding
)
from datasets import Dataset

def train_model():
    # --- Configuration ---

    # The data directory lives at the repo root, one level above scripts/.
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Path where we created the sample data
    data_path = os.path.join(base_dir, "app_files", "training_files", "sample_sentiment_data.json")
    
    # Path to save the trained model (and load from if it exists)
    model_output_path = os.path.join(base_dir, "app_files", "models", "bert1_sentiment_model")
    
    # Base model to use if local model doesn't exist yet
    # Using the one referenced in your dl.py
    base_model_name = "cardiffnlp/twitter-xlm-roberta-base-sentiment"

    print(f"1. Loading data from {data_path}...")
    
    if not os.path.exists(data_path):
        print(f"Error: Data file not found at {data_path}")
        return

    with open(data_path, 'r') as f:
        data = json.load(f)

    # Convert list of dicts to Hugging Face Dataset
    # Expected format: [{'text': '...', 'label': 0}, ...]
    full_dataset = Dataset.from_list(data)

    # Split into train and test (using a small test split for demo since we only have 10 items)
    dataset_split = full_dataset.train_test_split(test_size=0.2)
    train_dataset = dataset_split["train"]
    eval_dataset = dataset_split["test"]

    print("2. preparing model and tokenizer...")

    # Check if we have a local model already, otherwise download base
    load_path = model_output_path if os.path.exists(model_output_path) else base_model_name
    print(f"   Loading from: {load_path}")

    tokenizer = AutoTokenizer.from_pretrained(load_path)
    model = AutoModelForSequenceClassification.from_pretrained(load_path, num_labels=3)

    # Tokenization function
    def tokenize_function(examples):
        return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=128)

    tokenized_train = train_dataset.map(tokenize_function, batched=True)
    tokenized_eval = eval_dataset.map(tokenize_function, batched=True)

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    print("3. Setting up training arguments...")
    
    training_args = TrainingArguments(
        output_dir=os.path.join(base_dir, "app_files", "training_files", "runs"),
        learning_rate=2e-5,
        per_device_train_batch_size=4,  # Small batch size for small data/cpu
        per_device_eval_batch_size=4,
        num_train_epochs=3,             # Number of times to iterate over data
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        use_cpu=not torch.cuda.is_available() # Use GPU if available
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_eval,
        data_collator=data_collator,
    )

    print("4. Starting training...")
    trainer.train()

    print(f"5. Saving model to {model_output_path}...")
    trainer.save_model(model_output_path)
    tokenizer.save_pretrained(model_output_path)
    print("Done!")

if __name__ == "__main__":
    train_model()