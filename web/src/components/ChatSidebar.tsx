/**
 * ChatSidebar — structured-events panel that sits next to the xterm.js
 * terminal in the dashboard Chat tab.
 *
 * Two WebSockets, one per concern:
 *
 *   1. **JSON-RPC sidecar** (`GatewayClient` → /api/ws) — drives the
 *      sidebar's own slot of the dashboard's in-process gateway.  Owns
 *      the model badge / picker / connection state / error banner.
 *      Independent of the PTY pane's session by design — those are the
 *      pieces the sidebar needs to be able to drive directly (model
 *      switch via slash.exec, etc.).
 *
 *   2. **Event subscriber** (/api/events?channel=…) — passive, receives
 *      every dispatcher emit from the PTY-side `tui_gateway.entry` that
 *      the dashboard fanned out.  This is how `tool.start/progress/
 *      complete` from the agent loop reach the sidebar even though the
 *      PTY child runs three processes deep from us.  The `channel` id
 *      ties this listener to the same chat tab's PTY child — see
 *      `ChatPage.tsx` for where the id is generated.
 *
 * Best-effort throughout: WS failures show in the badge / banner, the
 * terminal pane keeps working unimpaired.
 */

import { Button } from "@nous-research/ui/ui/components/button";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Card } from "@nous-research/ui/ui/components/card";

import { ModelPickerDialog } from "@/components/ModelPickerDialog";
import { ToolCall, type ToolEntry } from "@/components/ToolCall";
import { GatewayClient, type ConnectionState } from "@/lib/gatewayClient";
import { HERMES_BASE_PATH, buildWsAuthParam } from "@/lib/api";

import { cn } from "@/lib/utils";
import { AlertCircle, ChevronDown, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface SessionInfo {
  cwd?: string;
  model?: string;
  provider?: string;
  credential_warning?: string;
}

interface PtySessionInfo {
  model?: string;
  provider?: string;
}

interface RpcEnvelope {
  method?: string;
  params?: { type?: string; payload?: unknown };
}

const TOOL_LIMIT = 20;

type BadgeKind = "live" | "switching" | "stale" | ConnectionState;

const BADGE_LABEL: Record<BadgeKind, string> = {
  idle: "idle",
  connecting: "connecting",
  open: "live",
  closed: "closed",
  error: "error",
  live: "live",
  switching: "switching",
  stale: "stale",
};

const BADGE_TONE: Record<
  BadgeKind,
  "secondary" | "warning" | "success" | "destructive"
> = {
  idle: "secondary",
  connecting: "warning",
  open: "success",
  closed: "secondary",
  error: "destructive",
  live: "success",
  switching: "warning",
  stale: "warning",
};

// Model sync status reported to ChatPage for send-guarding.
export type ModelSyncState =
  | { status: "live"; selectedModel: string; runtimeModel: string }
  | { status: "switching"; selectedModel: string; runtimeModel: string | null }
  | { status: "stale"; selectedModel: string | null; runtimeModel: string | null; reason: string }
  | { status: "unknown"; selectedModel: string | null; runtimeModel: string | null };

interface ChatSidebarProps {
  channel: string;
  className?: string;
  /** Called whenever the model sync state (live/switching/stale) changes. */
  onSyncStateChange?: (state: ModelSyncState) => void;
}

// Wall-clock fallback only — must exceed the backend's
// _MODEL_SWITCH_CONFIRM_S (web_server.py, currently 6s) plus normal HTTP
// latency so the backend's authoritative result wins under normal
// conditions.  We only hit this timer when /api/pty-cmd itself never
// returns (network drop, server hang).
const MODEL_SWITCH_TIMEOUT_MS = 9000;

// Parse the picker-emitted slash command (e.g.
// ``/model kimi-k2.5 --provider opencode-go --global``) into its bare
// model id and (optional) provider slug.  Mirrors
// _parse_model_switch_target in hermes_cli/web_server.py — flags are
// stripped, the first non-flag token after ``/model`` is the model, and
// ``--provider <slug>`` (if present) yields the provider.  Returns
// ``null`` for non-/model commands or bare ``/model``.
function parseModelSlash(
  slashCommand: string,
): { model: string; provider: string | null } | null {
  const trimmed = slashCommand.trim();
  if (!trimmed.toLowerCase().startsWith("/model")) {
    return null;
  }
  const tokens = trimmed.split(/\s+/).slice(1);
  if (tokens.length === 0) {
    return null;
  }
  let model: string | null = null;
  let provider: string | null = null;
  for (let i = 0; i < tokens.length; i++) {
    const tok = tokens[i];
    if (tok === "--provider" && i + 1 < tokens.length) {
      provider = tokens[i + 1];
      i++;
      continue;
    }
    if (tok === "--global" || tok === "--refresh") {
      continue;
    }
    if (tok.startsWith("--")) {
      continue;
    }
    if (model === null) {
      model = tok;
    }
  }
  return model ? { model, provider } : null;
}

export function ChatSidebar({ channel, className, onSyncStateChange }: ChatSidebarProps) {
  // `version` bumps on reconnect; gw is derived so we never call setState
  // for it inside an effect (React 19's set-state-in-effect rule). The
  // counter is the dependency on purpose — it's not read in the memo body,
  // it's the signal that says "rebuild the client".
  const [version, setVersion] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const gw = useMemo(() => new GatewayClient(), [version]);

  const [state, setState] = useState<ConnectionState>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [info, setInfo] = useState<SessionInfo>({});
  const [tools, setTools] = useState<ToolEntry[]>([]);
  const [modelOpen, setModelOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runtimeModel, setRuntimeModel] = useState<string | null>(null);

  // Tracks whether a model switch is pending runtime confirmation.
  const [pendingModelSwitch, setPendingModelSwitch] = useState<string | null>(null);
  const switchingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Set to {model, provider} when the live in-place /model swap timed out
  // and the backend signalled action_required="stop_runtime_then_rebuild".
  // Drives the explicit "Stop runtime and switch to <model>" CTA — the
  // operator must click it to actually issue /interrupt + /model via the
  // /api/model-switch/rebuild endpoint.  Stopping the active turn is a
  // destructive action, so it is NEVER triggered automatically on first
  // failure.
  const [restartRequired, setRestartRequired] = useState<{
    model: string;
    provider: string | null;
  } | null>(null);
  const [restartInFlight, setRestartInFlight] = useState(false);

  const syncStateRef = useRef<ModelSyncState>({ status: "unknown", selectedModel: null, runtimeModel: null });
  const buildSyncState = useCallback((): ModelSyncState => {
    const s = state;
    const sm = info.model ?? null;
    const rm = runtimeModel;

    if (s !== "open") {
      return { status: "unknown", selectedModel: sm, runtimeModel: rm } as ModelSyncState;
    }
    if (pendingModelSwitch) {
      return { status: "switching", selectedModel: pendingModelSwitch, runtimeModel: rm } as ModelSyncState;
    }
    if (!rm) {
      return { status: "stale", selectedModel: sm, runtimeModel: null, reason: "runtime model unknown" } as ModelSyncState;
    }
    if (sm === rm) {
      return { status: "live", selectedModel: sm, runtimeModel: rm } as ModelSyncState;
    }
    return { status: "stale", selectedModel: sm, runtimeModel: rm, reason: `selected ${sm} differs from runtime ${rm}` } as ModelSyncState;
  }, [state, info.model, runtimeModel, pendingModelSwitch]);

  useEffect(() => {
    const sync = buildSyncState();
    syncStateRef.current = sync;
    onSyncStateChange?.(sync);
  }, [buildSyncState, onSyncStateChange]);

  useEffect(() => {
    let cancelled = false;
    const offState = gw.onState(setState);

    const offSessionInfo = gw.on<SessionInfo>("session.info", (ev) => {
      if (ev.session_id) {
        setSessionId(ev.session_id);
      }

      if (ev.payload) {
        setInfo((prev) => ({ ...prev, ...ev.payload }));

        // Sidecar session.info updates the display model (for the picker
        // label) but MUST NOT update runtimeModel or clear a pending
        // model switch.  The sidecar and PTY have independent agents;
        // the sidecar confirming a /model switch only means the sidecar's
        // own agent switched — it says nothing about the PTY's agent
        // state.  Treating it as authoritative causes the badge to show
        // "live" even when the PTY's real agent is still on a different
        // model (see _apply_model_switch in tui_gateway/server.py which
        // emits session.info after switching the *local* agent only).
        //
        // The PTY's session.info (received via the event feed below)
        // is the authoritative source for runtimeModel and pending switch
        // resolution — it reflects the actual agent running in the PTY.
        if (ev.payload.model) {
          // Update info.model for the picker display label only.
          // DO NOT set runtimeModel or clear pendingModelSwitch here.
        }
      }
    });

    const offError = gw.on<{ message?: string }>("error", (ev) => {
      const message = ev.payload?.message;

      if (message) {
        setError(message);
      }
    });

    // Adopt whichever session the gateway hands us. session.create on the
    // sidecar is independent of the PTY pane's session by design — we
    // only need a sid to drive the model picker's slash.exec calls.
    gw.connect()
      .then(() => {
        if (cancelled) {
          return;
        }
        return gw.request<{ session_id: string }>("session.create", {});
      })
      .then((created) => {
        if (cancelled || !created?.session_id) {
          return;
        }
        setSessionId(created.session_id);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message);
        }
      });

    return () => {
      cancelled = true;
      offState();
      offSessionInfo();
      offError();
      gw.close();
    };
  }, [gw]);

  // Event subscriber WebSocket — receives the rebroadcast of every
  // dispatcher emit from the PTY child's gateway.  See /api/pub +
  // /api/events in hermes_cli/web_server.py for the broadcast hop.
  //
  // Failures (auth/loopback rejection, server too old to expose the
  // endpoint, transient drops) surface in the same banner as the
  // JSON-RPC sidecar so the sidebar matches its documented best-effort
  // UX and the user always has a reconnect affordance.
  useEffect(() => {
    if (!channel) {
      return;
    }
    // In loopback mode the legacy ?token=<session> path is fine; in gated
    // mode we have to mint a single-use ticket from the cookie. The IIFE
    // keeps the outer effect synchronous so its ``return cleanup`` stays
    // at the top level; the local ``ws`` is hoisted to a closed-over
    // binding the cleanup reads via ``wsRef``.
    let unmounting = false;
    let ws: WebSocket | null = null;
    void (async () => {
      const [authName, authValue] = await buildWsAuthParam();
      if (!authValue || unmounting) {
        return;
      }
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const qs = new URLSearchParams({ [authName]: authValue, channel });
      ws = new WebSocket(
        `${proto}//${window.location.host}${HERMES_BASE_PATH}/api/events?${qs.toString()}`,
      );

      // `unmounting` suppresses the banner during cleanup — `ws.close()`
      // from the effect's return fires a close event with code 1005 that
      // would otherwise look like an unexpected drop.
      const DISCONNECTED = "events feed disconnected — tool calls may not appear";
      const surface = (msg: string) => !unmounting && setError(msg);

      ws.addEventListener("error", () => surface(DISCONNECTED));

      ws.addEventListener("close", (ev) => {
        if (ev.code === 4401 || ev.code === 4403) {
          surface(`events feed rejected (${ev.code}) — reload the page`);
        } else if (ev.code !== 1000) {
          surface(DISCONNECTED);
        }
      });

      ws.addEventListener("message", (ev) => {
      let frame: RpcEnvelope;

      try {
        frame = JSON.parse(ev.data);
      } catch {
        return;
      }

      if (frame.method !== "event" || !frame.params) {
        return;
      }

      const { type, payload } = frame.params;

      if (type === "session.info") {
        const p = payload as PtySessionInfo | undefined;
        if (p?.model) {
          // PTY session.info is the authoritative source for the
          // actual runtime model — it reflects the real agent running
          // in the PTY child process.  Always accept it.
          setRuntimeModel(p.model);

          // Also update the display model so the badge label matches
          // the PTY's confirmed runtime.  Without this, the badge
          // shows the sidecar's independent session default (e.g.
          // deepseek-v4-pro) even after a rebuild started the PTY
          // with a different model (e.g. kimi-k2.6), producing a
          // permanent "stale" warning.
          setInfo((prev) => {
            const next: SessionInfo = { ...prev, model: p.model };
            if (p.provider) next.provider = p.provider;
            return next;
          });

          // If a model switch was pending and the runtime now matches,
          // clear the pending state.
          setPendingModelSwitch((prev) => {
            if (prev && p.model === prev) {
              return null;
            }
            return prev;
          });
        }
        return;
      }

      if (type === "tool.start") {
        const p = payload as
          | { tool_id?: string; name?: string; context?: string }
          | undefined;
        const toolId = p?.tool_id;

        if (!toolId) {
          return;
        }

        setTools((prev) =>
          [
            ...prev,
            {
              kind: "tool" as const,
              id: `tool-${toolId}-${prev.length}`,
              tool_id: toolId,
              name: p?.name ?? "tool",
              context: p?.context,
              status: "running" as const,
              startedAt: Date.now(),
            },
          ].slice(-TOOL_LIMIT),
        );
      } else if (type === "tool.progress") {
        const p = payload as
          | { name?: string; preview?: string }
          | undefined;

        if (!p?.name || !p.preview) {
          return;
        }

        setTools((prev) =>
          prev.map((t) =>
            t.status === "running" && t.name === p.name
              ? { ...t, preview: p.preview }
              : t,
          ),
        );
      } else if (type === "tool.complete") {
        const p = payload as
          | {
              tool_id?: string;
              summary?: string;
              error?: string;
              inline_diff?: string;
            }
          | undefined;

        if (!p?.tool_id) {
          return;
        }

        setTools((prev) =>
          prev.map((t) =>
            t.tool_id === p.tool_id
              ? {
                  ...t,
                  status: p.error ? "error" : "done",
                  summary: p.summary,
                  error: p.error,
                  inline_diff: p.inline_diff,
                  completedAt: Date.now(),
                }
              : t,
          ),
        );
      }
      });
    })();

    return () => {
      unmounting = true;
      ws?.close();
    };
  }, [channel, version]);

  const reconnect = useCallback(() => {
    setError(null);
    setTools([]);
    setVersion((v) => v + 1);
  }, []);

  // Picker hands us a fully-formed slash command (e.g. "/model anthropic/...").
  // Two-step handoff: (1) sidecar session gets the override via slash.exec,
  // (2) we inject the same command into the PTY via /api/pty-cmd so the
  // actual agent loop switches models.  The PTY will then emit
  // session.info (captured from the events WS) updating runtimeModel.
  const onModelSubmit = useCallback(
    (slashCommand: string) => {
      if (!sessionId) {
        return;
      }

      // Step 1: sidecar override (model badge / picker state)
      void gw.request("slash.exec", {
        session_id: sessionId,
        command: slashCommand,
      });

      // Step 2: PTY injection — fire /api/pty-cmd and check acceptance.
      // Set switching state; a timeout will revert to stale if no
      // runtime confirmation arrives.
      const modelName = slashCommand.startsWith("/model ")
        ? slashCommand.slice("/model ".length).trim()
        : slashCommand;

      setPendingModelSwitch(modelName);

      // Clear any previous timeout
      if (switchingTimeoutRef.current) {
        clearTimeout(switchingTimeoutRef.current);
      }

      void (async () => {
        // Auth for REST /api/pty-cmd differs from WS query params:
        // - Loopback mode: X-Hermes-Session-Token header (matching
        //   _has_valid_session_token in web_server.py)
        // - Gated mode: credentials: "include" so the cookie-based
        //   gated_auth_middleware reads the session cookie.
        // buildWsAuthParam() returns ['token', ...] or ['ticket', ...]
        // designed for WebSocket ?token= / ?ticket= query params —
        // those are NOT valid REST auth headers.
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        const gated = window.__HERMES_AUTH_REQUIRED__;
        if (!gated) {
          const sessionToken = window.__HERMES_SESSION_TOKEN__;
          if (!sessionToken) {
            setPendingModelSwitch((prev) => (prev === modelName ? null : prev));
            return;
          }
          headers["X-Hermes-Session-Token"] = sessionToken;
        }
        try {
          const resp = await fetch(
            `${window.location.protocol}//${window.location.host}${HERMES_BASE_PATH}/api/pty-cmd`,
            {
              method: "POST",
              headers,
              // credentials: "include" is essential for gated mode
              // (cookie auth) and harmless in loopback mode.
              credentials: "include",
              body: JSON.stringify({ channel, command: slashCommand }),
            },
          );
          const data = await resp.json();

          if (!data.accepted) {
            // /api/pty-cmd rejected the command — show error and
            // revert pending state.
            // Auth failures (401/403) take precedence over generic
            // `detail` stringification so the operator sees an
            // actionable "reload the page" instead of `"Unauthorized"`,
            // which is what loopback auth_middleware returns as
            // ``{"detail":"Unauthorized"}`` when the in-tab session
            // token is stale after a dashboard restart.
            let errMsg: string;
            if (resp.status === 401 || resp.status === 403) {
              errMsg = "Model switch rejected: authentication required — reload the page to refresh the dashboard session token.";
            } else if (data.channel_found === false) {
              errMsg = "No active chat session — model switch cannot be applied.";
            } else if (data.error) {
              errMsg = `Model switch rejected: ${data.error}`;
            } else if (data.detail) {
              // FastAPI returns 422 validation errors with `detail` field
              // instead of the expected shape.  Extract a user-facing
              // message from the validation error list.
              const detail = data.detail;
              if (Array.isArray(detail) && detail.length > 0) {
                const locs = detail.map((d: { loc?: string[]; msg?: string }) =>
                  d.loc ? d.loc.join(".") : ""
                ).filter(Boolean).join(", ");
                const msgs = detail.map((d: { msg?: string }) => d.msg || "").filter(Boolean).join("; ");
                errMsg = `Model switch rejected: validation error${locs ? ` in ${locs}` : ""}${msgs ? ` — ${msgs}` : ""}`;
              } else {
                errMsg = `Model switch rejected: ${JSON.stringify(detail)}`;
              }
            } else {
              errMsg = `Model switch rejected: server returned ${resp.status} with no error detail.`;
            }
            setError(errMsg);
            setPendingModelSwitch((prev) => (prev === modelName ? null : prev));
            return;
          }

          // For /model commands the backend now waits for the PTY-side
          // gateway to confirm the switch via the cached session.info
          // feed (see _await_runtime_model_switch in web_server.py).
          // Use that authoritative result instead of racing a wall-clock
          // timer that can't tell "still switching" from "runtime refused".
          if (data.is_model_switch) {
            // Cancel the fall-through wall-clock timer — the response
            // already represents the runtime's final verdict.
            if (switchingTimeoutRef.current) {
              clearTimeout(switchingTimeoutRef.current);
              switchingTimeoutRef.current = null;
            }
            if (data.runtime_switched && data.runtime_model) {
              setRuntimeModel(data.runtime_model);
              setPendingModelSwitch((prev) => (prev === modelName ? null : prev));
              setError(null);
              // Live swap worked — drop any prior rebuild CTA for this
              // model so the operator doesn't see a stale call to action.
              setRestartRequired(null);
            } else {
              // Structured restart-required signal from the backend.
              const reqd = data.action_required === "stop_runtime_then_rebuild";
              const tail = reqd
                ? " Click \u201CStop runtime and switch\u201D below, or open a new session."
                : "";
              setError(
                (data.error
                  ? `Model switch did not apply: ${data.error}.`
                  : `Model switch to "${modelName}" was sent but the runtime did not confirm the change.`)
                + tail,
              );
              setPendingModelSwitch((prev) => (prev === modelName ? null : prev));
              if (reqd) {
                const parsed = parseModelSlash(slashCommand);
                if (parsed) {
                  setRestartRequired({ model: parsed.model, provider: parsed.provider });
                }
              }
            }
            return;
          }
        } catch {
          // Network/parse error — fall back to the timeout; keep
          // pending state so the badge shows "switching".
        }
      })();

      // Wall-clock fallback for the case where /api/pty-cmd never returns
      // (network drop, server hang): if the backend confirmation never
      // arrives, revert to stale with the same actionable text the
      // structured restart-required path uses.
      switchingTimeoutRef.current = setTimeout(() => {
        setPendingModelSwitch((prev) => {
          if (prev !== modelName) {
            return prev;
          }
          setError(
            `Model switch to "${modelName}" was sent but not confirmed by runtime within ${MODEL_SWITCH_TIMEOUT_MS / 1000}s. ` +
            "Click \u201CStop runtime and switch\u201D below, or open a new session.",
          );
          // Offer the same CTA the structured failure path offers, so
          // a network drop doesn't strand the operator without a remedy.
          const parsed = parseModelSlash(slashCommand);
          if (parsed) {
            setRestartRequired({ model: parsed.model, provider: parsed.provider });
          }
          return null;
        });
      }, MODEL_SWITCH_TIMEOUT_MS);

      setModelOpen(false);
    },
    [gw, sessionId, channel],
  );

  // Operator-initiated session rebuild: only fires when the user clicks
  // the explicit "Restart session with <model>" CTA — stopping the
  // running session is destructive, so we never auto-trigger it.  POSTs
  // to the dashboard's /api/model-switch/rebuild endpoint, which closes
  // the old PTY process and returns {rebuilt: true}.  On success we
  // reload the page with ?model=...&provider=... in the URL so the new
  // PTY starts with the selected runtime from the beginning.
  const onForceRebuild = useCallback(async () => {
    if (!restartRequired || restartInFlight) {
      return;
    }
    const { model, provider } = restartRequired;
    setRestartInFlight(true);
    setPendingModelSwitch(model);
    setError(null);
    // Cancel any leftover wall-clock timer from the initial /model
    // attempt — the rebuild endpoint owns confirmation now.
    if (switchingTimeoutRef.current) {
      clearTimeout(switchingTimeoutRef.current);
      switchingTimeoutRef.current = null;
    }

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const gated = window.__HERMES_AUTH_REQUIRED__;
    if (!gated) {
      const sessionToken = window.__HERMES_SESSION_TOKEN__;
      if (!sessionToken) {
        setError("Rebuild rejected: missing session token — reload the page.");
        setPendingModelSwitch((prev) => (prev === model ? null : prev));
        setRestartInFlight(false);
        return;
      }
      headers["X-Hermes-Session-Token"] = sessionToken;
    }

    try {
      const resp = await fetch(
        `${window.location.protocol}//${window.location.host}${HERMES_BASE_PATH}/api/model-switch/rebuild`,
        {
          method: "POST",
          headers,
          credentials: "include",
          body: JSON.stringify({ channel, model, provider: provider || undefined }),
        },
      );
      const data = await resp.json().catch(() => ({}));
      if (resp.status === 401 || resp.status === 403) {
        setError(
          "Rebuild rejected: authentication required — reload the page to refresh the dashboard session token.",
        );
        setPendingModelSwitch((prev) => (prev === model ? null : prev));
        setRestartInFlight(false);
        return;
      }
      // New rebuild flow: the backend killed the old PTY and returned
      // {rebuilt: true}.  Reload the page with model/provider in URL
      // params so the new PTY starts with the selected runtime.
      if (data.rebuilt && data.requested_model) {
        const next = new URLSearchParams(window.location.search);
        next.set("model", data.requested_model);
        if (data.requested_provider) {
          next.set("provider", data.requested_provider);
        }
        // Remove resume param — this is a fresh session start.
        next.delete("resume");
        window.location.href =
          window.location.pathname + "?" + next.toString() + window.location.hash;
        return;
      }
      // Legacy or failure path: surface the error.
      const errorMsg =
        data.error
          ? `Rebuild failed: ${data.error}.`
          : `Rebuild did not confirm for model "${model}".`;
      setError(errorMsg + " Try reloading the page manually.");
      setPendingModelSwitch((prev) => (prev === model ? null : prev));
      setRestartInFlight(false);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`Force-switch network error: ${msg}`);
      setPendingModelSwitch((prev) => (prev === model ? null : prev));
    } finally {
      setRestartInFlight(false);
    }
  }, [restartRequired, restartInFlight, channel]);

  // Drop the rebuild CTA whenever /api/events delivers a session.info
  // showing the runtime already matches the requested model — handles
  // the case where the live swap eventually landed after the 6s window
  // (the CTA would otherwise stay visible and confuse the operator).
  useEffect(() => {
    if (restartRequired && runtimeModel === restartRequired.model) {
      setRestartRequired(null);
    }
  }, [runtimeModel, restartRequired]);

  const canPickModel = state === "open" && !!sessionId;
  const modelLabel = (info.model ?? "—").split("/").slice(-1)[0] ?? "—";
  const banner = error ?? info.credential_warning ?? null;

  // Badge kind:
  //   - switching: model switch command accepted, waiting for runtime conf.
  //   - live: WS open AND selected model === runtime model AND no pending
  //           switch (badge must never show "live" unless confirmed).
  //   - stale: WS open but runtime model unknown or doesn't match selected.
  const badgeKind: BadgeKind =
    state !== "open"
      ? state
      : pendingModelSwitch
        ? "switching"
        : !runtimeModel
          ? "stale"
          : info.model === runtimeModel
            ? "live"
            : "stale";

  return (
    <aside
      className={cn(
        "flex h-full w-full min-w-0 shrink-0 flex-col gap-3 overflow-y-auto overflow-x-hidden pr-1 lg:w-80",
        className,
      )}
    >
      <Card className="flex items-center justify-between gap-2 px-3 py-2">
        <div className="min-w-0">
          <div className="text-display text-xs tracking-wider text-text-tertiary">
            model
          </div>

          <Button
            ghost
            size="sm"
            disabled={!canPickModel}
            onClick={() => setModelOpen(true)}
            suffix={
              canPickModel ? (
                <ChevronDown className="text-text-secondary" />
              ) : undefined
            }
            className="self-start min-w-0 px-0 py-0 normal-case tracking-normal text-sm font-medium hover:underline disabled:no-underline"
            title={info.model ?? "switch model"}
          >
            <span className="truncate">{modelLabel}</span>
          </Button>
        </div>

        <Badge tone={BADGE_TONE[badgeKind]}>{BADGE_LABEL[badgeKind]}</Badge>
      </Card>

      {banner && (
        <Card className="flex items-start gap-2 border-destructive/40 bg-destructive/5 px-3 py-2 text-xs">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />

          <div className="min-w-0 flex-1">
            <div className="wrap-break-word text-destructive">{banner}</div>

            {error && (
              <Button
                size="sm"
                outlined
                className="mt-1"
                onClick={reconnect}
                prefix={<RefreshCw />}
              >
                reconnect
              </Button>
            )}
          </div>
        </Card>
      )}

      {restartRequired && (
        <Card className="flex flex-col gap-2 border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs">
          <div className="wrap-break-word text-amber-700 dark:text-amber-300">
            Live model switch to <span className="font-semibold">{restartRequired.model}</span>
            {restartRequired.provider ? <> ({restartRequired.provider})</> : null} did not
            take effect. Clicking the button below will restart the chat session
            with the selected model — the current runtime will be stopped and a new
            one started.
          </div>
          <Button
            size="sm"
            onClick={() => { void onForceRebuild(); }}
            disabled={restartInFlight}
          >
            {restartInFlight
              ? `Restarting with ${restartRequired.model}\u2026`
              : `Restart session with ${restartRequired.model}`}
          </Button>
        </Card>
      )}

      <Card className="flex min-h-0 flex-none flex-col px-2 py-2">
        <div className="text-display px-1 pb-2 text-xs tracking-wider text-text-tertiary">
          tools
        </div>

        <div className="flex min-h-0 flex-col gap-1.5">
          {tools.length === 0 ? (
            <div className="px-2 py-4 text-center text-xs text-text-secondary">
              no tool calls yet
            </div>
          ) : (
            tools.map((t) => <ToolCall key={t.id} tool={t} />)
          )}
        </div>
      </Card>

      {modelOpen && canPickModel && sessionId && (
        <ModelPickerDialog
          gw={gw}
          sessionId={sessionId}
          onClose={() => setModelOpen(false)}
          onSubmit={onModelSubmit}
        />
      )}
    </aside>
  );
}
