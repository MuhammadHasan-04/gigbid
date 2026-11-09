from peft import LoraConfig, get_peft_model
from transformers import AutoTokenizer, AutoModel
import torch
from torch.utils.data import DataLoader
import sagemaker


def main():
    """Entry point for fine-tune an open llm for real estate support tickets."""
    ...
