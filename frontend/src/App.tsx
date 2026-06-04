import { useCallback, useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type FileNode = {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: FileNode[];
};

type ChatItem =
  | { kind: "user"; content: string }
  | { kind: "assistant"; content: string }
  | { kind: "tool"; name: string; arguments: unknown; result?: string };

function FileTree({
  nodes,
  depth,
  active,
  onOpen,
}: {
  nodes: FileNode[];
  depth: number;
  active: string | null;
  onOpen: (path: string) => void;
}) {
  return (
    <>
      {nodes.map((n) =>
        n.type === "dir" ? (
          <div key={n.path}>
            <div
              className="file-item"
              style={{ paddingLeft: 12 + depth * 12, fontWeight: 500 }}
            >
              📁 {n.name}
            </div>
            {n.children && (
              <FileTree
                nodes={n.children}
                depth={depth + 1}
                active={active}
                onOpen={onOpen}
              />
            )}
          </div>
        ) : (
          <button
            key={n.path}
            type="button"
            className={`file-item ${active === n.path ? "active" : ""}`}
            style={{ paddingLeft: 12 + depth * 12 }}
            onClick={() => onOpen(n.path)}
          >
            📄 {n.name}
          </button>
        )
      )}
    </>
  );
}

export default function App() {
  const [tree, setTree] = useState<FileNode[]>([]);
  const [openFile, setOpenFile] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [chat, setChat] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [config, setConfig] = useState<{
    model?: string;
    github_configured?: boolean;
  }>({});
  const wsRef = useRef<WebSocket | null>(null);
  const assistantBuf = useRef("");

  const loadTree = useCallback(async () => {
    const r = await fetch("/api/files/tree");
    const d = await r.json();
    setTree(d.tree || []);
  }, []);

  const loadConfig = useCallback(async () => {
    const r = await fetch("/api/config");
    setConfig(await r.json());
  }, []);

  const openPath = useCallback(async (path: string) => {
    const r = await fetch(`/api/files/read?path=${encodeURIComponent(path)}`);
    if (!r.ok) return;
    const d = await r.json();
    setOpenFile(path);
    setEditorContent(d.content);
  }, []);

  const saveFile = useCallback(async () => {
    if (!openFile) return;
    await fetch("/api/files/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: openFile, content: editorContent }),
    });
  }, [openFile, editorContent]);

  useEffect(() => {
    loadTree();
    loadConfig();
  }, [loadTree, loadConfig]);

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/chat`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ action: "ping" }));
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as {
        type: string;
        content?: string;
        name?: string;
        arguments?: unknown;
        result?: string;
      };

      if (msg.type === "text" && msg.content) {
        assistantBuf.current += msg.content;
        setChat((prev) => {
          const last = prev[prev.length - 1];
          if (last?.kind === "assistant") {
            return [
              ...prev.slice(0, -1),
              { kind: "assistant", content: assistantBuf.current },
            ];
          }
          return [...prev, { kind: "assistant", content: assistantBuf.current }];
        });
      }

      if (msg.type === "tool_start" && msg.name) {
        setChat((prev) => [
          ...prev,
          {
            kind: "tool",
            name: msg.name!,
            arguments: msg.arguments ?? {},
          },
        ]);
      }

      if (msg.type === "tool_end" && msg.name) {
        setChat((prev) => {
          const idx = [...prev].reverse().findIndex(
            (x) => x.kind === "tool" && x.name === msg.name && !x.result
          );
          if (idx < 0) return prev;
          const realIdx = prev.length - 1 - idx;
          const copy = [...prev];
          const item = copy[realIdx];
          if (item.kind === "tool") {
            copy[realIdx] = { ...item, result: msg.result };
          }
          return copy;
        });
        loadTree();
        if (openFile) openPath(openFile);
      }

      if (msg.type === "done" || msg.type === "error") {
        setBusy(false);
        assistantBuf.current = "";
        if (msg.type === "error" && msg.content) {
          setChat((prev) => [
            ...prev,
            { kind: "assistant", content: `⚠️ ${msg.content}` },
          ]);
        }
      }
    };

    return () => ws.close();
  }, [loadTree, openFile, openPath]);

  const sendMessage = () => {
    const text = input.trim();
    if (!text || busy || !wsRef.current || wsRef.current.readyState !== 1) return;

    const history = [
      ...chat
        .filter((c) => c.kind === "user" || c.kind === "assistant")
        .map((c) => ({
          role: c.kind,
          content: c.content,
        })),
      { role: "user", content: text },
    ];

    setChat((prev) => [...prev, { kind: "user", content: text }]);
    setInput("");
    setBusy(true);
    assistantBuf.current = "";

    wsRef.current.send(
      JSON.stringify({
        action: "chat",
        messages: history,
      })
    );
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">
          Rebel <span>Agent</span>
        </div>
        <span className="badge">{config.model || "Copilot"}</span>
        {config.github_configured && (
          <span className="badge" style={{ background: "#3fb95033", color: "var(--green)" }}>
            GitHub
          </span>
        )}
        <div style={{ flex: 1 }} />
        <div
          className={`status-dot ${busy ? "busy" : connected ? "connected" : ""}`}
          title={connected ? "Connected" : "Disconnected"}
        />
      </header>

      <aside className="sidebar">
        <FileTree
          nodes={tree}
          depth={0}
          active={openFile}
          onOpen={openPath}
        />
      </aside>

      <section className="editor-pane">
        <div className="editor-tabs">
          {openFile || "No file open"}
          {openFile && (
            <button
              type="button"
              className="send-btn"
              style={{ marginLeft: "auto", padding: "4px 10px", fontSize: 11 }}
              onClick={saveFile}
            >
              Save
            </button>
          )}
        </div>
        <div className="editor-body">
          {openFile ? (
            <Editor
              height="100%"
              language={
                openFile.endsWith(".py")
                  ? "python"
                  : openFile.endsWith(".ts") || openFile.endsWith(".tsx")
                    ? "typescript"
                    : openFile.endsWith(".json")
                      ? "json"
                      : "plaintext"
              }
              theme="vs-dark"
              value={editorContent}
              onChange={(v) => setEditorContent(v ?? "")}
              options={{
                fontFamily: "JetBrains Mono",
                fontSize: 13,
                minimap: { enabled: false },
                padding: { top: 12 },
              }}
            />
          ) : (
            <div className="empty-editor">
              Open a file from the sidebar or ask the agent to create one
            </div>
          )}
        </div>
      </section>

      <section className="chat-pane">
        <div className="chat-header">Agent Chat</div>
        <div className="messages">
          {chat.length === 0 && (
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
              Example: &quot;Add a login page and push to GitHub on branch
              feature/login&quot;
            </p>
          )}
          {chat.map((item, i) => {
            if (item.kind === "user") {
              return (
                <div key={i} className="msg user">
                  {item.content}
                </div>
              );
            }
            if (item.kind === "tool") {
              return (
                <details key={i} className="tool-card" open={!item.result}>
                  <summary>
                    🔧 {item.name}
                    {item.result ? " ✓" : " …"}
                  </summary>
                  <pre>{JSON.stringify(item.arguments, null, 2)}</pre>
                  {item.result && <pre>{item.result}</pre>}
                </details>
              );
            }
            return (
              <div key={i} className="msg assistant">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {item.content}
                </ReactMarkdown>
              </div>
            );
          })}
        </div>
        <div className="chat-input-wrap">
          <div className="chat-input-row">
            <textarea
              className="chat-input"
              rows={2}
              placeholder="Ask Rebel to code, fix bugs, run tests, push to GitHub…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              disabled={busy}
            />
            <button
              type="button"
              className="send-btn"
              onClick={sendMessage}
              disabled={busy || !input.trim()}
            >
              {busy ? "…" : "Send"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
