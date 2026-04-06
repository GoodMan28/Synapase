import { useRef, useEffect, useMemo } from 'react';
import * as THREE from 'three';

export default function WormholeBackground({ active = false }) {
  const containerRef = useRef(null);
  const rendererRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const animRef = useRef(null);
  const particlesRef = useRef(null);
  const clockRef = useRef(new THREE.Clock());

  const PARTICLE_COUNT = 2500;

  const vertexShader = useMemo(() => `
    attribute float size;
    attribute float speed;
    attribute float offset;
    uniform float uTime;
    varying float vAlpha;
    varying float vDist;

    void main() {
      vec3 pos = position;

      // Move particles toward center (z-axis)
      float z = mod(pos.z + uTime * speed * 80.0 + offset, 200.0) - 100.0;
      pos.z = z;

      // Tunnel shape — particles orbit around z-axis
      float angle = atan(pos.y, pos.x) + uTime * 0.2 * speed;
      float radius = length(pos.xy);

      // Compress radius as particles approach center
      float zFactor = smoothstep(-100.0, 100.0, z);
      float tunnelRadius = radius * (0.15 + 0.85 * zFactor);

      pos.x = cos(angle) * tunnelRadius;
      pos.y = sin(angle) * tunnelRadius;

      vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
      gl_Position = projectionMatrix * mvPosition;

      // Size attenuation
      float sizeAtten = 300.0 / (-mvPosition.z);
      gl_PointSize = size * sizeAtten;

      // Alpha based on depth
      vAlpha = smoothstep(0.0, 0.5, 1.0 - zFactor) * 0.8;
      vDist = length(pos.xy) / 50.0;
    }
  `, []);

  const fragmentShader = useMemo(() => `
    varying float vAlpha;
    varying float vDist;

    void main() {
      // Circle shape
      vec2 center = gl_PointCoord - 0.5;
      float dist = length(center);
      if (dist > 0.5) discard;

      float alpha = vAlpha * (1.0 - dist * 2.0);
      alpha *= smoothstep(1.0, 0.0, vDist);

      // Monochrome with subtle warmth near center
      vec3 color = mix(vec3(1.0), vec3(0.85, 0.85, 0.9), vDist);

      gl_FragColor = vec4(color, alpha * 0.7);
    }
  `, []);

  useEffect(() => {
    if (!containerRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 5;
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({
      antialias: false,
      alpha: true,
      powerPreference: 'high-performance',
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Create particles
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const sizes = new Float32Array(PARTICLE_COUNT);
    const speeds = new Float32Array(PARTICLE_COUNT);
    const offsets = new Float32Array(PARTICLE_COUNT);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const angle = Math.random() * Math.PI * 2;
      const radius = 2 + Math.random() * 48;
      positions[i * 3] = Math.cos(angle) * radius;
      positions[i * 3 + 1] = Math.sin(angle) * radius;
      positions[i * 3 + 2] = Math.random() * 200 - 100;
      sizes[i] = 0.5 + Math.random() * 2.5;
      speeds[i] = 0.3 + Math.random() * 0.7;
      offsets[i] = Math.random() * 200;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    geometry.setAttribute('speed', new THREE.BufferAttribute(speeds, 1));
    geometry.setAttribute('offset', new THREE.BufferAttribute(offsets, 1));

    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: { uTime: { value: 0 } },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);
    particlesRef.current = particles;

    // Streaking lines for "data traversal" effect
    const lineCount = 80;
    const lineGeo = new THREE.BufferGeometry();
    const linePositions = new Float32Array(lineCount * 6);

    for (let i = 0; i < lineCount; i++) {
      const angle = Math.random() * Math.PI * 2;
      const radius = 5 + Math.random() * 40;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;
      const z = Math.random() * 200 - 100;
      linePositions[i * 6] = x;
      linePositions[i * 6 + 1] = y;
      linePositions[i * 6 + 2] = z;
      linePositions[i * 6 + 3] = x * 0.95;
      linePositions[i * 6 + 4] = y * 0.95;
      linePositions[i * 6 + 5] = z + 8;
    }

    lineGeo.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));
    const lineMat = new THREE.LineBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.08,
      blending: THREE.AdditiveBlending,
    });
    const lines = new THREE.LineSegments(lineGeo, lineMat);
    scene.add(lines);

    // Animate
    const tick = () => {
      const elapsed = clockRef.current.getElapsedTime();
      material.uniforms.uTime.value = elapsed;

      // Slowly rotate the tunnel
      particles.rotation.z = elapsed * 0.05;
      lines.rotation.z = elapsed * 0.03;

      renderer.render(scene, camera);
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);

    // Resize handler
    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (animRef.current) cancelAnimationFrame(animRef.current);
      renderer.dispose();
      geometry.dispose();
      material.dispose();
      lineGeo.dispose();
      lineMat.dispose();
      if (containerRef.current && renderer.domElement) {
        containerRef.current.removeChild(renderer.domElement);
      }
    };
  }, [vertexShader, fragmentShader]);

  return (
    <div
      ref={containerRef}
      className="wormhole-canvas"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        pointerEvents: 'none',
        opacity: active ? 1 : 0,
        transition: 'opacity 1.5s cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    />
  );
}
