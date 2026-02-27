import type { Context } from "grammy";
import {
  CORTEX_AUTO_TASK_ROUTING,
  CORTEX_BRIDGE_ENABLED,
  CORTEX_CONFIRMATION_ENABLED,
  CORTEX_TASK_DEFAULT_DOMAIN,
} from "../../config";
import { runCortexDispatch } from "./bridge";

type PendingTask = {
  prompt: string;
  createdAtMs: number;
};

type ActiveRunState = {
  runId: string;
  startedAtMs: number;
  cancelRequested: boolean;
  pollInFlight: boolean;
  lastProgressSignature: string;
  lastProgressSentAtMs: number;
  lastLifecycleTs: number;
};

const pendingTasks = new Map<string, PendingTask>();
const activeRuns = new Map<string, ActiveRunState>();

// Polling is intentionally lightweight: fixed interval and throttled updates.
const RUN_STATUS_POLL_INTERVAL_MS = 3000;
const RUN_STATUS_UPDATE_THROTTLE_MS = 9000;
const RUN_STATUS_POLL_EVENT_LIMIT = 6;

const POSITIVE_CONFIRM = new Set([
  "yes",
  "y",
  "run",
  "confirm",
  "go",
  "do it",
]);
const NEGATIVE_CONFIRM = new Set(["no", "n", "cancel", "skip", "stop"]);
const LEARN_STATUS_PREFIXES = ["/learn-status", "/learnstatus", "/learn_status"];
const RUN_STATUS_PREFIXES = ["/run-status", "/runstatus", "/run_status"];

type PollUpdate = {
  signature: string;
  message: string;
  terminal: boolean;
};

function chatScope(chatId: number): string {
  return `tg-${chatId}`;
}

function startsWithAny(text: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => text.startsWith(prefix));
}

function extractRunId(text: string): string | undefined {
  const control = text.match(/(?:^|\s)run_id=([A-Za-z0-9_-]+)/i);
  if (control?.[1]) return control[1];

  const token = text.match(/\brun_[A-Za-z0-9_-]+\b/);
  return token?.[0];
}

function createTransportRunId(): string {
  const epochMs = String(Date.now()).padStart(13, "0");
  const nonce = String(Math.floor(Math.random() * 100_000_000)).padStart(8, "0");
  return `run_${epochMs}_${nonce}`;
}

export function buildRunDispatchText(
  runText: string,
  preferredRunId?: string
): { dispatchText: string; runId: string } {
  const explicitRunId = extractRunId(runText);
  if (explicitRunId) {
    return { dispatchText: runText, runId: explicitRunId };
  }
  const runId = preferredRunId || createTransportRunId();
  return { dispatchText: `${runText.trim()} run_id=${runId}`, runId };
}

export function buildStatusDispatchText(
  statusText: string,
  activeRunId?: string
): { dispatchText: string; runId?: string } {
  const lowered = statusText.trim().toLowerCase();
  const isRunStatus = startsWithAny(lowered, RUN_STATUS_PREFIXES);
  const runId = extractRunId(statusText) || activeRunId;
  const explicitProgress = statusText.match(/\bprogress=(true|false|on|off|1|0|yes|no)\b/i);
  const hasProgressToken = /\b(--progress|progress)\b/i.test(statusText);
  const progressDisabled = explicitProgress
    ? /^(false|off|0|no)$/i.test(explicitProgress[1] || "")
    : false;
  const progressEnabled = progressDisabled
    ? false
    : isRunStatus || hasProgressToken || Boolean(explicitProgress);

  const limitMatch = statusText.match(/\b(?:limit|events)=([0-9]+)\b/i);
  const limitValue = limitMatch?.[1]
    ? Math.max(1, Math.min(20, Number(limitMatch[1])))
    : undefined;
  const progressArgs = progressEnabled
    ? ` progress=on${limitValue ? ` limit=${limitValue}` : ""}`
    : "";

  return runId
    ? { dispatchText: `/status run_id=${runId}${progressArgs}`, runId }
    : { dispatchText: `/status${progressArgs}` };
}

export function buildCancelDispatchText(
  stopText: string,
  activeRunId?: string
): { dispatchText: string; runId: string } | null {
  const runId = extractRunId(stopText) || activeRunId;
  if (!runId) return null;
  return { dispatchText: `/cancel run_id=${runId}`, runId };
}

function buildFollowupDispatchText(
  rawText: string,
  activeRunId?: string
): { dispatchText: string; runId: string; text: string } | null {
  const normalized = rawText.trim();
  const explicitRunId = extractRunId(normalized);
  const runId = explicitRunId || activeRunId;
  if (!runId) return null;

  let text = normalized;
  if (normalized.toLowerCase().startsWith("/followup")) {
    text = normalized.slice("/followup".length).trim();
  }
  // Remove explicit run id token from the free-form followup body to avoid
  // double-including controls in the transport payload.
  text = text.replace(/\brun_id=[A-Za-z0-9_-]+\b/gi, "").trim();
  if (!text) return null;
  return {
    dispatchText: `/followup run_id=${runId} ${text}`,
    runId,
    text,
  };
}

function looksLikeTaskIntent(message: string): boolean {
  const text = message.trim().toLowerCase();
  if (!text) return false;
  if (text.startsWith("/")) return false;

  const taskMarkers = [
    "build",
    "create",
    "generate",
    "fix",
    "run",
    "write",
    "import",
    "analyze",
    "summarize",
    "list files",
    "show me",
    "prepare",
  ];
  const containsMarker = taskMarkers.some((marker) => text.includes(marker));

  // Keep the heuristic strict enough to avoid hijacking normal chat.
  return containsMarker && text.length >= 24;
}

function summarizeStatus(payload: Record<string, unknown>): string {
  const lessonsTotal = payload.lessons_total;
  const lessonsScoped = payload.lessons_scoped;
  const activeRows = Array.isArray(payload.active_runs)
    ? (payload.active_runs as Record<string, unknown>[])
    : [];
  const run = payload.run as Record<string, unknown> | null | undefined;
  const latest = (payload.latest_session as Record<string, unknown>) || {};
  const lines = [
    "Cortex learning status:",
    `- lessons_total: ${lessonsTotal ?? "?"}`,
    `- lessons_scoped: ${lessonsScoped ?? "?"}`,
    `- active_runs: ${activeRows.length}`,
    `- latest_task: ${latest.task_id ?? "?"}`,
    `- latest_domain: ${latest.domain ?? "?"}`,
    `- latest_eval_passed: ${latest.eval_passed ?? "?"}`,
    `- lesson_activations: ${latest.lesson_activations ?? "?"}`,
    `- retrieval_help_ratio: ${latest.v2_retrieval_help_ratio ?? "?"}`,
  ];
  if (run) {
    lines.push(`- requested_run_id: ${run.run_id ?? "?"}`);
    lines.push(`- requested_run_status: ${run.status ?? "?"}`);
    lines.push(`- requested_run_last_step: ${run.last_step ?? "?"}`);
  }
  return lines.join("\n");
}

function summarizeRunStatus(payload: Record<string, unknown>): string {
  const activeRows = Array.isArray(payload.active_runs)
    ? (payload.active_runs as Record<string, unknown>[])
    : [];
  const run = payload.run as Record<string, unknown> | null | undefined;
  const lifecycleEvents = Array.isArray(payload.lifecycle_events)
    ? (payload.lifecycle_events as Record<string, unknown>[])
    : [];
  const progressMode = payload.progress_mode === true;
  if (run) {
    const followups = Array.isArray(run.followups)
      ? (run.followups as unknown[])
      : [];
    return [
      "Cortex run status:",
      `- run_id: ${run.run_id ?? "?"}`,
      `- status: ${run.status ?? "?"}`,
      `- cancel_requested: ${run.cancel_requested ?? "?"}`,
      `- last_step: ${run.last_step ?? "?"}`,
      `- followups: ${followups.length}`,
      `- task_id: ${run.task_id ?? "?"}`,
      `- domain: ${run.domain ?? "?"}`,
      `- active_runs: ${activeRows.length}`,
      `- progress_mode: ${progressMode}`,
      `- lifecycle_events: ${lifecycleEvents.length}`,
    ].join("\n");
  }

  if (activeRows.length === 0) {
    return "Cortex run status: no active runs.";
  }

  const first = activeRows[0] || {};
  return [
    "Cortex run status:",
    `- active_runs: ${activeRows.length}`,
    `- latest_run_id: ${first.run_id ?? "?"}`,
    `- latest_status: ${first.status ?? "?"}`,
    `- latest_last_step: ${first.last_step ?? "?"}`,
  ].join("\n");
}

function summarizeRun(
  plan: Record<string, unknown> | undefined,
  result: Record<string, unknown> | undefined
): string {
  const taskId = result?.task_id ?? plan?.task_id ?? "?";
  const domain = result?.domain ?? plan?.domain ?? "?";
  const ok = result?.ok ?? false;
  const runId = result?.run_id ?? plan?.run_id ?? "?";
  const runStatus = result?.run_status ?? "?";
  const sessionId = result?.session_id ?? "?";
  const sessionDir = result?.session_dir ?? "?";
  const metrics = (result?.metrics as Record<string, unknown>) || {};
  const runRecord = (result?.run as Record<string, unknown> | undefined) || undefined;
  const followups = Array.isArray(runRecord?.followups)
    ? (runRecord?.followups as Record<string, unknown>[])
    : [];
  const lastFollowup = followups.length > 0 ? followups[followups.length - 1] : undefined;
  const followupCount = Number(result?.run_followup_count ?? followups.length ?? 0);
  return [
    `Cortex run: ${ok ? "ok" : "failed"}`,
    `- run_id: ${runId}`,
    `- run_status: ${runStatus}`,
    `- task_id: ${taskId}`,
    `- domain: ${domain}`,
    `- session_id: ${sessionId}`,
    `- eval_passed: ${metrics.eval_passed ?? "?"}`,
    `- eval_score: ${metrics.eval_score ?? "?"}`,
    `- lesson_activations: ${metrics.lesson_activations ?? "?"}`,
    `- retrieval_help_ratio: ${metrics.v2_retrieval_help_ratio ?? "?"}`,
    `- followups_applied: ${followupCount}`,
    `- last_followup: ${lastFollowup?.text ?? "none"}`,
    `- session_dir: ${sessionDir}`,
  ].join("\n");
}

function summarizePollUpdate(
  statusPayload: Record<string, unknown>,
  runId: string,
  lastSeenLifecycleTs: number
): PollUpdate | null {
  const run = statusPayload.run as Record<string, unknown> | null | undefined;
  if (!run) return null;
  const lifecycleEvents = Array.isArray(statusPayload.lifecycle_events)
    ? (statusPayload.lifecycle_events as Record<string, unknown>[])
    : [];
  const latestLifecycle = lifecycleEvents.length
    ? lifecycleEvents[lifecycleEvents.length - 1]
    : null;
  const latestLifecycleTs = latestLifecycle
    ? Number(latestLifecycle.ts ?? 0)
    : 0;

  const status = String(run.status ?? "unknown");
  const lastStep = run.last_step ?? "?";
  const cancelRequested = Boolean(run.cancel_requested);
  const started = Number(run.started_at_epoch_s ?? 0);
  const elapsedSec =
    started > 0 ? Math.max(0, Math.floor(Date.now() / 1000 - started)) : null;
  const terminal = status === "completed" || status === "failed" || status === "cancelled";
  const latestEvent = latestLifecycle ? String(latestLifecycle.event ?? "") : "";
  const signature = `${status}|${lastStep}|${cancelRequested}|${latestLifecycleTs}|${latestEvent}`;
  const elapsedPart = elapsedSec === null ? "" : `, elapsed=${elapsedSec}s`;
  const cancelPart = cancelRequested ? ", cancel_requested=true" : "";
  const hasNewLifecycleEvent = latestLifecycleTs > lastSeenLifecycleTs;
  const followups = Array.isArray(run.followups)
    ? (run.followups as unknown[])
    : [];

  let eventPart = "";
  if (hasNewLifecycleEvent && latestLifecycle) {
    const eventName = String(latestLifecycle.event ?? "event");
    const eventStep = latestLifecycle.step ?? run.last_step ?? "?";
    if (eventName === "followup") {
      const text = String(latestLifecycle.text ?? "").trim();
      eventPart = text ? `, event=followup("${text.slice(0, 80)}")` : ", event=followup";
    } else {
      eventPart = `, event=${eventName}, event_step=${eventStep}`;
    }
  }

  return {
    signature,
    terminal,
    message: `Cortex run update (${runId}): status=${status}, last_step=${lastStep}, followups=${followups.length}${cancelPart}${elapsedPart}${eventPart}`,
  };
}

async function maybeSendRunProgressUpdate(
  ctx: Context,
  scope: string,
  runId: string
): Promise<void> {
  const state = activeRuns.get(scope);
  if (!state || state.runId !== runId || state.pollInFlight) return;
  state.pollInFlight = true;

  try {
    const bridge = await runCortexDispatch(
      `/status run_id=${runId} progress=on limit=${RUN_STATUS_POLL_EVENT_LIMIT}`,
      scope
    );
    if (!bridge.payload || bridge.payload.mode !== "status") return;

    const statusPayload = bridge.payload as Record<string, unknown>;
    const poll = summarizePollUpdate(statusPayload, runId, state.lastLifecycleTs);
    if (!poll) return;

    if (poll.signature === state.lastProgressSignature) return;
    const now = Date.now();
    if (
      !poll.terminal &&
      now - state.lastProgressSentAtMs < RUN_STATUS_UPDATE_THROTTLE_MS
    ) {
      return;
    }

    state.lastProgressSignature = poll.signature;
    state.lastProgressSentAtMs = now;
    const lifecycleEvents = Array.isArray(statusPayload.lifecycle_events)
      ? (statusPayload.lifecycle_events as Record<string, unknown>[])
      : [];
    for (const event of lifecycleEvents) {
      const ts = Number(event.ts ?? 0);
      if (Number.isFinite(ts) && ts > state.lastLifecycleTs) {
        state.lastLifecycleTs = ts;
      }
    }
    await ctx.reply(poll.message);
  } catch {
    // Polling is best-effort: failures should not break the foreground run flow.
  } finally {
    state.pollInFlight = false;
  }
}

function startRunStatusPolling(
  ctx: Context,
  scope: string,
  runId: string
): ReturnType<typeof setInterval> {
  return setInterval(() => {
    void maybeSendRunProgressUpdate(ctx, scope, runId);
  }, RUN_STATUS_POLL_INTERVAL_MS);
}

async function runTaskAndReply(
  ctx: Context,
  runText: string,
  chatId: number
): Promise<void> {
  const scope = chatScope(chatId);
  const runDispatch = buildRunDispatchText(runText);
  activeRuns.set(scope, {
    runId: runDispatch.runId,
    startedAtMs: Date.now(),
    cancelRequested: false,
    pollInFlight: false,
    lastProgressSignature: "",
    lastProgressSentAtMs: 0,
    lastLifecycleTs: 0,
  });

  await ctx.reply(
    `Running via Cortex learning loop...\n` +
      `- run_id: ${runDispatch.runId}\n` +
      `- use /run-status for progress\n` +
      `- use /stop to request cancel`
  );

  const pollTimer = startRunStatusPolling(ctx, scope, runDispatch.runId);
  let bridge: Awaited<ReturnType<typeof runCortexDispatch>>;
  try {
    bridge = await runCortexDispatch(runDispatch.dispatchText, scope);
  } catch (error) {
    await ctx.reply(`Cortex bridge error:\n${String(error).slice(0, 1200)}`);
    return;
  } finally {
    // Always cleanup polling state even if dispatch throws, otherwise /run-status
    // can get stuck behind stale in-memory active run markers.
    clearInterval(pollTimer);
    const active = activeRuns.get(scope);
    if (active && active.runId === runDispatch.runId) {
      activeRuns.delete(scope);
    }
  }

  if (!bridge.payload) {
    const tail =
      bridge.stderr.trim() || bridge.stdout.trim() || bridge.error || "unknown";
    await ctx.reply(`Cortex bridge error:\n${tail.slice(0, 1200)}`);
    return;
  }

  const payload = bridge.payload;
  const mode = payload.mode;
  if (mode === "status") {
    await ctx.reply(summarizeStatus(payload as Record<string, unknown>));
    return;
  }
  if (mode === "run") {
    await ctx.reply(
      summarizeRun(
        payload.plan as Record<string, unknown> | undefined,
        payload.result as Record<string, unknown> | undefined
      )
    );
    return;
  }

  if (mode === "cancel") {
    const ok = payload.ok === true;
    const runId = payload.run_id ?? runDispatch.runId;
    const error = payload.error ?? "cancel failed";
    await ctx.reply(
      ok
        ? `Cortex cancel requested for run ${runId}.`
        : `Cortex cancel request failed for run ${runId}:\n${String(error)}`
    );
    return;
  }

  await ctx.reply(
    (payload.reply as string) || "Cortex bridge completed with no summary."
  );
}

async function sendStatusReply(
  ctx: Context,
  normalizedCommand: string,
  chatId: number
): Promise<void> {
  const scope = chatScope(chatId);
  const activeRunId = activeRuns.get(scope)?.runId;
  const statusDispatch = buildStatusDispatchText(normalizedCommand, activeRunId);
  const bridge = await runCortexDispatch(statusDispatch.dispatchText, scope);

  if (!bridge.payload) {
    const tail =
      bridge.stderr.trim() || bridge.stdout.trim() || bridge.error || "unknown";
    await ctx.reply(`Cortex bridge error:\n${tail.slice(0, 1200)}`);
    return;
  }

  const payload = bridge.payload;
  if (payload.mode !== "status") {
    await ctx.reply(
      (payload.reply as string) || "Cortex bridge completed with no status payload."
    );
    return;
  }

  const isRunStatus = startsWithAny(
    normalizedCommand.toLowerCase(),
    RUN_STATUS_PREFIXES
  );
  await ctx.reply(
    isRunStatus
      ? summarizeRunStatus(payload as Record<string, unknown>)
      : summarizeStatus(payload as Record<string, unknown>)
  );
}

export async function handleCortexStopCommand(
  ctx: Context,
  chatId: number,
  rawCommand = "/stop"
): Promise<boolean> {
  if (!CORTEX_BRIDGE_ENABLED) return false;

  const scope = chatScope(chatId);
  const activeRunId = activeRuns.get(scope)?.runId;
  const cancelDispatch = buildCancelDispatchText(rawCommand, activeRunId);
  if (!cancelDispatch) return false;

  const state = activeRuns.get(scope);
  if (state && state.runId === cancelDispatch.runId) {
    state.cancelRequested = true;
  }

  const bridge = await runCortexDispatch(cancelDispatch.dispatchText, scope);
  if (!bridge.payload) {
    const tail =
      bridge.stderr.trim() || bridge.stdout.trim() || bridge.error || "unknown";
    await ctx.reply(`Cortex stop request failed:\n${tail.slice(0, 1200)}`);
    return true;
  }

  const payload = bridge.payload as Record<string, unknown>;
  if (payload.mode === "cancel" && payload.ok === true) {
    await ctx.reply(`Cortex stop requested for run ${cancelDispatch.runId}.`);
    return true;
  }

  const error = payload.error ?? bridge.error ?? "unknown";
  await ctx.reply(
    `Cortex stop request failed for run ${cancelDispatch.runId}:\n${String(error).slice(0, 1200)}`
  );
  return true;
}

async function handleCortexFollowupCommand(
  ctx: Context,
  chatId: number,
  rawText: string
): Promise<boolean> {
  if (!CORTEX_BRIDGE_ENABLED) return false;
  const scope = chatScope(chatId);
  const activeRunId = activeRuns.get(scope)?.runId;
  const followupDispatch = buildFollowupDispatchText(rawText, activeRunId);
  if (!followupDispatch) {
    await ctx.reply(
      "Follow-up requires an active run and non-empty text. Use /followup run_id=<id> <text>."
    );
    return true;
  }

  const bridge = await runCortexDispatch(followupDispatch.dispatchText, scope);
  if (!bridge.payload) {
    const tail =
      bridge.stderr.trim() || bridge.stdout.trim() || bridge.error || "unknown";
    await ctx.reply(`Cortex followup request failed:\n${tail.slice(0, 1200)}`);
    return true;
  }
  const payload = bridge.payload as Record<string, unknown>;
  if (payload.mode === "followup" && payload.ok === true) {
    const count =
      (payload.result as Record<string, unknown> | undefined)?.followups &&
      Array.isArray((payload.result as Record<string, unknown>).followups)
        ? ((payload.result as Record<string, unknown>).followups as unknown[]).length
        : undefined;
    await ctx.reply(
      count === undefined
        ? `Cortex followup accepted for run ${followupDispatch.runId}.`
        : `Cortex followup accepted for run ${followupDispatch.runId} (total followups=${count}).`
    );
    return true;
  }
  const error = payload.error ?? bridge.error ?? "unknown";
  await ctx.reply(
    `Cortex followup failed for run ${followupDispatch.runId}:\n${String(error).slice(0, 1200)}`
  );
  return true;
}

export async function maybeHandleCortexRoute(
  ctx: Context,
  message: string,
  chatId: number
): Promise<boolean> {
  if (!CORTEX_BRIDGE_ENABLED) return false;

  const normalized = message.trim();
  const lowered = normalized.toLowerCase();
  const scope = chatScope(chatId);
  const pending = pendingTasks.get(scope);

  if (startsWithAny(lowered, RUN_STATUS_PREFIXES)) {
    await sendStatusReply(ctx, normalized, chatId);
    return true;
  }

  if (startsWithAny(lowered, LEARN_STATUS_PREFIXES)) {
    await sendStatusReply(ctx, normalized, chatId);
    return true;
  }

  if (lowered.startsWith("/stop")) {
    const handled = await handleCortexStopCommand(ctx, chatId, normalized);
    return handled;
  }

  if (lowered.startsWith("/followup")) {
    return handleCortexFollowupCommand(ctx, chatId, normalized);
  }

  // UX alias: `/learnrun` should trigger the same natural task loop as `/run`.
  if (lowered.startsWith("/run") || lowered.startsWith("/learnrun")) {
    await runTaskAndReply(ctx, normalized, chatId);
    return true;
  }

  if (pending) {
    if (POSITIVE_CONFIRM.has(lowered)) {
      pendingTasks.delete(scope);
      // Keep natural-language task routing domain-agnostic. The Python
      // dispatcher infers domain/task when explicit controls are absent.
      const runText = `/run ${pending.prompt}`;
      await runTaskAndReply(ctx, runText, chatId);
      return true;
    }
    if (NEGATIVE_CONFIRM.has(lowered)) {
      pendingTasks.delete(scope);
      await ctx.reply("Task run canceled. Continuing in normal chat mode.");
      return true;
    }
    await ctx.reply("Reply with 'yes' to run via Cortex, or 'no' to cancel.");
    return true;
  }

  const activeRunId = activeRuns.get(scope)?.runId;
  if (activeRunId && !normalized.startsWith("/")) {
    // During active runs, plain text is treated as steering input.
    return handleCortexFollowupCommand(ctx, chatId, normalized);
  }

  if (!CORTEX_AUTO_TASK_ROUTING || !looksLikeTaskIntent(normalized)) {
    return false;
  }

  if (!CORTEX_CONFIRMATION_ENABLED) {
    // Same domain-agnostic routing path as the confirmation flow.
    const runText = `/run ${normalized}`;
    await runTaskAndReply(ctx, runText, chatId);
    return true;
  }

  pendingTasks.set(scope, { prompt: normalized, createdAtMs: Date.now() });
  await ctx.reply(
    "This looks like a task. Reply 'yes' to run it via Cortex learning loop, or 'no' to keep chatting."
  );
  return true;
}
