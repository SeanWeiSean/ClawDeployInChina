import { app, Tray, Menu, nativeImage } from "electron";
import * as path from "path";

let tray: Tray | null = null;

export function createTray(callbacks: {
  onShowWindow: () => void;
  onRestartGateway: () => void;
}): void {
  const iconPath = path.join(__dirname, "../assets/image.png");
  const icon = nativeImage.createFromPath(iconPath);

  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip("OpenClaw");

  updateTrayMenu("stopped", callbacks);

  tray.on("double-click", () => {
    callbacks.onShowWindow();
  });
}

export function updateTrayMenu(
  gatewayStatus: string,
  callbacks?: { onShowWindow: () => void; onRestartGateway: () => void }
): void {
  if (!tray) return;

  const statusLabels: Record<string, string> = {
    stopped: "⏹ Gateway Stopped",
    starting: "⏳ Gateway Starting...",
    running: "✅ Gateway Running",
    restarting: "🔄 Gateway Restarting...",
    failed: "❌ Gateway Failed",
    stopping: "⏳ Gateway Stopping...",
    timeout: "⚠️ Gateway Timeout",
  };

  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: statusLabels[gatewayStatus] || `Gateway: ${gatewayStatus}`,
      enabled: false,
    },
    { type: "separator" },
    {
      label: "Show Window",
      click: () => callbacks?.onShowWindow(),
    },
    {
      label: "Restart Gateway",
      click: () => callbacks?.onRestartGateway(),
    },
    { type: "separator" },
    {
      label: "Quit",
      click: () => {
        (app as any).isQuitting = true;
        app.quit();
      },
    },
  ];

  const contextMenu = Menu.buildFromTemplate(template);
  tray.setContextMenu(contextMenu);
}
