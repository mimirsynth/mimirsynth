// A stand-in for an OpenAI-compatible model, for api/tests/test_opencode_plugin.py: it records every request OpenCode makes and answers by
// script, so the test sees exactly what reached the model. No key, no account, and nothing leaves the machine.
//
//   node mock-llm.mjs <port> <log.jsonl> <project folder>
//
// A prompt that says WRITE_FILE gets a call to OpenCode's write tool (notes.md in the project), so the session changes a file; after
// the tool's result, or for any other prompt, it answers with text.
import { appendFileSync } from "node:fs";
import { createServer } from "node:http";

const [port, log, project] = [Number(process.argv[2]), process.argv[3], process.argv[4]];
const text = (c) => (typeof c === "string" ? c : Array.isArray(c) ? c.map((p) => p.text ?? "").join("\n") : "");

createServer((req, res) => {
  let raw = "";
  req.on("data", (d) => (raw += d));
  req.on("end", () => {
    let body = {};
    try {
      body = JSON.parse(raw || "{}");
    } catch {
      // logged as empty
    }
    appendFileSync(log, JSON.stringify({ url: req.url, body }) + "\n");
    if (!req.url.includes("chat/completions")) {
      res.writeHead(404);
      return res.end("{}");
    }
    const msgs = body.messages ?? [];
    const last = msgs.at(-1) ?? {};
    const all = msgs.map((m) => text(m.content)).join("\n");
    let delta, finish;
    if (last.role !== "tool" && all.includes("WRITE_FILE") && (body.tools ?? []).some((t) => t.function?.name === "write")) {
      const args = { filePath: `${project}/notes.md`, content: "the database runs on db-02\n" };
      delta = { role: "assistant", tool_calls: [{ index: 0, id: "call_1", type: "function", function: { name: "write", arguments: JSON.stringify(args) } }] };
      finish = "tool_calls";
    } else {
      delta = { role: "assistant", content: last.role === "tool" ? "Done: I wrote notes.md with where the database runs (db-02)." : "Mock answer." };
      finish = "stop";
    }
    const head = { id: "chatcmpl-mock", created: Math.floor(Date.now() / 1000), model: body.model ?? "echo" };
    const usage = { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 };
    if (body.stream) {
      res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
      res.write(`data: ${JSON.stringify({ ...head, object: "chat.completion.chunk", choices: [{ index: 0, delta, finish_reason: null }] })}\n\n`);
      res.write(`data: ${JSON.stringify({ ...head, object: "chat.completion.chunk", choices: [{ index: 0, delta: {}, finish_reason: finish }], usage })}\n\n`);
      res.end("data: [DONE]\n\n");
    } else {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ...head, object: "chat.completion", choices: [{ index: 0, message: delta, finish_reason: finish }], usage }));
    }
  });
}).listen(port, "127.0.0.1", () => console.log(`mock model on ${port}`));
