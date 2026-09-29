# Laya Text Judge

A small Django site that judges text with [Laya](https://huggingface.co/convaiinnovations/laya), an open decision model from Convai Innovations. Type or paste text (Vietnamese works) and the page answers 20 questions about it: intent, sentiment, toxicity, spam, urgency, churn risk and more. Every option probability and metric is shown as a bar, updated live as you type.

Laya does not generate text. It scores a fixed set of answers for each question, so every result is a probability distribution over known options.

## Requirements

- Python 3.10+ (developed on 3.13)
- About 4 GB of free disk space: roughly 2.8 GB for the model and 1 GB for the Python packages (PyTorch)
- Internet access on the first run, to download the model from Hugging Face

## Setup

```bash
git clone https://github.com/ducdinh-codehub/laya-demo.git
cd laya-demo

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run the website

```bash
.venv/bin/python manage.py runserver
```

Open http://127.0.0.1:8000 and wait for the **Model ready** pill in the top bar before typing.

- The **first run** downloads the model, which can take a few minutes.
- Later starts take about 5 seconds to load the model into memory.
- Once loaded, each analysis of all 20 questions takes about 0.2–0.3 s on a laptop CPU.

Stop the server with `Ctrl+C`.

### Useful options

```bash
# Use another port
.venv/bin/python manage.py runserver 8080

# Skip the Hugging Face update check once the model is cached
HF_HUB_OFFLINE=1 .venv/bin/python manage.py runserver
```

### Open it on your phone

The server only accepts `localhost` by default. To test from a phone on the same Wi-Fi:

1. Add your computer's local IP address to `ALLOWED_HOSTS` in `judge_site/settings.py`.
2. Run `.venv/bin/python manage.py runserver 0.0.0.0:8000`.
3. Open `http://<your-computer-ip>:8000` on the phone.

This makes the site reachable by anyone on the network, so only do it on a network you trust.

## Using the page

- **Live analysis** is on by default: results update as you type. Turn it off to analyze only when you press **Analyze**.
- **Checkpoint:** keep **Multilingual** for Vietnamese. **Auto** lets Laya pick, but it often classes Vietnamese typed without accents as English.
- **Review threshold:** answers with confidence below it are marked **Review** instead of **Auto**.
- **Question groups:** switch groups off to ask fewer questions. Their cards stay in the list, dimmed.

## Changing the questions

All questions live in `judge/questions.json`. Each has a type:

| Type | Answer | Example |
|---|---|---|
| `choice` | one of several named options | sentiment: positive / neutral / negative |
| `score` | a level on an ordered scale | urgency: low / medium / high |
| `noul` | probability that a yes/no statement is true | is this spam? |

Edit the file and restart the server. No code changes are needed.

## Test script

`main.py` runs the multilingual checkpoint on 12 labelled Vietnamese support tickets and prints accuracy and latency. It compares questions written in Vietnamese with the same questions in English.

```bash
.venv/bin/python main.py        # both
.venv/bin/python main.py vi     # Vietnamese questions only
.venv/bin/python main.py en     # English questions only
```

## Limitations

- **Confidence is not correctness.** Laya can be very confident and wrong. In testing it flagged ordinary support tickets as spam with 99% confidence. Label your own data and measure accuracy before relying on any question.
- **`score` questions are weak.** The Laya authors call this their weakest answer type, so the page marks them "experimental".
- **Long text is cut off.** The multilingual checkpoint reads about 760 tokens of text; the page warns when text is truncated.
- **No explanations.** Laya returns numbers, not reasons.

## Project layout

```
main.py                   Vietnamese accuracy and latency test
manage.py                 Django entry point
judge_site/               Django settings and URLs
judge/
  analyzer.py             runs Laya and gathers the results
  metrics.py              margin, entropy, odds and other derived numbers
  questions.json          the questions the page asks
  views.py                the page and the JSON API (/api/analyze, /api/status)
  templates/, static/     the page itself
```

## Deploying

This is a demo, set up for local use (`DEBUG` on, placeholder secret key). Before putting it online, set `DJANGO_SECRET_KEY` to a real secret, set `DJANGO_DEBUG=0`, and update `ALLOWED_HOSTS`.

## Credits

Laya is released by Convai Innovations under the Apache 2.0 license: [model card](https://huggingface.co/convaiinnovations/laya) · [source](https://github.com/NandhaKishorM/laya).
