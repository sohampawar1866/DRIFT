import React, { useEffect } from 'react';
import Lenis from 'lenis';
import { HeroSection } from './HeroSection';
import { ContentSection } from './ContentSection';

export const LandingPage: React.FC = () => {
  // Initialize Lenis for smooth scroll
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

    function raf(time: number) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);

    return () => lenis.destroy();
  }, []);

  return (
    <div className="bg-primary-navy min-h-screen text-text-main overflow-x-hidden selection:bg-accent-cyan selection:text-white">
      <HeroSection />
      <ContentSection />
    </div>
  );
};
