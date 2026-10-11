import hashlib
import json
import re

import streamlit as st

import sarvam
from customer import CUSTOMER as C, OPENING_INSTRUCTION, SUMMARY_PROMPT, SYSTEM_PROMPT

st.set_page_config(page_title="Collections Call Portal", page_icon="📞", layout="wide")


def init():
    st.session_state.setdefault("active", False)
    st.session_state.setdefault("history", [])  # list of {"role": "assistant"|"user", "content": str}
    st.session_state.setdefault("last_audio_hash", None)
    st.session_state.setdefault("play_audio", None)
    st.session_state.setdefault("report", None)


def llm_messages():
    return [{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.history


def bot_turn(first: bool = False):
    msgs = llm_messages()
    if first:
        msgs = msgs + [{"role": "user", "content": OPENING_INSTRUCTION}]
    reply = sarvam.chat(msgs)
    st.session_state.history.append({"role": "assistant", "content": reply})
    try:
        st.session_state.play_audio = sarvam.speak(reply)
    except Exception as e:
        st.session_state.play_audio = None
        st.warning(f"Voice playback failed: {e}")


def start_call():
    st.session_state.history = []
    st.session_state.report = None
    st.session_state.last_audio_hash = None
    st.session_state.active = True
    with st.spinner("Calling..."):
        bot_turn(first=True)


def end_call():
    st.session_state.active = False
    st.session_state.play_audio = None
    transcript = "\n".join(
        f"{'Agent' if m['role'] == 'assistant' else 'Customer'}: {m['content']}"
        for m in st.session_state.history
    )
    with st.spinner("Generating call report..."):
        raw = sarvam.chat(
            [{"role": "user", "content": SUMMARY_PROMPT + transcript}], temperature=0.1
        )
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        st.session_state.report = json.loads(m.group(0)) if m else {"summary": raw}
    except json.JSONDecodeError:
        st.session_state.report = {"summary": raw}


def handle_audio(audio):
    data = audio.getvalue()
    h = hashlib.md5(data).hexdigest()
    if h == st.session_state.last_audio_hash:
        return
    st.session_state.last_audio_hash = h
    with st.spinner("Listening..."):
        text = sarvam.transcribe(data)
    if not text:
        st.warning("Couldn't hear anything, please try again.")
        return
    st.session_state.history.append({"role": "user", "content": text})
    with st.spinner("Priya is replying..."):
        bot_turn()


init()
st.title("📞 Collections Call Portal")
st.caption("Real-time call simulation powered by Sarvam AI (Saarika · Sarvam-M · Bulbul)")

left, right = st.columns([1, 2])

with left:
    st.subheader("Customer")
    st.markdown(f"### {C['name']}")
    st.metric("EMI due", f"₹{C['emi']:,}")
    st.metric("Days overdue", C["days_overdue"])
    st.write(f"**Loan:** {C['loan']}  \n**Outstanding:** ₹{C['outstanding']:,}")
    st.write(f"**Last call:** {C['last_call']}")
    st.info(f"**Last conversation:** {C['last_convo']}")
    st.write(f"**History:** {C['history']}")

with right:
    st.subheader("Call")
    if not st.session_state.active:
        st.button("📞 Start Call", type="primary", on_click=start_call)
    else:
        st.button("🔴 End Call", on_click=end_call)

    for m in st.session_state.history:
        with st.chat_message("assistant" if m["role"] == "assistant" else "user"):
            st.write(m["content"])

    if st.session_state.active:
        if st.session_state.play_audio:
            st.audio(st.session_state.play_audio, format="audio/wav", autoplay=True)
        audio = st.audio_input("🎤 Reply as the customer (tap to record, tap again to stop)")
        if audio is not None:
            try:
                handle_audio(audio)
            except Exception as e:
                st.error(f"Error: {e}")
            else:
                st.rerun()

    if st.session_state.report:
        r = st.session_state.report
        st.subheader("Call report")
        c1, c2, c3 = st.columns(3)
        c1.metric("Outcome", str(r.get("outcome", "-")).replace("_", " "))
        c2.metric("Promise date", r.get("promise_date") or "-")
        c3.metric("Amount", f"₹{r['promise_amount']}" if r.get("promise_amount") else "-")
        st.write(f"**Customer sentiment:** {r.get('customer_sentiment', '-')}")
        st.write(f"**Agent compliant:** {'✅' if r.get('agent_compliance') else '⚠️'}")
        st.write(f"**Summary:** {r.get('summary', '-')}")
        st.write(f"**Next action:** {r.get('next_action', '-')}")
