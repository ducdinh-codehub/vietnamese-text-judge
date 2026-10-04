<div align="center">

# ⚖️ Laya Text Judge

**Paste a message. Get instant judgements, scam warnings and emotions. Runs on your laptop, no API key.**

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-5-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Model](https://img.shields.io/badge/model-Laya-FFD21E?logo=huggingface&logoColor=black)](https://huggingface.co/convaiinnovations/laya)
[![Tiếng Việt](https://img.shields.io/badge/ti%E1%BA%BFng%20vi%E1%BB%87t-supported-DA251D)](#)

<img src="docs/images/text-judge.png" alt="Text Judge page scoring a Vietnamese billing complaint on 20 questions" width="900">

</div>

## ✨ Features

- 🧠 **Text Judge**: 20 questions (intent, sentiment, toxicity, spam, urgency…) answered live as you type
- 🛡️ **Scam checker**: spots Vietnamese SMS, Zalo and email scams and explains why
- 💬 **Emotion checker**: 8 emotions, plus the words that show them
- 🔒 **100% local**: nothing you paste leaves your machine

## 🚀 Quick start

```bash
git clone https://github.com/ducdinh-codehub/laya-demo.git
cd laya-demo
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver
```

Open http://127.0.0.1:8000. The first run downloads the model (~2.8 GB).

## 📸 Screenshots

| Scam checker | Emotion checker |
|---|---|
| <img src="docs/images/scam-checker.png" alt="Scam checker flagging a fake bank SMS as dangerous"> | <img src="docs/images/emotion-checker.png" alt="Emotion checker reading a thank-you message as happy"> |

## ⚠️ Good to know

- Results can be confidently wrong. Test on your own messages before relying on them.
- Change the questions in `judge/questions.json`, no code needed.
- Built for local use. Harden it before putting it online.

## 🙏 Credits

Built on [Laya](https://huggingface.co/convaiinnovations/laya) by Convai Innovations (Apache 2.0).
