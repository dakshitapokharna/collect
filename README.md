# CollectAI: Real-Time Voice Agent for Loan Collections

Hi, I'm Dakshita Pokharna. I built this at the Sarvam AI Hackathon.

**🔗 Live demo: https://collect-static.vercel.app/**
(Use Chrome, allow the microphone, and wear headphones. The free backend sleeps when idle, so the first call can take ~30 seconds to wake up.)

CollectAI is a live voice-call simulator for loan collections. Pick an overdue customer, review their context (EMI, days overdue, last call, last conversation), and click **Call**. An AI agent named **Priya** talks to you in natural Hinglish, in real time.

## What it does

- **Remembers context.** It refers to the earlier call and broken promises, gently and without accusing.
- **Stays respectful.** It never threatens or shames, and it escalates real hardship cases to a human.
- **Pushes for commitment.** It asks for a specific date and amount, and offers a part-payment or a short extension when needed.
- **Allows interruption.** You can cut in mid-sentence, like a real phone call.
- **Reports after the call.** It gives the outcome, promise date and amount, customer sentiment, a compliance check and the next action.

## How it works

```
Browser mic ──(16 kHz audio over WebSocket)──► FastAPI server
                                                   │
        Sarvam Saaras  (streaming speech-to-text + voice activity detection)
                                                   ▼
        Sarvam-105B conversations  (streams the reply, sentence by sentence)
                                                   ▼
        Sarvam Bulbul v3  (text-to-speech) ──► audio plays in the browser
        Customer starts talking → agent stops instantly (barge-in)
```

## Tech stack

| Layer | Tech |
|---|---|
| Speech-to-text | Sarvam **Saaras v3** (streaming WebSocket, Hinglish code-mix) |
| Conversation | Sarvam **sarvam-105b-conversations** (streamed) |
| Text-to-speech | Sarvam **Bulbul v3** |
| Backend | Python, FastAPI, WebSockets (hosted on Render) |
| Frontend | Plain HTML/CSS/JS, Web Audio API (hosted on Vercel) |

## Run locally

```bash
git clone https://github.com/dakshitapokharna/collect.git
cd collect
copy .env.example .env        # then paste your own Sarvam API key into .env
pip install -r requirements.txt
python -m uvicorn server:app --port 8000
```

Open http://localhost:8000 in Chrome and allow the mic. Leave `static/config.js` as `window.BACKEND_URL = ""` to use the local server.

## Project structure

```
server.py          FastAPI app + WebSocket call loop (STT → LLM → TTS)
sarvam.py          Sarvam API helpers
customer.py        Customer data and the agent's rules (system prompt)
static/index.html  Three-screen UI: customers → details → live call
static/config.js   Backend URL used by the page
render.yaml        Render deployment config
.env.example       Sample env file (add your own SARVAM_API_KEY)
```

## Deployment

- **Backend:** Render (Blueprint from `render.yaml`). Set `SARVAM_API_KEY` in the Render dashboard.
- **Frontend:** Vercel, with Root Directory set to `static`. No environment variables needed.

## Notes

- Never commit your real `.env`. Each user supplies their own `SARVAM_API_KEY`.
- This is a demo with one sample customer and fictional data.
- Real phone calls (Twilio/Exotel) would be a next step.
