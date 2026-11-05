#!/usr/bin/env node
/**
 * TypeVector Arena — Unified Local Development Runner
 * Starts the Vite frontend server and FastAPI reload server concurrently.
 * Handles process shutdown and formats logs clearly.
 */

import { spawn } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, "..");

console.log("\x1b[36m%s\x1b[0m", "==================================================");
console.log("\x1b[36m%s\x1b[0m", "   TypeVector Arena — Local Development Runner   ");
console.log("\x1b[36m%s\x1b[0m", "==================================================");

const children = [];

function killChildren() {
  console.log("\n\x1b[33m%s\x1b[0m", "Shutting down TypeVector Arena development processes...");
  for (const child of children) {
    if (child && !child.killed) {
      try {
        child.kill();
      } catch (e) {
        // Ignore kill errors on exit
      }
    }
  }
}

process.on("SIGINT", () => {
  killChildren();
  process.exit(0);
});

process.on("SIGTERM", () => {
  killChildren();
  process.exit(0);
});

function spawnService(name, color, fullCommand, cwd) {
  const child = spawn(fullCommand, {
    cwd,
    shell: true,
    stdio: ["inherit", "pipe", "pipe"],
    env: { ...process.env, Path: `C:\\Users\\vivek\\.local\\bin;${process.env.Path}` },
  });

  children.push(child);

  child.stdout.on("data", (data) => {
    const lines = data.toString().trim().split("\n");
    for (const line of lines) {
      if (line.trim()) {
        console.log(`${color}[${name}]\x1b[0m ${line}`);
      }
    }
  });

  child.stderr.on("data", (data) => {
    const lines = data.toString().trim().split("\n");
    for (const line of lines) {
      if (line.trim()) {
        console.log(`${color}[${name}]\x1b[0m ${line}`);
      }
    }
  });

  child.on("close", (code) => {
    if (code !== 0 && code !== null) {
      console.log(`\x1b[31m[${name}] Process exited with code ${code}\x1b[0m`);
    }
  });

  return child;
}

// 1. Start FastAPI backend server
console.log("\x1b[32m%s\x1b[0m", "Starting FastAPI backend reload server on http://127.0.0.1:8000...");
spawnService(
  "API",
  "\x1b[34m", // Blue
  "uv run uvicorn typevector.main:app --reload --host 127.0.0.1 --port 8000",
  resolve(rootDir, "apps/api")
);

// 2. Start Vite frontend dev server
console.log("\x1b[32m%s\x1b[0m", "Starting Vite frontend dev server on http://127.0.0.1:5173...");
spawnService(
  "WEB",
  "\x1b[35m", // Magenta
  "pnpm --filter @typevector/web dev",
  rootDir
);

console.log("\x1b[32m%s\x1b[0m", "TypeVector Arena is running. Press Ctrl+C to stop.");
