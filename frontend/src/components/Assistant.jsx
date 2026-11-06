import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import api, { errorMessage, tokenStore } from "../api";
import { useAuth } from "../context/AuthContext";
import { VoiceStream } from "../voice/VoiceStream";
import EstimateDisclaimer from "./EstimateDisclaimer";
import {
  initialVoice,
  microphoneError,
  voiceReducer,
  voiceStatus,
} from "./voiceConversationMachine";

const MAX_LENGTH = 500;
const CHANGING_TOOLS = ["book_visit", "cancel_visit", "raise_ticket"];
export const ACCOUNT_CHANGED = "goldloan:account-changed";

const WELCOME = {
  role: "bot",
  text: "Hello! I can estimate a gold loan, book a branch visit for valuation, tell you about your loan, and help with documents, timings and complaints. Write or speak in English, Hindi, Kannada, Malayalam or Tamil.",
};

// Try one of these: the first is the headline demo
const SUGGESTIONS = [
  "Mere paas 30 gram sona hai, kitna loan milega?",
  "What is my outstanding amount?",
  "What documents do I need?",
];

function announceChanges(toolsCalled) {
  if (toolsCalled?.some((tool) => CHANGING_TOOLS.includes(tool))) {
    window.dispatchEvent(new Event(ACCOUNT_CHANGED));
  }
}

/** The assistant for customers: a floating button that opens a conversation, by text or voice. */
export default function Assistant() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([WELCOME]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [voice, dispatchVoice] = useReducer(voiceReducer, initialVoice);
  const sessionId = useRef(null);
  const stream = useRef(null);
  const inputRef = useRef(null);
  const launcherRef = useRef(null);
  const endRef = useRef(null);

  const addMessage = useCallback((message) => setMessages((current) => [...current, message]), []);

  const stopVoice = useCallback(() => {
    stream.current?.stop();
    stream.current = null;
    dispatchVoice({ type: "stopped" });
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, sending, open, voice.serverState]);

  // The microphone never outlives the panel or the login
  useEffect(() => () => stream.current?.stop(), []);

  if (user?.role !== "customer") return null;

  function close() {
    stopVoice();
    setOpen(false);
    // After the panel unmounts, so focus has somewhere to land
    setTimeout(() => launcherRef.current?.focus(), 0);
  }

  function onVoiceEvent(event) {
    if (event.type === "ready") {
      sessionId.current = event.session_id; // text and voice share one conversation
    } else if (event.type === "transcript") {
      addMessage({ role: "user", text: event.text, lang: event.language });
    } else if (event.type === "reply") {
      addMessage({
        role: "bot",
        text: event.text,
        lang: event.language,
        disclaimer: event.disclaimer,
      });
      announceChanges(event.tools_called);
    } else if (event.type === "closed") {
      stream.current = null;
    }
    dispatchVoice(event);
  }

  async function startVoice() {
    setError("");
    dispatchVoice({ type: "starting" });
    const voiceStream = new VoiceStream({
      token: tokenStore.get(),
      sessionId: sessionId.current,
      onEvent: onVoiceEvent,
    });
    stream.current = voiceStream;
    try {
      await voiceStream.start();
    } catch (err) {
      stream.current = null;
      dispatchVoice({ type: "failed", message: microphoneError(err) });
    }
  }

  async function ask(text) {
    addMessage({ role: "user", text });
    setDraft("");
    setError("");
    setSending(true);
    try {
      const { data } = await api.post("/api/chat", {
        message: text,
        ...(sessionId.current && { session_id: sessionId.current }),
      });
      sessionId.current = data.session_id;
      addMessage({
        role: "bot",
        text: data.reply,
        lang: data.reply_language,
        disclaimer: data.disclaimer,
      });
      announceChanges(data.tools_called);
    } catch (err) {
      setError(errorMessage(err, "The assistant could not answer. Please try again."));
      setDraft(text); // nothing is lost: the message goes back into the box
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  function send(event) {
    event.preventDefault();
    const text = draft.trim();
    if (text && !sending) ask(text);
  }

  if (!open) {
    return (
      <button
        type="button"
        className="chat-launcher button primary"
        ref={launcherRef}
        onClick={() => setOpen(true)}
      >
        Ask the assistant
      </button>
    );
  }

  const voiceOn = voice.phase !== "off";
  const status = voiceStatus(voice);
  const problem = error || voice.error;

  return (
    <section
      className="chat-panel"
      aria-label="Gold loan assistant"
      onKeyDown={(event) => event.key === "Escape" && close()}
    >
      <header className="chat-header">
        <h2>Gold loan assistant</h2>
        <button type="button" className="button quiet" onClick={close}>
          Close
        </button>
      </header>

      <div className="chat-messages" role="log" aria-live="polite" tabIndex={0}>
        {messages.map((message, index) => (
          <div key={index} className={`chat-message ${message.role}`}>
            <span className="visually-hidden">
              {message.role === "user" ? "You: " : "Assistant: "}
            </span>
            <p lang={message.lang}>{message.text}</p>
            <EstimateDisclaimer text={message.disclaimer} lang={message.lang} />
          </div>
        ))}
        {messages.length === 1 && (
          <div className="suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="button quiet"
                disabled={sending}
                onClick={() => ask(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        {sending && <p className="chat-typing muted">The assistant is replying…</p>}
        <div ref={endRef} />
      </div>

      {problem && (
        <p className="error chat-error" role="alert">
          {problem}
        </p>
      )}

      <div className="chat-voice">
        <button
          type="button"
          className={`button ${voiceOn ? "danger" : ""}`}
          aria-pressed={voiceOn}
          disabled={voice.phase === "starting"}
          onClick={voiceOn ? stopVoice : startVoice}
        >
          {voiceOn ? "Stop voice" : "Speak"}
        </button>
        <p className="chat-voice-status muted" role="status">
          {status}
        </p>
      </div>

      <form className="chat-form" onSubmit={send}>
        <label htmlFor="chat-input" className="visually-hidden">
          Message to the assistant
        </label>
        <input
          id="chat-input"
          ref={inputRef}
          value={draft}
          maxLength={MAX_LENGTH}
          autoComplete="off"
          placeholder="Type your question"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" className="button primary" disabled={sending || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
