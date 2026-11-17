import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { ContactShadows, Html, OrbitControls } from '@react-three/drei';
import { Euler, MeshStandardMaterial, Quaternion, Vector3 } from 'three';
import type { Group, Mesh, MeshBasicMaterial, PerspectiveCamera } from 'three';
import { ORCHESTRATOR, VERIFIER } from './backend/types';
import type { Agent, FileItem, FileType } from './backend/types';
import type { Huddle } from './Stage';

/** Up to this many translators are all shown. Above it, idle ones collapse into a group. */
const MAX_SHOWN = 10;
/** Files past this many stay on the shelf only; the bucket would be a heap. */
const MAX_IN_BUCKET = 42;
const PER_LAYER = 14;
const BUCKET_R = 1.5;
const BUCKET_H = 0.7;
/**
 * Members stand on the inner ring around the bucket; everyone else waits on the outer ring, so the huddle is empty
 * until a question starts. Translators wait behind the bucket, the orchestrator and the verifier at the front corners.
 */
const RING_IN = 2.8;
const RING_IDLE = 4.4;

/** Each kind of agent has its own shape and colour. Translators are alike; the orchestrator and the verifier stand out. */
type Role = 'translator' | 'orchestrator' | 'verifier';
const ROLE_COLOR: Record<Role, { light: string; dark: string }> = {
  translator: { light: '#d4d7dc', dark: '#b6bcc4' },
  orchestrator: { light: '#2f6f6a', dark: '#4fa79e' },
  verifier: { light: '#c98a1b', dark: '#e0aa45' },
};

const TYPE_COLOR: Record<FileType, string> = {
  pdf: '#e0796c', docx: '#6f97d6', csv: '#6dba7a', md: '#a585d6', txt: '#c9c4b8', image: '#e0b25c', other: '#b0b4bb',
};

/** A bubble shows the start of a message; the whole of it is in the chat and the huddle log. */
const BUBBLE_CHARS = 20;
const short = (text: string) => (text.length > BUBBLE_CHARS ? `${text.slice(0, BUBBLE_CHARS).trimEnd()}…` : text);

type Vec = [number, number, number];
/** A point on the floor. 90 degrees faces the camera. */
const at = (r: number, deg: number): Vec => {
  const a = (deg * Math.PI) / 180;
  return [Math.cos(a) * r, 0, Math.sin(a) * r];
};
const ORCHESTRATOR_WAITS = at(4.2, 135);
const VERIFIER_WAITS = at(4.2, 45);

export const reducedMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
/** Fraction of the way to move towards a target this frame. Reduced motion snaps. */
export const ease = (dt: number, speed = 4) => (reducedMotion ? 1 : 1 - Math.exp(-speed * dt));

/** The theme's colours, read from the CSS variables and re-read when the theme changes. */
export function usePalette() {
  const read = () => {
    const s = getComputedStyle(document.documentElement);
    const v = (n: string) => s.getPropertyValue(n).trim();
    return {
      accent: v('--accent'), text: v('--text'), bg: v('--bg'), stage: v('--stage'), surface: v('--surface'), line: v('--line'), muted: v('--muted'), soft: v('--soft'),
      dark: document.documentElement.dataset.theme === 'dark',
    };
  };
  const [palette, setPalette] = useState(read);
  useEffect(() => {
    const o = new MutationObserver(() => setPalette(read()));
    o.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => o.disconnect();
  }, []);
  return palette;
}
export type Palette = ReturnType<typeof usePalette>;

/** Where a file rests in the bucket: sunflower rings, stacked in layers. */
function fileSpot(i: number, n: number): { pos: Vec; yaw: number } {
  const layer = Math.floor(i / PER_LAYER);
  const k = i % PER_LAYER;
  const inLayer = Math.min(PER_LAYER, n - layer * PER_LAYER);
  const r = (BUCKET_R - 0.35) * Math.sqrt((k + 0.5) / inLayer);
  const a = k * 2.39996 + layer;
  return { pos: [Math.cos(a) * r, 0.3 + layer * 0.16, Math.sin(a) * r], yaw: Math.sin(a * 3) * 0.5 };
}

export interface FloorProps {
  agents: Agent[];
  files: FileItem[];
  huddle: Huddle;
  litAgent: string | null;
  litFile: string | null;
  nameOf: (id: string) => string;
  onAgent: (id: string) => void;
  onFile: (id: string) => void;
  onMore: () => void;
  /** Stops drawing, while the immersive view covers the stage. */
  paused?: boolean;
}

/**
 * Where the stage's camera is right now, in floor units. The immersive view starts its camera here, so the switch
 * from the stage to the room shows the same picture, and flies back here when you leave.
 */
export const stagePose = { position: new Vector3(0, 5.6, 8.6), target: new Vector3(0, 0.2, 0.8), fov: 40 };

function PoseReporter() {
  const controls = useThree((s) => s.controls) as unknown as { target: Vector3 } | null;
  useFrame(({ camera }) => {
    stagePose.position.copy(camera.position);
    if (controls) stagePose.target.copy(controls.target);
    stagePose.fov = (camera as PerspectiveCamera).fov;
  });
  return null;
}

export default function Floor3D(props: FloorProps) {
  const palette = usePalette();
  return (
    <div className="floor floor3d">
      <Canvas camera={{ position: [0, 5.6, 8.6], fov: 40 }} dpr={[1, 2]} frameloop={props.paused ? 'never' : 'always'}>
        <PoseReporter />
        <Scene {...props} palette={palette} />
      </Canvas>
      <NowLine now={props.huddle.now} />
    </div>
  );
}

/** The huddle floor. On its own it brings its lights and orbit camera; the immersive room brings its own. */
export function Scene({ agents, files, huddle, litAgent, litFile, nameOf, onAgent, onFile, onMore, palette, standalone = true }: FloorProps & { palette: Palette; standalone?: boolean }) {
  const { active, members, working, busy } = huddle;
  // Working: its turn is running. Waiting: in the huddle while others work. Idle: no part in the question now.
  const mode = (id: string, inHuddle: boolean): Mode => (busy[id] ? 'working' : active && inHuddle ? 'waiting' : 'idle');
  const idle = agents.filter((a) => !members.includes(a.id));
  const shown = agents.length > MAX_SHOWN ? idle.slice(0, Math.max(0, MAX_SHOWN - 1 - members.length)) : idle;
  const hidden = idle.length - shown.length;
  const slots = shown.length + (hidden ? 1 : 0);

  // Idle translators spread over the back arc; members close the circle around the bucket, leaving the front to the orchestrator and the verifier.
  const idleSpot = (i: number) => at(RING_IDLE, 180 + (180 * (i + 0.5)) / Math.max(slots, 1));
  const spots = new Map<string, Vec>();
  for (const a of agents) {
    const j = members.indexOf(a.id);
    if (j >= 0) spots.set(a.id, at(RING_IN, 130 + (280 * (j + 0.5)) / members.length));
    else if (shown.includes(a)) spots.set(a.id, idleSpot(shown.indexOf(a)));
  }
  // A question brings the orchestrator to the bucket first; the verifier steps in to check the claims.
  const orchestrator = active ? at(RING_IN, 90) : ORCHESTRATOR_WAITS;
  const verifier = huddle.verifier ? at(RING_IN, 64) : VERIFIER_WAITS;
  const where = (id: string) => (id === ORCHESTRATOR ? orchestrator : id === VERIFIER ? verifier : spots.get(id));

  const fileName = (id: string) => files.find((f) => f.id === id)?.name ?? id;
  const holder = (fileId: string) => Object.keys(working).find((a) => working[a] === fileId);
  const inBucket = files.slice(0, MAX_IN_BUCKET);

  return (
    <>
      {standalone && (
        <>
          <ambientLight intensity={0.9} />
          <directionalLight position={[4, 8, 5]} intensity={1.4} />
          <OrbitControls makeDefault enablePan={false} target={[0, 0.2, 0.8]} minDistance={5} maxDistance={16} minPolarAngle={0.35} maxPolarAngle={1.25} enableDamping />
        </>
      )}

      <mesh rotation-x={-Math.PI / 2} position-y={-0.01}>
        <circleGeometry args={[5, 64]} />
        <meshStandardMaterial color={palette.line} transparent opacity={0.35} />
      </mesh>
      <ContactShadows position={[0, 0, 0]} scale={12} blur={2.4} opacity={0.35} far={3} resolution={512} />

      <Bucket active={active} palette={palette} count={files.length} />

      {inBucket.map((f, i) => {
        const by = holder(f.id);
        const hand = by && spots.get(by);
        return (
          <FileCard key={f.id} file={f} rest={fileSpot(i, inBucket.length)} hand={hand || null}
            lit={litFile === f.id} reading={!!by && !!busy[by]?.startsWith('reading')} palette={palette} onClick={() => onFile(f.id)} />
        );
      })}

      {agents.filter((a) => spots.has(a.id)).map((a) => (
        <Figure key={a.id} role="translator" target={spots.get(a.id)!} lit={litAgent === a.id} palette={palette}
          mode={mode(a.id, members.includes(a.id))} doing={busy[a.id]} onClick={() => onAgent(a.id)} title={a.name}
          bubble={huddle.bubble?.agentId === a.id ? huddle.bubble.text : null}>
          <span className="label">{a.name}</span>
          {/* While it reads, the activity line names the file. */}
          {working[a.id] && !busy[a.id] && <span className="holding" title={fileName(working[a.id])}>{fileName(working[a.id])}</span>}
        </Figure>
      ))}

      {hidden > 0 && (
        <Figure role="translator" target={idleSpot(shown.length)} faded palette={palette} onClick={onMore} title={`${hidden} more translators`}>
          <span className="label">+{hidden} more</span>
        </Figure>
      )}

      <Figure role="orchestrator" target={orchestrator} palette={palette} title="Orchestrator"
        mode={mode(ORCHESTRATOR, true)} doing={busy[ORCHESTRATOR]}
        bubble={huddle.bubble?.agentId === ORCHESTRATOR ? huddle.bubble.text : null}>
        <span className="label strong">Orchestrator</span>
      </Figure>
      {huddle.pulse > 0 && <Pulse key={huddle.pulse} from={orchestrator} color={palette.accent} />}

      <Figure role="verifier" target={verifier} palette={palette} title="Verifier" mode={mode(VERIFIER, !!huddle.verifier)} doing={busy[VERIFIER]}>
        <span className="label strong">
          Verifier
          {huddle.verifier && huddle.verifier.state !== 'checking' && (
            <span className={`mark ${huddle.verifier.state}`} aria-label={huddle.verifier.state}>{huddle.verifier.state === 'passed' ? ' ✓' : ' ✗'}</span>
          )}
        </span>
      </Figure>

      {huddle.flights.map((f) => {
        const from = where(f.from);
        const to = where(f.to);
        return from && to ? <Flight key={f.id} from={from} to={to} color={palette.accent} /> : null;
      })}
    </>
  );
}

/** The bucket: an open cylinder holding the session's files. While a question is worked on it lights up and the huddle ring shows around it. */
function Bucket({ active, palette, count }: { active: boolean; palette: Palette; count: number }) {
  const wall = active ? palette.accent : palette.muted;
  return (
    <group>
      <mesh position-y={BUCKET_H / 2}>
        <cylinderGeometry args={[BUCKET_R, BUCKET_R * 0.92, BUCKET_H, 64, 1, true]} />
        <meshStandardMaterial color={wall} transparent opacity={active ? 0.28 : 0.18} side={2} depthWrite={false} />
      </mesh>
      <mesh position-y={BUCKET_H} rotation-x={Math.PI / 2}>
        <torusGeometry args={[BUCKET_R, 0.035, 12, 96]} />
        <meshStandardMaterial color={wall} emissive={active ? palette.accent : '#000000'} emissiveIntensity={0.4} />
      </mesh>
      <mesh position-y={0.01} rotation-x={-Math.PI / 2}>
        <circleGeometry args={[BUCKET_R * 0.92, 64]} />
        <meshStandardMaterial color={active ? palette.soft : palette.line} />
      </mesh>
      <HuddleRing active={active} color={palette.accent} />
      <Html position={[0, 0, BUCKET_R + 0.35]} center zIndexRange={[20, 0]}>
        <span className="tag3d">{active ? 'huddle' : `huddle · ${count} file${count === 1 ? '' : 's'}`}</span>
      </Html>
    </group>
  );
}

/** A file: a card standing in the bucket. Handed to a translator, it flies into that translator's hands. */
function FileCard({ file, rest, hand, lit, reading, palette, onClick }: {
  file: FileItem; rest: { pos: Vec; yaw: number }; hand: Vec | null; lit: boolean; reading: boolean; palette: Palette; onClick: () => void;
}) {
  const ref = useRef<Mesh>(null);
  const [hover, setHover] = useState(false);
  const goal = useMemo(() => {
    if (!hand) return { pos: new Vector3(...rest.pos).setY(rest.pos[1] + (lit ? 0.35 : 0)), rot: new Quaternion().setFromEuler(new Euler(-0.15, rest.yaw, 0)) };
    // In front of the translator, a little towards the bucket, facing the camera.
    const p = new Vector3(...hand).multiplyScalar((RING_IN - 0.55) / RING_IN).setY(1.0);
    return { pos: p, rot: new Quaternion() };
  }, [hand, rest, lit]);
  useFrame(({ clock }, dt) => {
    const m = ref.current;
    if (!m) return;
    m.position.lerp(goal.pos, ease(dt, 3));
    m.quaternion.slerp(goal.rot, ease(dt, 3));
    const mat = m.material as unknown as { emissiveIntensity: number };
    mat.emissiveIntensity = reading ? 0.45 + 0.35 * Math.sin(clock.elapsedTime * 5) : lit || hover ? 0.5 : 0;
  });
  const dim = file.status === 'missing' || file.status === 'changed' || file.status === 'unreadable';
  return (
    <mesh ref={ref} position={rest.pos} onClick={(e) => { e.stopPropagation(); onClick(); }}
      onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { setHover(false); document.body.style.cursor = ''; }}>
      <boxGeometry args={[0.4, 0.52, 0.03]} />
      <meshStandardMaterial color={TYPE_COLOR[file.type]} emissive={palette.accent} emissiveIntensity={0} transparent={dim} opacity={dim ? 0.45 : 1} />
      <Html position={[0, 0.42, 0]} center zIndexRange={[30, 0]}>
        {hover && <span className="tag3d name">{file.name}</span>}
      </Html>
    </mesh>
  );
}

type Mode = 'working' | 'waiting' | 'idle';

/** Keeps a bubble's text for a moment after it is gone, so it fades out instead of vanishing. */
function useLinger(text: string | null | undefined, ms = 300) {
  const [shown, setShown] = useState(text ?? null);
  useEffect(() => {
    if (text) return setShown(text);
    const timer = setTimeout(() => setShown(null), ms);
    return () => clearTimeout(timer);
  }, [text, ms]);
  return { shown, leaving: !text && shown !== null };
}

/**
 * An agent, gliding to its spot and facing the bucket, with a step in its walk and a slow breath when it stands.
 * A translator is a capsule with a round head; the orchestrator is taller, in a robe, with a halo turning over its
 * head; the verifier is a hexagonal block with a faceted head. Working, it bobs, glows, has dots circling over its
 * head and a pulsing ring at its feet, and its label says what it does. Waiting in the huddle, it fades back.
 */
function Figure({ role, target, mode = 'idle', doing, lit, faded, palette, title, onClick, bubble, children }: {
  role: Role; target: Vec; mode?: Mode; doing?: string; lit?: boolean; faded?: boolean; palette: Palette; title: string;
  onClick?: () => void; bubble?: string | null; children: ReactNode;
}) {
  const ref = useRef<Group>(null);
  const body = useRef<Group>(null);
  const ring = useRef<Mesh>(null);
  const dots = useRef<Group>(null);
  const goal = useMemo(() => new Vector3(...target), [target[0], target[1], target[2]]);
  const centre = useMemo(() => new Vector3(), []);
  const phase = useMemo(() => Math.random() * Math.PI * 2, []);
  const color = ROLE_COLOR[role][palette.dark ? 'dark' : 'light'];
  // One material for the whole body, eased towards its look every frame.
  const material = useMemo(() => new MeshStandardMaterial({ transparent: true, flatShading: role === 'verifier' }), [role]);
  useEffect(() => { material.color.set(color); material.emissive.set(palette.accent); }, [material, color, palette.accent]);
  useEffect(() => () => material.dispose(), [material]);
  const working = mode === 'working';
  const { shown, leaving } = useLinger(bubble);

  useFrame(({ clock }, dt) => {
    const g = ref.current;
    const b = body.current;
    if (!g || !b) return;
    const t = clock.elapsedTime + phase;
    const away = g.position.distanceTo(goal);
    g.position.lerp(goal, ease(dt, 2.5));
    centre.set(0, g.position.y, 0);
    g.lookAt(centre);
    if (!reducedMotion) {
      const stepping = Math.min(away, 1) * Math.abs(Math.sin(t * 9)) * 0.12;
      b.position.y = stepping + (working ? 0.05 + Math.sin(t * 5) * 0.05 : 0);
      b.scale.y = 1 + Math.sin(t * 1.7) * 0.015;
    }
    material.opacity += ((mode === 'waiting' ? 0.4 : faded ? 0.5 : 1) - material.opacity) * ease(dt, 4);
    const glow = lit ? 0.6 : working ? 0.22 + 0.12 * Math.sin(t * 4) : 0;
    material.emissiveIntensity += (glow - material.emissiveIntensity) * ease(dt, 5);
    if (ring.current) ring.current.scale.setScalar(working && !reducedMotion ? 1.1 + 0.15 * Math.sin(t * 4) : 1);
    if (dots.current) {
      const d = dots.current;
      const size = d.scale.x + ((working ? 1 : 0) - d.scale.x) * ease(dt, 5);
      d.scale.setScalar(size);
      d.visible = size > 0.02;
      if (!reducedMotion) d.rotation.y += dt * 3;
    }
  });
  const pointer = onClick && {
    onClick: (e: { stopPropagation: () => void }) => { e.stopPropagation(); onClick(); },
    onPointerOver: () => { document.body.style.cursor = 'pointer'; },
    onPointerOut: () => { document.body.style.cursor = ''; },
  };
  const head = role === 'orchestrator' ? 1.4 : role === 'verifier' ? 1.15 : 1.18;
  const label = (
    <>
      {children}
      {mode !== 'idle' && <span className={`doing ${mode}`}>{working ? doing : 'waiting'}</span>}
    </>
  );
  return (
    <group ref={ref} position={target}>
      <group {...pointer}>
        <group ref={body}>
          {role === 'translator' && (
            <>
              <mesh position-y={0.5} material={material}><capsuleGeometry args={[0.2, 0.42, 6, 16]} /></mesh>
              <mesh position-y={1.02} material={material}><sphereGeometry args={[0.16, 24, 16]} /></mesh>
            </>
          )}
          {role === 'orchestrator' && (
            <>
              <mesh position-y={0.55} material={material}><coneGeometry args={[0.32, 1.1, 32]} /></mesh>
              <mesh position-y={1.22} material={material}><sphereGeometry args={[0.18, 24, 16]} /></mesh>
              <Halo y={1.5} color={color} />
            </>
          )}
          {role === 'verifier' && (
            <>
              <mesh position-y={0.4} material={material}><cylinderGeometry args={[0.24, 0.28, 0.8, 6]} /></mesh>
              <mesh position-y={0.98} material={material}><icosahedronGeometry args={[0.17, 0]} /></mesh>
            </>
          )}
          <group ref={dots} position-y={head + (role === 'orchestrator' ? 0.32 : 0.2)} scale={0}>
            {[0, 1, 2].map((i) => (
              <mesh key={i} position={[Math.cos((i * 2 * Math.PI) / 3) * 0.22, 0, Math.sin((i * 2 * Math.PI) / 3) * 0.22]}>
                <sphereGeometry args={[0.045, 12, 8]} />
                <meshBasicMaterial color={palette.accent} />
              </mesh>
            ))}
          </group>
        </group>
        <mesh ref={ring} position-y={0.01} rotation-x={-Math.PI / 2}>
          <ringGeometry args={[0.32, 0.37, 32]} />
          <meshBasicMaterial color={lit || working ? palette.accent : color} transparent opacity={lit || working ? 1 : mode === 'waiting' ? 0.3 : 0.6} />
        </mesh>
      </group>
      {/* Each <Html> stays mounted and only its content changes: mounting one starts a React root. */}
      <Html position={[0, head + (role === 'orchestrator' ? 0.55 : 0.45), 0]} zIndexRange={[40, 20]}>
        {shown && <span key={shown} className={`bubble ${leaving ? 'leaving' : ''}`} title={shown}>{short(shown)}</span>}
      </Html>
      <Html position={[0, -0.1, 0]} zIndexRange={[20, 0]}>
        {onClick
          ? <button className={`label3d ${mode} ${lit ? 'lit' : ''}`} onClick={onClick} title={title}>{label}</button>
          : <div className={`label3d ${mode}`} title={title}>{label}</div>}
      </Html>
    </group>
  );
}

/** The ring the huddle stands on. It fades in when a question starts and out when the huddle ends. */
function HuddleRing({ active, color }: { active: boolean; color: string }) {
  const ref = useRef<Mesh>(null);
  useFrame((_, dt) => {
    const m = ref.current;
    if (!m) return;
    const mat = m.material as MeshBasicMaterial;
    mat.opacity += ((active ? 0.7 : 0) - mat.opacity) * ease(dt, 3);
    m.visible = mat.opacity > 0.01;
  });
  return (
    <mesh ref={ref} position-y={0.02} rotation-x={-Math.PI / 2}>
      <ringGeometry args={[RING_IN - 0.05, RING_IN + 0.05, 128]} />
      <meshBasicMaterial color={color} transparent opacity={0} depthWrite={false} />
    </mesh>
  );
}

/** The orchestrator's halo: a thin ring turning over its head. */
function Halo({ y, color }: { y: number; color: string }) {
  const ref = useRef<Mesh>(null);
  useFrame((_, dt) => { if (ref.current && !reducedMotion) ref.current.rotation.z += dt * 1.2; });
  return (
    <mesh ref={ref} position-y={y} rotation-x={Math.PI / 2 - 0.25}>
      <torusGeometry args={[0.2, 0.025, 8, 40, Math.PI * 1.6]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} />
    </mesh>
  );
}

/** A message on its way between two agents: a light arcing from one to the other, with a smaller one trailing it. */
const FLIGHT_S = 0.9;
function Flight({ from, to, color }: { from: Vec; to: Vec; color: string }) {
  const lead = useRef<Mesh>(null);
  const tail = useRef<Mesh>(null);
  const born = useRef<number | null>(null);
  const [a, b] = useMemo(() => [new Vector3(from[0], 1.1, from[2]), new Vector3(to[0], 1.1, to[2])], [from[0], from[2], to[0], to[2]]);
  useFrame(({ clock }) => {
    born.current ??= clock.elapsedTime;
    const t = (clock.elapsedTime - born.current) / FLIGHT_S;
    for (const [m, lag] of [[lead.current, 0], [tail.current, 0.08]] as const) {
      if (!m) continue;
      const k = Math.min(Math.max(t - lag, 0), 1);
      m.position.lerpVectors(a, b, k);
      m.position.y += Math.sin(Math.PI * k) * 0.9;
      m.visible = t - lag > 0 && k < 1;
    }
  });
  if (reducedMotion) return null;
  return (
    <>
      <mesh ref={lead} visible={false}><sphereGeometry args={[0.09, 16, 12]} /><meshBasicMaterial color={color} /></mesh>
      <mesh ref={tail} visible={false}><sphereGeometry args={[0.05, 12, 8]} /><meshBasicMaterial color={color} transparent opacity={0.5} /></mesh>
    </>
  );
}

/** The story line over the floor: what is happening now, and for how long, so a long turn still visibly moves on. */
export function NowLine({ now }: { now: Huddle['now'] }) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (!now) return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [now]);
  if (!now) return null;
  const seconds = Math.max(0, Math.floor((Date.now() - now.since) / 1000));
  return (
    <div className="now3d">
      <span className="dot" />
      <span key={now.since} className="now-text" aria-live="polite">{now.text}</span>
      <span className="muted" aria-hidden="true">{seconds}s</span>
    </div>
  );
}

/** A broadcast: a ring spreading out over the floor from the orchestrator. */
function Pulse({ from, color }: { from: Vec; color: string }) {
  const ref = useRef<Mesh>(null);
  const born = useRef<number | null>(null);
  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    born.current ??= clock.elapsedTime;
    const t = Math.min((clock.elapsedTime - born.current) / 1.4, 1);
    m.scale.setScalar(0.3 + t * 6);
    (m.material as MeshBasicMaterial).opacity = 1 - t;
    m.visible = t < 1;
  });
  if (reducedMotion) return null;
  return (
    <mesh ref={ref} position={[from[0], 0.03, from[2]]} rotation-x={-Math.PI / 2}>
      <ringGeometry args={[0.9, 1, 64]} />
      <meshBasicMaterial color={color} transparent />
    </mesh>
  );
}
