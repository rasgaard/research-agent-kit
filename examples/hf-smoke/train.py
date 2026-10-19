import os
import platform
import time

import torch
from datasets import load_dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
MODEL_ID = os.environ.get("MODEL_ID", "prajjwal1/bert-tiny")
BATCH_SIZE = 8
STEPS = 8


def main() -> None:
    print(f"host={platform.node()} python={platform.python_version()}")
    print(f"torch={torch.__version__} cuda={torch.cuda.is_available()}")
    print(f"hf_home={os.environ.get('HF_HOME', '~/.cache/huggingface')}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        print(f"device={torch.cuda.get_device_name(0)}")

    dataset = load_dataset("nyu-mll/glue", "mrpc", split="train[:64]")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, num_labels=2)
    model.to(device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
    torch.manual_seed(0)

    started = time.time()
    for step in range(STEPS):
        batch = dataset[step * BATCH_SIZE : (step + 1) * BATCH_SIZE]
        encoded = tokenizer(
            batch["sentence1"],
            batch["sentence2"],
            padding=True,
            truncation=True,
            max_length=64,
            return_tensors="pt",
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        labels = torch.tensor(batch["label"], device=device)
        output = model(**encoded, labels=labels)
        output.loss.backward()
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        print(f"step {step + 1}/{STEPS} loss={output.loss.item():.4f}")

    print(f"elapsed={time.time() - started:.1f}s")
    print("HF SMOKE OK")


if __name__ == "__main__":
    main()
