# Issue #5 Codex MCP Attachment Root-Cause Report

Date: 2026-05-13  
Repository: `paperorchestra-for-codex`  
Issue: [#5 MCP registers and responds but native Codex tools may not attach to active session](https://github.com/kosh7707/paperorchestra-for-codex/issues/5)

## Executive summary

A full Codex session restart is necessary after adding or changing MCP server configuration, but in this case restart is **not sufficient**.

The most strongly supported root cause is a **stdio transport framing mismatch**:

- In the reproduced container, Codex CLI `0.129.0` was observed sending its MCP stdio `initialize` request as newline-delimited JSON.
- The current PaperOrchestra MCP server reads and writes only `Content-Length` framed messages.
- Therefore Codex can start the `paperorchestra-mcp` subprocess and send `initialize`, but the server does not parse that input as a complete request, sends no response, and Codex eventually reports MCP startup timeout.
- A temporary framing bridge that converted Codex newline JSON to PaperOrchestra `Content-Length` framing caused Codex to successfully list tools and call `mcp__paperorchestra__status`.

So the user report — “I definitely restarted Codex, but the MCP tools still did not attach” — is consistent with the observed failure.

## Scope and constraints

This investigation was read-only with respect to repository code until this report was written. Earlier diagnostic wrappers were temporary files under `/tmp` or inside `docker run --rm` containers and were not committed.

Validated surfaces:

- repository code and docs
- GitHub issue #5
- container image `paperorchestra-ubuntu-tools:24.04`
- Codex CLI `0.129.0` inside the container
- raw MCP protocol probes
- temporary proxy/bridge instrumentation around `paperorchestra-mcp`

Evidence retention note: the proxy/bridge wrappers were temporary diagnostics, but the exact probe commands and abbreviated transcripts are preserved in the appendix of this report so the evidence is reproducible.

Tool inventory note: issue #5 originally mentioned an older smoke output with 57 tools. The current checkout exposed 58 tools during this investigation, so tool count differences should not be treated as the root cause by themselves.

Not yet validated:

- Codex CLI `0.130.0` or later
- Codex App behavior separate from Codex CLI
- a permanent patched PaperOrchestra MCP implementation

## Important distinction: restart-required vs restart-insufficient

Repository docs, observed Codex behavior, and official Codex MCP lifecycle/config documentation support the statement that a new session is required after MCP config changes.

However, issue #5 is not explained by restart alone. In the reproduced container case, Codex did start a new session and attempted to start the `paperorchestra` MCP server, but startup timed out.

The failure sequence is more precise:

1. Config can register `paperorchestra`.
2. Raw smoke can pass if it talks to the server using `Content-Length` framing.
3. Codex opens a new session and sends newline-delimited JSON to the server.
4. PaperOrchestra MCP waits for `Content-Length` headers and returns no response.
5. Codex times out MCP startup.
6. No `mcp__paperorchestra__...` tools appear in the session.

## Evidence

### 1. Current PaperOrchestra MCP server expects `Content-Length` framing

`paperorchestra/mcp_server.py` reads header lines until a blank line, then requires a `content-length` header:

```python
length = int(headers.get("content-length", "0"))
if length <= 0:
    return None
payload = sys.stdin.buffer.read(length)
```

It also writes responses with `Content-Length` headers:

```python
sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
sys.stdout.buffer.write(raw)
```

Relevant code: `paperorchestra/mcp_server.py`, `_read_message()` and `_write_message()`.

### 2. Codex CLI actually sent newline-delimited JSON

A temporary proxy wrapper was placed in front of `paperorchestra-mcp`. It logged the first Codex-to-server message as a single JSON line:

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"elicitation":{}},"clientInfo":{"name":"codex-mcp-client","title":"Codex","version":"0.129.0"}}}
```

There was no `Content-Length:` header. With the unmodified server behind the proxy, Codex reported the tool unavailable / startup did not complete.

### 3. Direct newline-framed input produces no server response

A direct probe sent the same newline JSON shape to the current `paperorchestra-mcp` process.

Observed result:

```text
--- newline-framed direct test (expect no response/timeout with current server) ---
rc=0 stdout_bytes=0 stderr_bytes=0
```

This matches the code path: `_read_message()` reads the JSON line, does not find a blank header terminator with `content-length`, then exits/returns without a JSON-RPC response.

### 4. Direct `Content-Length` input succeeds

The same initialize request sent with `Content-Length` framing returned a response:

```text
--- content-length direct test (expect response) ---
ready True
Content-Length: 169

{"jsonrpc": "2.0", "id": 0, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "paperorchestra-mcp", "version": "0.1.0"}, "capabilities": {"tools": {}}}}
```

This explains why the existing smoke script can pass even though Codex does not attach tools.

### 5. A temporary framing bridge makes Codex attach and call the tool

A temporary bridge converted:

- Codex newline JSON → PaperOrchestra `Content-Length`
- PaperOrchestra `Content-Length` → Codex newline JSON

With that bridge, `codex exec --json` produced a real MCP tool call:

```json
{
  "type": "item.started",
  "item": {
    "type": "mcp_tool_call",
    "server": "paperorchestra",
    "tool": "status",
    "arguments": {"cwd": "/tmp/po-bridge"}
  }
}
```

The result was:

```text
FileNotFoundError: No current PaperOrchestra session. Run `paperorchestra init` first.
```

That error is expected because `/tmp/po-bridge` had no PaperOrchestra session. The important part is that Codex successfully exposed and invoked `mcp__paperorchestra__status` once framing was adapted.

### 6. Existing smoke script does not validate Codex-compatible transport

`paperorchestra/mcp_smoke.py` uses the same `Content-Length` framing as the current server. It also explicitly says active Codex session attachment is not checked.

Repository docs already warn that smoke and `codex mcp list` are not proof of active session attachment:

- `README.md` says the MCP smoke checks config, executable availability, `initialize`, `tools/list`, expected tools, and a harmless `status` call, but does **not** prove the current Codex conversation received `mcp__paperorchestra__...` tools.
- `scripts/register-codex-mcp.sh` prints that `codex mcp list` shows config registration, not active session attachment/tool injection.

The missing piece is that the smoke also does not exercise the same newline-framed transport Codex CLI used in the container.

## Ranked root-cause assessment

| Rank | Candidate | Confidence | Assessment |
| --- | --- | --- | --- |
| 1 | stdio framing mismatch: Codex newline JSON vs PaperOrchestra `Content-Length` only | Very high | Direct proxy captured Codex newline JSON; direct newline probe gets no response; bridge conversion makes Codex tool call work. |
| 2 | Existing smoke false-positive for Codex compatibility | High | Smoke uses server-compatible `Content-Length` framing and explicitly does not check active session attachment. |
| 3 | Stale absolute `.venv` path in container config | High as a separate failure mode | `--use-local-venv` stores an absolute checkout path. If `/root/.codex` persists but repo/venv does not, command target disappears. This explains container recreation failures, but not the kept-container restart case. |
| 4 | Protocol version mismatch (`2025-06-18` request vs `2024-11-05` response) | Medium | Codex accepted the bridge-mediated response in this test, so it is not the primary blocker, but it should be cleaned up. |
| 5 | Tool schema ingestion problem | Low for the tested `status` attach path | Codex received the current 58-tool `tools/list` response through the bridge and called `status`; however, full behavior across every tool/schema remains unvalidated. |
| 6 | Simple failure to restart Codex | Low for issue #5 | Restart is required in general, but reproduced failure persists after new session because framing prevents initialization. |

## Why the user's report is plausible

A user who cloned this repository could correctly perform all of these steps:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
./scripts/register-codex-mcp.sh --use-local-venv
# restart Codex completely
```

Even then, Codex CLI `0.129.0` can still fail to attach tools because the server does not understand the newline JSON initialize request sent by Codex.

In that case, the user sees exactly this confusing split-brain state:

- `codex mcp list` can show config registration.
- `scripts/smoke-paperorchestra-mcp.py` can pass.
- A new Codex session still has no `mcp__paperorchestra__...` tools.

The reproduced evidence indicates this failure mode is not explained by user restart/config error alone; it is a compatibility gap between the server transport implementation and the observed Codex CLI stdio MCP client behavior.

## Recommended implementation work

### 1. Add newline-delimited JSON support to the MCP server

Preferred implementation: dual framing support.

`_read_message()` should support both:

1. newline-delimited JSON messages
2. existing `Content-Length` framed messages

Suggested approach:

- Read the first non-empty line.
- If the line starts with `{`, parse it as one complete newline-delimited JSON-RPC message.
- Otherwise, treat it as a header line and continue reading headers until blank line, preserving current `Content-Length` behavior.
- Track the detected transport mode for the process or current response.

`_write_message()` should respond in the same framing mode detected from the client:

- newline client input → newline JSON output
- `Content-Length` client input → `Content-Length` output

This preserves compatibility with the current smoke script and any clients that still use header framing, while adding Codex CLI compatibility.

### 2. Update protocol version negotiation

Codex sent:

```json
"protocolVersion":"2025-06-18"
```

Current server always returns:

```json
"protocolVersion":"2024-11-05"
```

Since the observed bridge test succeeded anyway, this is not the first blocker. Still, the server should implement explicit version negotiation:

- support `2025-06-18` if the implemented methods/schemas are compatible
- otherwise respond with the latest supported version and document the compatibility limit
- include tests for Codex's requested version

### 3. Expand MCP smoke coverage

Add a transport mode to `scripts/smoke-paperorchestra-mcp.py`:

```bash
scripts/smoke-paperorchestra-mcp.py --transport content-length --json
scripts/smoke-paperorchestra-mcp.py --transport newline --json
```

Or make both transports part of the default smoke.

Minimum assertions for both transports:

- `initialize` returns serverInfo
- `notifications/initialized` is accepted
- `tools/list` returns expected tool names
- `tools/call status` reaches the server

### 4. Add a Codex attach smoke

Add a separate smoke for actual Codex integration, because raw MCP smoke is still only a proxy.

Proposed script:

```bash
scripts/smoke-codex-mcp-attach.sh
```

Suggested behavior:

1. Create a temporary Codex config with only PaperOrchestra MCP enabled.
2. Register the local server command.
3. Set `enabled_tools = ["status"]` to reduce noise.
4. Run:

   ```bash
   codex exec --json --dangerously-bypass-approvals-and-sandbox \
     'Call mcp__paperorchestra__status for the current cwd.'
   ```

5. Pass if JSONL contains:

   ```json
   "type":"mcp_tool_call",
   "server":"paperorchestra",
   "tool":"status"
   ```

This would have caught issue #5 directly.

### 5. Harden container registration guidance

Keep this as a separate fix from the framing bug.

Current `--use-local-venv` stores an absolute path such as:

```toml
command = "/root/paperorchestra-for-codex/.venv/bin/paperorchestra-mcp"
```

That is fragile when `/root/.codex` is persistent but `/root/paperorchestra-for-codex` is recreated.

Recommended mitigations:

- install `paperorchestra-mcp` into a stable persistent path, or
- persist the repo/venv volume too, or
- re-run registration on every container entry after clone/install, or
- document a command-path check:

```bash
codex mcp get paperorchestra
# verify command points at the current checkout and is executable
```

## Suggested developer checklist

After patching transport support:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Existing server smoke should still pass.
scripts/smoke-paperorchestra-mcp.py --transport content-length --json

# New Codex-compatible transport smoke should pass.
scripts/smoke-paperorchestra-mcp.py --transport newline --json

# Register with Codex.
./scripts/register-codex-mcp.sh --use-local-venv --startup-timeout-sec 20

# Start a fresh Codex session or run attach smoke.
scripts/smoke-codex-mcp-attach.sh
```

Expected attach evidence:

```json
"type":"mcp_tool_call",
"server":"paperorchestra",
"tool":"status"
```

If the result says no current PaperOrchestra session exists, that is acceptable for attach smoke; it proves the tool was exposed and invoked.

## Known unknowns

- Whether Codex CLI `0.130.0+` uses the same observed newline framing and exhibits the same failure with the unpatched server.
- Whether Codex App uses the same transport framing as Codex CLI.
- Whether all 58 tool schemas are accepted across Codex versions after the framing fix. The bridge test strongly suggests schemas are not the primary blocker for `0.129.0`, but a full attach smoke should remain in CI/manual QA.

## Final conclusion

The previous investigation correctly suspected that restart alone was not the issue, but it did not identify the precise layer. The refined root cause is:

> PaperOrchestra MCP currently implements a `Content-Length` framed stdio protocol, while Codex CLI `0.129.0` was observed sending newline-delimited JSON-RPC MCP messages. Codex therefore sends `initialize`, the server does not parse/respond, and Codex times out startup. Existing smoke tests pass because they use the same `Content-Length` framing as the server rather than Codex's observed framing.

Fixing dual/newline stdio framing and adding a Codex attach smoke should be the first development task for issue #5.


## Appendix A: reproducible probe commands and abbreviated transcripts

This appendix preserves the temporary diagnostic evidence in a durable form. Paths under `/tmp` were intentionally temporary; the commands below recreate the probes from a fresh checkout/archive inside the container.

### A1. Direct newline vs Content-Length framing probe

Purpose: show that the current server responds to `Content-Length` framing but not to Codex-observed newline JSON framing.

Command shape used:

```bash
docker run --rm \
  -v /home/kosh/paperorchestra-for-codex:/host-repo:ro \
  paperorchestra-ubuntu-tools:24.04 bash -lc '
set -Eeuo pipefail
git config --global --add safe.directory /host-repo
rm -rf /tmp/po-framing && mkdir -p /tmp/po-framing
git -C /host-repo archive HEAD | tar -x -C /tmp/po-framing
cd /tmp/po-framing
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -q -e .
msg="{\"jsonrpc\":\"2.0\",\"id\":0,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{\"elicitation\":{}},\"clientInfo\":{\"name\":\"codex-mcp-client\",\"version\":\"0.129.0\"}}}"
printf "%s\n" "$msg" | timeout 3s .venv/bin/paperorchestra-mcp > /tmp/ndjson.out 2>/tmp/ndjson.err
echo "rc=$? stdout_bytes=$(wc -c </tmp/ndjson.out) stderr_bytes=$(wc -c </tmp/ndjson.err)"
'
```

Observed abbreviated output:

```text
--- newline-framed direct test (expect no response/timeout with current server) ---
rc=0 stdout_bytes=0 stderr_bytes=0

--- content-length direct test (expect response) ---
ready True
Content-Length: 169

{"jsonrpc": "2.0", "id": 0, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "paperorchestra-mcp", "version": "0.1.0"}, "capabilities": {"tools": {}}}}
```

### A2. Codex proxy evidence: Codex sent newline JSON

A temporary `/tmp/mcp_proxy.py` was registered as the `paperorchestra` MCP command and forwarded bytes to the real server while logging traffic. The first client-to-server message was captured as:

```text
PROXY_START ... real=/tmp/po-proxy/.venv/bin/paperorchestra-mcp
--- C2S 200 ---
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"elicitation":{}},"clientInfo":{"name":"codex-mcp-client","title":"Codex","version":"0.129.0"}}}
```

There was no `Content-Length:` prefix in the captured Codex request. With the unmodified server behind this proxy, Codex did not expose the tool and the model response was:

```json
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"UNAVAILABLE"}}
```

Earlier interactive TUI attempts in the same container family showed the user-facing startup failure as:

```text
⚠ MCP client for `paperorchestra` timed out after 10 seconds.
⚠ MCP startup incomplete (failed: paperorchestra)

# after raising startup_timeout_sec:
⚠ MCP client for `paperorchestra` timed out after 60 seconds.
⚠ MCP startup incomplete (failed: paperorchestra)
```

### A3. Temporary bridge evidence: translating framing makes Codex attach

A temporary `/tmp/mcp_bridge.py` translated Codex newline JSON to the server's `Content-Length` framing and translated server responses back to newline JSON. With a minimal Codex config containing only PaperOrchestra and `enabled_tools = ["status"]`, Codex produced:

```json
{"type":"item.started","item":{"id":"item_0","type":"mcp_tool_call","server":"paperorchestra","tool":"status","arguments":{"cwd":"/tmp/po-bridge"},"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_0","type":"mcp_tool_call","server":"paperorchestra","tool":"status","arguments":{"cwd":"/tmp/po-bridge"},"result":{"content":[{"type":"text","text":"FileNotFoundError: No current PaperOrchestra session. Run `paperorchestra init` first."}],"structured_content":null},"status":"failed"}}
```

The bridge log also proved the full handshake reached `tools/list` before the status call:

```text
BRIDGE_START ... real=/tmp/po-bridge/.venv/bin/paperorchestra-mcp
--- C2S_LINE ---
{"jsonrpc":"2.0","id":0,"method":"initialize",...}
--- S2C_OBJ ---
{"jsonrpc":"2.0","id":0,"result":{"protocolVersion":"2024-11-05","serverInfo":{"name":"paperorchestra-mcp","version":"0.1.0"},"capabilities":{"tools":{}}}}
--- C2S_LINE ---
{"jsonrpc":"2.0","method":"notifications/initialized"}
--- C2S_LINE ---
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{"progressToken":0}}}
--- S2C_OBJ ---
{"jsonrpc":"2.0","id":1,"result":{"tools":[... 58 tools ...]}}
--- C2S_LINE ---
{"jsonrpc":"2.0","id":2,"method":"tools/call",...,"name":"status","arguments":{"cwd":"/tmp/po-bridge"}}
--- S2C_OBJ ---
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"FileNotFoundError: No current PaperOrchestra session. Run `paperorchestra init` first."}],"isError":true}}
```

This bridge result down-ranks schema-ingestion and multi-server-interaction hypotheses for the tested `status` attach path. It does not prove every PaperOrchestra tool schema is accepted by every Codex version.
