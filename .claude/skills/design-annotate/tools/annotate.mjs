#!/usr/bin/env node

/**
 * Design Review Annotator — Interactive Mode
 *
 * Pages load live in an iframe — interact with the UI, then switch to
 * Annotate mode to draw and comment. Playwright only runs on save.
 *
 * Usage:
 *   node annotate.mjs                           Auto-load from .design/manifest.json
 *   node annotate.mjs <file-or-url> [...]       Ad-hoc targets
 *
 * Examples:
 *   node annotate.mjs                            Load all pages from manifest
 *   node annotate.mjs .design/prototypes/a.html  Ad-hoc single page
 *   node annotate.mjs http://localhost:3000       Ad-hoc URL
 *
 * Options:
 *   --size WxH       Default viewport for captures (default: 1920x1080)
 *   --dpr N          Device pixel ratio for captures (default: 2)
 */

import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { exec } from "node:child_process";
import { dirname, join, resolve, relative, basename, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { chromium } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Parse args ──
const args = process.argv.slice(2);
let defaultViewportWidth = 1920;
let defaultViewportHeight = 1080;
let dpr = 2;
const targets = [];
let sessionName = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--session") {
    sessionName = (args[i + 1] && !args[i + 1].startsWith("--")) ? args[++i] : "__default__";
  } else if (args[i] === "--size" && args[i + 1]) {
    const [w, h] = args[++i].split("x");
    defaultViewportWidth = parseInt(w);
    defaultViewportHeight = parseInt(h);
  } else if (args[i] === "--dpr" && args[i + 1]) {
    dpr = parseInt(args[++i]);
  } else if (!args[i].startsWith("--")) {
    targets.push(args[i]);
  }
}

// ── Load from sessions.json if --session flag used ──
if (sessionName) {
  const sessionsPath = join(__dirname, ".design", "sessions.json");
  if (!existsSync(sessionsPath)) {
    console.error("No .design/sessions.json found. Create one or use manifest.json instead.");
    process.exit(1);
  }
  const sessionsData = JSON.parse(await readFile(sessionsPath, "utf8"));
  const name = sessionName === "__default__" ? sessionsData.default : sessionName;
  const session = sessionsData.sessions[name];
  if (!session) {
    console.error(`Session "${name}" not found. Available: ${Object.keys(sessionsData.sessions).join(", ")}`);
    process.exit(1);
  }
  console.log(`Loading session: ${session.name}\n`);
  for (const page of session.pages) {
    if (session.type === "dev-server") {
      targets.push({ _url: `${session.base}${page.path}`, _name: page.name });
    } else {
      targets.push({ _url: `file:///${resolve(page.path).replace(/\\/g, "/")}`, _name: page.name });
    }
  }
}

// ── Auto-load from manifest if no targets specified ──
const manifestPath = join(__dirname, ".design", "manifest.json");

if (targets.length === 0) {
  if (!existsSync(manifestPath)) {
    console.error(
      "No pages specified and no .design/manifest.json found.\n\n" +
      "Usage:\n" +
      "  node annotate.mjs                      Auto-load from .design/manifest.json\n" +
      "  node annotate.mjs <file-or-url> [...]   Ad-hoc targets\n\n" +
      "Run /design-annotate --setup to create the manifest."
    );
    process.exit(1);
  }

  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  if (!manifest.pages || manifest.pages.length === 0) {
    console.error("manifest.json has no pages. Add pages with /design-web or /design-app.");
    process.exit(1);
  }

  console.log(`Loading ${manifest.pages.length} page(s) from manifest...\n`);
  for (const page of manifest.pages) {
    targets.push(page.path);
  }
}

// ── Build page list ──
// absPath: absolute local path (for /files/ serving). null for http:// targets.
const pages = targets.map((target) => {
  if (typeof target === "object" && target._url) {
    // Session entry — parse absPath from file:// URL if applicable
    let absPath = null;
    if (target._url.startsWith("file:///")) {
      absPath = decodeURIComponent(target._url.replace(/^file:\/\/\//, "")).replace(/\//g, "\\");
    }
    return { name: target._name, url: target._url, absPath };
  }

  if (!target.startsWith("http")) {
    const abs = resolve(target);
    if (!existsSync(abs)) {
      console.error(`File not found: ${abs}`);
      process.exit(1);
    }
    return {
      name: basename(target, extname(target)),
      url: `file:///${abs.replace(/\\/g, "/")}`,
      absPath: abs,
    };
  }

  const urlPath = new URL(target).pathname;
  const name = urlPath === "/" ? "home" : urlPath.replace(/^\//, "").replace(/\//g, "-");
  return { name, url: target, absPath: null };
});

// ── Setup ──
const reviewsDir = join(__dirname, ".design", "reviews");
await mkdir(reviewsDir, { recursive: true });

let browser = null;

async function ensureBrowser() {
  if (!browser) browser = await chromium.launch();
  return browser;
}

async function captureUrl(pageUrl, vw, vh, scrollY = 0, fullPage = false) {
  const b = await ensureBrowser();
  const ctx = await b.newContext({
    viewport: { width: vw, height: vh },
    deviceScaleFactor: dpr,
  });
  const pg = await ctx.newPage();
  await pg.goto(pageUrl, { waitUntil: "networkidle", timeout: 15000 });
  await pg.waitForTimeout(300);
  if (scrollY > 0) {
    await pg.evaluate((y) => window.scrollTo(0, y), scrollY);
    await pg.waitForTimeout(100);
  }
  const buffer = await pg.screenshot({ fullPage });
  await ctx.close();
  return buffer;
}

// ── MIME types ──
const MIME = {
  html: "text/html; charset=utf-8",
  css: "text/css", js: "application/javascript", mjs: "application/javascript",
  json: "application/json", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
  gif: "image/gif", svg: "image/svg+xml", webp: "image/webp",
  woff: "font/woff", woff2: "font/woff2", ttf: "font/ttf", ico: "image/x-icon",
};

const annotatorPath = join(__dirname, ".design", "tools", "annotator.html");

// ── HTTP Server ──
const server = createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");

  // Serve annotator UI — read fresh each request so HTML edits don't need a restart
  if (req.method === "GET" && req.url === "/") {
    try {
      const html = await readFile(annotatorPath, "utf8");
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(html);
    } catch (err) {
      res.writeHead(500);
      res.end("Failed to load annotator.html: " + err.message);
    }
    return;
  }

  // Static file serving for local HTML prototypes and their assets.
  // Maps /files/<relative-path> → <project-root>/<relative-path>
  if (req.method === "GET" && req.url.startsWith("/files/")) {
    const relPath = decodeURIComponent(req.url.slice(7)).replace(/\//g, "\\");
    const absPath = join(__dirname, relPath);
    if (!absPath.startsWith(__dirname)) {
      res.writeHead(403); res.end("Forbidden"); return;
    }
    try {
      const content = await readFile(absPath);
      const ext = extname(absPath).slice(1).toLowerCase();
      res.writeHead(200, {
        "Content-Type": MIME[ext] || "application/octet-stream",
        "Cache-Control": "no-cache",
      });
      res.end(content);
    } catch {
      res.writeHead(404); res.end("Not found");
    }
    return;
  }

  // Page list — includes iframeUrl per page
  if (req.method === "GET" && req.url === "/api/pages") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      pages: pages.map((p, i) => ({
        name: p.name,
        index: i,
        // Local files served via /files/; http:// targets loaded directly
        iframeUrl: p.absPath
          ? `/files/${relative(__dirname, p.absPath).replace(/\\/g, "/")}`
          : p.url,
      })),
      dpr,
    }));
    return;
  }

  // On-demand Playwright capture (called by client before compositing annotations)
  if (req.method === "POST" && req.url === "/api/capture") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString());

    const idx = body.pageIndex ?? 0;
    const [vw, vh] = (body.viewport || `${defaultViewportWidth}x${defaultViewportHeight}`).split("x").map(Number);
    const scrollY = body.scrollY ?? 0;
    const fp = body.fullPage ?? false;

    if (idx < 0 || idx >= pages.length) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Invalid page index" }));
      return;
    }

    process.stdout.write(`  Capturing ${pages[idx].name} @ ${vw}x${vh}${scrollY ? ` scroll=${scrollY}` : ""} ... `);
    try {
      const buffer = await captureUrl(pages[idx].url, vw, vh, scrollY, fp);
      console.log(`done (${(buffer.length / 1024).toFixed(0)}KB)`);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        image: `data:image/png;base64,${buffer.toString("base64")}`,
        width: fp ? undefined : vw * dpr,
        height: fp ? undefined : vh * dpr,
      }));
    } catch (err) {
      console.log(`FAILED: ${err.message}`);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  // Save annotated PNG + JSON sidecar
  if (req.method === "POST" && req.url === "/save") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString());

    const pName = body.pageName || "review";
    const base64Data = body.image.replace(/^data:image\/png;base64,/, "");
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const vpLabel = body.viewport ? `-${body.viewport}` : "";
    const filename = `${pName}${vpLabel}-${timestamp}.png`;
    const filepath = join(reviewsDir, filename);

    await writeFile(filepath, Buffer.from(base64Data, "base64"));

    if (body.review) {
      const jsonPath = filepath.replace(/\.png$/, ".json");
      await writeFile(jsonPath, JSON.stringify(body.review, null, 2));
    }

    console.log(`  Saved: ${filename}`);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ saved: filename, path: filepath }));
    return;
  }

  // Save session manifest (Save All)
  if (req.method === "POST" && req.url === "/api/manifest") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString());
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const sessionPath = join(reviewsDir, `session-${timestamp}.json`);
    await writeFile(sessionPath, JSON.stringify(body, null, 2));
    console.log(`\n  Session: session-${timestamp}.json`);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ saved: `session-${timestamp}.json` }));
    return;
  }

  // AI comment refinement
  if (req.method === "POST" && req.url === "/api/process") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString());

    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "No ANTHROPIC_API_KEY set. Export it to enable AI refinement." }));
      return;
    }

    try {
      const apiRes = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify({
          model: "claude-haiku-4-5-20251001",
          max_tokens: 256,
          messages: [{
            role: "user",
            content: `You are a design review assistant. Refine this rough UI feedback note into a clear, actionable design instruction. Keep it concise (1-3 sentences). Include specific CSS/layout terms where possible.\n\nRaw note: "${body.text}"\n\nRespond with only the refined instruction, no preamble.`,
          }],
        }),
      });

      if (!apiRes.ok) {
        const errBody = await apiRes.text();
        throw new Error(`API ${apiRes.status}: ${errBody.slice(0, 200)}`);
      }

      const result = await apiRes.json();
      const refined = result.content?.[0]?.text || body.text;
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ refined }));
    } catch (err) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  // Update manifest page statuses
  if (req.method === "POST" && req.url === "/api/update-manifest") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString());

    try {
      if (existsSync(manifestPath)) {
        const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
        const annotatedPages = body.annotatedPages || [];
        for (const page of manifest.pages) {
          if (annotatedPages.includes(page.name)) page.status = "reviewed";
        }
        await writeFile(manifestPath, JSON.stringify(manifest, null, 2));
        console.log(`  Manifest updated: ${annotatedPages.join(", ")} → reviewed`);
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
    } catch (err) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  // Shutdown
  if (req.method === "POST" && req.url === "/api/shutdown") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true }));

    console.log("\n────────────────────────────────────────");
    console.log("  Review complete. Shutting down.");
    console.log("");
    console.log("  Next step — process your feedback:");
    console.log("    /design-annotate --latest");
    console.log("────────────────────────────────────────\n");

    server.close();
    if (browser) await browser.close();
    process.exit(0);
  }

  res.writeHead(404);
  res.end("Not found");
});

server.listen(0, () => {
  const port = server.address().port;
  const url = `http://localhost:${port}`;
  console.log(`\nAnnotator ready: ${url}`);
  console.log(`Pages: ${pages.map((p) => p.name).join(", ")}`);
  console.log("Press Ctrl+C to stop.\n");

  const cmd =
    process.platform === "win32"
      ? `start "" "${url}"`
      : process.platform === "darwin"
        ? `open "${url}"`
        : `xdg-open "${url}"`;
  exec(cmd);
});

process.on("SIGINT", async () => {
  console.log("\nShutting down annotator.");
  server.close();
  if (browser) await browser.close();
  process.exit(0);
});
