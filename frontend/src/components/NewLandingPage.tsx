import React, { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { motion, type Variants } from 'framer-motion';
import Lenis from 'lenis';
import { Map, Satellite, Ship, Waves, type LucideIcon } from 'lucide-react';

gsap.registerPlugin(ScrollTrigger);

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
  const sequenceRef = useRef<HTMLDivElement>(null);

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
    <div className="bg-background min-h-screen text-text-main overflow-x-hidden selection:bg-primary/20 selection:text-text-main">

      {/* ═══ HERO: VIDEO BACKGROUND ═══ */}
      <div ref={sequenceRef} className="relative w-full h-screen overflow-hidden bg-background">
        <video 
          autoPlay 
          loop 
          muted 
          playsInline 
          className="absolute inset-0 w-full h-full object-cover"
        >
          <source src="/background.mp4" type="video/mp4" />
        </video>

        <div className="absolute inset-0 bg-black/10 z-10" />

        <div className="absolute inset-0 bg-linear-to-t from-gray via-transparent to-transparent z-10" />

        <div className="absolute top-10 left-4 md:top-16 md:left-16 z-20 pointer-events-none max-w-[92vw]">
          <h1 className="type-display-hero font-jakarta font-semibold tracking-tight text-white leading-none drop-shadow-md">
            D.R.I.F.T.
          </h1>
          <p className="text-[11px] sm:text-sm md:text-lg font-manrope tracking-[0.12em] sm:tracking-[0.2em] mt-3 md:mt-4 text-white/90 font-medium drop-shadow-sm">
            Debris Recognition, Imaging & Forecast Trajectory
          </p>
        </div>

        <div className="absolute bottom-24 left-4 right-4 md:left-16 md:right-auto z-20 pointer-events-none max-w-xl">
          <p className="text-sm sm:text-base md:text-xl font-manrope font-light leading-relaxed text-white/85 drop-shadow-sm">
            An AI-powered ocean surveillance platform that detects marine plastic debris from satellite imagery, forecasts its drift path, and plans optimal cleanup missions.
          </p>
        </div>

        <div className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center opacity-80 z-20 pointer-events-none">
          <span className="text-[11px] uppercase tracking-[0.3em] font-manrope mb-4 text-white drop-shadow-md">Scroll to explore</span>
          <motion.div
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            className="w-[1.5px] h-16 bg-linear-to-b from-white to-transparent shadow-sm"
          />
        </div>
      </div>

      {/* ═══ MAIN CONTENT ═══ */}
      <main className="relative z-20 bg-[#0D1417] pt-24 pb-48">
        <style>
          {`
            @keyframes wave-scroll {
              0% { transform: translateX(0); }
              100% { transform: translateX(-50%); }
            }
            .animate-wave {
              animation: wave-scroll 10s linear infinite;
              will-change: transform;
            }
          `}
        </style>
        <div className="absolute top-0 left-0 w-full overflow-hidden leading-[0] transform -translate-y-full">
          <svg className="relative block w-[200vw] h-[40px] sm:h-[60px] md:h-[80px] animate-wave" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2400 100" preserveAspectRatio="none">
            <path d="M0,50 Q300,100 600,50 T1200,50 L1200,100 L0,100 Z" fill="#0D1417" />
            <path d="M1200,50 Q1500,100 1800,50 T2400,50 L2400,100 L1200,100 Z" fill="#0D1417" />
          </svg>
        </div>

        {/* ── SECTION 1: THE PROBLEM ── */}
        <section className="max-w-5xl mx-auto px-6 mb-40">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-xs font-manrope uppercase tracking-[0.3em] text-secondary mb-6">The Problem</p>
            <h2 className="text-4xl md:text-7xl font-jakarta font-normal tracking-tight mb-10">
              8 million tons of plastic <span className="text-primary italic">enter</span> our oceans<br />every single year.
            </h2>
            <div className="grid md:grid-cols-2 gap-16 text-lg md:text-xl font-manrope font-light leading-relaxed text-text-main/70">
              <p>
                In satellite imagery, a single pixel at 10-meter resolution covers enormous areas. Macroplastics often occupy less than 20% of a pixel, rendering them invisible to standard classification. Existing monitoring relies on ship surveys and beach cleanups — reactive approaches that miss 99% of floating debris.
              </p>
              <p>
                D.R.I.F.T. changes this paradigm. By fusing multi-spectral satellite bands with AI-driven sub-pixel analysis, we detect plastic patches from space, predict where ocean currents will carry them, and generate actionable deployment plans — all before debris reaches the coastline.
              </p>
            </div>
          </motion.div>

          <motion.div
            className="w-full h-[1px] bg-surface-variant mt-24 origin-left"
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.5, delay: 0.2, ease: 'easeInOut' }}
          />
        </section>

        {/* ── KEY STATS BAR ── */}
        <section className="max-w-6xl mx-auto px-6 mb-40">
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
                className="bg-surface-container rounded-3xl p-8 ghost-border text-center card-hover"
              >
                <div className="text-4xl md:text-5xl font-jakarta font-bold text-primary mb-2">{s.value}</div>
                <div className="text-sm font-manrope text-text-main/50 uppercase tracking-wider">{s.label}</div>
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
            <h2 className="type-display-lg font-jakarta font-medium tracking-tight mb-6">
              Ready to scan the ocean?
            </h2>
            <p className="type-body-lg font-manrope font-light leading-relaxed mb-10 md:mb-12 text-text-main/60">
              Define a target sector, detect floating debris, trace its future path, and plan a Coast Guard mission — all from your browser.
            </p>

            <div className="flex flex-col sm:flex-row gap-3 md:gap-4 justify-center w-full sm:w-auto">
              <motion.button
                onClick={() => navigate('/drift')}
                className="btn-primary"
              >
                <span className="relative z-10 flex items-center justify-center gap-3 w-full">
                  Launch D.R.I.F.T. Map
                  <motion.span className="inline-block transition-transform duration-300 transform translate-x-0">→</motion.span>
                </span>
              </motion.button>

              <motion.button
                onClick={() => navigate('/drift/history')}
                className="btn-secondary"
              >
                View Search History
              </motion.button>

              <motion.button
                onClick={() => navigate('/drift/dashboard')}
                className="btn-secondary"
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
            <p className="text-xs font-manrope uppercase tracking-[0.3em] text-primary mb-6">Core Capabilities</p>
            <h2 className="text-4xl md:text-6xl font-jakarta font-medium tracking-tight mb-16">
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
                className="group bg-surface-container rounded-3xl p-8 card-hover ghost-border"
              >
                <div className="mb-5">
                  <f.icon className="h-10 w-10 text-primary" strokeWidth={1.8} />
                </div>
                <h3 className="text-xl font-jakarta font-medium mb-3 text-text-main group-hover:text-secondary transition-colors duration-300">{f.title}</h3>
                <p className="text-sm font-manrope font-light leading-relaxed text-text-main/60">{f.desc}</p>
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
            <p className="text-xs font-manrope uppercase tracking-[0.3em] text-primary mb-6">Workflow</p>
            <h2 className="text-4xl md:text-6xl font-jakarta font-medium tracking-tight mb-16">
              How it <span className="text-secondary italic">works.</span>
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
                className="flex gap-8 items-start py-10"
                style={{ borderTop: i > 0 ? '1px solid var(--color-surface-variant)' : 'none' }}
              >
                <span className="text-5xl md:text-7xl font-jakarta font-bold text-secondary/40 leading-none shrink-0">{s.step}</span>
                <div>
                  <h3 className="text-2xl font-jakarta font-medium mb-3">{s.title}</h3>
                  <p className="text-base font-manrope font-light leading-relaxed text-text-main/60 max-w-2xl">{s.desc}</p>
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
            <p className="text-xs font-manrope uppercase tracking-[0.3em] text-primary mb-6">Under the Hood</p>
            <h2 className="text-4xl md:text-6xl font-jakarta font-medium tracking-tight mb-16">
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
                className="bg-surface-container rounded-2xl p-5 card-hover ghost-border"
              >
                <div className="text-sm font-manrope font-medium text-text-main mb-1">{t.name}</div>
                <div className="text-xs font-manrope text-text-main/40">{t.role}</div>
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
            <p className="text-xs font-manrope uppercase tracking-[0.3em] text-primary mb-6">System Design</p>
            <h2 className="text-4xl md:text-5xl font-jakarta font-medium tracking-tight mb-12">
              End-to-End <span className="text-white/40">Pipeline.</span>
            </h2>
          </motion.div>

          <motion.div
            className="bg-surface-container rounded-3xl p-8 md:p-12 ghost-border"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="grid md:grid-cols-3 gap-8">
              {[
                {
                  stage: 'Data Ingestion',
                  color: 'var(--color-secondary)',
                  items: ['AWS Earth Search STAC API', 'Sentinel-2 L2A (10m bands)', 'NIR + Red + SWIR download', 'Local caching with fallback'],
                },
                {
                  stage: 'AI Analysis',
                  color: 'var(--color-primary)',
                  items: ['CNN + Vision Transformer pipeline', 'Sub-pixel plastic fraction extraction', 'FDI & NDVI spectral index calculation', 'Confidence-scored GeoJSON output'],
                },
                {
                  stage: 'Operations',
                  color: 'var(--color-tertiary)',
                  items: ['Lagrangian particle drift (Euler step)', 'Coastal impact intensity mapping', 'TSP-optimal cleanup vessel routing', 'GPX export for nav systems'],
                },
              ].map((col) => (
                <div key={col.stage}>
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: col.color }} />
                    <h3 className="text-lg font-jakarta font-medium">{col.stage}</h3>
                  </div>
                  <ul className="space-y-3">
                    {col.items.map((item) => (
                      <li key={item} className="flex items-start gap-3 text-sm font-manrope text-text-main/60">
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
        <footer className="max-w-5xl mx-auto px-6 pt-16 border-t border-surface-variant">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4 text-xs font-manrope text-text-main/30">
            <span>D.R.I.F.T. — Debris Recognition, Imaging & Forecast Trajectory</span>
            <span>Built for Sankalp Hackathon 2026 · Team MagicMoments</span>
          </div>
        </footer>

      </main>
    </div>
  );
};
