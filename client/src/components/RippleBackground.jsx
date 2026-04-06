import { useRef, useEffect, useCallback } from 'react';

export default function RippleBackground({ active = true }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const timeRef = useRef(0);

  const animate = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;
    const cx = w / 2;
    const cy = h / 2;

    ctx.clearRect(0, 0, w, h);
    timeRef.current += 0.008;
    const t = timeRef.current;

    const maxRadius = Math.sqrt(cx * cx + cy * cy);
    const waveCount = 20;
    const waveSpacing = maxRadius / waveCount;

    for (let i = 0; i < waveCount; i++) {
      const baseRadius = i * waveSpacing;
      const breathe = Math.sin(t * 0.5 + i * 0.3) * 8;
      const radius = baseRadius + breathe + (t * 15) % waveSpacing;

      if (radius <= 0 || radius > maxRadius) continue;

      const distFactor = 1 - radius / maxRadius;
      const alpha = distFactor * 0.06 * (0.5 + 0.5 * Math.sin(t + i * 0.5));

      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(255, 255, 255, ${alpha})`;
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    // Subtle center glow
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, 200);
    gradient.addColorStop(0, `rgba(255, 255, 255, ${0.02 + 0.01 * Math.sin(t * 0.3)})`);
    gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);

    animRef.current = requestAnimationFrame(animate);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = window.innerWidth + 'px';
      canvas.style.height = window.innerHeight + 'px';
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.scale(dpr, dpr);
    };

    resize();
    window.addEventListener('resize', resize);

    if (active) {
      animRef.current = requestAnimationFrame(animate);
    }

    return () => {
      window.removeEventListener('resize', resize);
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [active, animate]);

  return (
    <canvas
      ref={canvasRef}
      className="background-canvas"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        pointerEvents: 'none',
        opacity: active ? 1 : 0,
        transition: 'opacity 1.2s ease',
      }}
    />
  );
}
