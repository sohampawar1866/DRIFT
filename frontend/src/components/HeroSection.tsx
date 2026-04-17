import React, { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { motion } from 'framer-motion';

gsap.registerPlugin(ScrollTrigger);

const TOTAL_FRAMES = 40;

export const HeroSection: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sequenceRef = useRef<HTMLDivElement>(null);
  
  // To handle preloading images
  const [images, setImages] = useState<HTMLImageElement[]>([]);
  const [imagesLoaded, setImagesLoaded] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);

  // Preload images
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
            if (loadedCount === TOTAL_FRAMES) {
                setImages(loadedImages);
                setImagesLoaded(true);
            }
        };
        img.onerror = () => {
            console.error(`Failed to load frame ${index}`);
            loadedCount++;
            setLoadingProgress(Math.round((loadedCount / TOTAL_FRAMES) * 100));
            if (loadedCount === TOTAL_FRAMES) {
                setImages(loadedImages);
                setImagesLoaded(true);
            }
        };
        loadedImages.push(img);
    }
  }, []);

  // Canvas drawing & GSAP ScrollTrigger
  useEffect(() => {
    if (!imagesLoaded || !canvasRef.current || !sequenceRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const render = (index: number) => {
      const img = images[index];
      if (!img || !img.complete) return;

      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      
      ctx.scale(dpr, dpr);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';

      const cw = rect.width;
      const ch = rect.height;
      const iw = img.width;
      const ih = img.height;
      
      const scale = Math.max(cw / iw, ch / ih);
      const nw = iw * scale;
      const nh = ih * scale;
      
      const ox = (cw - nw) / 2;
      const oy = (ch - nh) / 2;

      ctx.clearRect(0, 0, cw, ch);
      ctx.drawImage(img, ox, oy, nw, nh);
    };

    // Draw initial frame
    render(0);

    // Resize handler
    const updateCanvasSize = () => {
        render(Math.round(obj.frame));
    };
    window.addEventListener('resize', updateCanvasSize);

    // GSAP ScrollTrigger mapping frame sequence and pinning
    const obj = { frame: 0 };
    const maxFrame = TOTAL_FRAMES - 1;

    const st = gsap.to(obj, {
        frame: maxFrame,
        snap: "frame",
        ease: "none",
        scrollTrigger: {
            trigger: sequenceRef.current,
            start: "top top",
            // Pin the screen for a long distance so user scrolls through all frames comfortably
            end: "+=600%", 
            scrub: 1, // Smooth dampening
            pin: true, // This locks the section in place
            onUpdate: () => render(Math.round(obj.frame)),
        }
    });

    return () => {
        window.removeEventListener('resize', updateCanvasSize);
        st.kill();
    };
  }, [imagesLoaded, images]);

  return (
    <>
      {!imagesLoaded && (
          <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-primary-navy">
              <span className="text-3xl font-syne font-light mb-4 text-text-main/50">Loading Experience</span>
              <div className="w-64 h-1 bg-black/10 rounded-full overflow-hidden">
                  <div className="h-full bg-accent-cyan transition-all duration-300" style={{ width: `${loadingProgress}%` }} />
              </div>
          </div>
      )}

      {/* 1. HERO SECTION: IMAGE SEQUENCE PINNED */}
      <div ref={sequenceRef} className="relative w-full h-screen overflow-hidden bg-white">
        
        {/* Canvas for precise frame rendering */}
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full object-cover" />
        
        {/* D.R.I.F.T Title - Big, relaxed, soft */}
        <div className="absolute top-12 left-8 md:top-16 md:left-16 z-20 pointer-events-none">
            <h1 className="text-6xl md:text-[9rem] font-syne font-bold tracking-tight text-white leading-none drop-shadow-md">
                D.R.I.F.T.
            </h1>
            <p className="text-sm md:text-lg font-inter tracking-[0.2em] mt-4 text-white/90 font-medium drop-shadow-sm">
                Debris Recognition, Imaging & Forecast Trajectory
            </p>
        </div>

        {/* Minimalist Scroll indicator */}
        <div className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center opacity-80 z-20 pointer-events-none">
            <span className="text-[11px] uppercase tracking-[0.3em] font-inter mb-4 text-white drop-shadow-md">Scroll to explore</span>
            <motion.div 
                animate={{ y: [0, 10, 0] }}
                transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                className="w-[1.5px] h-16 bg-gradient-to-b from-white to-transparent shadow-sm" 
            />
        </div>
      </div>
    </>
  );
};
