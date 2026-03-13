import { ChildProcess, spawn } from "child_process";
import { EventEmitter } from "events";
import * as path from "path";
import * as net from "net";
import * as http from "http";
import { app } from "electron";

const CREATE_NO_WINDOW = 0x08000000;

export class GatewayManager extends EventEmitter {
  private process: ChildProcess | null = null;
  private port: number = 18789;
  private stateDir: string;
  private restartCount: number = 0;
  private maxRestarts: number = 3;
  private stopping: boolean = false;

  constructor(stateDir: string) {
    super();
    this.stateDir = stateDir;
  }

  /** Resolve path to bundled node.exe */
  private getNodePath(): string {
    if (app.isPackaged) {
      return path.join(process.resourcesPath, "node.exe");
    }
    // Dev: use openclaw-node's bundled node first, fall back to system node
    const ocNode = process.env.USERPROFILE
      ? path.join(process.env.USERPROFILE, ".openclaw-node", "node.exe")
      : "";
    if (ocNode && require("fs").existsSync(ocNode)) return ocNode;
    return "node";
  }

  /** Resolve path to bundled openclaw entry */
  private getOpenClawEntry(): string {
    if (app.isPackaged) {
      return path.join(process.resourcesPath, "openclaw", "openclaw.mjs");
    }
    // Dev: check .openclaw-node install first, then npm global
    const candidates = [
      process.env.USERPROFILE
        ? path.join(process.env.USERPROFILE, ".openclaw-node", "node_modules", "openclaw", "dist", "index.js")
        : "",
      process.env.USERPROFILE
        ? path.join(process.env.USERPROFILE, ".openclaw-node", "node_modules", "openclaw", "openclaw.mjs")
        : "",
      process.env.APPDATA
        ? path.join(process.env.APPDATA, "npm", "node_modules", "openclaw", "dist", "index.js")
        : "",
      process.env.APPDATA
        ? path.join(process.env.APPDATA, "npm", "node_modules", "openclaw", "openclaw.mjs")
        : "",
    ];
    const fs = require("fs");
    for (const p of candidates) {
      if (p && fs.existsSync(p)) return p;
    }
    return candidates[0]; // will fail with a clear error
  }

  /** Find a free port */
  private findFreePort(): Promise<number> {
    return new Promise((resolve, reject) => {
      const server = net.createServer();
      server.listen(0, "127.0.0.1", () => {
        const addr = server.address();
        if (addr && typeof addr === "object") {
          const port = addr.port;
          server.close(() => resolve(port));
        } else {
          server.close(() => reject(new Error("Failed to get port")));
        }
      });
      server.on("error", reject);
    });
  }

  /** Check if gateway is ready */
  private checkHealth(): Promise<boolean> {
    return new Promise((resolve) => {
      const req = http.get(
        `http://127.0.0.1:${this.port}/health`,
        { timeout: 2000 },
        (res) => {
          resolve(res.statusCode === 200);
        }
      );
      req.on("error", () => resolve(false));
      req.on("timeout", () => {
        req.destroy();
        resolve(false);
      });
    });
  }

  /** Wait for gateway to become ready */
  private async waitForReady(timeoutMs: number = 30000): Promise<boolean> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (await this.checkHealth()) return true;
      await new Promise((r) => setTimeout(r, 500));
    }
    return false;
  }

  /** Start the gateway process */
  async start(): Promise<number> {
    this.stopping = false;
    this.emit("status", "starting");

    this.port = await this.findFreePort();

    const nodePath = this.getNodePath();
    const entryPath = this.getOpenClawEntry();

    const args = [
      entryPath,
      "gateway",
      "run",
      "--port",
      String(this.port),
      "--bind",
      "loopback",
      "--force",
      "--allow-unconfigured",
    ];

    const spawnOpts: any = {
      env: {
        ...process.env,
        OPENCLAW_STATE_DIR: this.stateDir,
        NODE_ENV: "production",
      },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    };

    // On Windows, use CREATE_NO_WINDOW to prevent console window flash
    if (process.platform === "win32") {
      spawnOpts.creationFlags = CREATE_NO_WINDOW;
    }

    this.process = spawn(nodePath, args, spawnOpts);

    this.process.stdout?.on("data", (data: Buffer) => {
      const msg = data.toString().trim();
      if (msg) this.emit("log", msg);
    });

    this.process.stderr?.on("data", (data: Buffer) => {
      const msg = data.toString().trim();
      if (msg) this.emit("log", `[stderr] ${msg}`);
    });

    this.process.on("exit", (code, signal) => {
      this.emit("log", `Gateway exited: code=${code} signal=${signal}`);
      this.process = null;

      if (!this.stopping && this.restartCount < this.maxRestarts) {
        this.restartCount++;
        this.emit("status", "restarting");
        this.emit("log", `Restarting gateway (attempt ${this.restartCount}/${this.maxRestarts})`);
        setTimeout(() => this.start(), 2000);
      } else if (!this.stopping) {
        this.emit("status", "failed");
      }
    });

    const ready = await this.waitForReady();
    if (ready) {
      this.restartCount = 0;
      this.emit("status", "running");
    } else {
      this.emit("status", "timeout");
    }

    return this.port;
  }

  /** Stop the gateway */
  stop(): void {
    this.stopping = true;
    if (this.process) {
      this.emit("status", "stopping");
      if (process.platform === "win32" && this.process.pid) {
        try {
          spawn("taskkill", ["/pid", String(this.process.pid), "/T", "/F"], {
            windowsHide: true,
            ...(process.platform === "win32" ? { creationFlags: CREATE_NO_WINDOW } : {}),
          } as any);
        } catch {
          this.process.kill("SIGKILL");
        }
      } else {
        this.process.kill("SIGTERM");
        setTimeout(() => {
          if (this.process) this.process.kill("SIGKILL");
        }, 5000);
      }
      this.process = null;
      this.emit("status", "stopped");
    }
  }

  /** Restart the gateway */
  async restart(): Promise<number> {
    this.restartCount = 0;
    this.stop();
    await new Promise((r) => setTimeout(r, 1000));
    return this.start();
  }

  getPort(): number {
    return this.port;
  }

  isRunning(): boolean {
    return this.process !== null && !this.process.killed;
  }
}
