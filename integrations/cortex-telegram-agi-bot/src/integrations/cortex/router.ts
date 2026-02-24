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

const pendingTasks = new Map<string, PendingTask>();

const POSITIVE_CONFIRM = new Set([
  "yes",
  "y",
  "run",
  "confirm",
  "go",
  "do it",
]);
const NEGATIVE_CONFIRM = new Set(["no", "n", "cancel", "skip", "stop"]);

function chatScope(chatId: number): string {
  return `tg-${chatId}`;
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
  const latest = (payload.latest_session as Record<string, unknown>) || {};
  return [
    "Cortex learning status:",
    `- lessons_total: ${lessonsTotal ?? "?"}`,
    `- lessons_scoped: ${lessonsScoped ?? "?"}`,
    `- latest_task: ${latest.task_id ?? "?"}`,
    `- latest_domain: ${latest.domain ?? "?"}`,
    `- latest_eval_passed: ${latest.eval_passed ?? "?"}`,
    `- lesson_activations: ${latest.lesson_activations ?? "?"}`,
    `- retrieval_help_ratio: ${latest.v2_retrieval_help_ratio ?? "?"}`,
  ].join("\n");
}

function summarizeRun(
  plan: Record<string, unknown> | undefined,
  result: Record<string, unknown> | undefined
): string {
  const taskId = result?.task_id ?? plan?.task_id ?? "?";
  const domain = result?.domain ?? plan?.domain ?? "?";
  const ok = result?.ok ?? false;
  const sessionId = result?.session_id ?? "?";
  const sessionDir = result?.session_dir ?? "?";
  const metrics = (result?.metrics as Record<string, unknown>) || {};
  return [
    `Cortex run: ${ok ? "ok" : "failed"}`,
    `- task_id: ${taskId}`,
    `- domain: ${domain}`,
    `- session_id: ${sessionId}`,
    `- eval_passed: ${metrics.eval_passed ?? "?"}`,
    `- eval_score: ${metrics.eval_score ?? "?"}`,
    `- lesson_activations: ${metrics.lesson_activations ?? "?"}`,
    `- retrieval_help_ratio: ${metrics.v2_retrieval_help_ratio ?? "?"}`,
    `- session_dir: ${sessionDir}`,
  ].join("\n");
}

async function runTaskAndReply(
  ctx: Context,
  runText: string,
  chatId: number
): Promise<void> {
  await ctx.reply("Running via Cortex learning loop...");
  const bridge = await runCortexDispatch(runText, chatScope(chatId));

  if (!bridge.ok || !bridge.payload) {
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

  await ctx.reply(
    (payload.reply as string) || "Cortex bridge completed with no summary."
  );
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

  if (
    lowered.startsWith("/run") ||
    lowered.startsWith("/learn-status") ||
    lowered.startsWith("/learnstatus") ||
    lowered.startsWith("/learn_status")
  ) {
    await runTaskAndReply(ctx, normalized, chatId);
    return true;
  }

  if (pending) {
    if (POSITIVE_CONFIRM.has(lowered)) {
      pendingTasks.delete(scope);
      const runText = `/run domain=${CORTEX_TASK_DEFAULT_DOMAIN} ${pending.prompt}`;
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

  if (!CORTEX_AUTO_TASK_ROUTING || !looksLikeTaskIntent(normalized)) {
    return false;
  }

  if (!CORTEX_CONFIRMATION_ENABLED) {
    const runText = `/run domain=${CORTEX_TASK_DEFAULT_DOMAIN} ${normalized}`;
    await runTaskAndReply(ctx, runText, chatId);
    return true;
  }

  pendingTasks.set(scope, { prompt: normalized, createdAtMs: Date.now() });
  await ctx.reply(
    "This looks like a task. Reply 'yes' to run it via Cortex learning loop, or 'no' to keep chatting."
  );
  return true;
}
