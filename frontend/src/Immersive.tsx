import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Html, PointerLockControls } from '@react-three/drei';
import { Color, MeshStandardMaterial, Quaternion, Vector3 } from 'three';
import type { Fog, Group, LineBasicMaterial, Mesh, PerspectiveCamera } from 'three';
import type { ChatMsg, Citation } from './backend/types';
import { NowLine, Scene, ease, reducedMotion, stagePose, usePalette } from './Floor3D';
import type { FloorProps, Palette } from './Floor3D';
import { LogEntries } from './Stage';

/**
 * The immersive view: the stage as a room you walk through in first person. The huddle stands in the middle, as on the
 * 3D floor but at human size. The chat agent sits at a desk on the south side, facing the huddle across its monitor
 * and typing while a question runs; the monitor is the 2D chat. The huddle log hangs on the north wall and opens the
 * full log. Nothing here talks to the backend: it is drawn from the same state as the regular stage, and the chat on
 * the monitor is the regular chat.
 *
 * It starts where the stage's 3D floor left off: the camera at the floor's angle, the huddle at the same size, no walls.
 * Then the walls grow up out of the floor and the camera comes down to eye level behind the chat agent, the narrow
 * view widening as it lands. Leaving plays it backwards, back to the floor's angle.
 */

type Vec = [number, number, number];

/** The huddle floor is drawn at this scale, so its figures stand about as tall as you. */
const HUDDLE_SCALE = 1.4;
/** Bucket radius on the 3D floor (1.5), scaled, plus room for your shoulders. */
const BUCKET_KEEP = 1.5 * HUDDLE_SCALE + 0.35;
const ROOM = { x0: -13, x1: 13, z0: -10.5, z1: 15, h: 4.2 };
const EYE = 1.65;
const WALK = 3.2;
const RUN = 6;
const DESK = { x: 0, z: 10.4, w: 3.2, d: 1.2, top: 0.77 };
/** The chat agent sits south of the desk, facing north: over its monitor, towards the huddle. */
const AGENT: Vec = [-1.15, 0, 11.6];
const MONITOR: Vec = [0.25, 0, 10.05];
const SCREEN_Y = 1.5;
const SCREEN_W = 1.6;
const SCREEN_H = 0.95;
/** You start behind the chat agent, with its monitor and the huddle in front of you. */
const SPAWN: Vec = [2.9, EYE, 13.8];
const LOOK: Vec = [0, 1.1, 0];
const WALK_FOV = 70;
const INTRO_S = 2.2;
const OUTRO_S = 1.5;
const BOARD: Vec = [0, 2.3, ROOM.z0 + 0.03];

/** What you can walk up to and open: the monitor (the chat) and the log board (the huddle log). */
type Target = 'chat' | 'log';
/** Each can be opened from this close, standing in front of it and looking at it. */
const TARGETS: { id: Target; at: Vec; reach: number; inFront: (z: number) => boolean }[] = [
  { id: 'chat', at: MONITOR, reach: 4, inFront: (z) => z > MONITOR[2] + 0.3 },
  { id: 'log', at: BOARD, reach: 8, inFront: (z) => z > BOARD[2] + 0.3 },
];
const TITLE: Record<Target, string> = { chat: 'Monitor', log: 'Huddle log' };
const USE: Record<Target, string> = { chat: 'Use the monitor', log: 'Read the huddle log' };

const CHAT_COLOR = { light: '#7566cc', dark: '#a596ee' };
/** Html with `transform` draws 400 / distanceFactor CSS pixels per metre. */
const SCREEN_DF = 1.25;
const BOARD_DF = 2;

const UP = new Vector3(0, 1, 0);
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

interface Props extends FloorProps {
  messages: ChatMsg[];
  running: boolean;
  /** The 2D chat, shown full size when you use the monitor. */
  chat: ReactNode;
  /** The open citation, shown over the monitor or the log. */
  citation?: ReactNode;
  onCite: (c: Citation) => void;
  /** Buttons for the pause card, such as the demo controls. */
  actions?: ReactNode;
  /** Asked from the controls card: the parent then sets `leaving`. */
  onExit: () => void;
  /** Fly back up to the stage's angle and take the room away; `onLeft` follows. */
  leaving: boolean;
  /** Fade out: the stage's floor is under the room again. */
  fading: boolean;
  /** Drawn but not shown yet, while the stage's floor grows: the room waits at the floor's angle. */
  holding: boolean;
  onEntered: () => void;
  onLeft: () => void;
}

export default function Immersive({ messages, running, chat, citation, onCite, actions, onExit, leaving, fading, holding, onEntered, onLeft, ...floor }: Props) {
  const palette = usePalette();
  const [locked, setLocked] = useState(false);
  const [near, setNear] = useState<Target | null>(null);
  const [screen, setScreen] = useState<Target | null>(null);
  /** The controls card. It shows only when asked for with Esc, never by itself after the way in. */
  const [menu, setMenu] = useState(false);
  /** The way in is over and the way out has not started: you can walk. */
  const [free, setFree] = useState(false);
  /** The handover has begun: the room fades in over the stage's floor, showing the same picture. */
  const [ready, setReady] = useState(false);
  const freeRef = useRef(false);
  const reveal = useRef(0);
  const unlockedByUs = useRef(false);
  const keys = useRef(new Set<string>());
  const lockedRef = useRef(false);
  const nearRef = useRef<Target | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  lockedRef.current = locked;
  nearRef.current = near;
  freeRef.current = free && !leaving;

  const lock = () => {
    const el = canvas.current;
    if (!el) return;
    // Some browsers return a promise and reject it when the lock is refused; the pause card stays up then.
    (el.requestPointerLock() as unknown as Promise<void> | undefined)?.catch?.(() => {});
  };
  const unlock = () => {
    if (!document.pointerLockElement) return;
    unlockedByUs.current = true;
    document.exitPointerLock();
  };
  const openScreen = (target: Target) => {
    keys.current.clear();
    setMenu(false);
    setScreen(target);
    unlock();
  };
  const closeScreen = (walk: boolean) => {
    setScreen(null);
    if (walk) lock();
  };

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (screen) {
        if (e.code === 'Escape') closeScreen(false);
        return;
      }
      // Walking, Esc only releases the pointer (the browser does that, and the card opens on unlock). Standing, it toggles the card.
      if (!lockedRef.current) {
        if (e.code === 'Escape' && freeRef.current) setMenu((m) => !m);
        return;
      }
      if (e.code === 'KeyE' && nearRef.current) { openScreen(nearRef.current); return; }
      keys.current.add(e.code);
    };
    const up = (e: KeyboardEvent) => keys.current.delete(e.code);
    const blur = () => keys.current.clear();
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
    };
  }, [screen]);
  useEffect(() => () => { if (document.pointerLockElement) document.exitPointerLock(); }, []);
  useEffect(() => {
    if (!leaving) return;
    setMenu(false);
    setScreen(null);
    unlock();
  }, [leaving]);

  const onLock = useCallback(() => { setLocked(true); setMenu(false); }, []);
  const onUnlock = useCallback(() => {
    keys.current.clear();
    setLocked(false);
    // Released by Esc: show the controls. Released by us, to open the monitor or to leave: do not.
    if (!unlockedByUs.current) setMenu(true);
    unlockedByUs.current = false;
  }, []);
  const entered = useCallback(() => { setFree(true); onEntered(); }, [onEntered]);
  const left = useCallback(() => onLeft(), [onLeft]);
  const shown = useCallback(() => setReady(true), []);
  /** Standing in the room: a click on the room starts walking. */
  const clickRoom = (e: React.MouseEvent) => {
    if (free && !leaving && !locked && !screen && !menu && e.target === canvas.current) lock();
  };
  const onNear = useCallback((n: Target | null) => setNear(n), []);

  const last = messages[messages.length - 1];
  const status = last?.pending ? last.status ?? null : null;
  const noop = () => {};

  return (
    <div className={`immersive ${ready ? 'ready' : ''} ${fading ? 'fading' : ''}`} onClick={clickRoom}>
      <Canvas camera={{ fov: WALK_FOV, near: 0.05, far: 120, position: SPAWN }} dpr={[1, 2]} frameloop={holding ? 'demand' : 'always'}
        onCreated={({ gl }) => { canvas.current = gl.domElement; }}>
        <color attach="background" args={[palette.stage]} />
        <fog attach="fog" args={[palette.bg, 200, 300]} />
        {/* The stage's own lights, so the huddle looks the same in both; the lamp over the desk comes with the walls. */}
        <ambientLight intensity={0.9} />
        <directionalLight position={[4, 8, 5]} intensity={1.4} />
        <Lamp reveal={reveal} />
        {/* Never locks by itself: only a click on the room, "Walk in" and the monitor's back button do. */}
        <PointerLockControls selector="#immersive-no-auto-lock" onLock={onLock} onUnlock={onUnlock} />
        <Director reveal={reveal} holding={holding} leaving={leaving} palette={palette} onShown={shown} onEntered={entered} onLeft={left} />
        <Player active={lockedRef} free={freeRef} keys={keys} onNear={onNear} />
        <Room palette={palette} reveal={reveal} />
        <group scale={HUDDLE_SCALE}>
          <Scene {...floor} standalone={false} palette={palette} onAgent={noop} onFile={noop} onMore={noop} />
        </group>
        <Reveal reveal={reveal} from={0.3}>
          <Desk palette={palette} />
          <ChatAgent typing={running} status={status} palette={palette} labels={free && !leaving} />
          <Monitor messages={messages} near={near === 'chat'} palette={palette} onUse={() => { if (nearRef.current === 'chat') openScreen('chat'); }} />
          <LogBoard log={floor.huddle.log} nameOf={floor.nameOf} near={near === 'log'} palette={palette}
            onUse={() => { if (nearRef.current === 'log') openScreen('log'); }} />
        </Reveal>
      </Canvas>

      <NowLine now={floor.huddle.now} />
      {locked && <div className="crosshair" aria-hidden="true" />}
      {locked && near && <div className="use-hint"><kbd>E</kbd> {USE[near]}</div>}
      {free && !leaving && !locked && !screen && !menu && (
        <div className="walk-hint">Click to walk <span className="sep">·</span> <kbd>Esc</kbd> for controls</div>
      )}

      {menu && !locked && !screen && !leaving && (
        <div className="pause">
          <div className="pause-card" role="dialog" aria-label="Immersive view">
            <h2>Immersive view</h2>
            <p className="muted">Walk around the room. The chat agent sits at its desk; its monitor is your chat. Walk up to the huddle to see what the agents are doing; the board behind it holds the huddle log.</p>
            <div className="keys">
              <span><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd></span><span>Walk (hold <kbd>Shift</kbd> to run)</span>
              <span><kbd>Mouse</kbd></span><span>Look around</span>
              <span><kbd>E</kbd></span><span>Use the monitor or read the log board when you face it</span>
              <span><kbd>Esc</kbd></span><span>Stop walking, and show or hide this card</span>
            </div>
            <div className="pause-actions">
              <button className="primary" onClick={lock} autoFocus>Walk</button>
              <button onClick={() => openScreen('chat')}>Use the monitor</button>
              <button onClick={() => openScreen('log')}>Read the huddle log</button>
              {actions}
              <span className="grow" />
              <button onClick={() => { setMenu(false); onExit(); }}>Leave immersive view</button>
            </div>
          </div>
        </div>
      )}

      {screen && (
        <div className="screen-view">
          <div className="screen-frame" role="dialog" aria-label={TITLE[screen]}>
            <header>
              <strong>{TITLE[screen]}</strong>
              {screen === 'log' && <span className="hint-text">{floor.huddle.log.length} entries</span>}
              <span className="grow" />
              <span className="hint-text">Esc to step back</span>
              <button onClick={() => closeScreen(true)}>Back to the room</button>
            </header>
            <div className="screen-body">
              {screen === 'chat' ? chat : <LogEntries log={floor.huddle.log} nameOf={floor.nameOf} onCite={onCite} />}
              {citation}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const smooth = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const part = (t: number, from: number, to: number) => clamp((t - from) / (to - from), 0, 1);

interface Flight { kind: 'in' | 'out'; t: number; seconds: number; p0: Vector3; p1: Vector3; l0: Vector3; l1: Vector3; f0: number; f1: number }

/**
 * Moves the camera on the way in and out, and sets `reveal`: 0 is the stage's floor alone, 1 the whole room. Walls,
 * furniture and the lamp grow with it, and the background and the fog turn from the stage's into the room's.
 */
function Director({ reveal, holding, leaving, palette, onShown, onEntered, onLeft }: {
  reveal: RefObject<number>; holding: boolean; leaving: boolean; palette: Palette;
  onShown: () => void; onEntered: () => void; onLeft: () => void;
}) {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const scene = useThree((s) => s.scene);
  const flight = useRef<Flight | null>(null);
  const started = useRef(false);
  const look = useMemo(() => new Vector3(), []);
  const colors = useMemo(() => ({ stage: new Color(), room: new Color() }), []);
  useEffect(() => { colors.stage.set(palette.stage); colors.room.set(palette.bg); }, [colors, palette.stage, palette.bg]);
  const stageView = () => ({
    p: stagePose.position.clone().multiplyScalar(HUDDLE_SCALE),
    l: stagePose.target.clone().multiplyScalar(HUDDLE_SCALE),
    fov: stagePose.fov,
  });
  const aim = (fov: number) => { camera.fov = fov; camera.updateProjectionMatrix(); };

  /** Shows what the stage's floor shows: same angle, same size, no walls yet. */
  const toStage = () => {
    const from = stageView();
    camera.position.copy(from.p);
    camera.lookAt(from.l);
    aim(from.fov);
    reveal.current = 0;
    return from;
  };
  // While the floor grows the room is drawn once, unseen, so its first real frame does not stall the handover.
  useLayoutEffect(() => { if (reducedMotion) { camera.position.set(...SPAWN); camera.lookAt(...LOOK); reveal.current = 1; } else toStage(); }, []);

  useEffect(() => {
    if (!leaving) return;
    if (reducedMotion) { onLeft(); return; }
    const to = stageView();
    const dir = camera.getWorldDirection(new Vector3());
    const l0 = camera.position.clone().addScaledVector(dir, camera.position.distanceTo(to.l));
    flight.current = { kind: 'out', t: 0, seconds: OUTRO_S, p0: camera.position.clone(), p1: to.p, l0, l1: to.l, f0: camera.fov, f1: to.fov };
  }, [leaving]);

  useFrame((_, delta) => {
    if (!holding && !started.current) {
      // The floor has finished growing: take over from it where its camera is now, and start down.
      started.current = true;
      if (!reducedMotion) {
        const from = toStage();
        flight.current = { kind: 'in', t: 0, seconds: INTRO_S, p0: from.p, p1: new Vector3(...SPAWN), l0: from.l, l1: new Vector3(...LOOK), f0: from.fov, f1: WALK_FOV };
      }
      onShown();
      if (reducedMotion) onEntered();
      delta = 0; // the first frame shows the stage's picture as it is
    }
    const f = flight.current;
    if (f) {
      f.t = Math.min(1, f.t + Math.min(delta, 0.1) / f.seconds);
      const k = smooth(f.t);
      camera.position.lerpVectors(f.p0, f.p1, k);
      camera.lookAt(look.lerpVectors(f.l0, f.l1, k));
      aim(f.f0 + (f.f1 - f.f0) * k);
      // In: the walls rise while the camera is still high. Out: they sink before it gets there.
      reveal.current = f.kind === 'in' ? smooth(part(f.t, 0.08, 0.7)) : 1 - smooth(part(f.t, 0.2, 0.85));
      if (f.t >= 1) {
        flight.current = null;
        if (f.kind === 'in') onEntered(); else onLeft();
      }
    }
    const r = reveal.current;
    if (scene.background instanceof Color) scene.background.lerpColors(colors.stage, colors.room, r);
    const fog = scene.fog as Fog | null;
    if (fog) {
      fog.color.copy(colors.room);
      // Far enough at 0 to touch nothing in view, so the haze builds with the room instead of arriving at the end.
      fog.near = 60 - 38 * r;
      fog.far = 120 - 72 * r;
    }
  });
  return null;
}

/** Its share of the room's reveal: 0 before `from`, 1 after `to`, eased between. Walls come first, furniture after. */
const within = (r: number, from: number, to: number) => smooth(part(r, from, to));

/** Grows its children up out of the floor as the room appears, between `from` and `to` of the reveal. */
function Reveal({ reveal, from = 0, to = 1, children }: { reveal: RefObject<number>; from?: number; to?: number; children: ReactNode }) {
  const ref = useRef<Group>(null);
  useFrame(() => {
    const g = ref.current;
    if (!g) return;
    const r = within(reveal.current, from, to);
    g.scale.y = Math.max(0.001, r);
    g.visible = r > 0.002;
  });
  return <group ref={ref}>{children}</group>;
}

/** The lamp over the desk, brightening with the room. */
function Lamp({ reveal }: { reveal: RefObject<number> }) {
  const ref = useRef<{ intensity: number }>(null);
  useFrame(() => { if (ref.current) ref.current.intensity = 6 * reveal.current; });
  return <pointLight ref={ref as never} position={[0, 3.4, 11]} intensity={0} distance={9} />;
}

/** You: walks while the pointer is locked, stays inside the room and out of the bucket and the desk, and notices what you can open. */
function Player({ active, free, keys, onNear }: {
  active: RefObject<boolean>; free: RefObject<boolean>; keys: RefObject<Set<string>>; onNear: (near: Target | null) => void;
}) {
  const camera = useThree((s) => s.camera);
  const near = useRef<Target | null>(null);
  const step = useRef(0);
  const v = useMemo(() => ({ fwd: new Vector3(), side: new Vector3(), move: new Vector3() }), []);

  useFrame((_, delta) => {
    // On the way in and out the Director holds the camera.
    if (!free.current) {
      if (near.current) { near.current = null; onNear(null); }
      return;
    }
    const dt = Math.min(delta, 0.1);
    const p = camera.position;
    const k = keys.current;
    const has = (...codes: string[]) => codes.some((c) => k.has(c));
    let moving = false;
    if (active.current) {
      const f = (has('KeyW', 'ArrowUp') ? 1 : 0) - (has('KeyS', 'ArrowDown') ? 1 : 0);
      const r = (has('KeyD', 'ArrowRight') ? 1 : 0) - (has('KeyA', 'ArrowLeft') ? 1 : 0);
      camera.getWorldDirection(v.fwd);
      v.fwd.y = 0;
      v.fwd.normalize();
      v.side.crossVectors(v.fwd, UP);
      v.move.copy(v.fwd).multiplyScalar(f).addScaledVector(v.side, r);
      if (v.move.lengthSq() > 0) {
        const speed = has('ShiftLeft', 'ShiftRight') ? RUN : WALK;
        p.addScaledVector(v.move.normalize(), speed * dt);
        step.current += dt * speed * 2.2;
        moving = true;
      }
      collide(p);
    }
    const bob = moving && !reducedMotion ? Math.abs(Math.sin(step.current)) * 0.045 : 0;
    p.y += (EYE + bob - p.y) * ease(dt, 12);

    // Near the monitor or the log board: in front of it, within reach, and looking at it.
    camera.getWorldDirection(v.fwd);
    const flat = Math.hypot(v.fwd.x, v.fwd.z) || 1;
    const facing = (at: Vec) => {
      const dx = at[0] - p.x;
      const dz = at[2] - p.z;
      const dist = Math.hypot(dx, dz) || 1;
      return { dist, dot: (v.fwd.x * dx + v.fwd.z * dz) / (flat * dist) };
    };
    const n = !active.current ? null : TARGETS.find((t) => {
      const f = facing(t.at);
      return f.dist < t.reach && t.inFront(p.z) && f.dot > 0.8;
    })?.id ?? null;
    if (n !== near.current) { near.current = n; onNear(n); }
  });
  return null;
}

function collide(p: Vector3) {
  const pad = 0.4;
  p.x = clamp(p.x, ROOM.x0 + pad, ROOM.x1 - pad);
  p.z = clamp(p.z, ROOM.z0 + pad, ROOM.z1 - pad);
  const d = Math.hypot(p.x, p.z);
  if (d < BUCKET_KEEP && d > 0) { p.x *= BUCKET_KEEP / d; p.z *= BUCKET_KEEP / d; }
  // The desk, pushed out along the shortest way.
  const x0 = DESK.x - DESK.w / 2 - 0.3, x1 = DESK.x + DESK.w / 2 + 0.3;
  const z0 = DESK.z - DESK.d / 2 - 0.3, z1 = DESK.z + DESK.d / 2 + 0.3;
  if (p.x > x0 && p.x < x1 && p.z > z0 && p.z < z1) {
    const out = [p.x - x0, x1 - p.x, p.z - z0, z1 - p.z];
    const i = out.indexOf(Math.min(...out));
    if (i === 0) p.x = x0; else if (i === 1) p.x = x1; else if (i === 2) p.z = z0; else p.z = z1;
  }
  // The chat agent's chair.
  const ax = p.x - AGENT[0], az = p.z - AGENT[2];
  const ad = Math.hypot(ax, az);
  if (ad < 0.65 && ad > 0) { p.x = AGENT[0] + (ax / ad) * 0.65; p.z = AGENT[2] + (az / ad) * 0.65; }
}

/** The floor, four walls, and a soft grid so walking reads as moving. The walls grow and the grid fades in with the room. */
function Room({ palette, reveal }: { palette: Palette; reveal: RefObject<number> }) {
  const grid = useRef<{ material: LineBasicMaterial }>(null);
  // The floor fades in too: lit, it is a shade darker than the stage's flat background it starts over.
  const floor = useMemo(() => new MeshStandardMaterial({ transparent: true, opacity: 0, depthWrite: false }), []);
  const walls = useMemo(() => new MeshStandardMaterial({ transparent: true, opacity: 0 }), []);
  useEffect(() => { floor.color.set(palette.stage); walls.color.set(palette.surface); }, [floor, walls, palette.stage, palette.surface]);
  useEffect(() => () => { floor.dispose(); walls.dispose(); }, [floor, walls]);
  useFrame(() => {
    const r = reveal.current;
    const m = grid.current?.material;
    if (m) { m.transparent = true; m.opacity = r; }
    floor.opacity = r;
    walls.opacity = within(r, 0, 0.6);
    walls.transparent = walls.opacity < 1;
    walls.depthWrite = !walls.transparent;
  });
  const w = ROOM.x1 - ROOM.x0;
  const d = ROOM.z1 - ROOM.z0;
  const cx = (ROOM.x0 + ROOM.x1) / 2;
  const cz = (ROOM.z0 + ROOM.z1) / 2;
  const wall = (pos: Vec, rotY: number, width: number) => (
    <mesh position={pos} rotation-y={rotY} material={walls}>
      <planeGeometry args={[width, ROOM.h]} />
    </mesh>
  );
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position={[cx, -0.02, cz]} material={floor} renderOrder={-1}>
        <planeGeometry args={[w, d]} />
      </mesh>
      <gridHelper ref={grid as never} args={[Math.max(w, d), Math.max(w, d), palette.line, palette.line]} position={[cx, -0.015, cz]} />
      <Reveal reveal={reveal} to={0.6}>
        {wall([cx, ROOM.h / 2, ROOM.z0], 0, w)}
        {wall([cx, ROOM.h / 2, ROOM.z1], Math.PI, w)}
        {wall([ROOM.x0, ROOM.h / 2, cz], Math.PI / 2, d)}
        {wall([ROOM.x1, ROOM.h / 2, cz], -Math.PI / 2, d)}
      </Reveal>
    </group>
  );
}

function Desk({ palette }: { palette: Palette }) {
  const wood = palette.dark ? '#5b4a3a' : '#a88a6a';
  const legs: [number, number][] = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
  return (
    <group position={[DESK.x, 0, DESK.z]}>
      <mesh position-y={DESK.top - 0.03}>
        <boxGeometry args={[DESK.w, 0.06, DESK.d]} />
        <meshStandardMaterial color={wood} />
      </mesh>
      {legs.map(([sx, sz], i) => (
        <mesh key={i} position={[sx * (DESK.w / 2 - 0.08), (DESK.top - 0.06) / 2, sz * (DESK.d / 2 - 0.08)]}>
          <boxGeometry args={[0.06, DESK.top - 0.06, 0.06]} />
          <meshStandardMaterial color={palette.muted} />
        </mesh>
      ))}
    </group>
  );
}

/** A capsule from one point to another: an arm or a leg. */
function Limb({ from, to, r, material }: { from: Vec; to: Vec; r: number; material: MeshStandardMaterial }) {
  const { pos, quat, len } = useMemo(() => {
    const a = new Vector3(...from);
    const b = new Vector3(...to);
    const dir = b.clone().sub(a);
    return { pos: a.clone().add(b).multiplyScalar(0.5), quat: new Quaternion().setFromUnitVectors(UP, dir.clone().normalize()), len: dir.length() };
  }, [from.join(), to.join()]);
  return <mesh position={pos} quaternion={quat} material={material}><capsuleGeometry args={[r, len, 4, 10]} /></mesh>;
}

const HAND_Y = 0.82;

/** The chat agent: seated at the desk, facing its monitor. While a question runs its hands tap the keyboard and its bubble says what it waits on. */
function ChatAgent({ typing, status, palette, labels }: { typing: boolean; status: string | null; palette: Palette; labels: boolean }) {
  const left = useRef<Mesh>(null);
  const right = useRef<Mesh>(null);
  const head = useRef<Mesh>(null);
  const body = useRef<Group>(null);
  const keyGlow = useRef<MeshStandardMaterial>(null);
  const color = CHAT_COLOR[palette.dark ? 'dark' : 'light'];
  const material = useMemo(() => new MeshStandardMaterial(), []);
  const chair = useMemo(() => new MeshStandardMaterial(), []);
  useEffect(() => { material.color.set(color); material.emissive.set(palette.accent); }, [material, color, palette.accent]);
  useEffect(() => { chair.color.set(palette.muted); }, [chair, palette.muted]);
  useEffect(() => () => { material.dispose(); chair.dispose(); }, [material, chair]);

  useFrame(({ clock }, dt) => {
    const t = clock.elapsedTime;
    const tap = (phase: number) => (typing && !reducedMotion ? Math.max(0, Math.sin(t * 15 + phase)) * 0.035 : 0);
    if (left.current) left.current.position.y = HAND_Y + tap(0);
    if (right.current) right.current.position.y = HAND_Y + tap(Math.PI * 0.85);
    if (head.current && !reducedMotion) head.current.rotation.x = typing ? 0.12 + Math.sin(t * 2.3) * 0.04 : Math.sin(t * 0.6) * 0.03;
    if (body.current && !reducedMotion) body.current.scale.y = 1 + Math.sin(t * 1.7) * 0.012;
    material.emissiveIntensity += ((typing ? 0.18 + 0.08 * Math.sin(t * 4) : 0) - material.emissiveIntensity) * ease(dt, 5);
    if (keyGlow.current) keyGlow.current.emissiveIntensity = typing ? 0.35 + 0.35 * Math.abs(Math.sin(t * 11)) : 0.05;
  });

  return (
    // Built facing +z, turned to face north.
    <group position={AGENT} rotation-y={Math.PI}>
      {/* The chair */}
      <mesh position-y={0.46} material={chair}><boxGeometry args={[0.52, 0.08, 0.5]} /></mesh>
      <mesh position={[0, 0.82, -0.24]} material={chair}><boxGeometry args={[0.52, 0.62, 0.06]} /></mesh>
      <mesh position-y={0.22} material={chair}><cylinderGeometry args={[0.04, 0.04, 0.42, 10]} /></mesh>
      <mesh position-y={0.02} material={chair}><cylinderGeometry args={[0.26, 0.26, 0.04, 20]} /></mesh>
      {/* The agent */}
      <group ref={body}>
        <mesh position-y={0.89} material={material}><capsuleGeometry args={[0.2, 0.38, 6, 16]} /></mesh>
        <mesh ref={head} position-y={1.44} material={material}><sphereGeometry args={[0.16, 24, 16]} /></mesh>
      </group>
      {[-1, 1].map((s) => (
        <group key={s}>
          <Limb from={[s * 0.1, 0.56, 0.02]} to={[s * 0.1, 0.56, 0.38]} r={0.08} material={material} />
          <Limb from={[s * 0.1, 0.56, 0.4]} to={[s * 0.1, 0.08, 0.44]} r={0.07} material={material} />
          <Limb from={[s * 0.24, 1.12, 0.02]} to={[s * 0.14, HAND_Y + 0.02, 0.64]} r={0.055} material={material} />
        </group>
      ))}
      <mesh ref={left} position={[-0.14, HAND_Y, 0.68]} material={material}><sphereGeometry args={[0.055, 12, 10]} /></mesh>
      <mesh ref={right} position={[0.14, HAND_Y, 0.68]} material={material}><sphereGeometry args={[0.055, 12, 10]} /></mesh>
      {/* The keyboard, on the desk in front of it */}
      <mesh position={[0, DESK.top + 0.012, 0.74]}>
        <boxGeometry args={[0.56, 0.025, 0.2]} />
        <meshStandardMaterial ref={keyGlow} color={palette.dark ? '#2a2f36' : '#3a3f46'} emissive={palette.accent} emissiveIntensity={0.05} />
      </mesh>
      <Html position={[0, 1.95, 0]} zIndexRange={[40, 20]}>
        {typing && status && <span className={`bubble fades ${labels ? '' : 'hidden'}`} title={status}>{status}</span>}
      </Html>
      <Html position={[0, 0.0, 0]} zIndexRange={[20, 0]}>
        {/* Faded, not removed, on the way in and out: they would pop otherwise. */}
        <div className={`label3d fades ${typing ? 'working' : 'idle'} ${labels ? '' : 'hidden'}`}>
          <span className="label strong">Chat agent</span>
          {typing && <span className="doing working">typing</span>}
        </div>
      </Html>
    </group>
  );
}

/** The chat agent's monitor. It shows the latest messages; using it opens the 2D chat. */
function Monitor({ messages, near, palette, onUse }: { messages: ChatMsg[]; near: boolean; palette: Palette; onUse: () => void }) {
  const recent = messages.slice(-4);
  const clip = (s: string) => (s.length > 220 ? `${s.slice(0, 220).trimEnd()}…` : s);
  return (
    // Its screen faces south, towards the chat agent; its back is to the huddle.
    <group position={MONITOR}>
      <mesh position-y={(DESK.top + SCREEN_Y - 0.55) / 2}>
        <cylinderGeometry args={[0.04, 0.05, SCREEN_Y - 0.55 - DESK.top, 12]} />
        <meshStandardMaterial color={palette.muted} />
      </mesh>
      <mesh position-y={DESK.top + 0.01}>
        <boxGeometry args={[0.5, 0.02, 0.3]} />
        <meshStandardMaterial color={palette.muted} />
      </mesh>
      <mesh position-y={SCREEN_Y} onClick={(e) => { e.stopPropagation(); onUse(); }}>
        <boxGeometry args={[SCREEN_W + 0.1, SCREEN_H + 0.1, 0.06]} />
        <meshStandardMaterial color="#14171b" emissive={palette.accent} emissiveIntensity={near ? 0.55 : 0} />
      </mesh>
      <Html transform position={[0, SCREEN_Y, 0.032]} distanceFactor={SCREEN_DF} zIndexRange={[10, 0]} pointerEvents="none">
        <div className="screen3d">
          <header><strong>Talk With Your Files</strong><span className="muted">chat</span></header>
          <div className="screen3d-msgs">
            {recent.length === 0 && <p className="muted">Ask a question about your files.</p>}
            {recent.map((m) => (
              <div key={m.id} className={`msg ${m.role}`}>
                {m.error ? <span className="error-text">{m.error}</span>
                  : m.pending ? <span className="status"><i className="dot" />{m.status}</span>
                  : clip(m.text)}
              </div>
            ))}
          </div>
        </div>
      </Html>
    </group>
  );
}

/** The huddle log, on the north wall behind the huddle: its latest entries. Reading it opens the whole log. */
function LogBoard({ log, nameOf, near, palette, onUse }: {
  log: FloorProps['huddle']['log']; nameOf: (id: string) => string; near: boolean; palette: Palette; onUse: () => void;
}) {
  const recent = log.slice(-9);
  return (
    <group position={BOARD}>
      <mesh onClick={(e) => { e.stopPropagation(); onUse(); }}>
        <boxGeometry args={[4.6, 2.8, 0.04]} />
        <meshStandardMaterial color={palette.line} emissive={palette.accent} emissiveIntensity={near ? 0.55 : 0} />
      </mesh>
      <Html transform position={[0, 0, 0.03]} distanceFactor={BOARD_DF} zIndexRange={[10, 0]} pointerEvents="none">
        <div className="board3d">
          <header><strong>Huddle log</strong><span className="muted">{log.length}</span></header>
          {recent.length === 0 && <p className="muted">The agents' discussion appears here.</p>}
          {recent.map((e, i) => (
            <p key={log.length - recent.length + i} className={e.who === 'system' ? 'muted' : ''}>
              {e.who !== 'system' && <b>{nameOf(e.who)} </b>}{e.text}
            </p>
          ))}
        </div>
      </Html>
    </group>
  );
}
