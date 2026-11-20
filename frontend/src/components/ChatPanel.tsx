import { useEffect, useRef } from "react";
import type { Config, Message } from "../types";

const prompts = [
  "Покажи только ночные смены",
  "Выведи топ-3 станка по доле брака",
  "Покажи простои длиннее 30 минут с причиной"
];

const shortPrompts: Record<string, string> = {
  "Покажи только ночные смены": "Ночные смены",
  "Выведи топ-3 станка по доле брака": "Топ-3 по браку",
  "Покажи простои длиннее 30 минут с причиной": "Простои > 30 мин"
};

interface Props {
  messages: Message[];
  config: Config | null;
  busy: boolean;
  question: string;
  onQuestion: (value: string) => void;
  onAsk: (question: string) => void;
  onReset: () => void;
}

export function ChatPanel({ messages, config, busy, question, onQuestion, onAsk, onReset }: Props) {
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [messages]);

  const mode = busy
    ? "Обрабатываю запрос…"
    : config?.mode === "llm" ? `LLM · ${config.model}` : "Демонстрационный режим";

  return (
    <aside className="panel chat">
      <header className="chat-head">
        <div>
          <h2>BI-ассистент</h2>
          <p className="chat-mode">{mode}</p>
        </div>
        <button type="button" className="button" disabled={busy} onClick={onReset}>
          Новый диалог
        </button>
      </header>

      <div className="conversation" ref={log} role="log" aria-live="polite">
        {messages.map((message, index) => (
          <article key={index} className={`message ${message.role}`}>
            <p className="message-meta">{message.role === "user" ? "Вы" : "Такт"}</p>
            <p className="message-text">{message.text}</p>
            {message.tips && message.tips.length > 0 && (
              <div className="tips">
                <strong>{message.tips.length === 1 ? "Рекомендация" : "Рекомендации"}</strong>
                {message.tips.map(tip => <p key={tip}>{tip}</p>)}
              </div>
            )}
          </article>
        ))}
      </div>

      <div className="chat-foot">
        <p className="prompt-title">Уточнить анализ</p>
        <div className="chips">
          {prompts.map(prompt => (
            <button key={prompt} type="button" disabled={busy} onClick={() => onAsk(prompt)}>
              {shortPrompts[prompt]}
            </button>
          ))}
        </div>
        <form
          className="ask"
          onSubmit={event => {
            event.preventDefault();
            onAsk(question);
          }}
        >
          <textarea
            value={question}
            onChange={event => onQuestion(event.target.value)}
            onKeyDown={event => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                onAsk(question);
              }
            }}
            maxLength={1500}
            rows={2}
            placeholder="Спросите о работе цеха…"
            aria-label="Ваш вопрос"
          />
          <button type="submit" className="button primary" disabled={busy || !question.trim()}>
            Отправить
          </button>
        </form>
      </div>
    </aside>
  );
}
