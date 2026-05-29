
"""
RLVR Training — Ambient Travel Companion
=========================================
Uses GRPO (Group Relative Policy Optimisation) — the same algorithm as
DeepSeek-R1. Directly mirrors the smoltldr GRPO pattern you shared,
adapted for the ambient notification task.

WHY GRPO over PPO
-----------------
  PPO needs a separate critic/value model (doubles VRAM).
  GRPO scores N completions per prompt, ranks them relative to each
  other, and uses that ranking as the reward signal — no critic needed.
  Simpler, faster, more stable for small models.

Reward functions  (directly parallel to smoltldr)
-------------------------------------------------
  reward_len      ←→  reward_len    (concision: ≤ 120 words)
  reward_style    ←→  reward_style  (tone matches meeting formality)
  reward_correct  ←→  reward_sim    (structural correctness: delay/attendees/times/fallback)

Setup
-----
  pip install torch transformers peft trl accelerate bitsandbytes
  pip install sentence-transformers python-dotenv datasets

Usage
-----
  # dry-run — no GPU, tests rewards only
  python rlvr_grpo_ambient.py --dry-run

  # train Phi-3-mini (≈16 GB VRAM with 4-bit)
  python rlvr_grpo_ambient.py --model phi3

  # train Gemma-2-9B (≈24 GB VRAM with 4-bit)
  python rlvr_grpo_ambient.py --model gemma2 --epochs 8

  # evaluate saved checkpoint
  python rlvr_grpo_ambient.py --eval-only --checkpoint ./ambient_model_out
"""
import typing
import argparse
import json
import logging
import os
import random
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import torch
from dotenv import load_dotenv
from peft import LoraConfig, get_peft_model
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import GRPOConfig, GRPOTrainer



load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths from .env (mirrors smoltldr pattern) ────────────────────────────────
OUTPUT_DIR       = os.getenv("OUTPUT_DIR",      "./ambient_grpo_out")
LOGGING_DIR      = os.getenv("LOGGING_DIR",     "./ambient_grpo_logs")
MODEL_SAVE_PATH  = os.getenv("MODEL_OUT_PATH",  "./ambient_model_out")

# ── Model registry ─────────────────────────────────────────────────────────────
MODEL_IDS = {
    "phi3":   "microsoft/Phi-3-mini-4k-instruct",
    "gemma2": "google/gemma-2-9b-it",
    "smol":   "HuggingFaceTB/SmolLM-135M-Instruct",   # fast dev/debug
}

# ── Reward constants (from capstone spec) ─────────────────────────────────────
WORD_LIMIT       = 120    # concision ceiling
MAX_COMPLETION   = 220    # GRPOConfig.max_completion_length
NUM_GENERATIONS  = 8      # completions per prompt (GRPO group size)


# ══════════════════════════════════════════════════════════════════════════════
# 1.  SCENARIO DATA  (replaces smoltldr dataset)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DelayScenario:
    delay_minutes:   int
    meeting_weight:  float          # 0 = casual, 1 = critical
    attendees:       list[str]
    weather:         str
    current_time:    str
    proposed_times:  list[str]      # always 3 options
    meeting_title:   str            = "meeting"

    @property
    def is_formal(self) -> bool:
        return self.meeting_weight >= 0.6


def _offset(base: str, delta: int) -> str:
    """Add delta minutes to a 'H:MM AM/PM' string."""
    t = datetime.strptime(base, "%I:%M %p") + timedelta(minutes=delta)
    return t.strftime("%I:%M %p").lstrip("0")


def build_dataset(n: int = 80, seed: int = 42) -> list[dict]:
    """
    Build synthetic dataset as a list of dicts with keys:
        prompt      — formatted user message (same role as smoltldr 'prompt')
        scenario    — serialised DelayScenario for reward functions
    """
    random.seed(seed)

    attendee_pool = [
        ["Alice Chen", "Bob Patel"],
        ["CEO Sarah Kim", "CFO Marcus Liu"],
        ["James O'Brien"],
        ["Dr. Priya Nair", "Investors"],
        ["Team"],
    ]
    weather_pool = ["clear", "light rain", "heavy rain", "snow", "fog"]
    title_pool   = [
        "Q3 board review", "1:1 check-in", "client pitch",
        "investor update", "team standup", "product demo",
    ]
    base_times   = ["2:30 PM", "3:00 PM", "3:30 PM", "4:00 PM"]

    rows: list[dict] = []
    for _ in range(n):
        delay     = random.choice([30, 45, 60, 90, 120, 150])
        weight    = round(random.uniform(0.1, 1.0), 2)
        base      = random.choice(base_times)
        attendees = random.choice(attendee_pool)
        title     = random.choice(title_pool)

        s = DelayScenario(
            delay_minutes  = delay,
            meeting_weight = weight,
            attendees      = attendees,
            weather        = random.choice(weather_pool),
            current_time   = datetime.now().strftime("%I:%M %p").lstrip("0"),
            proposed_times = [
                _offset(base, delay),
                _offset(base, delay + 30),
                base + " tomorrow",
            ],
            meeting_title  = title,
        )

        rows.append({
            "prompt":   _build_prompt(s),
            "scenario": json.dumps({
                "delay_minutes":  s.delay_minutes,
                "meeting_weight": s.meeting_weight,
                "attendees":      s.attendees,
                "proposed_times": s.proposed_times,
                "is_formal":      s.is_formal,
            }),
        })

    log.info("Built %d synthetic scenarios", len(rows))
    return rows


# ── System prompt (capstone spec verbatim) ────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""\
    You are an executive assistant helping reschedule a meeting.
    Draft a brief notification to attendees proposing a new time.
    Keep it under 120 words. Be professional but warm.
    Always mention the exact delay in minutes, name the attendees,
    propose specific rescheduling times, and include a fallback option.
""")


def _build_prompt(s: DelayScenario) -> str:
    """
    Mirrors smoltldr's 'POST: ... TL;DR:' format —
    one structured block the model learns to complete.
    """
    times_str     = " / ".join(s.proposed_times)
    formality     = "formal and professional" if s.is_formal else "warm and casual"
    attendees_str = ", ".join(s.attendees)

    return (
        f"SCENARIO:\n"
        f"  Delay:       {s.delay_minutes} minutes\n"
        f"  Meeting:     {s.meeting_title}\n"
        f"  Attendees:   {attendees_str}\n"
        f"  Time now:    {s.current_time}\n"
        f"  Weather:     {s.weather}\n"
        f"  New times:   {times_str}\n"
        f"  Tone:        {formality}\n\n"
        f"NOTIFICATION:"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2.  REWARD FUNCTIONS  (same signature as smoltldr — list[str] → list[float])
# ══════════════════════════════════════════════════════════════════════════════

# ── reward_len  ←→  smoltldr reward_len ──────────────────────────────────────

_tokenizer_ref: AutoTokenizer | None = None   # set after tokenizer load

def reward_len(completions: list[str], **kwargs) -> list[float]:
    """
    Concision reward — directly implements the capstone spec formula.
    Target: ≤ WORD_LIMIT (120) words.
    Score:  1.0 if under/at limit. Gradients down if over limit.
    """
    out = []
    for c in completions:
        n = len(c.split())
        
        # 🔍 FIX: Perfect score for staying concise; penalize only when over the limit
        if n <= WORD_LIMIT:
            reward = 1.0
        else:
            # Drop score by 0.05 for every word over the limit, bottoming out at 0.0
            reward = max(0.0, 1.0 - (n - WORD_LIMIT) * 0.05)
            
        out.append(float(reward))
    return out

# ── reward_style  ←→  smoltldr reward_style ──────────────────────────────────

def reward_style(completions: list[str], **kwargs) -> list[float]:
    """
    Tone / formality reward — mirrors smoltldr reward_style.

    smoltldr penalises '\\n' (multi-line = bad format).
    Here we check formality signal vs meeting_weight instead —
    same binary pattern, richer domain signal.

    1.0 = tone matches meeting formality
    0.5 = borderline meeting (weight ≈ 0.5)
    0.0 = tone mismatch
    """
    scenarios_raw = kwargs.get("scenario", [])

    # Decode serialised scenarios passed through dataset column
    scenarios = []
    for sr in scenarios_raw:
        try:
            scenarios.append(json.loads(sr) if isinstance(sr, str) else sr)
        except Exception:
            scenarios.append({})

    # Pad if batch is smaller than completions (GRPO repeats prompts)
    if scenarios and len(scenarios) < len(completions):
        reps = (len(completions) + len(scenarios) - 1) // len(scenarios)
        scenarios = (scenarios * reps)[:len(completions)]

    formal_kw = [
        "sincerely", "regards", "apologies", "i regret", "please accept",
        "at your earliest", "kindly", "i would like", "respectfully", "dear",
    ]
    casual_kw = [
        "hey", "hi there", "sorry about", "heads up", "quick note",
        "just wanted", "hope that works", "let me know", "thanks!", "cheers",
    ]

    out = []
    for i, c in enumerate(completions):
        cl = c.lower()
        formal_count = sum(1 for kw in formal_kw if kw in cl)
        casual_count = sum(1 for kw in casual_kw if kw in cl)
        is_formal_msg = formal_count >= casual_count

        if i < len(scenarios):
            is_formal_req = scenarios[i].get("is_formal", True)
            weight        = scenarios[i].get("meeting_weight", 0.5)
            borderline    = abs(weight - 0.5) < 0.15

            if is_formal_req == is_formal_msg:
                out.append(1.0)
            elif borderline:
                out.append(0.5)
            else:
                out.append(0.0)
        else:
            out.append(0.5)   # no scenario metadata — neutral

    return out


# ── reward_correct  ←→  smoltldr reward_sim ──────────────────────────────────

_sem_model: SentenceTransformer | None = None

def _get_sem_model() -> SentenceTransformer:
    """Lazy-load semantic similarity model — identical to smoltldr pattern."""
    global _sem_model
    if _sem_model is None:
        log.info("Loading sentence-transformer (all-MiniLM-L6-v2)...")
        _sem_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _sem_model


def reward_correct(completions: list[str], **kwargs) -> list[float]:
    """
    Structural correctness reward — mirrors smoltldr reward_sim.

    smoltldr: cosine similarity between POST text and TL;DR completion.
    Here:     (a) rule-based sub-scores  +  (b) semantic similarity
              between the scenario block and the notification.

    Sub-scores (rule-based, 0.25 each):
        delay_mentioned     — exact delay number in output
        attendee_named      — at least one attendee name found
        time_proposed       — at least one proposed time found
        fallback_present    — fallback keyword present

    Semantic bonus (0.0–0.2):
        cosine sim between scenario text and completion
        ensures the notification is actually about this scenario.

    Total normalised to [0, 1].
    """
    scenarios_raw = kwargs.get("scenario", [])
    prompts       = kwargs.get("prompts",  [])

    scenarios = []
    for sr in scenarios_raw:
        try:
            scenarios.append(json.loads(sr) if isinstance(sr, str) else sr)
        except Exception:
            scenarios.append({})

    if scenarios and len(scenarios) < len(completions):
        reps = (len(completions) + len(scenarios) - 1) // len(scenarios)
        scenarios = (scenarios * reps)[:len(completions)]

    fallback_kw = [
        "call", "dial in", "virtual", "reschedule", "alternative",
        "if that doesn't work", "if none", "remote", "zoom", "teams",
    ]

    # ── semantic similarity (mirrors smoltldr's cosine sim block) ────────────
    sem_scores: list[float] = []
    if prompts:
        sem_model = _get_sem_model()
        # Extract SCENARIO block from prompts (parallel to smoltldr's POST: regex)
        scenario_re = re.compile(r"SCENARIO:(.*?)NOTIFICATION:", re.DOTALL)
        scenario_texts = []
        for p in prompts:
            m = scenario_re.search(p)
            scenario_texts.append(m.group(1).strip() if m else p)

        # Align length with completions (GRPO generates NUM_GENERATIONS per prompt)
        if len(scenario_texts) < len(completions):
            reps = (len(completions) + len(scenario_texts) - 1) // len(scenario_texts)
            scenario_texts = (scenario_texts * reps)[:len(completions)]

        with torch.no_grad():
            e_comp = sem_model.encode(
                completions, convert_to_tensor=True, normalize_embeddings=True
            )
            e_scen = sem_model.encode(
                scenario_texts, convert_to_tensor=True, normalize_embeddings=True
            )
            sims   = torch.sum(e_comp * e_scen, dim=1)        # cosine in [-1,1]
            sims01 = torch.clamp((sims + 1) / 2, 0.0, 1.0)   # normalise [0,1]
            sem_scores = sims01.cpu().tolist()
    else:
        sem_scores = [0.5] * len(completions)

    # ── rule-based sub-scores ────────────────────────────────────────────────
    out = []
    for i, c in enumerate(completions):
        cl    = c.lower()
        score = 0.0

        s = scenarios[i] if i < len(scenarios) else {}

        # +0.25  delay duration
        delay = s.get("delay_minutes", 0)
        if str(delay) in c or f"{delay}-minute" in cl:
            score += 0.25

        # +0.25  attendee named
        for att in s.get("attendees", []):
            parts = att.lower().split()
            if any(p in cl for p in parts if len(p) > 2):
                score += 0.25
                break

        # +0.25  proposed time appears
        for t in s.get("proposed_times", []):
            t_core = t.replace(" tomorrow", "").strip()
            if t_core.lower() in cl or t.lower() in cl:
                score += 0.25
                break

        # +0.25  fallback
        if any(kw in cl for kw in fallback_kw):
            score += 0.25

        # semantic bonus (0–0.2) — scales with how on-topic the response is
        sem_bonus = sem_scores[i] * 0.2 if i < len(sem_scores) else 0.1

        # combine: 80% rule-based + 20% semantic, normalise to [0,1]
        total = min(1.0, score + sem_bonus)
        out.append(float(total))

    return out


# ══════════════════════════════════════════════════════════════════════════════
# 3.  MODEL + LORA  (identical structure to smoltldr)
# ══════════════════════════════════════════════════════════════════════════════

def load_model_and_tokenizer(model_key: str):
    global _tokenizer_ref
    model_id = MODEL_IDS[model_key]
    log.info("Loading %s", model_id)


    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    
    # 1. Defend against NoneType runtime initialization failures
    if tokenizer is not None:
        # 2. Check if it's wrapped by a DSPy backend wrapper, and extract the raw object
        raw_hf_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)
        
        # 3. Safely assign the padding rules to the native Hugging Face reference
        if hasattr(raw_hf_tokenizer, "pad_token") and raw_hf_tokenizer.pad_token is None:
            raw_hf_tokenizer.pad_token = raw_hf_tokenizer.eos_token
    
        _tokenizer_ref = typing.cast(typing.Any, tokenizer)

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype         = "auto",
        device_map          = "auto",
        trust_remote_code   = True,
        attn_implementation = "sdpa",     # flash-attn-style efficient attention
    )

    # LoRA — identical config to smoltldr, targets all linear layers
    lora_config = LoraConfig(
        task_type      = "CAUSAL_LM",
        r              = 16,
        lora_alpha     = 32,
        target_modules = "all-linear",    # same as smoltldr
        lora_dropout   = 0.05,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, tokenizer


# ══════════════════════════════════════════════════════════════════════════════
# 4.  GRPO TRAINING  (directly parallel to smoltldr trainer setup)
# ══════════════════════════════════════════════════════════════════════════════

def build_grpo_config(epochs: int) -> GRPOConfig:
    """
    Mirror of smoltldr's GRPOConfig.
    Key differences for notification task:
      - max_completion_length = 220  (longer than 96 — notifications need ~120 words)
      - num_generations = 8          (GRPO group size; 48 needs multi-GPU)
      - per_device_train_batch_size smaller for single GPU
    """
    # Inside build_grpo_config(epochs):
    return GRPOConfig(
        output_dir                   = OUTPUT_DIR,
        logging_dir                  = LOGGING_DIR,
        learning_rate                = 2e-5,
        per_device_train_batch_size  = 1,          # 💡 Set to 1 to protect your Mac's unified memory
        gradient_accumulation_steps  = 4,
        max_completion_length        = MAX_COMPLETION,
        num_generations              = 4,          # 💡 Lower this from 8 to 4 for local Mac VRAM constraints
        # optim                        = "adamw_8bit", # ❌ Remove or comment this out (8-bit optimizers require Nvidia CUDA)
        num_train_epochs             = epochs,
        report_to                    = ["tensorboard"],
        remove_unused_columns        = False,
        logging_steps                = 1,
)

def train(model_key: str = "phi3", epochs: int = 8):
    model, tokenizer = load_model_and_tokenizer(model_key)

    # Build dataset — same shape as smoltldr (list of dicts with 'prompt' key)
    rows     = build_dataset(n=80)
    from datasets import Dataset
    dataset  = Dataset.from_list(rows)

    grpo_cfg = build_grpo_config(epochs)

    # ── Trainer — identical call signature to smoltldr ───────────────────────
    trainer = GRPOTrainer(
        model        = model, # type: ignore[bad-argument-type]
        reward_funcs = [reward_len, reward_style, reward_correct],  # ←→ smoltldr # type: ignore[bad-argument-type]
        args         = grpo_cfg,
        train_dataset = dataset,
    )

    trainer.train()

  # Merge LoRA weights and save — identical to smoltldr
    log.info("Merging LoRA weights...")
    
    # 1. Defend against top-level NoneType warnings during teardown
    if trainer is not None and getattr(trainer, "model", None) is not None:
        
        # Extract the true underlying model reference out of any trainer wrappers
        raw_model = trainer.model
        
        # 2. Check if the model has a Peft wrapper interface safely
        if hasattr(raw_model, "merge_and_unload"):
            # Explicitly type-cast to Any to bypass Pyrefly's missing-attribute check
            peft_model: Any = raw_model
            merged_model = peft_model.merge_and_unload()
            
            # Explicitly type-cast the returned base model to ensure save_pretrained is accepted
            typing.cast(Any, merged_model).save_pretrained(MODEL_SAVE_PATH)
        else:
            log.warning("trainer.model does not have 'merge_and_unload'. Saving model state directly.")
            # Use getattr or an inline cast to prevent Pyrefly from checking the base Module spec
            typing.cast(Any, raw_model).save_pretrained(MODEL_SAVE_PATH)
            
        # 3. Save the companion tokenizer asset safely
        if tokenizer is not None:
            typing.cast(Any, tokenizer).save_pretrained(MODEL_SAVE_PATH)
            
        log.info("Saved merged model to %s", MODEL_SAVE_PATH)
    else:
        log.error("Failed to save: trainer or trainer.model evaluates to None.")
# ══════════════════════════════════════════════════════════════════════════════
# 5.  DRY-RUN  (validates rewards without GPU — same idea as smoltldr unit test)
# ══════════════════════════════════════════════════════════════════════════════

def dry_run():
    """
    Test all three reward functions with known examples.
    Runs on CPU, no model required.
    """
    log.info("=== DRY-RUN: testing reward functions only (no GPU) ===")

    # Build a fixed scenario
    base_scenario = json.dumps({
        "delay_minutes":  90,
        "meeting_weight": 0.9,
        "attendees":      ["CEO Sarah Kim", "CFO Marcus Liu"],
        "proposed_times": ["4:00 PM", "5:00 PM", "3:30 PM tomorrow"],
        "is_formal":      True,
    })

    prompt = (
        "SCENARIO:\n"
        "  Delay: 90 minutes\n"
        "  Meeting: board review\n"
        "  Attendees: CEO Sarah Kim, CFO Marcus Liu\n"
        "  New times: 4:00 PM / 5:00 PM / 3:30 PM tomorrow\n"
        "  Tone: formal and professional\n\n"
        "NOTIFICATION:"
    )

    completions = [
        # Good — all four sub-scores + formal tone
        (
            "Dear CEO Sarah Kim and CFO Marcus Liu, I sincerely apologise — my flight "
            "is delayed 90 minutes. Could we reschedule our board review to 4:00 PM, "
            "5:00 PM, or tomorrow at 3:30 PM? I can also dial in from the car if none "
            "of these work. Regards."
        ),
        # Missing delay number and proposed times
        "Hi team, running a bit late today. Heads up — let me know what works.",
        # Over word limit (130+ words)
        " ".join(["word"] * 130) + " delayed 90 minutes Sarah Kim please note.",
    ]
    labels = ["GOOD (all criteria)", "VAGUE (missing key info)", "OVER LIMIT (too long)"]

    kwargs = {
        "scenario": [base_scenario] * len(completions),
        "prompts":  [prompt] * len(completions),
    }

    r_len   = reward_len(completions, **kwargs)
    r_sty   = reward_style(completions, **kwargs)
    r_cor   = reward_correct(completions, **kwargs)

    print(f"\n{'Label':<30} {'r_len':>6} {'r_sty':>6} {'r_cor':>6} {'words':>6}")
    print("─" * 60)
    for i, label in enumerate(labels):
        wc = len(completions[i].split())
        print(
            f"{label:<30} {r_len[i]:>6.3f} {r_sty[i]:>6.3f} {r_cor[i]:>6.3f} {wc:>6}"
        )
    print()
    log.info("=== Dry-run complete ===")


# ══════════════════════════════════════════════════════════════════════════════
# 6.  EVALUATION  (post-training quality check)
# ══════════════════════════════════════════════════════════════════════════════

def evaluate(checkpoint_path: str):
    """
    Load a saved checkpoint and score it on held-out scenarios.
    Target from capstone spec: avg composite ≥ 0.80 (≡ 4.0/5 manual score).
    """
    from transformers import pipeline as hf_pipeline
    log.info("Loading checkpoint: %s", checkpoint_path)

    tokenizer = AutoTokenizer.from_pretrained(checkpoint_path)
    model     = AutoModelForCausalLM.from_pretrained(
        checkpoint_path, torch_dtype="auto", device_map="auto"
    )
    gen_pipe  = hf_pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=MAX_COMPLETION, temperature=0.3, do_sample=True,
    )

    rows    = build_dataset(n=40, seed=99)   # held-out seed
    results = []

    for row in rows[:30]:
        prompt   = row["prompt"]
        scenario = row["scenario"]

        out      = gen_pipe(prompt)[0]["generated_text"]
        # Strip the prompt prefix, keep only the completion
        message  = out[len(prompt):].strip()

        kwargs   = {"scenario": [scenario], "prompts": [prompt]}
        rl  = reward_len([message],     **kwargs)[0]
        rs  = reward_style([message],   **kwargs)[0]
        rc  = reward_correct([message], **kwargs)[0]
        # Composite: same weights as capstone spec
        total = 0.2 * rl + 0.3 * rs + 0.5 * rc
        results.append({"r_len": rl, "r_style": rs, "r_correct": rc, "total": total})

    avg = {k: sum(r[k] for r in results) / len(results) for k in results[0]}
    log.info("── Evaluation results ──────────────────────────────")
    log.info("  r_correct (avg): %.3f", avg["r_correct"])
    log.info("  r_style   (avg): %.3f", avg["r_style"])
    log.info("  r_len     (avg): %.3f", avg["r_len"])
    log.info("  composite (avg): %.3f  (target ≥ 0.80)", avg["total"])
    log.info("────────────────────────────────────────────────────")
    return avg


# ══════════════════════════════════════════════════════════════════════════════
# 7.  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model",      choices=list(MODEL_IDS), default="phi3")
    p.add_argument("--epochs",     type=int, default=8)
    p.add_argument("--dry-run",    action="store_true")
    p.add_argument("--eval-only",  action="store_true")
    p.add_argument("--checkpoint", type=str, default=MODEL_SAVE_PATH)
    return p.parse_args()


def main():
    args = parse_args()

    if args.dry_run:
        dry_run()
        return

    if args.eval_only:
        evaluate(args.checkpoint)
        return

    train(model_key=args.model, epochs=args.epochs)
    evaluate(MODEL_SAVE_PATH)


if __name__ == "__main__":
    main()

