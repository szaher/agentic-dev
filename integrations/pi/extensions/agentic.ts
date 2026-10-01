import { execFile } from "node:child_process";
import { promisify } from "node:util";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const execFileAsync = promisify(execFile);

async function runAgentic(args: string[]): Promise<string> {
  try {
    const { stdout, stderr } = await execFileAsync("agentic", args, {
      cwd: process.cwd(),
      maxBuffer: 1024 * 1024,
    });
    return (stdout || stderr || "agentic completed").trim();
  } catch (error: any) {
    const detail = error?.stderr || error?.stdout || error?.message || String(error);
    throw new Error(String(detail).trim());
  }
}

function notify(ctx: any, text: string, kind: "info" | "error" = "info") {
  const limit = 7000;
  ctx.ui.notify(text.length > limit ? text.slice(0, limit) + "\n…output truncated" : text, kind);
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("agentic-doctor", {
    description: "Check the local agentic development toolchain",
    handler: async (_args, ctx) => {
      try {
        notify(ctx, await runAgentic(["doctor"]));
      } catch (error: any) {
        notify(ctx, String(error.message || error), "error");
      }
    },
  });

  pi.registerCommand("agentic-skills", {
    description: "Preview repository/task-aware Agent Skill recommendations",
    handler: async (task, ctx) => {
      const args = ["skills", "suggest", ".", "--no-prompt", "--target", "pi"];
      const trimmed = String(task || "").trim();
      if (trimmed) args.push("--task", trimmed);
      try {
        notify(ctx, await runAgentic(args));
      } catch (error: any) {
        notify(ctx, String(error.message || error), "error");
      }
    },
  });

  pi.registerCommand("agentic-skills-activate", {
    description: "Activate recommended Agent Skills for Pi in the current repository",
    handler: async (task, ctx) => {
      const args = ["skills", "suggest", ".", "--yes", "--target", "pi"];
      const trimmed = String(task || "").trim();
      if (trimmed) args.push("--task", trimmed);
      try {
        notify(ctx, await runAgentic(args));
      } catch (error: any) {
        notify(ctx, String(error.message || error), "error");
      }
    },
  });

  pi.registerCommand("agentic-status", {
    description: "Show Agent Skills active in the current repository",
    handler: async (_args, ctx) => {
      try {
        notify(ctx, await runAgentic(["skills", "status", "."]));
      } catch (error: any) {
        notify(ctx, String(error.message || error), "error");
      }
    },
  });
}
