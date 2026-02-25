import { spawn } from "child_process";
import { existsSync } from "fs";
import {
  CORTEX_BRIDGE_TIMEOUT_MS,
  CORTEX_DISPATCHER_PATH,
  CORTEX_ROOT,
} from "../../config";

export type CortexDispatchPayload = {
  mode?: "run" | "status" | "chat" | "cancel" | "followup";
  plan?: Record<string, unknown>;
  result?: Record<string, unknown>;
  ok?: boolean;
  reply?: string;
  [key: string]: unknown;
};

type BridgeResult = {
  ok: boolean;
  payload: CortexDispatchPayload | null;
  stdout: string;
  stderr: string;
  error?: string;
};

function parseJsonOutput(stdout: string): CortexDispatchPayload | null {
  const text = stdout.trim();
  if (!text) return null;
  try {
    return JSON.parse(text) as CortexDispatchPayload;
  } catch {
    return null;
  }
}

export async function runCortexDispatch(
  text: string,
  chatId: string
): Promise<BridgeResult> {
  if (!existsSync(CORTEX_DISPATCHER_PATH)) {
    return {
      ok: false,
      payload: null,
      stdout: "",
      stderr: "",
      error: `Dispatcher not found at ${CORTEX_DISPATCHER_PATH}`,
    };
  }

  return new Promise<BridgeResult>((resolve) => {
    const child = spawn(
      "python3",
      [CORTEX_DISPATCHER_PATH, "--text", text, "--chat-id", chatId],
      { cwd: CORTEX_ROOT }
    );

    let stdout = "";
    let stderr = "";
    let finished = false;

    const timeout = setTimeout(() => {
      if (finished) return;
      finished = true;
      child.kill("SIGTERM");
      resolve({
        ok: false,
        payload: null,
        stdout,
        stderr,
        error: `Cortex dispatch timed out after ${CORTEX_BRIDGE_TIMEOUT_MS}ms`,
      });
    }, CORTEX_BRIDGE_TIMEOUT_MS);

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", (error) => {
      if (finished) return;
      finished = true;
      clearTimeout(timeout);
      resolve({
        ok: false,
        payload: null,
        stdout,
        stderr,
        error: String(error),
      });
    });

    child.on("close", (code) => {
      if (finished) return;
      finished = true;
      clearTimeout(timeout);

      const payload = parseJsonOutput(stdout);
      resolve({
        ok: code === 0 && payload !== null,
        payload,
        stdout,
        stderr,
        error:
          code === 0
            ? payload
              ? undefined
              : "Dispatcher returned non-JSON output"
            : `Dispatcher exited with code ${code}`,
      });
    });
  });
}
