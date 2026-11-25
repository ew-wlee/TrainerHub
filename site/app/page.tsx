const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const REPO = "https://github.com/ew-wlee/TrainerHub";
const shot = (name: string) => `${BASE}/screenshots/${name}`;

const features = [
  {
    title: "Bilingual instant search",
    body: "Chinese, English, full pinyin or initials — typing “hshwk” finds 黑神话：悟空. The index lives in memory, so every keystroke is a local lookup.",
    tag: "search.py",
    icon: "search",
  },
  {
    title: "Multi-source aggregation",
    body: "FLiNG Trainer for direct downloads, XiaoXing for indexed netdisk releases, plus local folder import and any JSON index you host yourself.",
    tag: "sources/",
    icon: "layers",
  },
  {
    title: "One-click pipeline",
    body: "Resolve the real file URL, stream with progress, sniff the container, extract safely, tag the version and archive it as source / game / version.",
    tag: "downloader.py",
    icon: "download",
  },
  {
    title: "A library you can reason about",
    body: "Every install writes a manifest.json with its origin, version and page URL. “Where did this exe come from” is always answerable.",
    tag: "library.py",
    icon: "folder",
  },
  {
    title: "Version awareness",
    body: "The index records what the site ships today; the library records what you have. Differences show up as an update badge.",
    tag: "updater.py",
    icon: "refresh",
  },
  {
    title: "Safety rails",
    body: "Zip-slip protection, size caps, and nothing is ever auto-executed. Defender helper is opt-in, scoped to the library folder and needs admin rights.",
    tag: "archive.py",
    icon: "shield",
  },
];

const sources = [
  {
    name: "FLiNG Trainer",
    url: "flingtrainer.com",
    delivery: "Direct file",
    handling: "One-click download",
    tone: "text-mint-400",
  },
  {
    name: "小幸修改器",
    url: "xiaoxingjie.com",
    delivery: "百度网盘 / MediaFire",
    handling: "Indexed, opens page",
    tone: "text-amber-400",
  },
  {
    name: "Custom JSON",
    url: "your own URL",
    delivery: "Whatever you host",
    handling: "Index adapter",
    tone: "text-brand-300",
  },
  {
    name: "Local import",
    url: "your folders",
    delivery: "Already on disk",
    handling: "Registered into library",
    tone: "text-mist-400",
  },
];

const stats = [
  { value: "827", label: "entries indexed live" },
  { value: "~5s", label: "full catalogue sync" },
  { value: "30 ms", label: "P95 search latency" },
  { value: "41", label: "offline unit tests" },
];

type Shot = { file: string; title: string; note: string; fit?: "cover" | "contain" };

const screenshots: Shot[] = [
  { file: "01-discover.png", title: "Discover", note: "One list, every source, detail on the right." },
  { file: "02-detail-zh.png", title: "Detail", note: "Options, supported game version, install state." },
  { file: "03-downloads.png", title: "Downloads", note: "Inline progress instead of modal dialogs." },
  { file: "04-library.png", title: "Library", note: "Everything installed, with update badges." },
  { file: "05-settings.png", title: "Settings", note: "Sources, storage, safety — one page, no submenus." },
  {
    file: "06-wizard.png",
    title: "First run",
    note: "Disclaimer, library folder, sources — three steps, once.",
    fit: "contain" as const,
  },
];

const icons: Record<string, React.ReactNode> = {
  search: (
    <path d="M11 4a7 7 0 1 0 4.2 12.6l3.1 3.1 1.4-1.4-3.1-3.1A7 7 0 0 0 11 4Zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z" />
  ),
  layers: (
    <path d="m12 3 9 5-9 5-9-5 9-5Zm0 12.2 6.9-3.8L21 13l-9 5-9-5 2.1-1.6L12 15.2Zm0 4 6.9-3.8L21 17l-9 5-9-5 2.1-1.6L12 19.2Z" />
  ),
  download: <path d="M11 3h2v9.2l3.3-3.3 1.4 1.4L12 16.4l-5.7-6.1 1.4-1.4L11 12.2V3ZM4 19h16v2H4v-2Z" />,
  folder: (
    <path d="M3 6a2 2 0 0 1 2-2h4.2l2 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6Zm2 0v2H19V8H5Zm0 4v7h14v-7H5Z" />
  ),
  refresh: (
    <path d="M12 5a7 7 0 0 1 6.3 4H20V4.5h-1.7v1.9A8.9 8.9 0 0 0 12 3a9 9 0 1 0 8.6 11.7l-1.7-.6A7 7 0 1 1 12 5Z" />
  ),
  shield: (
    <path d="M12 2 4 5v7c0 4.4 3.2 8.4 8 10 4.8-1.6 8-5.6 8-10V5l-8-3Zm0 2.2 6 2.2V12c0 3.4-2.3 6.6-6 8-3.7-1.4-6-4.6-6-8V6.4l6-2.2Zm-1 4.3h2v4h3l-4 4-4-4h3v-4Z" />
  ),
};

export default function Page() {
  return (
    <main className="relative overflow-hidden">
      {/* backdrop */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 aurora" />
        <div className="absolute inset-0 grid-veil opacity-70" />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      </div>

      {/* nav */}
      <header className="sticky top-0 z-50 border-b border-white/5 bg-ink-950/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-6">
          <a href="#top" className="flex items-center gap-2.5">
            <Logo />
            <span className="text-[15px] font-semibold tracking-wide">TrainerHub</span>
          </a>
          <nav className="hidden items-center gap-1 text-sm text-mist-400 md:flex">
            {[
              ["Features", "#features"],
              ["Screens", "#screens"],
              ["Sources", "#sources"],
              ["Architecture", "#architecture"],
              ["Docs", "#docs"],
            ].map(([label, href]) => (
              <a
                key={href}
                href={href}
                className="rounded-lg px-3 py-1.5 transition-colors hover:bg-white/5 hover:text-mist-100"
              >
                {label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <a
              href={`${REPO}`}
              className="hidden rounded-lg border border-white/10 px-3.5 py-2 text-sm text-mist-300 transition-colors hover:border-white/20 hover:text-white sm:block"
            >
              GitHub
            </a>
            <a
              href={`${REPO}/releases/latest`}
              className="rounded-lg bg-brand-400 px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_24px_-8px_rgba(78,140,255,0.8)] transition-transform hover:-translate-y-0.5 hover:bg-brand-300"
            >
              Download
            </a>
          </div>
        </div>
      </header>

      {/* hero */}
      <section id="top" className="mx-auto max-w-6xl px-6 pt-20 pb-10">
        <div className="flex flex-col items-center text-center">
          <div className="animate-float-up inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3.5 py-1.5 text-xs text-mist-400">
            <span className="h-1.5 w-1.5 rounded-full bg-mint-400 animate-pulse-dot" />
            Windows first · MIT licensed · No Python required
          </div>

          <h1
            className="animate-float-up mt-7 max-w-[900px] text-balance text-[38px] font-semibold leading-[1.08] tracking-tight sm:text-[56px]"
            style={{ animationDelay: "60ms" }}
          >
            Every single-player trainer,
            <br />
            <span className="bg-gradient-to-r from-brand-300 via-brand-400 to-mint-400 bg-clip-text text-transparent">
              in one window.
            </span>
          </h1>

          <p
            className="animate-float-up mt-6 max-w-2xl text-balance text-[15px] leading-7 text-mist-400"
            style={{ animationDelay: "120ms" }}
          >
            Searches nine hundred trainer records across multiple sites, in Chinese or
            English, then downloads, extracts and archives them into a library that
            actually tells you what version you have.
          </p>

          <div
            className="animate-float-up mt-9 flex flex-wrap items-center justify-center gap-3"
            style={{ animationDelay: "180ms" }}
          >
            <a
              href={`${REPO}/releases/latest`}
              className="group inline-flex items-center gap-2.5 rounded-xl bg-brand-400 px-6 py-3.5 text-sm font-semibold text-white shadow-[0_16px_40px_-16px_rgba(78,140,255,0.9)] transition-all hover:-translate-y-0.5 hover:bg-brand-300"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M11 3h2v9.2l3.3-3.3 1.4 1.4L12 16.4l-5.7-6.1 1.4-1.4L11 12.2V3ZM4 19h16v2H4v-2Z" />
              </svg>
              Download for Windows
              <span className="text-white/60 transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </a>
            <a
              href="#docs"
              className="rounded-xl border border-white/12 px-6 py-3.5 text-sm text-mist-300 transition-colors hover:border-white/25 hover:text-white"
            >
              Run from source
            </a>
          </div>

          <p className="mt-4 text-xs text-mist-600">
            Single self-contained <code className="font-mono text-mist-400">TrainerHub.exe</code> ·
            ~60 MB · no installer, no admin rights
          </p>
        </div>

        {/* hero shot */}
        <div
          className="animate-float-up relative mx-auto mt-14 max-w-5xl"
          style={{ animationDelay: "240ms" }}
        >
          <div className="absolute -inset-x-10 -top-10 h-40 bg-brand-400/20 blur-3xl" />
          <div className="glow-frame relative overflow-hidden rounded-2xl bg-ink-900">
            <div className="flex h-9 items-center gap-1.5 border-b border-white/5 bg-ink-800/80 px-4">
              <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]/80" />
              <span className="ml-3 font-mono text-[11px] text-mist-600">TrainerHub · 0.1.0</span>
            </div>
            <img
              src={shot("01-discover.png")}
              alt="TrainerHub discover page with search, results list and detail panel"
              className="w-full"
              loading="eager"
            />
          </div>
        </div>
      </section>

      {/* stats */}
      <section className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl bg-white/5 md:grid-cols-4">
          {stats.map((item) => (
            <div key={item.label} className="bg-ink-900/80 px-6 py-7 text-center">
              <div className="text-2xl font-semibold text-mist-100">{item.value}</div>
              <div className="mt-1 text-xs text-mist-600">{item.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* features */}
      <section id="features" className="mx-auto max-w-6xl px-6 py-16">
        <SectionHead
          eyebrow="Capabilities"
          title="Built around the boring parts"
          body="Not another search page — the work is in resolution, verification and keeping state across sessions."
        />
        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <article
              key={feature.title}
              className="group relative overflow-hidden rounded-xl border border-white/[0.07] bg-ink-900/70 p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-400/40 hover:bg-ink-800/80"
            >
              <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-brand-400/50 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
              <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-brand-400/10 text-brand-300 ring-1 ring-inset ring-brand-400/20">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  {icons[feature.icon]}
                </svg>
              </div>
              <h3 className="text-[15px] font-semibold text-mist-100">{feature.title}</h3>
              <p className="mt-2 text-[13px] leading-6 text-mist-400">{feature.body}</p>
              <div className="mt-4 font-mono text-[11px] text-mist-600">{feature.tag}</div>
            </article>
          ))}
        </div>
      </section>

      {/* screenshots */}
      <section id="screens" className="mx-auto max-w-6xl px-6 py-16">
        <SectionHead
          eyebrow="Interface"
          title="Three panes, no clutter"
          body="Sources on the left, results in the middle, evidence on the right. Download progress lives in the list, not in a modal."
        />
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {screenshots.map((item) => (
            <figure
              key={item.file}
              className="group overflow-hidden rounded-xl border border-white/[0.07] bg-ink-900/70 transition-colors hover:border-white/15"
            >
              <div className="aspect-[16/10] w-full border-b border-white/5 bg-ink-950">
                <img
                  src={shot(item.file)}
                  alt={item.title}
                  className={`h-full w-full ${
                    item.fit === "contain" ? "object-contain" : "object-cover object-top"
                  }`}
                  loading="lazy"
                />
              </div>
              <figcaption className="flex items-baseline gap-3 px-5 py-4">
                <span className="text-sm font-medium text-mist-100">{item.title}</span>
                <span className="text-xs text-mist-600">{item.note}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      {/* sources */}
      <section id="sources" className="mx-auto max-w-6xl px-6 py-16">
        <SectionHead
          eyebrow="Data sources"
          title="Metadata only, always"
          body="TrainerHub never hosts or mirrors trainer binaries. Downloads go from the original site straight to your disk."
        />
        <div className="mt-10 overflow-hidden rounded-xl border border-white/[0.07]">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-mist-600">
              <tr>
                <th className="px-6 py-3.5 font-medium">Source</th>
                <th className="px-6 py-3.5 font-medium">Delivery</th>
                <th className="px-6 py-3.5 font-medium">In TrainerHub</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {sources.map((source) => (
                <tr key={source.name} className="transition-colors hover:bg-white/[0.02]">
                  <td className="px-6 py-4">
                    <div className="font-medium text-mist-100">{source.name}</div>
                    <div className="font-mono text-[11px] text-mist-600">{source.url}</div>
                  </td>
                  <td className="px-6 py-4 text-mist-400">{source.delivery}</td>
                  <td className={`px-6 py-4 font-medium ${source.tone}`}>{source.handling}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* architecture */}
      <section id="architecture" className="mx-auto max-w-6xl px-6 py-16">
        <SectionHead
          eyebrow="How it works"
          title="A Qt shell over a testable core"
          body="core/ has no Qt dependency, so search, parsing, archiving and the download pipeline are unit-tested without a display."
        />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {[
            {
              step: "01",
              title: "Source adapters",
              body: "Two-phase sync: eight REST pages build the index in ~5 s, detail pages load lazily and cache in SQLite.",
              items: ["fling.py", "xiaoxing.py", "custom_json.py"],
            },
            {
              step: "02",
              title: "Pipeline",
              body: "Resolve → stream → sniff → extract → archive. Zip-slip checks, size caps, cancellable, nothing executed.",
              items: ["downloader.py", "archive.py", "library.py"],
            },
            {
              step: "03",
              title: "Presentation",
              body: "QThread workers bridge to PySide6. One token table feeds both the stylesheet and the painted list delegate.",
              items: ["main_window.py", "theme.py", "app.qss"],
            },
          ].map((card) => (
            <div
              key={card.step}
              className="relative rounded-xl border border-white/[0.07] bg-ink-900/70 p-6"
            >
              <div className="font-mono text-xs text-brand-400">{card.step}</div>
              <h3 className="mt-3 text-[15px] font-semibold">{card.title}</h3>
              <p className="mt-2 text-[13px] leading-6 text-mist-400">{card.body}</p>
              <ul className="mt-4 flex flex-wrap gap-1.5">
                {card.items.map((item) => (
                  <li
                    key={item}
                    className="rounded-md bg-white/[0.04] px-2 py-1 font-mono text-[11px] text-mist-400"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* docs / quickstart */}
      <section id="docs" className="mx-auto max-w-6xl px-6 py-16">
        <SectionHead
          eyebrow="Get started"
          title="Run it, or build the exe"
          body="The released executable is self-contained. Building locally takes one command and produces the same onefile bundle."
        />
        <div className="mt-10 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-white/[0.07] bg-ink-900/70 p-7">
            <h3 className="text-[15px] font-semibold">Run from source</h3>
            <pre className="mt-4 overflow-x-auto rounded-lg bg-ink-950/80 p-4 font-mono text-[12.5px] leading-6 text-mist-300 ring-1 ring-inset ring-white/5">
              <code>{`git clone ${REPO}.git
cd TrainerHub
uv sync --extra dev
uv run trainerhub`}</code>
            </pre>
            <p className="mt-3 text-xs text-mist-600">
              Python 3.10+ · PySide6 · httpx · SQLite · 41 offline tests
            </p>
          </div>

          <div className="rounded-xl border border-white/[0.07] bg-ink-900/70 p-7">
            <h3 className="text-[15px] font-semibold">Build the executable</h3>
            <pre className="mt-4 overflow-x-auto rounded-lg bg-ink-950/80 p-4 font-mono text-[12.5px] leading-6 text-mist-300 ring-1 ring-inset ring-white/5">
              <code>{`# Windows
pwsh scripts/build_windows.ps1

# macOS / Linux
./scripts/build_macos.sh`}</code>
            </pre>
            <p className="mt-3 text-xs text-mist-600">
              Every <code className="font-mono text-mist-400">v*</code> tag is built and
              published by GitHub Actions on windows-latest.
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {[
            ["README (English)", `${REPO}/blob/main/README.md`],
            ["README（简体中文）", `${REPO}/blob/main/README.zh-CN.md`],
            ["Architecture notes", `${REPO}/blob/main/docs/architecture.md`],
          ].map(([label, href]) => (
            <a
              key={href}
              href={href}
              className="group flex items-center justify-between rounded-xl border border-white/[0.07] bg-ink-900/50 px-5 py-4 text-sm text-mist-300 transition-colors hover:border-brand-400/40 hover:text-white"
            >
              {label}
              <span className="text-mist-600 transition-transform group-hover:translate-x-0.5 group-hover:text-brand-300">
                ↗
              </span>
            </a>
          ))}
        </div>
      </section>

      {/* disclaimer + footer */}
      <footer className="mt-10 border-t border-white/5 bg-ink-950/60">
        <div className="mx-auto max-w-6xl px-6 py-12">
          <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-5 text-[13px] leading-6 text-amber-400/90">
            <strong className="font-semibold">Single-player only.</strong> TrainerHub is an
            index and download manager, not a cheat provider. No anti-cheat bypass is
            provided by design. Using third-party trainers in games with online components
            may violate their terms of service.
          </div>

          <div className="mt-8 flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3">
              <Logo />
              <div>
                <div className="text-sm font-semibold">TrainerHub</div>
                <div className="text-xs text-mist-600">
                  MIT © 2026 ew-wlee · inspired by Game Cheats Manager
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-5 text-sm text-mist-400">
              <a href={REPO} className="transition-colors hover:text-white">
                GitHub
              </a>
              <a href={`${REPO}/releases/latest`} className="transition-colors hover:text-white">
                Releases
              </a>
              <a href={`${REPO}/issues`} className="transition-colors hover:text-white">
                Issues
              </a>
              <a href={`${REPO}/blob/main/NOTICE.md`} className="transition-colors hover:text-white">
                Legal
              </a>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}

function SectionHead({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div className="max-w-2xl">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand-400">
        {eyebrow}
      </div>
      <h2 className="mt-3 text-balance text-[28px] font-semibold leading-tight sm:text-[34px]">
        {title}
      </h2>
      <p className="mt-3 text-[14px] leading-7 text-mist-400">{body}</p>
    </div>
  );
}

function Logo() {
  return (
    <svg width="30" height="30" viewBox="0 0 64 64" aria-hidden>
      <defs>
        <linearGradient id="th-mark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4E8CFF" />
          <stop offset="1" stopColor="#2DD4BF" />
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="56" height="56" rx="16" fill="url(#th-mark)" opacity="0.14" />
      <rect
        x="4.75"
        y="4.75"
        width="54.5"
        height="54.5"
        rx="15.25"
        fill="none"
        stroke="url(#th-mark)"
        strokeWidth="1.5"
      />
      <path d="M21 20h22v7.4H37.2V45h-8.4V27.4H21z" fill="url(#th-mark)" />
      <circle cx="44.5" cy="44.5" r="3.6" fill="#E6EAF2" opacity="0.9" />
    </svg>
  );
}
