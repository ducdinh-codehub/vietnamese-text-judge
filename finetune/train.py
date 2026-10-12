"""Fine-tune Laya's multilingual checkpoint on Vietnamese school multiple-choice questions.

    .venv/bin/python finetune/train.py --eval-only                 # score the original checkpoint
    .venv/bin/python finetune/train.py --limit 300 --epochs 1      # quick smoke test
    .venv/bin/python finetune/train.py                             # full run

Reads finetune/data/processed/{train,val,test}.jsonl (finetune/build_dataset.py) and writes
checkpoints/laya-vi-school/ at the project root, a directory laya.Agent loads like the Hub
checkpoint and the web app picks up from there:

    Agent("checkpoints/laya-vi-school")

Questions are fed exactly the way the web app's worksheet page asks them: the stem as
{"body": stem}, the options as choice criteria {"A": text, ...} and the INSTRUCTIONS below. This
script does not import the web app; if the page's prompt changes, change INSTRUCTIONS to match.

The training data is non-commercial / research-only (see finetune/README.md), and so is a checkpoint
trained on it.
"""

import argparse
import json
import math
import os
import random
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path

# The checkpoint is already in the local cache; do not ask the Hub (it rate-limits us).
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402
from safetensors import safe_open  # noqa: E402
from safetensors.torch import save_file  # noqa: E402

from laya.agent import Agent  # noqa: E402
from laya.common import QTYPES, build_sequence, collate_items, ece_score  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # project root: checkpoints/ lives there, shared with the web app
DATA = HERE / "data" / "processed"
# The prompt judge/worksheet.py sends with every question (LAYA_INSTRUCTIONS there).
INSTRUCTIONS = "Which option correctly answers the question?"
REPO, SUBFOLDER = "convaiinnovations/laya", "multilingual"
LETTERS = "ABCDE"
# An option that names another option ("Cả A và B đều đúng") must keep its letter.
NAMES_A_LETTER = re.compile(r"(?<![A-Za-zÀ-ỹ])[A-E](?![A-Za-zÀ-ỹ])")


def load_rows(split, limit=None, seed=0):
    rows = [json.loads(line) for line in open(DATA / f"{split}.jsonl", encoding="utf-8")]
    rows = [r for r in rows if r["usable"]]
    if limit and len(rows) > limit:
        rows = random.Random(seed).sample(rows, limit)
    return rows


def shuffled(row, rng):
    """(options, answer) with the option texts moved to random letters, when that is safe."""
    letters = list(row["options"])
    texts = [row["options"][k] for k in letters]
    if rng is None or any(NAMES_A_LETTER.search(t) for t in texts):
        return row["options"], row["answer"]
    order = list(range(len(texts)))
    rng.shuffle(order)
    options = {LETTERS[i]: texts[j] for i, j in enumerate(order)}
    answer = LETTERS[order.index(letters.index(row["answer"]))]
    return options, answer


def encode(tok, cfg, row, max_len, rng=None):
    options, answer = shuffled(row, rng)
    q = {"t": "choice", "ins": INSTRUCTIONS, "crit": options}
    ids, markers = build_sequence(tok, {"body": row["stem"]}, q, max_len, cfg.get("head_max_len", 192))
    if len(markers) != len(options):  # an option was cut off: cannot be scored
        return None
    return {"ids": ids, "markers": markers, "qtype": QTYPES["choice"],
            "label": list(options).index(answer), "id": row["id"]}


def batches(items, batch_size, shuffle_rng=None, max_tokens=None):
    """Batches of similar length (less padding), in random order when training.

    `max_tokens` caps questions x padded length, so a batch of long questions gets fewer of them.
    """
    order = sorted(range(len(items)), key=lambda i: len(items[i]["ids"]))
    chunks, chunk = [], []
    for i in order:
        longest = len(items[i]["ids"])  # sorted, so the newest item is the longest
        if chunk and (len(chunk) == batch_size or (max_tokens and (len(chunk) + 1) * longest > max_tokens)):
            chunks.append(chunk)
            chunk = []
        chunk.append(i)
    if chunk:
        chunks.append(chunk)
    if shuffle_rng:
        shuffle_rng.shuffle(chunks)
    for chunk in chunks:
        yield [items[i] for i in chunk]


def to_device(b, device):
    return {k: v.to(device) if torch.is_tensor(v) else v for k, v in b.items()}


@torch.no_grad()
def predict(model, tok, cfg, rows, device, max_len, batch_size=32):
    """{row id: logits over its options} with the model in eval mode."""
    model.eval()
    items = [it for it in (encode(tok, cfg, r, max_len) for r in rows) if it]
    out = {}
    for group in batches(items, batch_size):
        b = to_device(collate_items([[it] for it in group], tok.pad_token_id), device)
        logits, _ = model(b["input_ids"], b["attention_mask"], b["marker_pos"], b["marker_mask"], b["qtype"])
        for it, row in zip(group, logits.float().cpu().numpy()):
            out[it["id"]] = row[:len(it["markers"])]
    return out


def evaluate(rows, logits, temperature=1.0):
    """Accuracy overall and per slice, plus calibration, from `predict` output."""
    by = defaultdict(lambda: [0, 0])
    conf, correct, nll, chance = [], [], [], []
    skipped = 0
    for r in rows:
        z = logits.get(r["id"])
        if z is None:
            skipped += 1
            continue
        p = np.exp((z - z.max()) / temperature)
        p /= p.sum()
        gold = list(r["options"]).index(r["answer"])
        ok = int(p.argmax() == gold)
        conf.append(p.max())
        correct.append(ok)
        nll.append(-math.log(max(p[gold], 1e-12)))
        chance.append(1 / len(p))
        for key in ("all", f"source:{r['source']}", f"level:{r['level']}", f"{r['level']}/{r['subject']}"):
            by[key][0] += ok
            by[key][1] += 1
    conf, correct = np.array(conf), np.array(correct)
    return {
        "n": len(correct), "skipped": skipped,
        "accuracy": float(correct.mean()), "chance": float(np.mean(chance)),
        "nll": float(np.mean(nll)), "ece": ece_score(conf, correct),
        "slices": {k: {"accuracy": v[0] / v[1], "n": v[1]} for k, v in sorted(by.items())},
    }


def fit_temperature(rows, logits):
    """The temperature that minimises NLL on `rows` (searched over the range Laya accepts)."""
    grid = np.exp(np.linspace(math.log(0.5), math.log(5.0), 60))
    return float(min(grid, key=lambda t: evaluate(rows, logits, t)["nll"]))


def print_report(name, res):
    print(f"\n== {name}: accuracy {res['accuracy']:.1%} on {res['n']} questions "
          f"(chance {res['chance']:.1%}), NLL {res['nll']:.3f}, ECE {res['ece']:.3f}"
          + (f", {res['skipped']} too long to score" if res["skipped"] else ""))
    for key, s in res["slices"].items():
        if key != "all" and s["n"] >= 10:
            print(f"   {key:<34} {s['accuracy']:6.1%}  (n={s['n']})")


def save_checkpoint(model, src_dir, out_dir, cfg, temperature, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("tokenizer", "encoder"):
        if (src_dir / sub).exists():
            shutil.copytree(src_dir / sub, out_dir / sub, dirs_exist_ok=True)
    # Same tensor names as the original file, so Agent's strict load accepts it.
    with safe_open(str(src_dir / "model.safetensors"), "pt") as f:
        names = set(f.keys())
    state = {k: v.detach().to("cpu").contiguous() for k, v in model.state_dict().items() if k in names}
    missing = names - set(state)
    if missing:
        raise RuntimeError(f"checkpoint would lack {sorted(missing)[:5]}")
    save_file(state, str(out_dir / "model.safetensors"))
    cfg = dict(cfg)
    buckets = dict(cfg.get("temperature_by_options", {}))
    buckets.update({"choice:2": temperature, "choice:3-5": temperature})
    cfg["temperature_by_options"] = buckets
    cfg["model_name"] = "laya-vi-school"
    cfg["training"] = {**cfg.get("training", {}), "fine_tuned_from_checkpoint": True, "vi_school": meta}
    (out_dir / "rl_agent_config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-5, help="encoder learning rate")
    ap.add_argument("--head-lr", type=float, default=1e-4, help="decision head learning rate")
    ap.add_argument("--max-len", type=int, default=384, help="tokens per question while training")
    ap.add_argument("--max-tokens", type=int, default=3072,
                    help="cap on questions x tokens per batch; lower it if the Mac starts swapping")
    ap.add_argument("--limit", type=int, help="use at most this many train questions (smoke tests)")
    ap.add_argument("--eval-limit", type=int, help="use at most this many val/test questions")
    ap.add_argument("--eval-only", action="store_true", help="only score the starting checkpoint")
    ap.add_argument("--init", help="start from this checkpoint directory instead of the Hub one")
    ap.add_argument("--out", default="checkpoints/laya-vi-school")
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    src_dir = Path(args.init) if args.init else Path(
        snapshot_download(REPO, allow_patterns=[f"{SUBFOLDER}/*"])) / SUBFOLDER
    agent = Agent(str(src_dir), device=args.device)
    model, tok, cfg, device = agent.model.float(), agent.tok, agent.cfg, agent.device
    print(f"checkpoint {src_dir} on {device}")

    train = load_rows("train", args.limit, args.seed)
    val = load_rows("val", args.eval_limit, args.seed)
    test = load_rows("test", args.eval_limit, args.seed)
    print(f"questions: train {len(train)}, val {len(val)}, test {len(test)}")
    eval_len = cfg.get("max_len", 1024)  # score at the length the app uses

    t0 = time.time()
    base_val = predict(model, tok, cfg, val, device, eval_len)
    print_report("val, before fine-tuning", evaluate(val, base_val))
    print(f"   ({time.time() - t0:.0f}s)")
    if args.eval_only:
        base_test = predict(model, tok, cfg, test, device, eval_len)
        print_report("test, before fine-tuning", evaluate(test, base_test))
        return

    # Keep the 256k-token embedding table (most of the parameters) as it is: it is shared by every
    # language Laya reads, and freezing it saves the memory its gradients and Adam state would use.
    for p in model.encoder.embeddings.parameters():
        p.requires_grad = False
    for p in model.act_head.parameters():  # the act head is not trained by this objective
        p.requires_grad = False
    # Recompute activations in the backward pass instead of keeping them: an 18 GB Mac ran out of
    # memory and swapped to a standstill without this.
    model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.head_checkpointing = True
    head = [p for n, p in model.named_parameters()
            if p.requires_grad and not n.startswith("encoder.")]
    enc = [p for n, p in model.named_parameters() if p.requires_grad and n.startswith("encoder.")]
    print(f"training {sum(p.numel() for p in enc + head) / 1e6:.0f}M of "
          f"{sum(p.numel() for p in model.parameters()) / 1e6:.0f}M parameters")
    opt = torch.optim.AdamW([{"params": enc, "lr": args.lr}, {"params": head, "lr": args.head_lr}],
                            weight_decay=0.01)
    # Upper bound on optimizer steps; the token cap can only add batches, so count them for real.
    steps = args.epochs * sum(1 for _ in batches(
        [it for it in (encode(tok, cfg, r, args.max_len) for r in train) if it], args.batch_size,
        max_tokens=args.max_tokens))
    warmup = max(1, int(0.06 * steps))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min((s + 1) / warmup, max(0.0, (steps - s) / max(1, steps - warmup))))

    rng = random.Random(args.seed)
    best = {"accuracy": evaluate(val, base_val)["accuracy"], "epoch": 0, "state": None}
    step = 0
    for epoch in range(1, args.epochs + 1):
        # Fresh option shuffles every epoch, so the model cannot learn which letter tends to be right.
        items = [it for it in (encode(tok, cfg, r, args.max_len, rng) for r in train) if it]
        model.train()
        t0, seen, loss_sum, hits = time.time(), 0, 0.0, 0
        for group in batches(items, args.batch_size, rng, args.max_tokens):
            b = to_device(collate_items([[it] for it in group], tok.pad_token_id), device)
            logits, _ = model(b["input_ids"], b["attention_mask"], b["marker_pos"], b["marker_mask"], b["qtype"])
            loss = F.cross_entropy(logits.float(), b["label"])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(enc + head, 1.0)
            opt.step()
            sched.step()
            step += 1
            seen += len(group)
            loss_sum += loss.item() * len(group)
            hits += (logits.argmax(-1) == b["label"]).sum().item()
            if step % 50 == 0:
                if device.type == "mps":
                    torch.mps.empty_cache()
                rate = seen / (time.time() - t0)
                mem = (f"gpu mem {torch.mps.driver_allocated_memory() / 2**30:.1f} GB  "
                       if device.type == "mps" else "")
                print(f"epoch {epoch} step {step}/{steps}  loss {loss_sum / seen:.3f}  "
                      f"train acc {hits / seen:.1%}  {rate:.1f} q/s  {mem}"
                      f"eta {(len(items) - seen) / rate / 60:.0f} min", flush=True)
        res = evaluate(val, predict(model, tok, cfg, val, device, eval_len))
        print_report(f"val after epoch {epoch} (train loss {loss_sum / max(1, seen):.3f})", res)
        if res["accuracy"] > best["accuracy"]:
            best = {"accuracy": res["accuracy"], "epoch": epoch,
                    "state": {k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()}}

    if best["state"] is None:
        print("\nFine-tuning never beat the original checkpoint on val; nothing saved.")
        return
    model.load_state_dict(best["state"])
    val_logits = predict(model, tok, cfg, val, device, eval_len)
    temperature = fit_temperature(val, val_logits)
    test_logits = predict(model, tok, cfg, test, device, eval_len)
    test_res = evaluate(test, test_logits, temperature)
    print(f"\nbest epoch {best['epoch']}, fitted temperature {temperature:.2f}")
    print_report("test, after fine-tuning", test_res)

    meta = {"epochs": args.epochs, "best_epoch": best["epoch"], "lr": args.lr, "head_lr": args.head_lr,
            "batch_size": args.batch_size, "max_len": args.max_len, "train_questions": len(train),
            "seed": args.seed, "val_accuracy": best["accuracy"], "test_accuracy": test_res["accuracy"],
            "data": "finetune/data/processed (finetune/build_dataset.py); non-commercial / research only",
            "instructions": INSTRUCTIONS}
    out = ROOT / args.out
    save_checkpoint(model, src_dir, out, cfg, temperature, meta)
    (out / "eval_test.json").write_text(json.dumps(test_res, indent=2, ensure_ascii=False))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
