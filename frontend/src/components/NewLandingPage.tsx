import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { motion, type Variants } from 'framer-motion';
import Lenis from 'lenis';
import { Map, Satellite, Ship, Waves, type LucideIcon } from 'lucide-react';

gsap.registerPlugin(ScrollTrigger);

const TOTAL_FRAMES = 40;

// Stagger helper for child animations
const staggerContainer: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.15 } },
};

const smoothEase: [number, number, number, number] = [0.16, 1, 0.3, 1];

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.8, ease: smoothEase } },
};

export const NewLandingPage: React.FC = () => {
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sequenceRef = useRef<HTMLDivElement>(null);

  const [images, setImages] = useState<HTMLImageElement[]>([]);
  const [imagesLoaded, setImagesLoaded] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);

  // Lenis smooth scroll
  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.5,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      orientation: 'vertical',
      gestureOrientation: 'vertical',
      smoothWheel: true,
      wheelMultiplier: 0.8,
      touchMultiplier: 2,
    });

    // Keep Lenis and ScrollTrigger in the same clock to avoid jitter/stalls.
    lenis.on('scroll', ScrollTrigger.update);
    const update = (time: number) => {
      lenis.raf(time * 1000);
    };
    gsap.ticker.add(update);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(update);
      lenis.destroy();
    };
  }, []);

  // Preload image sequence
  useEffect(() => {
    const loadedImages: HTMLImageElement[] = [];
    let loadedCount = 0;
    for (let i = 1; i <= TOTAL_FRAMES; i++) {
      const img = new Image();
      const index = i.toString().padStart(3, '0');
      img.src = `/gallery1/ezgif-frame-${index}.jpg`;
      img.onload = () => {
        loadedCount++;
        setLoadingProgress(Math.round((loadedCount / TOTAL_FRAMES) * 100));
        if (loadedCount === TOTAL_FRAMES) { setImages(loadedImages); setImagesLoaded(true); }
      };
      img.onerror = () => {
        loadedCount++;
        setLoadingProgress(Math.round((loadedCount / TOTAL_FRAMES) * 100));
        if (loadedCount === TOTAL_FRAMES) { setImages(loadedImages); setImagesLoaded(true); }
      };
      loadedImages.push(img);
    }
  }, []);

  // Canvas + GSAP scroll-triggered frame animation
  useEffect(() => {
    if (!imagesLoaded || !canvasRef.current || !sequenceRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let cw = 0;
    let ch = 0;
    let rafId: number | null = null;
    let queuedFrame = 0;

    const setCanvasSize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      cw = rect.width;
      ch = rect.height;
      canvas.width = Math.round(cw * dpr);
      canvas.height = Math.round(ch * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
    };

    const render = (index: number) => {
      const img = images[index];
      if (!img || !img.complete || cw === 0 || ch === 0) return;
      const iw = img.width;
      const ih = img.height;
      const scale = Math.max(cw / iw, ch / ih);
      const nw = iw * scale, nh = ih * scale;
      const ox = (cw - nw) / 2, oy = (ch - nh) / 2;
      ctx.clearRect(0, 0, cw, ch);
      ctx.drawImage(img, ox, oy, nw, nh);
    };

    const queueRender = (index: number) => {
      queuedFrame = index;
      if (rafId !== null) return;
      rafId = window.requestAnimationFrame(() => {
        render(queuedFrame);
        rafId = null;
      });
    };

    setCanvasSize();

    queueRender(0);
    const updateCanvasSize = () => {
      setCanvasSize();
      queueRender(Math.round(obj.frame));
    };
    window.addEventListener('resize', updateCanvasSize);

    const obj = { frame: 0 };
    const st = gsap.to(obj, {
      frame: TOTAL_FRAMES - 1,
      snap: 'frame',
      ease: 'none',
      scrollTrigger: {
        trigger: sequenceRef.current,
        start: 'top top',
        end: '+=600%',
        scrub: 1,
        pin: true,
        onUpdate: () => queueRender(Math.round(obj.frame)),
      },
    });

    return () => {
      window.removeEventListener('resize', updateCanvasSize);
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
      st.kill();
    };
  }, [imagesLoaded, images]);

  /* ──────────────────────── DATA ──────────────────────── */

  const features = [
    {
      icon: Satellite,
      title: 'Satellite-Powered Detection',
      desc: 'Queries the AWS Earth Search STAC API for Sentinel-2 L2A multi-spectral imagery (NIR, Red, SWIR bands) to identify sub-pixel macroplastic concentrations invisible to the naked eye.',
    },
    {
      icon: Waves,
      title: 'Lagrangian Drift Forecasting',
      desc: 'Predicts where detected debris will travel over 24h, 48h, and 72h windows using CMEMS ocean current vectors and ERA5 wind data fused through Euler-step particle tracking.',
    },
    {
      icon: Map,
      title: 'Interactive AOI Mapping',
      desc: 'Click 4 points on a dark-matter basemap to define a target ocean sector. A 100×100 grid land-check ensures your polygon is strictly over water before analysis begins.',
    },
    {
      icon: Ship,
      title: 'Cleanup Mission Planner',
      desc: 'Generates optimal Coast Guard vessel routes using TSP heuristics over high-density hotspots, and exports the route as a downloadable GPX file for direct nav-system integration.',
    },
  ] as Array<{ icon: LucideIcon; title: string; desc: string }>;

  const steps = [
    {
      step: '01',
      title: 'Define Your Sector',
      desc: 'Open the D.R.I.F.T. Map and click 4 points on the ocean to draw a target polygon. The system validates that no land is enclosed — if it is, you\'ll be prompted to redraw.',
    },
    {
      step: '02',
      title: 'Analyze & Detect',
      desc: 'Hit "Initialize AWS Deep Scan" and D.R.I.F.T. fetches the latest Sentinel-2 satellite tile, runs AI-based sub-pixel detection, and overlays plastic density zones in real-time.',
    },
    {
      step: '03',
      title: 'Forecast & Deploy',
      desc: 'View 24h/48h/72h drift trajectories, inspect coastal impact zones with intensity heat-mapping, and download a GPX mission file for cleanup vessel deployment.',
    },
  ];

  const techStack = [
    { name: 'React + TypeScript', role: 'Frontend framework' },
    { name: 'deck.gl + MapLibre', role: 'GPU-accelerated map rendering' },
    { name: 'GSAP + Framer Motion', role: 'Scroll animations & transitions' },
    { name: 'FastAPI (Python)', role: 'Backend REST API' },
    { name: 'AWS STAC (Sentinel-2)', role: 'Satellite imagery pipeline' },
    { name: 'global_land_mask', role: 'Land/ocean validation' },
    { name: 'Shapely + Turf.js', role: 'Geospatial computation' },
    { name: 'Recharts', role: 'Dashboard data visualisation' },
  ];

  const stats = [
    { value: '10m', label: 'Pixel Resolution' },
    { value: '100×100', label: 'Land Validation Grid' },
    { value: '72h', label: 'Max Forecast Window' },
    { value: 'GPX', label: 'Mission Export Format' },
  ];

  /* ──────────────────────── RENDER ──────────────────────── */

  return (
    <div className="bg-primary-navy min-h-screen text-text-main overflow-x-hidden selection:bg-accent-cyan selection:text-primary-navy">

      {/* Loading overlay */}
      {!imagesLoaded && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-primary-navy">
          <span className="text-3xl font-syne font-light mb-4 text-text-main/50">Loading Experience</span>
          <div className="w-64 h-1 bg-white/10 rounded-full overflow-hidden">
            <div className="h-full bg-accent-cyan transition-all duration-300" style={{ width: `${loadingProgress}%` }} />
          </div>
        </div>
      )}

      {/* ═══ HERO: IMAGE SEQUENCE ═══ */}
      <div ref={sequenceRef} className="relative w-full h-screen overflow-hidden bg-primary-navy">
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full object-cover" />

        <div className="absolute inset-0 bg-black/35 z-10" />

        <div className="absolute inset-0 bg-gradient-to-t from-primary-navy/80 via-transparent to-transparent z-10" />

        <div className="absolute top-10 left-4 md:top-16 md:left-16 z-20 pointer-events-none max-w-[92vw]">
          <h1 className="type-display-hero font-syne font-bold tracking-tight text-white leading-none drop-shadow-md">
            D.R.I.F.T.
          </h1>
          <p className="text-[11px] sm:text-sm md:text-lg font-inter tracking-[0.12em] sm:tracking-[0.2em] mt-3 md:mt-4 text-white/90 font-medium drop-shadow-sm">
            Debris Recognition, Imaging & Forecast Trajectory
          </p>
        </div>

        <div className="absolute bottom-24 left-4 right-4 md:left-16 md:right-auto z-20 pointer-events-none max-w-xl">
          <p className="text-sm sm:text-base md:text-xl font-inter font-light leading-relaxed text-white/85 drop-shadow-sm">
            An AI-powered ocean surveillance platform that detects marine plastic debris from satellite imagery, forecasts its drift path, and plans optimal cleanup missions.
          </p>
        </div>

        <div className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center opacity-80 z-20 pointer-events-none">
          <span className="text-[11px] uppercase tracking-[0.3em] font-inter mb-4 text-white drop-shadow-md">Scroll to explore</span>
          <motion.div
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            className="w-[1.5px] h-16 bg-gradient-to-b from-white to-transparent shadow-sm"
          />
        </div>
      </div>

      {/* ═══ MAIN CONTENT ═══ */}
      <main className="relative z-20 bg-primary-navy pt-32 pb-48 rounded-t-[3rem] -mt-[3rem] shadow-[0_-20px_50px_rgba(0,0,0,0.3)] border-t border-white/5">

        {/* ── SECTION 1: THE PROBLEM ── */}
        <section className="max-w-5xl mx-auto px-6 mb-40">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-xs font-inter uppercase tracking-[0.3em] text-accent-amber mb-6">The Problem</p>
            <h2 className="text-4xl md:text-7xl font-syne font-normal tracking-tight mb-10">
              8 million tons of plastic <span className="text-accent-amber italic">enter</span> our oceans<br />every single year.
            </h2>
            <div className="grid md:grid-cols-2 gap-16 text-lg md:text-xl font-inter font-light leading-relaxed text-text-main/70">
              <p>
                In satellite imagery, a single pixel at 10-meter resolution covers enormous areas. Macroplastics often occupy less than 20% of a pixel, rendering them invisible to standard classification. Existing monitoring relies on ship surveys and beach cleanups — reactive approaches that miss 99% of floating debris.
              </p>
              <p>
                D.R.I.F.T. changes this paradigm. By fusing multi-spectral satellite bands with AI-driven sub-pixel analysis, we detect plastic patches from space, predict where ocean currents will carry them, and generate actionable deployment plans — all before debris reaches the coastline.
              </p>
            </div>
          </motion.div>

          <motion.div
            className="w-full h-[1px] bg-white/10 mt-24 origin-left"
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.5, delay: 0.2, ease: 'easeInOut' }}
          />
        </section>

        {/* ── KEY STATS BAR ── */}
        <section className="max-w-5xl mx-auto px-6 mb-40">
          <motion.div
            className="grid grid-cols-2 md:grid-cols-4 gap-6"
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.3 }}
          >
            {stats.map((s) => (
              <motion.div
                key={s.label}
                variants={fadeUp}
                className="bg-stone rounded-2xl p-8 border border-white/5 text-center"
              >
                <div className="text-4xl md:text-5xl font-syne font-bold text-accent-amber mb-2">{s.value}</div>
                <div className="text-sm font-inter text-text-main/50 uppercase tracking-wider">{s.label}</div>
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* ── FINAL CTA ── */}
        <section className="flex flex-col justify-center items-center text-center max-w-3xl mx-auto px-4 md:px-6 mb-28 md:mb-40">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.5 }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <h2 className="type-display-lg font-syne font-medium tracking-tight mb-6">
              Ready to scan the ocean?
            </h2>
            <p className="type-body-lg font-inter font-light leading-relaxed mb-10 md:mb-12 text-text-main/60">
              Define a target sector, detect floating debris, trace its future path, and plan a Coast Guard mission — all from your browser.
            </p>

            <div className="flex flex-col sm:flex-row gap-3 md:gap-4 justify-center w-full sm:w-auto">
              <motion.button
                onClick={() => navigate('/drift')}
                className="group relative inline-flex items-center justify-center w-full sm:w-auto px-8 md:px-12 py-4 md:py-5 font-inter font-medium text-sm bg-accent-cyan text-primary-navy rounded-full transition-all duration-500 overflow-hidden"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <div className="absolute inset-0 w-full h-full bg-accent-amber translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-[0.16,1,0.3,1]" />
                <span className="relative z-10 flex items-center gap-3">
                  Launch D.R.I.F.T. Map
                  <motion.span className="inline-block transition-transform duration-300 group-hover:translate-x-1">→</motion.span>
                </span>
              </motion.button>

              <motion.button
                onClick={() => navigate('/drift/history')}
                className="inline-flex items-center justify-center w-full sm:w-auto px-8 md:px-12 py-4 md:py-5 font-inter font-medium text-sm border border-white/10 text-text-main/70 rounded-full hover:border-accent-amber/40 hover:text-accent-amber transition-all duration-300"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                View Search History
              </motion.button>

              <motion.button
                onClick={() => navigate('/drift/dashboard')}
                className="inline-flex items-center justify-center w-full sm:w-auto px-8 md:px-12 py-4 md:py-5 font-inter font-medium text-sm border border-accent-cyan/40 text-accent-cyan rounded-full hover:bg-accent-cyan/10 transition-all duration-300"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Open Intel Dashboard
              </motion.button>
            </div>
          </motion.div>
        </section>

        {/* ── SECTION 2: PLATFORM FEATURES ── */}
        <section className="max-w-5xl mx-auto px-6 mb-40">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-xs font-inter uppercase tracking-[0.3em] text-accent-cyan mb-6">Core Capabilities</p>
            <h2 className="text-4xl md:text-6xl font-syne font-medium tracking-tight mb-16">
              What D.R.I.F.T. <span className="text-white/40">does.</span>
            </h2>
          </motion.div>

          <motion.div
            className="grid md:grid-cols-2 gap-6"
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.2 }}
          >
            {features.map((f) => (
              <motion.div
                key={f.title}
                variants={fadeUp}
                className="group bg-stone rounded-2xl p-8 border border-white/5 hover:border-accent-cyan/30 transition-colors duration-500"
              >
                <div className="mb-5">
                  <f.icon className="h-10 w-10 text-accent-cyan" strokeWidth={1.8} />
                </div>
                <h3 className="text-xl font-syne font-medium mb-3 text-text-main group-hover:text-accent-amber transition-colors duration-300">{f.title}</h3>
                <p className="text-sm font-inter font-light leading-relaxed text-text-main/60">{f.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* ── SECTION 3: HOW TO USE ── */}
        <section className="max-w-5xl mx-auto px-6 mb-40">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-xs font-inter uppercase tracking-[0.3em] text-accent-cyan mb-6">Workflow</p>
            <h2 className="text-4xl md:text-6xl font-syne font-medium tracking-tight mb-16">
              How it <span className="text-accent-amber italic">works.</span>
            </h2>
          </motion.div>

          <motion.div
            className="space-y-0"
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.2 }}
          >
            {steps.map((s, i) => (
              <motion.div
                key={s.step}
                variants={fadeUp}
                className="flex gap-8 items-start py-10 border-t border-white/5"
                style={i === steps.length - 1 ? { borderBottom: '1px solid rgba(255,255,255,0.05)' } : {}}
              >
                <span className="text-5xl md:text-7xl font-syne font-bold text-accent-amber/20 leading-none shrink-0">{s.step}</span>
                <div>
                  <h3 className="text-2xl font-syne font-medium mb-3">{s.title}</h3>
                  <p className="text-base font-inter font-light leading-relaxed text-text-main/60 max-w-2xl">{s.desc}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* ── SECTION 4: TECH STACK ── */}
        <section className="max-w-5xl mx-auto px-6 mb-40">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-xs font-inter uppercase tracking-[0.3em] text-accent-cyan mb-6">Under the Hood</p>
            <h2 className="text-4xl md:text-6xl font-syne font-medium tracking-tight mb-16">
              Tech <span className="text-white/40">Stack.</span>
            </h2>
          </motion.div>

          <motion.div
            className="grid grid-cols-2 md:grid-cols-4 gap-4"
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.2 }}
          >
            {techStack.map((t) => (
              <motion.div
                key={t.name}
                variants={fadeUp}
                className="bg-stone rounded-xl p-5 border border-white/5 hover:border-accent-amber/20 transition-colors duration-300"
              >
                <div className="text-sm font-inter font-medium text-text-main mb-1">{t.name}</div>
                <div className="text-xs font-inter text-text-main/40">{t.role}</div>
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* ── SECTION 5: ARCHITECTURE OVERVIEW ── */}
        <section className="max-w-5xl mx-auto px-6 mb-40">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-xs font-inter uppercase tracking-[0.3em] text-accent-cyan mb-6">System Design</p>
            <h2 className="text-4xl md:text-5xl font-syne font-medium tracking-tight mb-12">
              End-to-End <span className="text-white/40">Pipeline.</span>
            </h2>
          </motion.div>

          <motion.div
            className="bg-stone rounded-2xl p-8 md:p-12 border border-white/5"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="grid md:grid-cols-3 gap-8">
              {[
                {
                  stage: 'Data Ingestion',
                  color: '#f59e0b',
                  items: ['AWS Earth Search STAC API', 'Sentinel-2 L2A (10m bands)', 'NIR + Red + SWIR download', 'Local caching with fallback'],
                },
                {
                  stage: 'AI Analysis',
                  color: '#10b981',
                  items: ['CNN + Vision Transformer pipeline', 'Sub-pixel plastic fraction extraction', 'FDI & NDVI spectral index calculation', 'Confidence-scored GeoJSON output'],
                },
                {
                  stage: 'Operations',
                  color: '#f59e0b',
                  items: ['Lagrangian particle drift (Euler step)', 'Coastal impact intensity mapping', 'TSP-optimal cleanup vessel routing', 'GPX export for nav systems'],
                },
              ].map((col) => (
                <div key={col.stage}>
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: col.color }} />
                    <h3 className="text-lg font-syne font-medium">{col.stage}</h3>
                  </div>
                  <ul className="space-y-3">
                    {col.items.map((item) => (
                      <li key={item} className="flex items-start gap-3 text-sm font-inter text-text-main/60">
                        <span className="text-text-main/20 mt-0.5">→</span>
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </motion.div>
        </section>

        {/* ── FOOTER ── */}
        <footer className="max-w-5xl mx-auto px-6 pt-16 border-t border-white/5">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4 text-xs font-inter text-text-main/30">
            <span>D.R.I.F.T. — Debris Recognition, Imaging & Forecast Trajectory</span>
            <span>Built for Sankalp Hackathon 2026 · Team MagicMoments</span>
          </div>
        </footer>

      </main>
    </div>
  );
};
