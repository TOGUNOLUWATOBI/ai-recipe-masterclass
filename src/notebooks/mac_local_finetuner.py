import os
import torch
import random
from datasets import load_dataset, interleave_datasets, IterableDataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

print("Checking Apple Silicon (MPS) availability...")
if torch.backends.mps.is_available():
    device = "mps"
    print("✅ Apple Metal Performance Shaders (MPS) activated!")
else:
    device = "cpu"
    print("⚠️ MPS not found. Falling back to CPU (This will be very slow).")

# Where to save the final model locally
OUTPUT_DIR = "./mac_food_model"
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

print(f"Loading {MODEL_ID} into 16-bit memory...")
# We load in float16. 32GB of Mac RAM can easily hold this ~14GB model.
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map=device
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# We enable gradient checkpointing to keep your 32GB RAM from overflowing during training
model.gradient_checkpointing_enable()

peft_config = LoraConfig(
    r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, peft_config)
print("✅ LoRA adapters injected successfully.")

print("Connecting to live dataset streams...")
food_com_stream = load_dataset("AkashPS11/recipes_data_food.com", split="train", streaming=True)
kaggle_stream = load_dataset("Hieu-Pham/kaggle_food_recipes", split="train", streaming=True)
just_recipe_stream = load_dataset("awidjaja/just_a_recipe_dataset", split="train", streaming=True)

def format_recipe(row, source_type):
    """Converts varied dataset columns into ChatML formatting"""
    system_instruction = "You are an expert culinary AI capable of providing detailed, accurate recipes, optimizing budget meals, and matching available ingredients to delicious dishes."
    
    if source_type == "food.com":
        title = row.get("name", "Unknown Recipe")
        ingredients = row.get("ingredients", "Not specified")
        steps = row.get("steps", "Not specified")
        desc = row.get("description", "")
    elif source_type == "kaggle":
        title = row.get("RecipeName", "Unknown Recipe")
        ingredients = row.get("Ingredients", "Not specified")
        steps = row.get("Directions", "Not specified")
        desc = row.get("Description", "")
    else:
        title = row.get("title", "Meal Idea")
        ingredients = row.get("components", "Not specified")
        steps = row.get("summary", "Not specified")
        desc = ""

    title = title if title else "Meal Idea"
    desc = desc if desc else ""
    ingredients = ingredients if ingredients else "Not specified"
    steps = steps if steps else "Not specified"

    # Randomize prompt formats for RAG/Discount capability
    prompt_style = random.choice(["name_based", "ingredient_based", "budget_based"])
    
    if prompt_style == "name_based":
        user_query = f"Can you provide a recipe for {title}? {desc}".strip()
    elif prompt_style == "ingredient_based":
        user_query = f"I have the following ingredients available: {ingredients}. What is a good dish I can make with these?"
    else:
        user_query = f"I need a budget-friendly meal idea. How do I make {title}?"

    assistant_reply = f"### {title}\n\n**Ingredients:**\n{ingredients}\n\n**Instructions:**\n{steps}"
    text = f"<|im_start|>system\n{system_instruction}<|im_end|>\n<|im_start|>user\n{user_query}<|im_end|>\n<|im_start|>assistant\n{assistant_reply}<|im_end|>"
    return {"text": text}

food_stream = food_com_stream.map(lambda x: format_recipe(x, "food.com"))
kag_stream = kaggle_stream.map(lambda x: format_recipe(x, "kaggle"))
just_stream = just_recipe_stream.map(lambda x: format_recipe(x, "just_recipe"))

training_stream = interleave_datasets([food_stream, kag_stream, just_stream])

if hasattr(training_stream, "_ex_iterable"):
    training_stream._ex_iterable.batch_size = 2

training_args = SFTConfig(
    per_device_train_batch_size=1, 
    gradient_accumulation_steps=8, 
    warmup_steps=5,
    max_steps=10000, 
    learning_rate=2e-4,
    fp16=True, 
    bf16=False,
    logging_steps=10,
    optim="adamw_torch", 
    weight_decay=0.01,
    lr_scheduler_type="linear",
    seed=42,
    output_dir=f"{OUTPUT_DIR}/checkpoints",
    save_strategy="steps", 
    save_steps=1000, 
    save_total_limit=3,
    
    # --- MOVED FROM SFTTrainer ---
    dataset_text_field="text",
    max_length=2048,
    # dataset_batch_size=1,
    packing=False
)


trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer, 
    train_dataset=training_stream,
    args=training_args, # This now contains all the dataset args!
)

print("\n🚀 Starting Mac-Optimized Finetuning...")
trainer.train()

print("\n💾 Saving final adapters to local disk...")
final_save_path = f"{OUTPUT_DIR}/final_adapters"
model.save_pretrained(final_save_path)
tokenizer.save_pretrained(final_save_path)

print(f"✅ Training Complete! Your model is saved locally at {final_save_path}")