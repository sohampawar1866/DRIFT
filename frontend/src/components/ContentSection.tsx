import React, { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';

export const ContentSection: React.FC = () => {
  const navigate = useNavigate();
  const contentRef = useRef<HTMLDivElement>(null);

  return (
    <main ref={contentRef} className="relative z-20 flex flex-col items-center bg-primary-navy text-text-main pt-32 pb-48 rounded-t-[3rem] -mt-[3rem] shadow-[0_-20px_50px_rgba(0,0,0,0.05)] border-t border-black/5">
        
        {/* SECTION 1: Sub-Pixel Blindness */}
        <section className="min-h-[70vh] flex flex-col justify-center max-w-5xl mx-auto px-6 mb-32">
            <motion.div 
                initial={{ opacity: 0, y: 40 }} 
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }} // smooth apple-like ease
            >
              <h2 className="text-5xl md:text-7xl font-syne font-normal tracking-tight mb-10 text-text-main">
                  Beyond human <span className="text-accent-cyan italic">vision.</span>
              </h2>
              <div className="grid md:grid-cols-2 gap-16 text-lg md:text-2xl font-inter font-light leading-relaxed text-text-main/80">
                  <p>
                      In satellite imagery, a single pixel covers tremendous real estate. Often, macroplastics cover less than 20% of a pixel, rendering them virtually invisible to standard thresholding.
                  </p>
                  <p>
                      Our mission begins beyond human sight. We pierce the spectral confusion of whitecaps, glint, and cloud shadows to find the microscopic footprint of environmental decay.
                  </p>
              </div>
            </motion.div>

            {/* Decorative Soft Line */}
            <motion.div 
                className="w-full h-[1px] bg-black/10 mt-32 origin-left"
                initial={{ scaleX: 0 }}
                whileInView={{ scaleX: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 1.5, delay: 0.2, ease: 'easeInOut' }}
            />
        </section>

        {/* SECTION 2: The Core Architecture */}
        <section className="min-h-[80vh] flex flex-col justify-center max-w-5xl mx-auto px-6 mb-32 w-full">
            <div className="grid md:grid-cols-2 gap-20 items-center">
                <motion.div 
                    initial={{ opacity: 0, y: 40 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.3 }}
                    transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
                >
                      <h2 className="text-4xl md:text-5xl font-syne font-medium tracking-tight mb-8">
                          Intelligent <br/>
                          <span className="text-black/40">Architecture.</span>
                      </h2>
                      <p className="text-lg font-inter font-light leading-relaxed mb-10 text-text-main/80">
                          Utilizing a sophisticated dual-pathway approach. Advanced Convolutional Neural Networks (CNNs) coupled with Vision Transformers extract spatial hierarchies and spectral sequences simultaneously.
                      </p>
                      <ul className="space-y-6 font-inter text-base font-normal text-text-main/70">
                          <li className="flex items-center gap-4">
                              <div className="w-8 h-[1px] bg-accent-cyan" /> Multi-spectral Analysis
                          </li>
                          <li className="flex items-center gap-4">
                              <div className="w-8 h-[1px] bg-accent-cyan" /> Attention Contextualization
                          </li>
                          <li className="flex items-center gap-4">
                              <div className="w-8 h-[1px] bg-accent-amber" /> Sub-Pixel Confidence Scoring
                          </li>
                      </ul>
                </motion.div>
                
                {/* Clean elegant graphic instead of sci-fi panel */}
                <motion.div 
                    className="relative h-[600px] bg-stone rounded-3xl overflow-hidden shadow-xl shadow-black/5 flex flex-col justify-end p-8 border border-black/5"
                    initial={{ opacity: 0, scale: 0.98, y: 20 }}
                    whileInView={{ opacity: 1, scale: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.3 }}
                    transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
                >
                      <div className="absolute inset-0 opacity-30 flex items-center justify-center pointer-events-none">
                          <motion.div 
                              className="w-[150%] h-[150%] rounded-full bg-gradient-to-tr from-accent-cyan/10 to-transparent blur-3xl"
                              animate={{ rotate: 360 }}
                              transition={{ duration: 40, repeat: Infinity, ease: 'linear' }}
                          />
                      </div>
                      
                      <div className="z-10 bg-white/80 backdrop-blur-xl p-6 rounded-2xl border border-white/50 shadow-sm w-full">
                          <div className="flex justify-between items-center mb-4">
                              <span className="font-inter text-xs tracking-widest text-text-main/50 uppercase">Analysis Stream</span>
                              <span className="w-2 h-2 rounded-full bg-accent-cyan animate-pulse" />
                          </div>
                          <div className="flex gap-2">
                              {[1, 2, 3, 4, 5].map((i) => (
                                  <motion.div 
                                      key={i}
                                      className="h-1 bg-black/10 flex-1 rounded-full overflow-hidden"
                                  >
                                      <motion.div 
                                          className="h-full bg-accent-cyan"
                                          initial={{ width: 0 }}
                                          whileInView={{ width: '100%' }}
                                          viewport={{ once: true }}
                                          transition={{ duration: 1, delay: 0.5 + (i * 0.1), ease: 'easeOut' }}
                                      />
                                  </motion.div>
                              ))}
                          </div>
                      </div>
                </motion.div>
            </div>
        </section>

        {/* SECTION 3: Trajectory & Forecast */}
        <section className="min-h-[50vh] flex flex-col justify-center items-center text-center max-w-3xl mx-auto px-6 mb-24">
            <motion.div
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.5 }}
                transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            >
                <h2 className="text-4xl md:text-6xl font-syne font-medium tracking-tight mb-8">
                    Trace & Forecast
                </h2>
                <p className="text-lg md:text-xl font-inter font-light leading-relaxed mb-16 text-text-main/70">
                    We don’t just map what is; we project what will be. Fusing global wind data and ocean current vectors into sophisticated Lagrangian equations, DRIFT computes impact trajectories with pristine clarity.
                </p>
                
                {/* CTA BUTTON - Elegant Minimal */}
                <motion.button 
                    onClick={() => navigate('/drift')}
                    className="group relative inline-flex items-center justify-center px-12 py-5 font-inter font-medium text-sm bg-text-main text-white rounded-full transition-all duration-500 overflow-hidden"
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                >
                    <div className="absolute inset-0 w-full h-full bg-accent-cyan translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-[0.16,1,0.3,1]" />
                    <span className="relative z-10 flex items-center gap-3">
                        Launch Environment
                        <motion.span 
                            className="inline-block transition-transform duration-300 group-hover:translate-x-1"
                        >→</motion.span>
                    </span>
                </motion.button>
            </motion.div>
        </section>

    </main>
  );
};
