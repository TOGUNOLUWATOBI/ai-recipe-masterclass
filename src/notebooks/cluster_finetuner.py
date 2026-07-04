import os
import re
import json
import torch
import random
from datasets import load_dataset, concatenate_datasets, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from transformers.trainer_utils import get_last_checkpoint
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

print("Checking GPU availability...")
if torch.cuda.is_available():
    device = "cuda"
    print("✅ Nvidia CUDA acceleration activated!")
else:
    device = "cpu"
    print("⚠️ GPU not found. Falling back to CPU.")

# Where to save the final model locally
OUTPUT_DIR = "./mac_food_model"
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

# Must stay word-for-word identical to the SYSTEM block in the Ollama Modelfile.
# If they drift, the model is served with rules it never saw reinforced during LoRA training.
SYSTEM_INSTRUCTION = """You are a master chef and a strictly professional culinary assistant.
Your goal is to provide accurate, delicious, and easy-to-follow recipes.

STRICT FORMATTING RULES:
1. NEVER use R-programming syntax (like c(), quotes, or brackets around lists).
2. Ingredients must be presented as a simple, clean bulleted list.
3. Instructions must be a numbered list of clear, concise steps.
4. If you do not have a specific ingredient for a dish, suggest a common substitute instead of hallucinating.
5. Do not include conversational filler unless asked.
6. Use only standard, plain English text.

If you see an ingredient list or instruction set in your memory that looks like code, you must translate it into standard human-readable text before outputting."""

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

print("Downloading and caching dataset sources locally...")
# Both source CSVs are small (~30MB / ~25MB) so a full one-time download is cheap. We deliberately
# do NOT use streaming=True here: live-streaming every row from the HF Hub on every training step
# was causing repeated network timeouts/disconnects mid-run (multi-minute stalls, sometimes worse),
# and combining a per-source .shuffle() with a probability-weighted interleave_datasets(...,
# stopping_strategy="all_exhausted") hits a hard, deterministic crash in the datasets library
# (DataSourcesShufflingDisallowed) the moment a new epoch starts. Fully-materialized local Datasets
# sidestep both problems — no network dependency during training, and plain concatenate+shuffle
# instead of the fragile streaming-shuffle/interleave combination.
food_com_raw = load_dataset("AkashPS11/recipes_data_food.com", split="train")
kaggle_raw = load_dataset("Hieu-Pham/kaggle_food_recipes", split="train")

# Curated, hand-verified African recipes (kept alongside this script so it travels with it
# to the training server). Corrects the model's tendency to hallucinate cross-cuisine
# ingredient pairings (e.g. coconut milk in jollof rice) that food.com/kaggle can't teach it,
# since both sources are overwhelmingly Western recipes.
AFRICAN_RECIPES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthetic_african_recipes.json")
with open(AFRICAN_RECIPES_PATH, "r", encoding="utf-8") as f:
    african_recipes = json.load(f)
african_raw = Dataset.from_list(african_recipes)


# R's `c(...)` vector wrapper leaks into food.com's RecipeIngredientParts/RecipeInstructions
# columns as literal text (e.g. c("1 cup flour", "2 eggs")). Strip that wrapper before
# the list-syntax cleanup below, or the model trains on "c(...)" as if it were correct formatting.
def clean_field(raw):
    s = str(raw).strip()
    s = re.sub(r'^c\(\s*', '', s)
    s = re.sub(r'\s*\)$', '', s)
    s = s.replace("[", "").replace("]", "").replace('"', "").replace("'", "")
    s = re.sub(r'\s+', ' ', s).strip(' ,')
    return s

# 1. Strict filter for only our two high-quality datasets
def is_valid_recipe(row, source_type):
    if source_type == "food.com":
        title, ingredients, steps = row.get("Name"), row.get("RecipeIngredientParts"), row.get("RecipeInstructions")
    elif source_type == "kaggle":
        title, ingredients, steps = row.get("Title"), row.get("Ingredients"), row.get("Instructions")
    elif source_type == "african":
        title, ingredients, steps = row.get("title"), row.get("ingredients"), row.get("instructions")
        return bool(title and ingredients and steps)
    else:
        return False

    if not (title and ingredients and steps):
        return False

    # Drop garbled/experimental rows: too short to be a real recipe, or still carrying
    # unresolved R/list syntax after cleaning (a sign the source row was malformed).
    cleaned_ingredients = clean_field(ingredients)
    cleaned_steps = clean_field(steps)
    if len(cleaned_ingredients) < 10 or len(cleaned_steps) < 20:
        return False
    if re.search(r'\bc\(|NA_character_|\bNULL\b', cleaned_ingredients + cleaned_steps):
        return False
    return True

# 2. Format function using the exact verified columns
def format_recipe(row, source_type):
    if source_type == "food.com":
        title = row.get("Name")
        ingredients = clean_field(row.get("RecipeIngredientParts"))
        steps = clean_field(row.get("RecipeInstructions"))

    elif source_type == "kaggle":
        title = row.get("Title")
        ingredients = clean_field(row.get("Ingredients"))
        steps = clean_field(row.get("Instructions"))

    elif source_type == "african":
        title = row.get("title")
        ingredients = ", ".join(row.get("ingredients"))
        steps = " ".join(row.get("instructions"))

    assistant_reply = f"### {title}\n\n**Ingredients:**\n{ingredients}\n\n**Instructions:**\n{steps}"

    # Randomize how the user asks for the recipe
    prompt_style = random.choice(["name_based", "ingredient_based", "budget_based"])
    
    if prompt_style == "name_based":
        user_query = f"Can you provide a recipe for {title}?".strip()
    elif prompt_style == "ingredient_based":
        user_query = f"I have the following ingredients available: {ingredients}. What is a good dish I can make with these?"
    else:
        user_query = f"I need a budget-friendly meal idea. How do I make {title}?"

    text = f"<|im_start|>system\n{SYSTEM_INSTRUCTION}<|im_end|>\n<|im_start|>user\n{user_query}<|im_end|>\n<|im_start|>assistant\n{assistant_reply}<|im_end|>"
    return {"text": text}

# 3. Filter and map all three datasets, dropping the original source-specific columns so
# schemas match (concatenate_datasets requires identical columns across inputs).
food_stream = food_com_raw.filter(lambda x: is_valid_recipe(x, "food.com")).map(
    lambda x: format_recipe(x, "food.com"), remove_columns=food_com_raw.column_names
)
kag_stream = kaggle_raw.filter(lambda x: is_valid_recipe(x, "kaggle")).map(
    lambda x: format_recipe(x, "kaggle"), remove_columns=kaggle_raw.column_names
)
afr_stream = african_raw.filter(lambda x: is_valid_recipe(x, "african")).map(
    lambda x: format_recipe(x, "african"), remove_columns=african_raw.column_names
)

# 4. Combine all three. The African set only has 150 rows versus food.com/kaggle's much larger
# row counts, so it's mildly oversampled (simple repetition) rather than left at its tiny natural
# share. Capped at MAX_REPEATS rather than hit-a-fixed-percentage: a previous run computed ~20x
# repeats to reach a 10% target share, and the model memorized specific recipes' phrasing well
# enough to leak it into unrelated dishes (e.g. jollof rice's "smoky bottom layer" motif showing
# up, mislabeled, in a biryani response). A small capped multiple still gives each recipe enough
# repeated exposure to shift behavior on the dishes it's meant to fix, without enough repetition
# to memorize and leak distinctive phrasing.
TARGET_AFRICAN_SHARE = 0.10
MAX_REPEATS = 3
n_other = len(food_stream) + len(kag_stream)
repeats = max(1, min(MAX_REPEATS, round((TARGET_AFRICAN_SHARE / (1 - TARGET_AFRICAN_SHARE)) * n_other / len(afr_stream))))
afr_repeated = concatenate_datasets([afr_stream] * repeats)

combined_stream = concatenate_datasets([food_stream, kag_stream, afr_repeated]).shuffle(seed=42)
print(f"Combined dataset: {len(combined_stream)} examples ({len(afr_stream)} African recipes x{repeats})")

# Carve out a small fixed held-out set so we can see eval loss during training,
# instead of flying blind on whether 4000 steps over/under-fits the data.
EVAL_SIZE = 100
eval_stream = combined_stream.select(range(EVAL_SIZE))
training_stream = combined_stream.select(range(EVAL_SIZE, len(combined_stream)))

training_args = SFTConfig(
    per_device_train_batch_size=1, 
    gradient_accumulation_steps=8, 
    warmup_steps=5,
    max_steps=4000, 
    learning_rate=2e-4,
    fp16=False, 
    bf16=True,
    logging_steps=10,
    optim="adamw_torch", 
    weight_decay=0.01,
    lr_scheduler_type="linear",
    seed=42,
    output_dir=f"{OUTPUT_DIR}/checkpoints",
    save_strategy="steps",
    save_steps=1000,
    save_total_limit=3,
    eval_strategy="steps",
    eval_steps=1000,
    per_device_eval_batch_size=8,

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
    eval_dataset=eval_stream,
    args=training_args, # This now contains all the dataset args!
)

# Auto-resume from the latest checkpoint in output_dir if one exists (e.g. from the crashed
# run), otherwise train from scratch — get_last_checkpoint returns None on a fresh output_dir,
# unlike resume_from_checkpoint=True which errors out if no checkpoint is found.
last_checkpoint = get_last_checkpoint(training_args.output_dir) if os.path.isdir(training_args.output_dir) else None
if last_checkpoint:
    print(f"\n♻️  Resuming from checkpoint: {last_checkpoint}")
else:
    print("\nNo checkpoint found — starting training from scratch.")

print("\n🚀 Starting Mac-Optimized Finetuning...")
trainer.train(resume_from_checkpoint=last_checkpoint)

print("\n💾 Saving final adapters to local disk...")
final_save_path = f"{OUTPUT_DIR}/final_adapters"
model.save_pretrained(final_save_path)
tokenizer.save_pretrained(final_save_path)

print("\n🔗 Merging LoRA adapters into the base model for GGUF conversion...")
# convert_hf_to_gguf.py needs full model weights, not LoRA deltas — merge_and_unload()
# bakes the adapter into the base weights and returns the plain (non-PEFT) model.
merged_model = model.merge_and_unload()
merged_save_path = f"{OUTPUT_DIR}/merged_full_model"
merged_model.save_pretrained(merged_save_path)
tokenizer.save_pretrained(merged_save_path)

print(f"✅ Training Complete! Adapters saved at {final_save_path}, merged full model at {merged_save_path}")
