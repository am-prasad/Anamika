"use client";

import { Line, PerformanceMonitor } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { buildFigure } from "./body";

/**
 * "Dissolving Identity". ~12k points form a figure; identity particles (amber) peel off into
 * a glass shield ring; the figure re-forms in teal. All motion runs in the vertex shader.
 */
const VERT = /* glsl */ `
  uniform float uTime;
  uniform float uPixel;
  attribute vec3 aScatter;
  attribute vec3 aRing;
  attribute float aSeed;
  attribute float aIdentity;
  varying float vMix;
  varying float vIdentity;
  varying float vAlpha;

  float ease(float t) { return 1.0 - pow(1.0 - clamp(t, 0.0, 1.0), 3.0); }

  void main() {
    float form = ease(uTime / 0.6 - aSeed * 0.35);
    vec3 p = mix(aScatter, position, form);

    float peel = ease((uTime - 0.6 - aSeed * 0.5) / 1.1);
    if (aIdentity > 0.5) {
      vec3 ring = aRing;
      float ang = uTime * 0.18 + aSeed * 6.2831;
      ring.xz = vec2(cos(ang), sin(ang)) * length(aRing.xz);
      vec3 mid = mix(position, ring, 0.5) + vec3(sin(aSeed * 40.0), cos(aSeed * 31.0) * 0.6, sin(aSeed * 17.0)) * 0.35;
      vec3 a = mix(position, mid, peel);
      vec3 b = mix(mid, ring, peel);
      p = mix(p, mix(a, b, peel), step(0.001, peel));
    } else {
      p += 0.004 * vec3(sin(uTime * 1.3 + aSeed * 50.0), cos(uTime * 1.1 + aSeed * 40.0), 0.0);
    }

    vMix = ease((uTime - 2.2) / 1.0);
    vIdentity = aIdentity;
    vAlpha = mix(0.0, 1.0, form);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = uPixel * (aIdentity > 0.5 ? 1.5 : 1.05) * (1.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const FRAG = /* glsl */ `
  varying float vMix;
  varying float vIdentity;
  varying float vAlpha;
  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = length(c);
    if (d > 0.5) discard;
    float soft = smoothstep(0.5, 0.0, d);
    vec3 start = vec3(0.62, 0.70, 0.78);   // text-mid: raw record light
    vec3 teal = vec3(0.176, 0.831, 0.749); // teal-400: protected
    vec3 amber = vec3(0.984, 0.749, 0.141); // amber-400: identity in transit
    vec3 rose = vec3(0.957, 0.247, 0.369);
    vec3 idc = mix(mix(amber, rose, 0.18), vec3(0.40, 0.91, 0.98) * 0.42, vMix);
    vec3 col = vIdentity > 0.5 ? idc : mix(start, teal, vMix);
    gl_FragColor = vec4(col, soft * vAlpha * (vIdentity > 0.5 ? 0.55 : 0.26));
  }
`;

function Figure({ count, identityShare, replayKey, still }: { count: number; identityShare: number; replayKey: string; still: boolean }) {
  const group = useRef<THREE.Group>(null);
  const mat = useRef<THREE.ShaderMaterial>(null);
  const start = useRef<number | null>(null);
  const { size, viewport } = useThree();

  const geo = useMemo(() => {
    const f = buildFigure(count, identityShare);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(f.base, 3));
    g.setAttribute("aScatter", new THREE.BufferAttribute(f.scatter, 3));
    g.setAttribute("aRing", new THREE.BufferAttribute(f.ring, 3));
    g.setAttribute("aSeed", new THREE.BufferAttribute(f.seed, 1));
    g.setAttribute("aIdentity", new THREE.BufferAttribute(f.identity, 1));
    return g;
  }, [count, identityShare]);

  const uniforms = useMemo(() => ({ uTime: { value: still ? 4 : 0 }, uPixel: { value: 60 } }), [still]);

  useEffect(() => {
    start.current = null; // replay when a new run lands
  }, [replayKey]);

  useEffect(() => () => geo.dispose(), [geo]);

  useFrame((state) => {
    if (!mat.current || !group.current) return;
    mat.current.uniforms.uPixel.value = (size.height * viewport.dpr) / 40;
    if (still) {
      mat.current.uniforms.uTime.value = 4;
      return;
    }
    if (start.current === null) start.current = state.clock.elapsedTime;
    const t = state.clock.elapsedTime - start.current;
    mat.current.uniforms.uTime.value = t;
    const parallaxY = state.pointer.x * 0.105; // ≤ 6°
    const parallaxX = -state.pointer.y * 0.05;
    group.current.rotation.y = t * 0.03 + parallaxY;
    group.current.rotation.x = THREE.MathUtils.lerp(group.current.rotation.x, parallaxX, 0.05);
  });

  return (
    <group ref={group} position={[0, -0.74, 0]}>
      <points geometry={geo} frustumCulled={false}>
        <shaderMaterial
          ref={mat}
          vertexShader={VERT}
          fragmentShader={FRAG}
          uniforms={uniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <mesh position={[0, 1.05, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.15, 0.006, 8, 220]} />
        <meshBasicMaterial color="#67E8F9" transparent opacity={0.35} />
      </mesh>
      <mesh position={[0, 1.05, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.15, 0.09, 16, 220]} />
        <meshBasicMaterial color="#2DD4BF" transparent opacity={0.035} depthWrite={false} />
      </mesh>
    </group>
  );
}

function Helix() {
  const points = useMemo(() => {
    const a: [number, number, number][] = [];
    const b: [number, number, number][] = [];
    for (let i = 0; i <= 220; i++) {
      const t = i / 220;
      const y = -1.6 + t * 4.2;
      const ang = t * Math.PI * 7;
      a.push([Math.cos(ang) * 0.35 + 2.2, y, Math.sin(ang) * 0.35 - 3.2]);
      b.push([Math.cos(ang + Math.PI) * 0.35 + 2.2, y, Math.sin(ang + Math.PI) * 0.35 - 3.2]);
    }
    return { a, b };
  }, []);
  return (
    <group>
      <Line points={points.a} color="#2DD4BF" transparent opacity={0.14} lineWidth={1} />
      <Line points={points.b} color="#67E8F9" transparent opacity={0.1} lineWidth={1} />
    </group>
  );
}

/** True when WebGL runs on the CPU (SwiftShader, llvmpipe): no GPU, so render less. */
function softwareGL(): boolean {
  try {
    const gl = document.createElement("canvas").getContext("webgl");
    const ext = gl?.getExtension("WEBGL_debug_renderer_info");
    const name = ext && gl ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : "";
    return /swiftshader|llvmpipe|software/i.test(name);
  } catch {
    return false;
  }
}

export default function HeroScene({
  identifiers,
  replayKey,
  still,
  active,
}: {
  identifiers: number;
  replayKey: string;
  still: boolean;
  active: boolean;
}) {
  // identity share scales with what the pipeline actually found
  const identityShare = Math.min(0.32, Math.max(0.1, identifiers / 12000));
  // software renderers (no GPU) start light; any machine that falls behind drops DPR and bloom
  const [soft] = useState(() => softwareGL());
  const [low, setLow] = useState(soft);
  const count = soft ? 6000 : 12000;
  return (
    <Canvas
      dpr={low ? 1 : [1, 1.75]}
      frameloop={active && !still ? "always" : "demand"}
      camera={{ position: [0, 1.05, 4.3], fov: 32 }}
      onCreated={({ camera }) => camera.lookAt(0, -0.05, 0)}
      gl={{ antialias: false, alpha: true, powerPreference: "high-performance" }}
      aria-hidden
    >
      <PerformanceMonitor onDecline={() => setLow(true)} flipflops={1} />
      <fog attach="fog" args={["#050B14", 4.5, 10]} />
      <Figure count={count} identityShare={identityShare} replayKey={replayKey} still={still} />
      <Helix />
      {!low && (
        <EffectComposer multisampling={0}>
          <Bloom luminanceThreshold={0.6} luminanceSmoothing={0.3} intensity={0.45} mipmapBlur />
        </EffectComposer>
      )}
    </Canvas>
  );
}
